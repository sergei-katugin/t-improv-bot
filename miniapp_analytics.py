from __future__ import annotations
from miniapp_common import *
from miniapp_helpers import _manageable_api_show, _show_id


async def miniapp_show_analytics(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    registration_source = func.coalesce(Registration.source, "direct")
    manual_source = func.coalesce(ManualAttendee.source, "manual")
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        reg_summary = (await session.execute(select(
            func.coalesce(func.sum(case((Registration.is_cancelled == False, 1 + Registration.guests), else_=0)), 0),
            func.coalesce(func.sum(case((Registration.is_cancelled == True, 1), else_=0)), 0),
            func.coalesce(func.sum(case((
                (Registration.is_cancelled == False) & (Registration.confirmed == True),
                1 + Registration.guests,
            ), else_=0)), 0),
            func.coalesce(func.sum(case((Registration.is_cancelled == False, Registration.checked_in_count), else_=0)), 0),
            func.min(Registration.registered_at),
        ).where(Registration.show_id == show_id))).one()
        manual_summary = (await session.execute(select(
            func.coalesce(func.sum(ManualAttendee.guests + 1), 0),
            func.coalesce(func.sum(ManualAttendee.checked_in_count), 0),
            func.min(ManualAttendee.added_at),
        ).where(ManualAttendee.show_id == show_id))).one()
        rating_rows = (await session.execute(
            select(ShowFeedback.rating, func.count(ShowFeedback.id))
            .where(ShowFeedback.show_id == show_id)
            .group_by(ShowFeedback.rating).order_by(ShowFeedback.rating.desc())
        )).all()
        reg_source_rows = (await session.execute(
            select(registration_source, func.sum(1 + Registration.guests))
            .where(Registration.show_id == show_id, Registration.is_cancelled == False)
            .group_by(registration_source)
        )).all()
        manual_source_rows = (await session.execute(
            select(manual_source, func.sum(ManualAttendee.guests + 1))
            .where(ManualAttendee.show_id == show_id)
            .group_by(manual_source)
        )).all()
        comments = (await session.execute(
            select(ShowFeedback, User)
            .join(User, User.id == ShowFeedback.user_id)
            .where(ShowFeedback.show_id == show_id, ShowFeedback.comment.isnot(None), ShowFeedback.comment != "")
            .order_by(ShowFeedback.created_at.desc()).limit(100)
        )).all()

    sources: dict[str, int] = {}
    for source, count in [*reg_source_rows, *manual_source_rows]:
        key = str(source)
        sources[key] = sources.get(key, 0) + int(count or 0)
    registered = int(reg_summary[0]) + int(manual_summary[0])
    feedback_count = sum(int(count) for _, count in rating_rows)
    average_rating = (
        sum(int(rating) * int(count) for rating, count in rating_rows) / feedback_count
        if feedback_count else 0.0
    )
    arrived = int(show.checkin_counter or 0) + int(reg_summary[3]) + int(manual_summary[1])
    occupancy_rate = round(registered / show.max_seats * 100) if show.max_seats else 0
    cancellation_rate = round(int(reg_summary[1]) / max(1, int(reg_summary[1]) + registered) * 100)
    attendance_rate = round(arrived / registered * 100) if registered else 0
    starts = [item for item in (reg_summary[4], manual_summary[2]) if item]
    elapsed_days = max(1.0, (utc_now() - min(starts)).total_seconds() / 86_400) if starts else 1.0
    daily_rate = round(registered / elapsed_days, 1)
    remaining_days = max(0.0, (show.show_date - utc_now()).total_seconds() / 86_400)
    projected = min(show.max_seats, round(registered + daily_rate * remaining_days)) if not show.is_active is False else registered
    recommendation = "Мест достаточно — продолжай следить за динамикой"
    if show.show_date > utc_now() and occupancy_rate < 50 and remaining_days <= 7:
        recommendation = "Заполненность низкая: стоит сделать повторный анонс"
    elif show.show_date > utc_now() and projected < show.max_seats * .75:
        recommendation = "Текущего темпа недостаточно для заполнения 75% мест"
    return web.json_response({
        "registered": registered,
        "capacity": show.max_seats,
        "cancelledRegistrations": int(reg_summary[1]),
        "confirmed": int(reg_summary[2]),
        "arrived": arrived,
        "checkinEnabled": show.checkin_enabled,
        "feedbackEnabled": show.feedback_enabled,
        "feedbackCount": feedback_count,
        "averageRating": round(average_rating, 1),
        "occupancyRate": occupancy_rate,
        "cancellationRate": cancellation_rate,
        "attendanceRate": attendance_rate,
        "dailyRegistrationRate": daily_rate,
        "projectedAttendance": projected,
        "recommendation": recommendation,
        "ratingDistribution": {str(rating): int(count) for rating, count in rating_rows},
        "sources": [
            {"source": source, "count": count}
            for source, count in sorted(sources.items(), key=lambda item: (-item[1], item[0]))
        ],
        "comments": [{
            "id": feedback.id,
            "rating": feedback.rating,
            "comment": feedback.comment,
            "username": user.username,
            "name": " ".join(part for part in (user.first_name, user.last_name) if part) or feedback.user_id,
            "createdAt": feedback.created_at.isoformat(),
        } for feedback, user in comments],
        "commentsLimit": 100,
    })


def _csv_value(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


async def miniapp_export_show_csv(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Имя", "Telegram", "Доп. гости", "Статус записи", "Подтверждение",
        "Пришло фактически", "Источник", "Оценка", "Отзыв",
    ])
    source_labels = {
        "direct": "Прямая ссылка", "instagram": "Instagram", "channel": "Telegram-канал",
        "team": "Команда", "manual": "Добавлен вручную", "social": "Другие соцсети",
    }
    row_count = 0
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        registration_rows = await session.stream(
            select(Registration, User, ShowFeedback)
            .join(User, User.id == Registration.user_id)
            .outerjoin(ShowFeedback, (ShowFeedback.show_id == show_id) & (ShowFeedback.user_id == User.id))
            .where(Registration.show_id == show_id)
            .order_by(Registration.id).limit(10_000)
        )
        async for registration, user, feedback in registration_rows:
            writer.writerow([
                _csv_value(registration.attendee_name),
                _csv_value(f"@{user.username}" if user.username else user.telegram_id),
                registration.guests or 0,
                "Отменена" if registration.is_cancelled else "Активна",
                "Да" if registration.confirmed is True else "Нет" if registration.confirmed is False else "Не отвечал(а)",
                registration.checked_in_count or 0,
                _csv_value(source_labels.get(registration.source or "direct", registration.source or "Прямая ссылка")),
                feedback.rating if feedback else "",
                _csv_value(feedback.comment if feedback else ""),
            ])
            row_count += 1
        if row_count < 10_000:
            manual_rows = await session.stream(
                select(ManualAttendee).where(ManualAttendee.show_id == show_id)
                .order_by(ManualAttendee.id).limit(10_000 - row_count)
            )
            async for attendee in manual_rows.scalars():
                writer.writerow([
                    _csv_value(attendee.name), _csv_value(attendee.contact), attendee.guests or 0, "Добавлен вручную",
                    "Не требуется", attendee.checked_in_count or 0,
                    _csv_value(source_labels.get(attendee.source or "manual", attendee.source or "Добавлен вручную")),
                    "", "",
                ])
    data = ("\ufeff" + output.getvalue()).encode("utf-8")
    return web.Response(
        body=data, content_type="text/csv", charset="utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="show-{show_id}-attendees.csv"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        },
    )
