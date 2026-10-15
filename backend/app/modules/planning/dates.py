from datetime import datetime, timedelta, timezone

INDIA = timezone(timedelta(hours=5, minutes=30))


def today_in_india():
    """Keep sowing validation and provider dates independent of server timezone."""
    return datetime.now(INDIA).date()
