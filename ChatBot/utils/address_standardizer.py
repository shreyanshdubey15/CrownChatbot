"""
Address Standardization Engine
================================
Normalizes extracted addresses into standardized US postal format.

Pipeline:
  1. Parse raw address into components
  2. Normalize abbreviations (St → Street, Ave → Avenue, etc.)
  3. Standardize state names/abbreviations
  4. Validate ZIP code format
  5. Reassemble into canonical format

No external API required — rule-based standardization.
"""

import re
from typing import Optional, Dict


# ── Street Type Abbreviations ─────────────────────────────────
STREET_TYPES = {
    "st": "Street", "str": "Street", "street": "Street",
    "ave": "Avenue", "aven": "Avenue", "avenue": "Avenue",
    "blvd": "Boulevard", "boulevard": "Boulevard",
    "dr": "Drive", "drv": "Drive", "drive": "Drive",
    "ln": "Lane", "lane": "Lane",
    "rd": "Road", "road": "Road",
    "ct": "Court", "court": "Court",
    "cir": "Circle", "circle": "Circle",
    "pl": "Place", "place": "Place",
    "pkwy": "Parkway", "parkway": "Parkway",
    "hwy": "Highway", "highway": "Highway",
    "trl": "Trail", "trail": "Trail",
    "ter": "Terrace", "terrace": "Terrace",
    "way": "Way",
    "sq": "Square", "square": "Square",
    "ste": "Suite", "suite": "Suite",
    "fl": "Floor", "floor": "Floor",
    "apt": "Apt", "apartment": "Apt",
    "bldg": "Building", "building": "Building",
    "rm": "Room", "room": "Room",
}

# ── Directional Abbreviations ─────────────────────────────────
DIRECTIONS = {
    "n": "N", "north": "N",
    "s": "S", "south": "S",
    "e": "E", "east": "E",
    "w": "W", "west": "W",
    "ne": "NE", "northeast": "NE",
    "nw": "NW", "northwest": "NW",
    "se": "SE", "southeast": "SE",
    "sw": "SW", "southwest": "SW",
}

# ── US State Abbreviations ────────────────────────────────────
STATE_MAP = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}

# Reverse map: abbreviation → abbreviation (for validation)
VALID_STATE_ABBRS = set(STATE_MAP.values())


def standardize_address(raw_address: str) -> Dict[str, Optional[str]]:
    """
    Parse and standardize a US address.

    Returns:
        {
            "standardized": "123 Main Street, Suite 100, New York, NY 10001",
            "street": "123 Main Street",
            "unit": "Suite 100",
            "city": "New York",
            "state": "NY",
            "zip": "10001",
            "original": <raw input>
        }
    """
    if not raw_address or not raw_address.strip():
        return {"standardized": None, "original": raw_address}

    text = raw_address.strip()
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove trailing periods
    text = text.rstrip(".")

    result = {
        "original": raw_address,
        "street": None,
        "unit": None,
        "city": None,
        "state": None,
        "zip": None,
        "standardized": None,
    }

    # Try to extract ZIP code
    zip_match = re.search(r"\b(\d{5})(?:-(\d{4}))?\s*$", text)
    if zip_match:
        result["zip"] = zip_match.group(0).strip()
        text = text[:zip_match.start()].strip().rstrip(",").strip()

    # Try to extract state
    parts = [p.strip() for p in text.rsplit(",", 1)]
    if len(parts) == 2:
        possible_state = parts[1].strip()
        state_abbr = _normalize_state(possible_state)
        if state_abbr:
            result["state"] = state_abbr
            text = parts[0].strip()

    # Try to extract city
    parts = [p.strip() for p in text.rsplit(",", 1)]
    if len(parts) == 2:
        result["city"] = _title_case(parts[1].strip())
        text = parts[0].strip()
    elif not result["state"] and not result["zip"]:
        # Single line address — the whole thing is the street
        pass

    # Extract unit/suite
    unit_match = re.search(
        r",?\s*((?:Suite|Ste|Apt|Unit|Floor|Fl|Room|Rm|Bldg|Building|#)\s*[\w\-]+)\s*$",
        text,
        re.IGNORECASE,
    )
    if unit_match:
        raw_unit = unit_match.group(1).strip()
        result["unit"] = _normalize_unit(raw_unit)
        text = text[:unit_match.start()].strip().rstrip(",").strip()

    # Remaining text is the street
    result["street"] = _normalize_street(text)

    # Reassemble
    parts = []
    if result["street"]:
        parts.append(result["street"])
    if result["unit"]:
        parts.append(result["unit"])
    city_state_zip = []
    if result["city"]:
        city_state_zip.append(result["city"])
    if result["state"]:
        city_state_zip.append(result["state"])
    if result["zip"]:
        city_state_zip.append(result["zip"])

    full = ", ".join(parts)
    if city_state_zip:
        csz = " ".join(city_state_zip) if len(city_state_zip) <= 2 else ", ".join(city_state_zip[:2]) + " " + city_state_zip[2]
        # Format: Street, City, ST ZIP
        if result["city"] and result["state"] and result["zip"]:
            csz = f"{result['city']}, {result['state']} {result['zip']}"
        elif result["city"] and result["state"]:
            csz = f"{result['city']}, {result['state']}"
        elif result["state"] and result["zip"]:
            csz = f"{result['state']} {result['zip']}"
        full = full + ", " + csz if full else csz

    result["standardized"] = full if full else raw_address

    return result


def _normalize_state(text: str) -> Optional[str]:
    """Convert state name/abbreviation to standard 2-letter code."""
    t = text.strip().lower().rstrip(".")
    # Already an abbreviation?
    if t.upper() in VALID_STATE_ABBRS:
        return t.upper()
    # Full name?
    return STATE_MAP.get(t)


def _normalize_street(text: str) -> str:
    """Normalize street abbreviations and directions."""
    words = text.split()
    result = []
    for w in words:
        w_lower = w.lower().rstrip(".,")
        # Direction
        if w_lower in DIRECTIONS:
            result.append(DIRECTIONS[w_lower])
        # Street type
        elif w_lower in STREET_TYPES:
            result.append(STREET_TYPES[w_lower])
        else:
            result.append(w)
    return " ".join(result)


def _normalize_unit(text: str) -> str:
    """Normalize unit/suite identifiers."""
    for abbr, full in STREET_TYPES.items():
        pattern = re.compile(r"\b" + re.escape(abbr) + r"\b", re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(full, text)
            break
    return text.strip()


def _title_case(text: str) -> str:
    """Title case with handling for small words."""
    small_words = {"of", "the", "and", "in", "at", "on", "for", "to"}
    words = text.split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in small_words:
            result.append(w.capitalize())
        else:
            result.append(w.lower())
    return " ".join(result)

