from __future__ import annotations

import calendar
from datetime import date
from typing import Union

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters.callback_data import CallbackData
from aiogram3_calendar import SimpleCalendar
from aiogram3_calendar.calendar_types import SimpleCalendarCallback, SimpleCalendarAction
from time_utils import local_now

_MONTHS = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


class RuCalendar(SimpleCalendar):
    """Russian-locale calendar. Pass busy_dates to highlight days with existing shows."""

    def __init__(self, busy_dates: dict[date, list[str]] | None = None):
        # busy_dates: {date: [show_title, ...]}
        self._busy: dict[date, list[str]] = busy_dates or {}

    async def start_calendar(
        self,
        year: int | None = None,
        month: int | None = None,
    ) -> InlineKeyboardMarkup:
        now = local_now()
        year = year or now.year
        month = month or now.month
        busy_days = {d.day for d in self._busy if d.year == year and d.month == month}

        markup = []
        ignore_cb = SimpleCalendarCallback(
            act=SimpleCalendarAction.IGNORE, year=year, month=month, day=0
        )

        markup.append([
            InlineKeyboardButton(
                text="<<",
                callback_data=SimpleCalendarCallback(
                    act=SimpleCalendarAction.PREV_YEAR, year=year, month=month, day=1
                ).pack(),
            ),
            InlineKeyboardButton(
                text=f"{_MONTHS[month]} {year}",
                callback_data=ignore_cb.pack(),
            ),
            InlineKeyboardButton(
                text=">>",
                callback_data=SimpleCalendarCallback(
                    act=SimpleCalendarAction.NEXT_YEAR, year=year, month=month, day=1
                ).pack(),
            ),
        ])

        markup.append([
            InlineKeyboardButton(text=d, callback_data=ignore_cb.pack())
            for d in _WEEKDAYS
        ])

        day = None
        for week in calendar.monthcalendar(year, month):
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(text=" ", callback_data=ignore_cb.pack()))
                else:
                    label = f"🔴{day}" if day in busy_days else str(day)
                    row.append(InlineKeyboardButton(
                        text=label,
                        callback_data=SimpleCalendarCallback(
                            act=SimpleCalendarAction.DAY, year=year, month=month, day=day
                        ).pack(),
                    ))
            markup.append(row)

        markup.append([
            InlineKeyboardButton(
                text="<",
                callback_data=SimpleCalendarCallback(
                    act=SimpleCalendarAction.PREV_MONTH, year=year, month=month, day=day
                ).pack(),
            ),
            InlineKeyboardButton(text=" ", callback_data=ignore_cb.pack()),
            InlineKeyboardButton(
                text=">",
                callback_data=SimpleCalendarCallback(
                    act=SimpleCalendarAction.NEXT_MONTH, year=year, month=month, day=day
                ).pack(),
            ),
        ])

        return InlineKeyboardMarkup(inline_keyboard=markup, row_width=7)

    async def process_selection(
        self,
        query: CallbackQuery,
        data: Union[CallbackData, SimpleCalendarCallback],
    ) -> tuple:
        if data.act == SimpleCalendarAction.DAY:
            picked = date(int(data.year), int(data.month), int(data.day))
            titles = self._busy.get(picked)
            if titles:
                names = ", ".join(titles)
                await query.answer(
                    f"📅 {picked.strftime('%d.%m.%Y')} занято: {names}",
                    show_alert=True,
                )
                return False, None
        return await super().process_selection(query, data)
