"""The system clock, as a domain `Clock`."""

from datetime import UTC, date, datetime

from sunquote.domain.ports import ISTANBUL


class SystemClock:
    """Supplies the quote date (today's date in Turkey) and the current UTC time."""

    def today(self) -> date:
        return datetime.now(UTC).astimezone(ISTANBUL).date()

    def now(self) -> datetime:
        return datetime.now(UTC)
