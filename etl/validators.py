"""Reusable Bronze -> Silver cleaning and field-level validation helpers.

Design rule:
- Validators never reject an entire record.
- They return a cleaned value or None for invalid/non-critical fields.
- The ETL decides which fields are critical enough to reject the row.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd


VALID_ACCOUNT_TYPES = {
    "SAVINGS",
    "CURRENT",
    "SALARY",
    "FIXED_DEPOSIT",
}

VALID_GENDERS = {
    "MALE",
    "FEMALE",
    "OTHER",
}

VALID_BLOOD_GROUPS = {
    "A+",
    "A-",
    "B+",
    "B-",
    "AB+",
    "AB-",
    "O+",
    "O-",
}

VALID_CHANNELS = {
    "EMAIL",
    "SMS",
    "SOCIAL",
    "SEARCH",
    "REFERRAL",
}


def is_missing(value):
    if value is None:
        return True

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def clean_text(value):
    """Trim text and collapse repeated whitespace."""
    if is_missing(value):
        return None

    value = re.sub(r"\s+", " ", str(value).strip())
    return value or None


def clean_name(value):
    """
    Clean person/doctor names.

    Allows:
    - Alphabetic characters
    - Spaces
    - Apostrophes
    - Hyphens
    - Periods for titles such as Dr.
    """
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Allow letters, spaces, apostrophes, hyphens and periods.
    if not re.fullmatch(r"[A-Za-zÀ-ÿ.' -]+", value):
        return None

    return re.sub(r"\s+", " ", value)


def clean_email(value):
    value = clean_text(value)

    if value is None:
        return None

    value = value.lower()

    return value if is_valid_email(value) else None


def is_valid_email(value):
    if value is None or not isinstance(value, str):
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            value,
        )
    )


def clean_phone(value):
    """Return a normalized 10-digit Indian mobile number or None."""
    value = clean_text(value)

    if value is None:
        return None

    if not re.fullmatch(r"[+\d ()-]+", value):
        return None

    digits = re.sub(r"\D", "", value)

    # +91XXXXXXXXXX / 91XXXXXXXXXX
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]

    # 0XXXXXXXXXX
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def is_valid_phone(value):
    return isinstance(value, str) and bool(
        re.fullmatch(r"[6-9]\d{9}", value)
    )


def clean_date(value):
    """Parse project dates, primarily Indian DD/MM/YYYY dates."""
    if is_missing(value):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    value = clean_text(value)

    if value is None:
        return None

    formats = (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d.%m.%y",
        "%Y-%m-%d",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


def clean_int(value):
    """Convert an integer-like value to int."""
    value = clean_text(value)

    if value is None:
        return None

    try:
        number = Decimal(value)
    except InvalidOperation:
        return None

    if number != number.to_integral_value():
        return None

    return int(number)


def clean_amount(value):
    """
    Parse monetary values.

    Negative balances are intentionally allowed because an account
    can legitimately have an overdraft or negative balance.
    """
    value = clean_text(value)

    if value is None:
        return None

    value = value.replace("₹", "").replace(",", "").strip()

    try:
        return float(Decimal(value))
    except InvalidOperation:
        return None


def clean_percentage(value):
    value = clean_text(value)

    if value is None:
        return None

    value = value.rstrip("%").strip()

    try:
        number = float(Decimal(value))
    except InvalidOperation:
        return None

    return number if 0 <= number <= 100 else None


def clean_age(value):
    value = clean_int(value)

    if value is None:
        return None

    return value if 0 <= value <= 120 else None


def clean_upper(value):
    value = clean_text(value)

    return value.upper() if value is not None else None


def clean_account_type(value):
    value = clean_upper(value)

    return value if value in VALID_ACCOUNT_TYPES else None


def clean_gender(value):
    value = clean_upper(value)

    return value if value in VALID_GENDERS else None


def clean_blood_group(value):
    value = clean_upper(value)

    return value if value in VALID_BLOOD_GROUPS else None


def clean_channel(value):
    value = clean_upper(value)

    return value if value in VALID_CHANNELS else None


def clean_account_number(value):
    value = clean_text(value)

    if value is None:
        return None

    return (
        value
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,49}", value)
        else None
    )


def clean_medical_record_number(value):
    value = clean_text(value)

    if value is None:
        return None

    return (
        value
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,49}", value)
        else None
    )


def clean_location(value):
    """
    Clean an address and derive city/state when the address
    contains a known city.

    Returns:
        (cleaned_address, city, state)
    """

    if is_missing(value):
        return None, None, None

    address = clean_text(value)

    if address is None:
        return None, None, None

    city_state_map = {
        "mumbai": ("Mumbai", "Maharashtra"),
        "delhi": ("Delhi", "Delhi"),
        "new delhi": ("New Delhi", "Delhi"),
        "kolkata": ("Kolkata", "West Bengal"),
        "bangalore": ("Bangalore", "Karnataka"),
        "bengaluru": ("Bangalore", "Karnataka"),
        "chennai": ("Chennai", "Tamil Nadu"),
        "hyderabad": ("Hyderabad", "Telangana"),
        "pune": ("Pune", "Maharashtra"),
        "ahmedabad": ("Ahmedabad", "Gujarat"),
        "jaipur": ("Jaipur", "Rajasthan"),
        "lucknow": ("Lucknow", "Uttar Pradesh"),
        "patna": ("Patna", "Bihar"),
        "bhubaneswar": ("Bhubaneswar", "Odisha"),
        "ranchi": ("Ranchi", "Jharkhand"),
        "guwahati": ("Guwahati", "Assam"),
        "chandigarh": ("Chandigarh", "Chandigarh"),
        "kochi": ("Kochi", "Kerala"),
        "thiruvananthapuram": (
            "Thiruvananthapuram",
            "Kerala",
        ),
        "surat": ("Surat", "Gujarat"),
        "nagpur": ("Nagpur", "Maharashtra"),
        "indore": ("Indore", "Madhya Pradesh"),
        "bhopal": ("Bhopal", "Madhya Pradesh"),
        "coimbatore": ("Coimbatore", "Tamil Nadu"),
        "visakhapatnam": ("Visakhapatnam", "Andhra Pradesh"),
        "vijayawada": ("Vijayawada", "Andhra Pradesh"),
        "kanpur": ("Kanpur", "Uttar Pradesh"),
        "varanasi": ("Varanasi", "Uttar Pradesh"),
        "noida": ("Noida", "Uttar Pradesh"),
        "gurgaon": ("Gurgaon", "Haryana"),
        "gurugram": ("Gurgaon", "Haryana"),
    }

    address_lower = address.lower()

    for city_key, (city, state) in city_state_map.items():
        if city_key in address_lower:
            return address, city, state

    # Address itself is still valid even if we cannot
    # derive city/state.
    return address, None, None


def date_is_not_future(value, today=None):
    if value is None:
        return True

    today = today or date.today()

    return value <= today


def admission_date_is_consistent(
    admission_date,
    date_of_birth,
):
    if admission_date is None or date_of_birth is None:
        return True

    return admission_date >= date_of_birth