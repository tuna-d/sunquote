"""The system clock, as a domain `Clock`."""

from datetime import UTC, date, datetime, timedelta, timezone

# Turkey has been on UTC+3 all year since 2016. A fixed offset avoids a tz database.
_TURKEY = timezone(timedelta(hours=3), name="TRT")


class SystemClock:
    """Supplies the quote date: today's date in Turkey."""

    def today(self) -> date:
        return datetime.now(UTC).astimezone(_TURKEY).date()
