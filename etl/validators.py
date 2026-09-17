import re
import pandas as pd
from datetime import datetime


# ============================================================
# GENERAL TEXT CLEANING
# ============================================================

def clean_text(value):
    """
    Remove leading/trailing whitespace and
    normalize multiple spaces.
    """

    if pd.isna(value):
        return None

    value = str(value).strip()

    if value == "":
        return None

    value = re.sub(r"\s+", " ", value)

    return value


# ============================================================
# EMAIL
# ============================================================

def clean_email(email):
    """
    Trim whitespace and convert email to lowercase.
    """

    email = clean_text(email)

    if email is None:
        return None

    return email.lower()


def is_valid_email(email):
    """
    Validate a basic email format.
    """

    if email is None or pd.isna(email) or not isinstance(email, str):
        return False

    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"

    return bool(re.fullmatch(pattern, email))


# ============================================================
# INDIAN PHONE NUMBER
# ============================================================

def clean_phone(phone):
    """
    Normalize Indian mobile numbers.

    Accepted examples:

        9876543210
        09876543210
        +919876543210
        +91 9876543210
        98765 43210
        917000205965

    Output:

        9876543210
    """

    phone = clean_text(phone)

    if phone is None:
        return None

    # Remove spaces, hyphens and other separators
    phone = re.sub(r"[^\d+]", "", phone)

    # Remove +91 country code
    if phone.startswith("+91"):
        phone = phone[3:]

    # Remove leading 91 from a 12-digit Indian number (e.g. if parsed without +)
    elif phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]

    # Remove leading 0 from an 11-digit Indian number
    elif phone.startswith("0") and len(phone) == 11:
        phone = phone[1:]

    # Validate Indian mobile number
    if re.fullmatch(r"[6-9]\d{9}", phone):
        return phone

    return None


def is_valid_phone(phone):
    """
    Validate standardized Indian 10-digit mobile number.
    """

    if phone is None or pd.isna(phone) or not isinstance(phone, str):
        return False

    return bool(re.fullmatch(r"[6-9]\d{9}", phone))


# ============================================================
# INDIAN DATE
# ============================================================

def clean_date(value):
    """
    Convert common Indian date formats into a Python date.

    Supported examples:

        23/06/1985
        23-06-1985
        23.06.1985
        23.6.85
        1985-06-23

    DD/MM/YYYY and similar DD-first formats are used
    for the Indian datasets in this project.
    """

    if value is None or pd.isna(value):
        return None

    if isinstance(value, datetime):
        return value.date()

    from datetime import date
    if isinstance(value, date):
        return value

    value = clean_text(value)

    if value is None:
        return None

    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d.%m.%y",
        "%Y-%m-%d"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def is_valid_date(value):
    """
    Check whether a date was successfully parsed.
    """

    return value is not None


# ============================================================
# NUMERIC VALUES
# ============================================================

def clean_amount(value):
    """
    Clean monetary values.

    Examples:

        ₹45,000.50  -> 45000.50
        45,000.50   -> 45000.50
        45000.50    -> 45000.50
    """

    value = clean_text(value)

    if value is None:
        return None

    value = value.replace("₹", "")
    value = value.replace(",", "")
    value = value.strip()

    try:
        return float(value)
    except ValueError:
        return None


def clean_int(value):
    """
    Convert a value into an integer.
    """

    value = clean_text(value)

    if value is None:
        return None

    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def clean_percentage(value):
    """
    Convert percentage value into a float.

    Example:

        "87.50%" -> 87.50
    """

    value = clean_text(value)

    if value is None:
        return None

    value = value.replace("%", "").strip()

    try:
        return float(value)
    except ValueError:
        return None


# ============================================================
# CATEGORIES
# ============================================================

def clean_upper(value):
    """
    Trim and convert categorical values to uppercase.
    """

    value = clean_text(value)

    if value is None:
        return None

    return value.upper()


# ============================================================
# RANGE VALIDATION
# ============================================================

def valid_percentage(value):
    """
    Percentage must be between 0 and 100.
    """

    if value is None or pd.isna(value):
        return False

    try:
        return 0 <= float(value) <= 100
    except (ValueError, TypeError):
        return False


def valid_age(value):
    """
    Age must be between 0 and 120.
    """

    if value is None or pd.isna(value):
        return False

    try:
        return 0 <= int(value) <= 120
    except (ValueError, TypeError):
        return False


# ============================================================
# BLOOD GROUP
# ============================================================

VALID_BLOOD_GROUPS = {
    "A+",
    "A-",
    "B+",
    "B-",
    "AB+",
    "AB-",
    "O+",
    "O-"
}


def clean_blood_group(value):
    """
    Normalize blood group.
    """

    value = clean_text(value)

    if value is None:
        return None

    return value.upper()


def is_valid_blood_group(value):
    """
    Check whether blood group is valid.
    """

    if value is None or pd.isna(value) or not isinstance(value, str):
        return False

    return value in VALID_BLOOD_GROUPS