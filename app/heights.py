"""Height parsing for AuditionConcierge.

Canonical unit: inches. Centimeters are only a display conversion:
cm = inches * 2.54. Never store both as editable fields.
"""

import re

_INCH_TO_CM = 2.54

# Feet/inches forms: 5'4", 5'4, 5 ft 4 in, 5 feet 4 inches
_FEET_INCHES_RE = re.compile(
    r"(?P<feet>\d+)\s*(?:'|ft|feet)\s*(?P<inches>\d+(?:\.\d+)?)?\s*(?:\"|in|inches)?"
)
_CM_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:cm|centimeters?)\b", re.IGNORECASE)
_INCHES_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:in|inches|\"|”)\b", re.IGNORECASE)
# Bare range with a shared trailing unit: "60-66 inches", "152-168 cm"
_SHARED_RANGE_RE = re.compile(
    r"(?P<lo>\d+(?:\.\d+)?)\s*[-–—]\s*(?P<hi>\d+(?:\.\d+)?)\s*(?P<unit>cm|centimeters?|in|inches|\")",
    re.IGNORECASE,
)


def to_cm(inches: float) -> float:
    return round(inches * _INCH_TO_CM, 1)


def from_cm(cm: float) -> float:
    return round(cm / _INCH_TO_CM, 1)


def _parse_single_token(text: str):
    """Parse one height token. Returns inches or None."""
    text = text.strip()
    m = _FEET_INCHES_RE.match(text)
    if m and ("'" in text or "ft" in text.lower() or "feet" in text.lower()):
        feet = int(m.group("feet"))
        inches = float(m.group("inches")) if m.group("inches") else 0.0
        return float(feet * 12 + inches)
    m = _CM_RE.match(text)
    if m:
        return from_cm(float(m.group("value")))
    m = _INCHES_RE.match(text)
    if m:
        return float(m.group("value"))
    return None


def _find_height_tokens(text: str):
    """Find height tokens in order, each as (start, end, inches)."""
    tokens = []
    # Feet/inches tokens first so "5'4\"" is not read as plain "5".
    for m in re.finditer(r"\d+\s*(?:'|ft|feet)\s*\d+(?:\.\d+)?\s*(?:\"|in|inches)?", text):
        feet_m = re.match(
            r"(\d+)\s*(?:'|ft|feet)\s*(\d+(?:\.\d+)?)", m.group(0)
        )
        if feet_m:
            tokens.append(
                (m.start(), m.end(), float(feet_m.group(1)) * 12 + float(feet_m.group(2)))
            )
    for m in _CM_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, _ in tokens):
            tokens.append((m.start(), m.end(), from_cm(float(m.group("value")))))
    for m in _INCHES_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, _ in tokens):
            # Avoid matching the inches part of a feet/inches token twice.
            if re.search(r"\d+\s*(?:'|ft|feet)\s*$", text[: m.start()]):
                continue
            tokens.append((m.start(), m.end(), float(m.group("value"))))
    tokens.sort()
    return tokens


def parse_height_range(text: str):
    """Parse a height range from free text.

    Returns (min_inches, max_inches) with min <= max, or (None, None).
    A single height is returned as (value, value). Mixed units are
    handled, e.g. "5'4\\" to 162 cm" -> (63.8, 64.0).
    """
    if not text:
        return (None, None)
    text = text.replace("’", "'").replace("‘", "'").replace("″", '"').replace("“", '"')
    # Shared-unit bare range first: "60-66 inches", "152-168 cm".
    m = _SHARED_RANGE_RE.search(text)
    if m:
        unit = m.group("unit").lower()
        lo, hi = float(m.group("lo")), float(m.group("hi"))
        if unit.startswith("cm") or unit.startswith("centimet"):
            lo, hi = from_cm(lo), from_cm(hi)
        return (min(lo, hi), max(lo, hi))
    tokens = _find_height_tokens(text)
    if not tokens:
        return (None, None)
    if len(tokens) == 1:
        value = tokens[0][2]
        return (value, value)
    lo, hi = tokens[0][2], tokens[1][2]
    return (min(lo, hi), max(lo, hi))


def parse_single_height(text: str):
    """Parse one height value in inches, or None."""
    if not text:
        return None
    text = text.replace("’", "'").replace("‘", "'").replace("″", '"')
    tokens = _find_height_tokens(text)
    return tokens[0][2] if tokens else None
