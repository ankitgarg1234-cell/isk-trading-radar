"""Strict, deterministic encodings shared by offline controls."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re


class ControlError(ValueError):
    """Evidence is incomplete, inconsistent, or unsafe."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def utc(value):
    if not isinstance(value, str):
        raise ControlError("Timestamp must be an ISO-8601 string with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlError("Invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ControlError("Naive timestamps are forbidden")
    return parsed.astimezone(timezone.utc)


def sha256(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ControlError("Expected lowercase SHA-256")
    return value


def money(value):
    # Do not silently inherit binary float approximations in cash accounting.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ControlError("Money must be a decimal string, integer, or Decimal")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ControlError("Invalid monetary value") from exc
    if not result.is_finite() or result < 0:
        raise ControlError("Money must be finite and nonnegative")
    return result


def positive_integer(value, allow_zero=False):
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ControlError("Expected whole nonnegative shares" if allow_zero else "Expected positive integer")
    return value
