from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from admin_bot.callbacks import AdminVenueActionCb, AdminVenueFieldCb
from admin_bot.keyboards.inline import venues_list_kb, venue_detail_kb, confirm_kb, fsm_cancel_kb

router = Router()


class AddVenueFSM(StatesGroup):
    name = State()
    city = State()
    default_seats = State()
    maps_url = State()


class EditVenueFSM(StatesGroup):
    new_value = State()


def _venue_summary(venue) -> str:
    maps = venue.maps_url or "не указана"
    status = "активна" if venue.is_active else "скрыта"
    return (
        f"🎭 <b>{venue.name}</b>\n"
        f"🏙 Город: {venue.city}\n"
        f"🪑 Мест по умолчанию: {venue.default_seats}\n"
        f"🗺 Ссылка: {maps}\n"
        f"Статус: {status}"
    )


# ── Entry points ─────────────────────────────────────────────────────────────

@router.message(F.text == "🏛 Площадки")
@router.message(Command("venues"))
@router.callback_query(F.data == "admin_venues_list")
async def venues_list(event, state: FSMContext, session: AsyncSession):
    await state.clear()
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    venues = await crud.list_venues(session, active_only=False)
    text = "🏛 <b>Площадки</b>\n\nВыбери площадку для редактирования или добавь новую:"
    if isinstance(event, Message):
        await msg.answer(text, reply_markup=venues_list_kb(venues))
    else:
        await msg.edit_text(text, reply_markup=venues_list_kb(venues))


@router.callback_query(F.data == "admin_back_main")
async def back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.delete()


# ── Venue detail ─────────────────────────────────────────────────────────────

@router.callback_query(AdminVenueActionCb.filter(F.action == "open"))
async def venue_detail(callback: CallbackQuery, callback_data: AdminVenueActionCb, state: FSMContext, session: AsyncSession):
    await state.clear()
    await callback.answer()
    venue = await crud.get_venue(session, callback_data.venue_id)
    if venue is None:
        await callback.message.answer("Площадка не найдена.")
        return
    await callback.message.edit_text(_venue_summary(venue), reply_markup=venue_detail_kb(venue))


# ── Edit field ────────────────────────────────────────────────────────────────

@router.callback_query(AdminVenueFieldCb.filter())
async def venue_field_action(
    callback: CallbackQuery, callback_data: AdminVenueFieldCb, state: FSMContext, session: AsyncSession
):
    await callback.answer()
    venue_id = callback_data.venue_id
    field = callback_data.field

    if field == "toggle":
        venue = await crud.get_venue(session, venue_id)
        if venue:
            await crud.update_venue(session, venue_id, is_active=not venue.is_active)
            venue = await crud.get_venue(session, venue_id)
        await callback.message.edit_text(_venue_summary(venue), reply_markup=venue_detail_kb(venue))
        return

    if field == "delete":
        await callback.message.edit_text(
            "Удалить площадку? Это действие необратимо.",
            reply_markup=confirm_kb(
                AdminVenueActionCb(action="confirm_delete", venue_id=venue_id).pack(),
                AdminVenueActionCb(action="open", venue_id=venue_id).pack(),
            ),
        )
        return

    prompts = {
        "name":          "Введи новое название площадки:",
        "city":          "Введи новый город:",
        "default_seats": "Введи новое количество мест (только цифры):",
        "maps_url":      "Введи новую ссылку на Google Maps (или «-» чтобы убрать):",
    }
    await state.set_state(EditVenueFSM.new_value)
    await state.update_data(venue_id=venue_id, field=field)
    await callback.message.edit_text(prompts[field], reply_markup=fsm_cancel_kb())


@router.message(EditVenueFSM.new_value, F.text)
async def venue_save_field(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    venue_id: int = data["venue_id"]
    field: str = data["field"]
    raw = message.text.strip()

    if field == "default_seats":
        try:
            value = int(raw)
            if value <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Введи корректное число:", reply_markup=fsm_cancel_kb())
            return
    elif field == "maps_url":
        value = None if raw == "-" else raw
    else:
        value = raw  # name, city

    venue = await crud.update_venue(session, venue_id, **{field: value})
    await state.clear()
    await message.answer(_venue_summary(venue), reply_markup=venue_detail_kb(venue))


# ── Confirm delete ────────────────────────────────────────────────────────────

@router.callback_query(AdminVenueActionCb.filter(F.action == "confirm_delete"))
async def venue_confirm_delete(callback: CallbackQuery, callback_data: AdminVenueActionCb, session: AsyncSession):
    await callback.answer()
    await crud.delete_venue(session, callback_data.venue_id)
    venues = await crud.list_venues(session, active_only=False)
    await callback.message.edit_text(
        "🗑 Площадка удалена.\n\n🏛 <b>Площадки</b>:",
        reply_markup=venues_list_kb(venues),
    )


# ── Add venue ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_venue_add")
async def venue_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddVenueFSM.name)
    await callback.message.edit_text("Введи название новой площадки:", reply_markup=fsm_cancel_kb())


@router.message(AddVenueFSM.name, F.text)
async def venue_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddVenueFSM.city)
    await message.answer("Введи город (например: Лимасол):", reply_markup=fsm_cancel_kb())


@router.message(AddVenueFSM.city, F.text)
async def venue_add_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(AddVenueFSM.default_seats)
    await message.answer("Введи количество мест (только цифры):", reply_markup=fsm_cancel_kb())


@router.message(AddVenueFSM.default_seats, F.text)
async def venue_add_seats(message: Message, state: FSMContext):
    try:
        seats = int(message.text.strip())
        if seats <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректное число:", reply_markup=fsm_cancel_kb())
        return
    await state.update_data(default_seats=seats)
    await state.set_state(AddVenueFSM.maps_url)
    await message.answer(
        "Введи ссылку на Google Maps (или «-» чтобы пропустить):",
        reply_markup=fsm_cancel_kb(),
    )


@router.message(AddVenueFSM.maps_url, F.text)
async def venue_add_maps_url(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    maps_url = None if message.text.strip() == "-" else message.text.strip()
    venue = await crud.create_venue(session, data["name"], data["city"], maps_url, data["default_seats"])
    venues = await crud.list_venues(session, active_only=False)
    await state.clear()
    await message.answer(
        f"✅ Площадка <b>{venue.name}</b> добавлена!\n\n🏛 <b>Площадки</b>:",
        reply_markup=venues_list_kb(venues),
    )


# ── FSM back handlers ─────────────────────────────────────────────────────────

@router.callback_query(EditVenueFSM.new_value, F.data == "fsm_back")
async def venue_edit_back(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    data = await state.get_data()
    await state.clear()
    venue = await crud.get_venue(session, data["venue_id"])
    if venue:
        await callback.message.edit_text(_venue_summary(venue), reply_markup=venue_detail_kb(venue))
    else:
        await callback.message.edit_text("Площадка не найдена.")


@router.callback_query(AddVenueFSM.city, F.data == "fsm_back")
async def venue_add_back_to_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddVenueFSM.name)
    await callback.message.edit_text("Введи название новой площадки:", reply_markup=fsm_cancel_kb())


@router.callback_query(AddVenueFSM.default_seats, F.data == "fsm_back")
async def venue_add_back_to_city(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddVenueFSM.city)
    await callback.message.edit_text("Введи город (например: Лимасол):", reply_markup=fsm_cancel_kb())


@router.callback_query(AddVenueFSM.maps_url, F.data == "fsm_back")
async def venue_add_back_to_seats(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddVenueFSM.default_seats)
    await callback.message.edit_text("Введи количество мест (только цифры):", reply_markup=fsm_cancel_kb())
