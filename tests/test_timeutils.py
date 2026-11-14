from datetime import UTC, datetime, timedelta, timezone

from tickets.time import from_unix


def test_from_unix_accepts_number_and_datetime():
    expected = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
    assert from_unix(expected.timestamp()) == expected
    assert from_unix(int(expected.timestamp())) == expected
    # vkbottle-types отдаёт date уже как datetime (в т. ч. с другим поясом)
    moscow = timezone(timedelta(hours=3))
    assert from_unix(expected.astimezone(moscow)) == expected
    assert from_unix(expected.astimezone(moscow)).tzinfo == UTC
