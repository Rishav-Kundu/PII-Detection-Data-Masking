# etl/preprocess_bronze.py

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import inspect, text

from etl.db import engine
from etl.validators import (
    clean_account_number,
    clean_account_type,
    clean_age,
    clean_amount,
    clean_blood_group,
    clean_channel,
    clean_date,
    clean_email,
    clean_gender,
    clean_int,
    clean_location,
    clean_medical_record_number,
    clean_name,
    clean_percentage,
    clean_phone,
    clean_text,
    is_missing,
)


# ============================================================
# DOMAIN CONFIGURATION
# ============================================================

DOMAIN_CONFIG = {
    "banking": {
        "primary_key": "customer_id",
        "source_columns": [
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "date_of_birth",
            "account_number",
            "account_type",
            "balance",
            "address",
        ],
    },
    "education": {
        "primary_key": "student_id",
        "source_columns": [
            "student_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "date_of_birth",
            "address",
            "course",
            "department",
            "enrollment_date",
            "percentage",
        ],
    },
    "medical": {
        "primary_key": "patient_id",
        "source_columns": [
            "patient_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "date_of_birth",
            "address",
            "blood_group",
            "diagnosis",
            "doctor_name",
            "admission_date",
            "medical_record_number",
        ],
    },
    "marketing": {
        "primary_key": "customer_id",
        "source_columns": [
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "age",
            "gender",
            "campaign_name",
            "campaign_date",
            "channel",
        ],
    },
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def normalize_raw_value(value: Any) -> str:
    """
    Convert a value into a stable normalized string representation.

    This is used only for duplicate detection.
    It does NOT modify the actual stored data.
    """

    if value is None:
        return ""

    if pd.isna(value):
        return ""

    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))

    return str(value).strip().lower()


def build_duplicate_signature(
    row: dict[str, Any],
    columns: list[str],
) -> tuple[str, ...]:
    """
    Build a normalized signature for exact duplicate detection.

    Only business/source columns are included.
    Technical columns such as _bronze_id and ingestion metadata
    are intentionally excluded.
    """

    return tuple(
        normalize_raw_value(row.get(column))
        for column in columns
    )


def table_exists(schema: str, table: str) -> bool:
    inspector = inspect(engine)
    return inspector.has_table(table, schema=schema)


# ============================================================
# EXISTING SILVER DATA
# ============================================================

def get_existing_bronze_ids(
    conn,
    domain: str,
) -> set[int]:
    """
    Return Bronze IDs that have already been processed into Silver.

    This makes the ETL incremental.
    """

    query = text(
        f"""
        SELECT _bronze_id
        FROM silver.{domain}
        WHERE _bronze_id IS NOT NULL
        """
    )

    rows = conn.execute(query).fetchall()

    return {
        int(row[0])
        for row in rows
        if row[0] is not None
    }


def get_existing_primary_keys(
    conn,
    domain: str,
    primary_key: str,
) -> set[int]:
    """
    Return all existing business primary keys in Silver.

    A duplicate business PK is intentionally rejected.
    """

    query = text(
        f"""
        SELECT {primary_key}
        FROM silver.{domain}
        WHERE {primary_key} IS NOT NULL
        """
    )

    rows = conn.execute(query).fetchall()

    result = set()

    for row in rows:
        value = row[0]

        if value is not None:
            try:
                result.add(int(value))
            except (TypeError, ValueError):
                pass

    return result


def get_existing_signatures(
    conn,
    domain: str,
    source_columns: list[str],
) -> set[tuple[str, ...]]:
    """
    Build normalized duplicate signatures from existing Silver rows.

    IMPORTANT:
    Silver values have already been cleaned.

    Therefore, existing Silver rows are normalized before comparison
    instead of comparing raw Bronze strings directly with Silver values.
    """

    columns_sql = ", ".join(source_columns)

    query = text(
        f"""
        SELECT {columns_sql}
        FROM silver.{domain}
        """
    )

    rows = conn.execute(query).mappings().all()

    signatures = set()

    for row in rows:
        row_dict = dict(row)

        signature = build_duplicate_signature(
            row_dict,
            source_columns,
        )

        signatures.add(signature)

    return signatures


# ============================================================
# COMMON CLEANING
# ============================================================

