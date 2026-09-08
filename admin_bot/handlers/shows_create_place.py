from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()
from admin_bot.handlers.shows_create_confirm import _ask_registrar

@router.callback_query(CreateShowFSM.select_venue, VenueCb.filter())
async def process_venue_select(callback: CallbackQuery, callback_data: VenueCb, state: FSMContext, session: AsyncSession):
    await callback.answer()
    if callback_data.venue_id == 0:
        await state.update_data(_total=_TOTAL_STEPS_CUSTOM)
        await state.set_state(CreateShowFSM.location)
        await callback.message.edit_text(f"{_progress(4, _TOTAL_STEPS_CUSTOM)}Введи название площадки/театра:", reply_markup=fsm_cancel_kb())
    else:
        venue = await crud.get_venue(session, callback_data.venue_id)
        if venue is None:
            await callback.message.answer("Площадка не найдена. Попробуй ещё раз.")
            return
        await state.update_data(
            location=venue.name, location_url=venue.maps_url,
            city=venue.city, max_seats=venue.default_seats,
            _total=_TOTAL_STEPS_PRESET,
        )
        await state.set_state(CreateShowFSM.poster_text)
        await callback.message.edit_text(
            f"✅ Площадка: {h(venue.name)} ({h(venue.city)}) · {venue.default_seats} мест"
        )
        await callback.message.answer(
            f"{_progress(5, _TOTAL_STEPS_PRESET)}Введи текст афиши:\n⚠️ Не указывай дату, время и адрес — они уже есть в отдельных полях.",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"),
        )


@router.message(CreateShowFSM.location, F.text)
async def process_location(message: Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    await state.set_state(CreateShowFSM.location_url)
    await message.answer(
        f"{_progress(5, _TOTAL_STEPS_CUSTOM)}Введи ссылку на Google Maps для этой площадки:",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_location_url"),
    )


@router.callback_query(CreateShowFSM.location_url, F.data == "fsm_skip_location_url")
async def skip_location_url(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(location_url=None)
    await state.set_state(CreateShowFSM.select_city)
    await callback.message.edit_text("⏭ Ссылка на карты пропущена.")
    await callback.message.answer(f"{_progress(6, _TOTAL_STEPS_CUSTOM)}Выбери город:", reply_markup=city_kb())


@router.message(CreateShowFSM.location_url, F.text)
async def process_location_url(message: Message, state: FSMContext):
    url = message.text.strip()
    if not _is_google_maps_url(url):
        await message.answer(
            "Это не ссылка на Google Maps. Примеры допустимых ссылок:\n"
            "• https://maps.google.com/...\n"
            "• https://goo.gl/maps/...\n"
            "• https://maps.app.goo.gl/...\n\n"
            "Попробуй ещё раз или нажми ⏭ Пропустить:",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_location_url"),
        )
        return
    await state.update_data(location_url=url)
    await state.set_state(CreateShowFSM.select_city)
    await message.answer(f"{_progress(6, _TOTAL_STEPS_CUSTOM)}Выбери город:", reply_markup=city_kb())


@router.callback_query(CreateShowFSM.select_city, CityCb.filter())
async def process_city_select(callback: CallbackQuery, callback_data: CityCb, state: FSMContext):
    await callback.answer()
    if callback_data.value == "custom":
        await state.set_state(CreateShowFSM.city)
        await callback.message.edit_text(f"{_progress(6, _TOTAL_STEPS_CUSTOM)}Введи название города:", reply_markup=fsm_cancel_kb())
    else:
        await state.update_data(city=callback_data.value)
        await state.set_state(CreateShowFSM.max_seats)
        await callback.message.edit_text(f"✅ Город: {callback_data.value}")
        await callback.message.answer(f"{_progress(7, _TOTAL_STEPS_CUSTOM)}Введи количество мест (только цифры):", reply_markup=fsm_cancel_kb())


@router.message(CreateShowFSM.city, F.text)
async def process_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(CreateShowFSM.max_seats)
    await message.answer(f"{_progress(7, _TOTAL_STEPS_CUSTOM)}Введи количество мест (только цифры):", reply_markup=fsm_cancel_kb())


@router.message(CreateShowFSM.max_seats, F.text)
async def process_max_seats(message: Message, state: FSMContext):
    try:
        seats = int(message.text.strip())
        if seats <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректное число мест:", reply_markup=fsm_cancel_kb())
        return
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_CUSTOM)
    await state.update_data(max_seats=seats)
    await state.set_state(CreateShowFSM.poster_text)
    logger.info("create_show moved to poster_text state total=%s", total)
    await message.answer(
        f"{_progress(total - 2, total)}Введи текст афиши:\n⚠️ Не указывай дату, время и адрес — они уже есть в отдельных полях.",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"),
    )


@router.callback_query(CreateShowFSM.poster_text, F.data == "fsm_skip_poster_text")
async def skip_poster_text(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_PRESET)
    await state.update_data(poster_text=None)
    await state.set_state(CreateShowFSM.poster_image)
    await callback.message.edit_text("⏭ Текст афиши пропущен.")
    await callback.message.answer(
        f"{_progress(total - 1, total)}Отправь изображение афиши:",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
    )


@router.message(CreateShowFSM.poster_text, F.text)
async def process_poster_text(message: Message, state: FSMContext):
    text = message.text.strip()
    logger.info("create_show poster_text received length=%s", len(text))
    error = _validate_poster_text(text)
    if error:
        await message.answer(error, reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"))
        return
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_PRESET)
    await state.update_data(poster_text=text)
    await state.set_state(CreateShowFSM.poster_image)
    await message.answer(
        f"{_progress(total - 1, total)}Отправь изображение афиши:",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
    )


@router.message(CreateShowFSM.poster_text)
async def process_poster_text_fallback(message: Message, state: FSMContext):
    if message.text is not None:
        return
    await message.answer(
        "Отправь текст афиши или нажми ⏭ Пропустить.",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"),
    )


@router.callback_query(CreateShowFSM.poster_image, F.data == "fsm_skip_poster_image")
async def skip_poster_image(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(poster_file_id=None)
    await callback.message.edit_text("⏭ Изображение пропущено.")
    # proceed to optional registrar selection
    await _ask_registrar(callback.message, state, callback._current_bot)


@router.message(CreateShowFSM.poster_image, F.photo)
async def process_poster_image(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(poster_file_id=file_id)
    # proceed to optional registrar selection
    await _ask_registrar(message, state, message.bot)


@router.message(CreateShowFSM.poster_image)
async def process_poster_image_invalid(message: Message, state: FSMContext):
    await message.answer(
        "Отправь фото или нажми ⏭ Пропустить",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
    )
