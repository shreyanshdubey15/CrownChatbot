"""
Utility Routes
===============
/normalize-date, /extract-dates, /standardize-address
"""

from typing import Dict
from fastapi import APIRouter

from api.models import DateNormalizeRequest, AddressStandardizeRequest
from utils.date_normalizer import normalize_date, extract_dates_from_text
from utils.address_standardizer import standardize_address

router = APIRouter(tags=["Utils"])


@router.post("/normalize-date", summary="Normalize a date string to ISO 8601")
def api_normalize_date(body: DateNormalizeRequest):
    """Convert any date format to YYYY-MM-DD."""
    result = normalize_date(body.date_string)
    return {
        "original": body.date_string,
        "normalized": result,
        "success": result is not None,
    }


@router.post("/extract-dates", summary="Extract and normalize all dates from text")
def api_extract_dates(body: Dict[str, str]):
    """Find all dates in a text block and normalize them."""
    text = body.get("text", "")
    dates = extract_dates_from_text(text)
    return {"dates": dates, "count": len(dates)}


@router.post("/standardize-address", summary="Standardize a US address")
def api_standardize_address(body: AddressStandardizeRequest):
    """Parse and normalize a US address into standard postal format."""
    result = standardize_address(body.address)
    return result