def clean_common_fields(row: dict[str, Any]) -> dict[str, Any]:
    """
    Clean fields shared by all four domains.
    """

    cleaned = {}

    # --------------------------------------------------------
    # PRIMARY / ID
    # --------------------------------------------------------

    for key, value in row.items():
        cleaned[key] = value

    # --------------------------------------------------------
    # NAMES
    # --------------------------------------------------------

    cleaned["first_name"] = clean_name(
        row.get("first_name")
    )

    cleaned["last_name"] = clean_name(
        row.get("last_name")
    )

    # --------------------------------------------------------
    # CONTACT
    # --------------------------------------------------------

    cleaned["email"] = clean_email(
        row.get("email")
    )

    cleaned["phone"] = clean_phone(
        row.get("phone")
    )

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    address, city, state = clean_location(
        row.get("address")
    )

    cleaned["address"] = address
    cleaned["city"] = city
    cleaned["state"] = state

    return cleaned


# ============================================================
# DOMAIN-SPECIFIC CLEANING
# ============================================================

def clean_banking(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = clean_common_fields(row)

    cleaned["customer_id"] = clean_int(
        row.get("customer_id")
    )

    cleaned["date_of_birth"] = clean_date(
        row.get("date_of_birth")
    )

    cleaned["account_number"] = clean_account_number(
        row.get("account_number")
    )

    cleaned["account_type"] = clean_account_type(
        row.get("account_type")
    )

    # Negative values ARE allowed.
    cleaned["balance"] = clean_amount(
        row.get("balance")
    )

    return cleaned


def clean_education(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = clean_common_fields(row)

    cleaned["student_id"] = clean_int(
        row.get("student_id")
    )

    cleaned["date_of_birth"] = clean_date(
        row.get("date_of_birth")
    )

    cleaned["course"] = clean_text(
        row.get("course")
    )

    cleaned["department"] = clean_text(
        row.get("department")
    )

    cleaned["enrollment_date"] = clean_date(
        row.get("enrollment_date")
    )

    cleaned["percentage"] = clean_percentage(
        row.get("percentage")
    )

    return cleaned


def clean_medical(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = clean_common_fields(row)

    cleaned["patient_id"] = clean_int(
        row.get("patient_id")
    )

    cleaned["date_of_birth"] = clean_date(
        row.get("date_of_birth")
    )

    cleaned["blood_group"] = clean_blood_group(
        row.get("blood_group")
    )

    cleaned["diagnosis"] = clean_text(
        row.get("diagnosis")
    )

    cleaned["doctor_name"] = clean_name(
        row.get("doctor_name")
    )

    cleaned["admission_date"] = clean_date(
        row.get("admission_date")
    )

    cleaned["medical_record_number"] = clean_medical_record_number(
        row.get("medical_record_number")
    )

    return cleaned


def clean_marketing(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = clean_common_fields(row)

    cleaned["customer_id"] = clean_int(
        row.get("customer_id")
    )

    cleaned["age"] = clean_age(
        row.get("age")
    )

    cleaned["gender"] = clean_gender(
        row.get("gender")
    )

    cleaned["campaign_name"] = clean_text(
        row.get("campaign_name")
    )

    cleaned["campaign_date"] = clean_date(
        row.get("campaign_date")
    )

    cleaned["channel"] = clean_channel(
        row.get("channel")
    )

    return cleaned


def clean_row(
    domain: str,
    row: dict[str, Any],
) -> dict[str, Any]:

    if domain == "banking":
        return clean_banking(row)

    if domain == "education":
        return clean_education(row)

    if domain == "medical":
        return clean_medical(row)

    if domain == "marketing":
        return clean_marketing(row)

    raise ValueError(f"Unknown domain: {domain}")


# ============================================================
# CRITICAL VALIDATION
# ============================================================

def is_valid_critical_row(
    cleaned: dict[str, Any],
    primary_key: str,
) -> tuple[bool, str | None]:
    """
    Validate fields whose failure causes entire-row rejection.

    Critical fields:
    1. Primary key
    2. First name
    """

    # --------------------------------------------------------
    # PRIMARY KEY
    # --------------------------------------------------------

    primary_key_value = cleaned.get(primary_key)

    if primary_key_value is None:
        return False, "INVALID_PRIMARY_KEY"

    # clean_int() should already return an integer.
    # This additional check protects against unexpected values.
    if not isinstance(primary_key_value, int):
        return False, "INVALID_PRIMARY_KEY"

    # --------------------------------------------------------
    # FIRST NAME
    # --------------------------------------------------------

    first_name = cleaned.get("first_name")

    if first_name is None:
        return False, "MISSING_FIRST_NAME"

    if is_missing(first_name):
        return False, "MISSING_FIRST_NAME"

    return True, None


# ============================================================
# DATE RELATIONSHIPS
# ============================================================

def to_python_date(value: Any) -> date | None:

    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        return value.date()

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def validate_date_relationships(
    domain: str,
    cleaned: dict[str, Any],
) -> dict[str, Any]:
    """
    Date errors are NON-CRITICAL.

    Therefore, invalid/future dates are converted to NULL
    rather than causing the entire row to be rejected.
    """

    today = date.today()

    # --------------------------------------------------------
    # DATE OF BIRTH
    # --------------------------------------------------------

    if "date_of_birth" in cleaned:

        dob = to_python_date(
            cleaned.get("date_of_birth")
        )

        if dob is not None and dob > today:
            cleaned["date_of_birth"] = None

    # --------------------------------------------------------
    # EDUCATION ENROLLMENT DATE
    # --------------------------------------------------------

    if domain == "education":

        enrollment_date = to_python_date(
            cleaned.get("enrollment_date")
        )

        if (
            enrollment_date is not None
            and enrollment_date > today
        ):
            cleaned["enrollment_date"] = None

    # --------------------------------------------------------
    # MEDICAL ADMISSION DATE
    # --------------------------------------------------------

    if domain == "medical":

        admission_date = to_python_date(
            cleaned.get("admission_date")
        )

        if (
            admission_date is not None
            and admission_date > today
        ):
            cleaned["admission_date"] = None

        dob = to_python_date(
            cleaned.get("date_of_birth")
        )

        if (
            dob is not None
            and admission_date is not None
            and admission_date < dob
        ):
            cleaned["admission_date"] = None

    # --------------------------------------------------------
    # MARKETING CAMPAIGN DATE
    # --------------------------------------------------------

    if domain == "marketing":

        campaign_date = to_python_date(
            cleaned.get("campaign_date")
        )

        if (
            campaign_date is not None
            and campaign_date > today
        ):
            cleaned["campaign_date"] = None

    return cleaned


# ============================================================
# SILVER INSERT
# ============================================================

def insert_silver_row(
    conn,
    domain: str,
    cleaned: dict[str, Any],
) -> None:

    # Silver keeps cleaned business data plus the Bronze lineage ID
    # and derived location fields.
    allowed_columns = (
        DOMAIN_CONFIG[domain]["source_columns"]
        + [
            "_bronze_id",
            "city",
            "state",
        ]
    )

    # Keep only columns that actually belong in Silver.
    silver_row = {
        column: cleaned.get(column)
        for column in allowed_columns
    }

    columns = list(silver_row.keys())

    column_sql = ", ".join(
        f'"{column}"'
        for column in columns
    )

    values_sql = ", ".join(
        f":{column}"
        for column in columns
    )

    query = text(
        f"""
        INSERT INTO silver.{domain}
        ({column_sql})
        VALUES ({values_sql})
        """
    )

    conn.execute(
        query,
        silver_row,
    )


# ============================================================
# PROCESS ONE DOMAIN
# ============================================================

def process_domain(
    conn,
    domain: str,
) -> dict[str, int]:

    config = DOMAIN_CONFIG[domain]

    primary_key = config["primary_key"]
    source_columns = config["source_columns"]

    stats = {
        "bronze_rows": 0,
        "already_processed": 0,
        "inserted": 0,
        "rejected": 0,
        "invalid_primary_key": 0,
        "duplicate_primary_key": 0,
        "missing_first_name": 0,
        "exact_duplicate": 0,
    }

    # --------------------------------------------------------
    # EXISTING SILVER STATE
    # --------------------------------------------------------

    existing_bronze_ids = get_existing_bronze_ids(
        conn,
        domain,
    )

    existing_primary_keys = get_existing_primary_keys(
        conn,
        domain,
        primary_key,
    )

    existing_signatures = get_existing_signatures(
        conn,
        domain,
        source_columns,
    )

    # These are updated while processing the current run.
    # This catches duplicates appearing twice in the same Bronze batch.
    processed_signatures = set(existing_signatures)

    # --------------------------------------------------------
    # READ BRONZE
    # --------------------------------------------------------

    query = text(
        f"""
        SELECT *
        FROM bronze.{domain}
        ORDER BY _bronze_id
        """
    )

    bronze_rows = conn.execute(
        query
    ).mappings().all()

    stats["bronze_rows"] = len(bronze_rows)

    # --------------------------------------------------------
    # PROCESS EACH ROW
    # --------------------------------------------------------

    for raw_mapping in bronze_rows:

        raw_row = dict(raw_mapping)

        bronze_id = raw_row.get("_bronze_id")

        # ----------------------------------------------------
        # ALREADY PROCESSED?
        # ----------------------------------------------------

        if bronze_id in existing_bronze_ids:

            stats["already_processed"] += 1
            continue

        # ----------------------------------------------------
        # CLEAN
        # ----------------------------------------------------

        cleaned = clean_row(
            domain,
            raw_row,
        )

        # ----------------------------------------------------
        # DATE RELATIONSHIPS
        # ----------------------------------------------------

        cleaned = validate_date_relationships(
            domain,
            cleaned,
        )

        # ----------------------------------------------------
        # CRITICAL VALIDATION
        # ----------------------------------------------------

        valid, reason = is_valid_critical_row(
            cleaned,
            primary_key,
        )

        if not valid:

            stats["rejected"] += 1

            if reason == "INVALID_PRIMARY_KEY":
                stats["invalid_primary_key"] += 1

            elif reason == "MISSING_FIRST_NAME":
                stats["missing_first_name"] += 1

            continue

        # ----------------------------------------------------
        # DUPLICATE PRIMARY KEY
        # ----------------------------------------------------

        pk_value = cleaned.get(primary_key)

        if pk_value in existing_primary_keys:

            stats["rejected"] += 1
            stats["duplicate_primary_key"] += 1

            continue

        # ----------------------------------------------------
        # EXACT NORMALIZED DUPLICATE
        # ----------------------------------------------------

        signature = build_duplicate_signature(
            cleaned,
            source_columns,
        )

        if signature in processed_signatures:

            stats["rejected"] += 1
            stats["exact_duplicate"] += 1

            continue

        # ----------------------------------------------------
        # ADD BRONZE ID
        # ----------------------------------------------------

        cleaned["_bronze_id"] = bronze_id

        # ----------------------------------------------------
        # INSERT INTO SILVER
        # ----------------------------------------------------

        insert_silver_row(
            conn,
            domain,
            cleaned,
        )

        # ----------------------------------------------------
        # UPDATE IN-MEMORY STATE
        # ----------------------------------------------------

        existing_primary_keys.add(
            pk_value
        )

        processed_signatures.add(
            signature
        )

        existing_bronze_ids.add(
            bronze_id
        )

        stats["inserted"] += 1

    return stats


# ============================================================
# PRINT STATISTICS
# ============================================================

def print_domain_stats(
    domain: str,
    stats: dict[str, int],
) -> None:

    print()
    print("=" * 64)
    print(domain.upper())
    print("=" * 64)

    print(
        f"Bronze rows:            {stats['bronze_rows']}"
    )

    print(
        f"Already processed:      {stats['already_processed']}"
    )

    print(
        f"Inserted into Silver:   {stats['inserted']}"
    )

    print(
        f"Rejected:                {stats['rejected']}"
    )

    if stats["rejected"] > 0:

        print(
            f"  Invalid primary key:  "
            f"{stats['invalid_primary_key']}"
        )

        print(
            f"  Duplicate primary key:"
            f" {stats['duplicate_primary_key']}"
        )

        print(
            f"  Missing first name:   "
            f"{stats['missing_first_name']}"
        )

        print(
            f"  Exact duplicate:      "
            f"{stats['exact_duplicate']}"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print("=" * 64)
    print("BRONZE -> SILVER")
    print("=" * 64)

    print(
        "Silver mode: persistent incremental cleansing."
    )

    print(
        "No Silver truncation. Bronze rows are never deleted."
    )

    print(
        "Critical rejection: invalid/duplicate PK or invalid first name."
    )

    print(
        "Non-critical invalid fields are converted to NULL."
    )

    print()

    if not table_exists("bronze", "banking"):
        raise RuntimeError(
            "Bronze tables were not found. Run Bronze ingestion first."
        )

    with engine.begin() as conn:

        all_stats = {}

        for domain in DOMAIN_CONFIG:

            stats = process_domain(
                conn,
                domain,
            )

            all_stats[domain] = stats

            print_domain_stats(
                domain,
                stats,
            )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 64)
    print("SILVER PREPROCESSING COMPLETED")
    print("=" * 64)

    total_bronze = sum(
        s["bronze_rows"]
        for s in all_stats.values()
    )

    total_inserted = sum(
        s["inserted"]
        for s in all_stats.values()
    )

    total_rejected = sum(
        s["rejected"]
        for s in all_stats.values()
    )

    total_skipped = sum(
        s["already_processed"]
        for s in all_stats.values()
    )

    print(
        f"Total Bronze rows:      {total_bronze}"
    )

    print(
        f"Inserted into Silver:   {total_inserted}"
    )

    print(
        f"Rejected:               {total_rejected}"
    )

    print(
        f"Already processed:      {total_skipped}"
    )

    print()
    print("Bronze remains unchanged.")
    print("Silver remains persistent.")
    print()


if __name__ == "__main__":
    main()