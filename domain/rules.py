from datetime import datetime, timezone, timedelta

def can_cancel_booking(start_time: str) -> bool:
    start = datetime.fromisoformat(start_time)
    return (start - datetime.now(timezone.utc)) >= timedelta(minutes=30)
