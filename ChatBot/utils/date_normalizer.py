"""
Date Normalization Engine
==========================
Normalizes all date formats to ISO 8601 (YYYY-MM-DD).

Handles:
  - "Jan 5, 2025" / "January 5, 2025"
  - "01/05/2025" / "1/5/2025"
  - "2025-01-05"
  - "05-Jan-2025"
  - "5th January 2025"
  - "05.01.2025"
  - "20250105"
  - Relative: "today", "yesterday"
"""

import re
from datetime import datetime, timedelta
from typing import Optional


# Month name → number
_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Ordered patterns (most specific first)
_DATE_PATTERNS = [
    # ISO: 2025-01-05
    re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"),
    # US: 01/05/2025 or 1/5/2025
    re.compile(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$"),
    # EU dot: 05.01.2025
    re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"),
    # Compact: 20250105
    re.compile(r"^(\d{4})(\d{2})(\d{2})$"),
    # Month name: Jan 5, 2025 / January 5th, 2025
    re.compile(
        r"^(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})$",
        re.IGNORECASE,
    ),
    # Day-Month-Year: 05-Jan-2025 / 5 January 2025
    re.compile(
        r"^(\d{1,2})[\s\-](\w+)[\s\-,]*(\d{4})$",
        re.IGNORECASE,
    ),
]


def normalize_date(raw: str) -> Optional[str]:
    """
    Normalize a date string to ISO 8601 format (YYYY-MM-DD).

    Returns:
        ISO date string or None if parsing fails.
    """
    if not raw:
        return None

    text = raw.strip().strip(".,;:")

    # Relative dates
    lower = text.lower()
    if lower == "today":
        return datetime.utcnow().strftime("%Y-%m-%d")
    if lower == "yesterday":
        return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Try each pattern
    for i, pattern in enumerate(_DATE_PATTERNS):
        m = pattern.match(text)
        if not m:
            continue

        try:
            if i == 0:
                # ISO
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif i in (1, 2):
                # US or EU dot — assume MM/DD/YYYY
                mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif i == 3:
                # Compact YYYYMMDD
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif i == 4:
                # Month name first
                month_str = m.group(1).lower()
                mo = _MONTH_MAP.get(month_str)
                if mo is None:
                    continue
                d = int(m.group(2))
                y = int(m.group(3))
            elif i == 5:
                # Day-Month-Year
                d = int(m.group(1))
                month_str = m.group(2).lower()
                mo = _MONTH_MAP.get(month_str)
                if mo is None:
                    continue
                y = int(m.group(3))
            else:
                continue

            # Validate
            dt = datetime(y, mo, d)
            return dt.strftime("%Y-%m-%d")

        except (ValueError, TypeError):
            continue

    # Last resort: dateutil
    try:
        from dateutil.parser import parse as dateutil_parse
        dt = dateutil_parse(text, dayfirst=False)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    return None


def extract_dates_from_text(text: str) -> list:
    """
    Extract and normalize all dates found in a block of text.
    Returns list of {"raw": ..., "normalized": ...} dicts.
    """
    date_pattern = re.compile(
        r"\b("
        r"\d{4}-\d{1,2}-\d{1,2}"
        r"|\d{1,2}/\d{1,2}/\d{4}"
        r"|\d{1,2}\.\d{1,2}\.\d{4}"
        r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\w*\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}"
        r"|\d{1,2}[\s\-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\w*[\s\-,]*\d{4}"
        r")\b",
        re.IGNORECASE,
    )

    results = []
    for match in date_pattern.finditer(text):
        raw = match.group(0)
        normalized = normalize_date(raw)
        if normalized:
            results.append({"raw": raw, "normalized": normalized})

    return results

