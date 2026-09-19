from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
INCOMING_DIR = DATA_DIR / "incoming"

load_dotenv(BASE_DIR / ".env")


# ============================================================
# DATABASE CONNECTION
# ============================================================

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("SUPABASE_DB_URL")
    or os.getenv("POSTGRES_URL")
)

if not DATABASE_URL:
    raise RuntimeError(
        "Database connection string not found.\n"
        "Set DATABASE_URL in your .env file."
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# ============================================================
# EXPECTED DOMAIN COLUMNS
# ============================================================

DOMAIN_REQUIRED_COLUMNS = {
    "banking": {
        "customer_id",
        "account_number",
        "account_type",
        "balance",
    },
    "education": {
        "student_id",
        "course",
        "department",
        "enrollment_date",
        "percentage",
    },
    "medical": {
        "patient_id",
        "diagnosis",
        "doctor_name",
        "admission_date",
        "medical_record_number",
    },
    "marketing": {
        "customer_id",
        "campaign_name",
        "campaign_date",
        "channel",
    },
}


# ============================================================
# BRONZE SOURCE COLUMN DEFINITIONS
# ============================================================

DOMAIN_SOURCE_COLUMNS = {
    "banking": [
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
    "education": [
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
    "medical": [
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
    "marketing": [
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
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def normalize_column_name(column: str) -> str:
    """
    Convert a CSV column name into a consistent database-style name.

    Examples:
        'Customer ID'      -> 'customer_id'
        'customer-id'     -> 'customer_id'
        ' First Name '    -> 'first_name'
    """

    column = str(column).strip().lower()

    column = re.sub(r"[^a-z0-9]+", "_", column)

    column = re.sub(r"_+", "_", column)

    return column.strip("_")


def normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize all CSV column names.
    """

    df = df.copy()

    df.columns = [
        normalize_column_name(column)
        for column in df.columns
    ]

    return df


def detect_domain(columns: set[str]) -> str:
    """
    Determine which domain a CSV belongs to based on its columns.

    This does NOT inspect or validate row values.
    It only looks at the CSV structure.
    """

    matches = []

    for domain, required_columns in DOMAIN_REQUIRED_COLUMNS.items():

        if required_columns.issubset(columns):
            matches.append(domain)

    if len(matches) == 1:
        return matches[0]

    if len(matches) == 0:
        raise ValueError(
            "Could not determine the domain from the CSV columns.\n"
            f"Available columns: {sorted(columns)}"
        )

    raise ValueError(
        "CSV matches multiple domains.\n"
        f"Possible domains: {matches}\n"
        f"Columns: {sorted(columns)}"
    )


def prepare_dataframe(
    df: pd.DataFrame,
    domain: str,
) -> pd.DataFrame:
    """
    Prepare the raw dataframe for Bronze.

    IMPORTANT:
    This function performs NO business/data validation.

    Missing columns are added as NULL so that Bronze can still
    receive the raw record structure.

    Extra columns are ignored because the current Bronze schemas
    contain the defined domain columns plus technical metadata.
    """

    source_columns = DOMAIN_SOURCE_COLUMNS[domain]

    df = df.copy()

    # Make sure all expected source columns exist.
    # Missing columns become NULL.
    for column in source_columns:

        if column not in df.columns:
            df[column] = None

    # Keep only columns supported by the Bronze schema.
    df = df[source_columns].copy()

    return df


def get_file_signature(file_path: Path) -> str:
    """
    Create a stable identifier for the current file.

    We use:
        filename + file size + last modified time

    This prevents accidentally loading the exact same local file
    repeatedly while still allowing a changed/new version of a file
    to be ingested later.
    """

    stat = file_path.stat()

    return (
        f"{file_path.name}|"
        f"{stat.st_size}|"
        f"{stat.st_mtime_ns}"
    )


# ============================================================
# INGESTION MANIFEST
# ============================================================

def ensure_manifest_table(conn) -> None:
    """
    Create a small Bronze metadata table used to track files that
    have already been ingested.

    This is NOT a business-data table.

    It only prevents accidental duplicate ingestion of the same
    physical file.
    """

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS bronze._ingestion_manifest (
                manifest_id BIGSERIAL PRIMARY KEY,
                source_file TEXT NOT NULL,
                file_signature TEXT NOT NULL UNIQUE,
                domain TEXT NOT NULL,
                ingestion_batch_id UUID NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )


def file_already_ingested(
    conn,
    file_signature: str,
) -> bool:

    result = conn.execute(
        text(
            """
            SELECT 1
            FROM bronze._ingestion_manifest
            WHERE file_signature = :file_signature
            LIMIT 1
            """
        ),
        {
            "file_signature": file_signature,
        },
    )

    return result.first() is not None


def register_file(
    conn,
    file_path: Path,
    file_signature: str,
    domain: str,
    batch_id: str,
    ingested_at: datetime,
) -> None:

    conn.execute(
        text(
            """
            INSERT INTO bronze._ingestion_manifest
            (
                source_file,
                file_signature,
                domain,
                ingestion_batch_id,
                ingested_at
            )
            VALUES
            (
                :source_file,
                :file_signature,
                :domain,
                :ingestion_batch_id,
                :ingested_at
            )
            """
        ),
        {
            "source_file": file_path.name,
            "file_signature": file_signature,
            "domain": domain,
            "ingestion_batch_id": batch_id,
            "ingested_at": ingested_at,
        },
    )


# ============================================================
# BRONZE TABLE SUPPORT
# ============================================================

def ensure_bronze_table(
    conn,
    domain: str,
) -> None:
    """
    Verify that the expected Bronze table exists.

    Bronze tables are expected to have already been created in
    Supabase.

    We intentionally do not recreate or replace them here.
    """

    result = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'bronze'
                  AND table_name = :table_name
            )
            """
        ),
        {
            "table_name": domain,
        },
    )

    exists = result.scalar()

    if not exists:
        raise RuntimeError(
            f"Bronze table bronze.{domain} does not exist."
        )


# ============================================================
# INGEST ONE CSV
# ============================================================

def ingest_file(
    conn,
    file_path: Path,
    batch_id: str,
    ingested_at: datetime,
) -> int:
    """
    Ingest one CSV file into the appropriate Bronze table.

    Every row is accepted.

    No:
        - validation
        - cleaning
        - deduplication
        - rejection
        - filtering
    """

    print()
    print("-" * 70)
    print(f"FILE: {file_path.name}")

    # --------------------------------------------------------
    # Read CSV exactly as strings.
    # --------------------------------------------------------

    df = pd.read_csv(
        file_path,
        dtype=str,
        keep_default_na=False,
    )

    # --------------------------------------------------------
    # Normalize only COLUMN NAMES.
    #
    # We do NOT clean the actual values.
    # --------------------------------------------------------

    df = normalize_dataframe_columns(df)

    # Remove accidental pandas index column if present.
    index_columns = {
        "index",
        "unnamed_0",
    }

    columns_to_remove = [
        column
        for column in df.columns
        if column in index_columns
    ]

    if columns_to_remove:
        df = df.drop(
            columns=columns_to_remove
        )

    # --------------------------------------------------------
    # Detect domain from columns.
    # --------------------------------------------------------

    domain = detect_domain(set(df.columns))

    print(f"Detected domain: {domain}")

    # --------------------------------------------------------
    # Verify Bronze table.
    # --------------------------------------------------------

    ensure_bronze_table(
        conn,
        domain,
    )

    # --------------------------------------------------------
    # Prepare dataframe.
    #
    # Missing columns become NULL.
    # No row validation occurs.
    # --------------------------------------------------------

    df = prepare_dataframe(
        df,
        domain,
    )

    # --------------------------------------------------------
    # Add technical metadata.
    # --------------------------------------------------------

    df["_source_file"] = file_path.name

    df["_ingestion_batch_id"] = batch_id

    df["_ingested_at"] = ingested_at

    # --------------------------------------------------------
    # Insert EVERYTHING into Bronze.
    #
    # if_exists="append" is intentional.
    #
    # Bronze is append-only.
    # --------------------------------------------------------

    df.to_sql(
        name=domain,
        con=conn,
        schema="bronze",
        if_exists="append",
        index=False,
        method="multi",
    )

    row_count = len(df)

    print(f"Rows loaded:    {row_count}")
    print(f"Batch ID:       {batch_id}")
    print("Status:         INGESTED")

    return row_count


# ============================================================
# MAIN INGESTION PROCESS
# ============================================================

def main() -> None:

    print()
    print("=" * 70)
    print("CSV -> BRONZE INGESTION")
    print("=" * 70)

    print()
    print("Bronze rules:")
    print("  - Accept every source row")
    print("  - No row-level validation")
    print("  - No cleaning")
    print("  - No deduplication")
    print("  - No rejection")
    print("  - Bronze is append-only")
    print()

    # --------------------------------------------------------
    # Make sure incoming directory exists.
    # --------------------------------------------------------

    INCOMING_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Find every CSV file in data/incoming.
    # --------------------------------------------------------

    csv_files = sorted(
        [
            path
            for path in INCOMING_DIR.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".csv"
        ]
    )

    if not csv_files:

        print(
            f"No CSV files found in:\n"
            f"{INCOMING_DIR}"
        )

        return

    print(
        f"Found {len(csv_files)} CSV file(s) in:"
    )

    print(
        f"  {INCOMING_DIR}"
    )

    # --------------------------------------------------------
    # One batch ID for this execution.
    # --------------------------------------------------------

    batch_id = str(uuid.uuid4())

    ingested_at = datetime.now(
        timezone.utc
    )

    print()
    print(f"Batch ID: {batch_id}")
    print(
        f"Ingestion time: "
        f"{ingested_at.isoformat()}"
    )

    total_rows = 0
    skipped_files = 0
    failed_files = 0
    successful_files = 0

    # --------------------------------------------------------
    # Database transaction.
    # --------------------------------------------------------

    with engine.begin() as conn:

        # Make sure manifest exists.
        ensure_manifest_table(conn)

        for file_path in csv_files:

            try:

                # --------------------------------------------
                # Check whether this exact file was already
                # ingested.
                # --------------------------------------------

                file_signature = get_file_signature(
                    file_path
                )

                if file_already_ingested(
                    conn,
                    file_signature,
                ):

                    print()
                    print("-" * 70)
                    print(
                        f"FILE: {file_path.name}"
                    )
                    print(
                        "Status:         SKIPPED"
                    )
                    print(
                        "Reason:         "
                        "This file was already ingested."
                    )

                    skipped_files += 1

                    continue

                # --------------------------------------------
                # Ingest file.
                # --------------------------------------------

                row_count = ingest_file(
                    conn,
                    file_path,
                    batch_id,
                    ingested_at,
                )

                # --------------------------------------------
                # Detect domain again for manifest.
                #
                # This only reads the CSV structure.
                # No row validation.
                # --------------------------------------------

                manifest_df = pd.read_csv(
                    file_path,
                    dtype=str,
                    keep_default_na=False,
                    nrows=0,
                )

                manifest_df = normalize_dataframe_columns(
                    manifest_df
                )

                domain = detect_domain(
                    set(manifest_df.columns)
                )

                # --------------------------------------------
                # Register successful ingestion.
                # --------------------------------------------

                register_file(
                    conn,
                    file_path,
                    file_signature,
                    domain,
                    batch_id,
                    ingested_at,
                )

                total_rows += row_count
                successful_files += 1

            except Exception as exc:

                failed_files += 1

                print()
                print("-" * 70)
                print(
                    f"FILE: {file_path.name}"
                )
                print(
                    "Status:         FAILED"
                )
                print(
                    f"Reason:         {exc}"
                )

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print("BRONZE INGESTION COMPLETED")
    print("=" * 70)

    print()
    print(f"Files found:       {len(csv_files)}")
    print(f"Files ingested:    {successful_files}")
    print(f"Files skipped:     {skipped_files}")
    print(f"Files failed:      {failed_files}")
    print(f"Rows ingested:     {total_rows}")

    print()
    print("Bronze remains append-only.")
    print("No source rows were cleaned or rejected.")
    print()


if __name__ == "__main__":
    main()
