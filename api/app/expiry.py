"""A fact remains valid through its expiry date (UTC); blank means no expiry."""
from datetime import date, datetime, timezone


def parse_expiry(value: object) -> date | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError("expires must be a date in YYYY-MM-DD format")
    value = value.strip()
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("expires must be a valid date in YYYY-MM-DD format") from None
    if parsed.isoformat() != value:
        raise ValueError("expires must be a date in YYYY-MM-DD format")
    return parsed


def normalize_attributes(attributes: dict) -> dict:
    result = dict(attributes)
    expiry = parse_expiry(result.get("expires"))
    if expiry is None:
        result.pop("expires", None)
    else:
        result["expires"] = expiry.isoformat()
    return result


def is_expired(attributes: dict) -> bool:
    try:
        expiry = parse_expiry(attributes.get("expires"))
    except ValueError:
        return False  # Never delete legacy data on the strength of an invalid date.
    return expiry is not None and expiry < datetime.now(timezone.utc).date()


def is_active(entity) -> bool:
    if not entity.enabled:
        return False
    try:
        parse_expiry((entity.attributes or {}).get("expires"))
    except ValueError:
        return False  # Keep invalid legacy facts for staff to repair, out of answers.
    return not is_expired(entity.attributes or {})
