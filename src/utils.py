import re
from datetime import datetime

# --- Helpers ---

def parse_date(date_str):
    """Parse date string, handling invalid dates and 0001-01-01."""
    if not date_str or str(date_str).startswith('0001'):
        return None
    try:
        clean_str = str(date_str).split('T')[0]
        return datetime.strptime(clean_str, '%Y-%m-%d')
    except:
        return None

def parse_float(value):
    """Safely parse float values."""
    try:
        return float(value) if value else 0.0
    except:
        return 0.0

def location_contains(location: str, text: str) -> bool:
    """Case-insensitive check if location contains text."""
    return text.lower() in str(location).lower()

def sanitize_rows(rows):
    """Normalize row values so the analyzer & cache can digest them."""
    sanitized = []
    for row in rows:
        clean_row = {}
        for key, value in row.items():
            if isinstance(value, datetime):
                clean_row[key] = value.strftime('%Y-%m-%d')
            else:
                clean_row[key] = value
        sanitized.append(clean_row)
    return sanitized

# --- Date Inference ---

MONTH_LOOKUP = {
    name.lower(): idx
    for idx, name in enumerate(
        ["January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"], 1
    )
}
# Add 3-letter abbreviations
MONTH_LOOKUP.update({
    name[:3].lower(): idx for name, idx in
    zip(
        ["January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"],
        range(1, 13)
    )
})

def infer_month_year_from_location(location: str):
    """
    Extracts month/year from strings like '💸 Other Income / November 2025'.
    Returns (month_int, year_int) or (None, None).
    """
    if not location:
        return None, None

    loc = str(location).lower()

    # 1. Try finding explicit YYYY-MM patterns
    match = re.search(r"(20\d{2})[\-/](\d{1,2})", loc)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if 1 <= month <= 12:
            return month, year

    # 2. Try finding Month Name + Optional Year
    for key, month_idx in MONTH_LOOKUP.items():
        # We look for the month name as a distinct word or segment
        if key in loc:
            # Try to find a year near it
            year_match = re.search(r"(20\d{2})", loc)
            year = int(year_match.group(1)) if year_match else None
            return month_idx, year

    return None, None
