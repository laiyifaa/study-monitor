from datetime import datetime, timedelta, timezone

CN_TIMEZONE = timezone(timedelta(hours=8))


def parse_cn_datetime_input(value: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("时间不能为空")

    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(CN_TIMEZONE).replace(tzinfo=None)


def now_cn_naive() -> datetime:
    return datetime.now(CN_TIMEZONE).replace(tzinfo=None)
