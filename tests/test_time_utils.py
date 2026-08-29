from datetime import datetime

from time_utils import format_local, local_date, local_naive_to_utc, utc_to_local


def test_winter_local_time_is_normalized_to_utc():
    utc_value = local_naive_to_utc(datetime(2026, 1, 15, 19, 30))
    assert utc_value == datetime(2026, 1, 15, 17, 30)
    assert format_local(utc_value) == "15.01.2026 19:30"


def test_summer_local_time_is_normalized_to_utc():
    utc_value = local_naive_to_utc(datetime(2026, 7, 15, 19, 30))
    assert utc_value == datetime(2026, 7, 15, 16, 30)
    assert format_local(utc_value) == "15.07.2026 19:30"


def test_local_date_handles_utc_day_boundary():
    utc_value = datetime(2026, 7, 14, 22, 30)
    assert local_date(utc_value).isoformat() == "2026-07-15"
    assert utc_to_local(utc_value).hour == 1
