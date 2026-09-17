import os
import uuid
import hashlib
import json
import pandas as pd
from sqlalchemy import text, inspect
from db import engine


# Map CSV file paths to their corresponding Bronze table names
CSV_MAPPING = {
    "banking": "data/raw_banking.csv",
    "education": "data/raw_education.csv",
    "medical": "data/raw_medical.csv",
    "marketing": "data/raw_marketing.csv",
}


def ensure_bronze_schema(conn):
    """Ensure the Bronze schema exists in PostgreSQL."""
    conn.execute(
        text("CREATE SCHEMA IF NOT EXISTS bronze;")
    )


def bronze_table_exists(conn, table_name):
    """Check whether a table already exists in the Bronze schema."""
    inspector = inspect(conn)

    return inspector.has_table(
        table_name,
        schema="bronze"
    )


def generate_row_hash(row):
    """
    Generate a deterministic SHA-256 hash for a source row.

    The hash is based only on the source columns and their values.
    Bronze ingestion metadata is added later and is therefore not
    included in the hash.

    Column names are sorted so that the hash does not depend on
    DataFrame column order.
    """

    canonical_data = {}

    for column in sorted(row.index):
        value = row[column]

        # Normalize missing values
        if pd.isna(value):
            value = None
        else:
            value = str(value)

        canonical_data[column] = value

    # Convert to a deterministic JSON representation
    row_string = json.dumps(
        canonical_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    )

    return hashlib.sha256(
        row_string.encode("utf-8")
    ).hexdigest()


def prepare_dataframe(df, file_path, batch_id):
    """
    Prepare a DataFrame for Bronze ingestion.

    Adds ingestion metadata:
        _row_hash
        _source_file
        _ingestion_batch_id
        _ingested_at
    """

    # Strip whitespace from column headers
    df.columns = [
        c.strip().lower()
        for c in df.columns
    ]

    # Generate a hash for every source row
    df["_row_hash"] = df.apply(
        generate_row_hash,
        axis=1
    )

    # Add ingestion metadata
    df["_source_file"] = os.path.basename(file_path)
    df["_ingestion_batch_id"] = batch_id
    df["_ingested_at"] = pd.Timestamp.now()

    return df


def ensure_bronze_metadata_columns(conn, table_name):
    """
    Add Bronze ingestion metadata columns to an existing table
    if they do not already exist.
    """

    inspector = inspect(conn)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(
            table_name,
            schema="bronze"
        )
    }

    metadata_columns = {
        "_row_hash": "VARCHAR(64)",
        "_source_file": "VARCHAR(255)",
        "_ingestion_batch_id": "UUID",
        "_ingested_at": "TIMESTAMP",
    }

    for column_name, column_type in metadata_columns.items():

        if column_name not in existing_columns:

            conn.execute(
                text(
                    f"""
                    ALTER TABLE bronze.{table_name}
                    ADD COLUMN {column_name} {column_type};
                    """
                )
            )


def ensure_row_hash_constraint(conn, table_name):
    """
    Create a unique constraint on _row_hash.

    This provides database-level protection against
    inserting the exact same row twice.
    """

    constraint_name = f"{table_name}_row_hash_key"

    conn.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = :constraint_name
                ) THEN
                    ALTER TABLE bronze.{table_name}
                    ADD CONSTRAINT {constraint_name}
                    UNIQUE (_row_hash);
                END IF;
            END $$;
            """
        ),
        {"constraint_name": constraint_name}
    )


def get_existing_hashes(conn, table_name, hashes):
    """
    Return the row hashes that already exist in a Bronze table.
    """

    if not hashes:
        return set()

    result = conn.execute(
        text(
            f"""
            SELECT _row_hash
            FROM bronze.{table_name}
            WHERE _row_hash = ANY(:hashes);
            """
        ),
        {"hashes": list(hashes)}
    )

    return {
        row[0]
        for row in result
    }


def load_csv_to_bronze(conn, table_name, file_path, batch_id):
    """
    Read a CSV file and load it into bronze.<table_name>.

    Bronze is append-only and historical.

    Exact duplicate rows are skipped using _row_hash.

    If the same business entity changes, its row hash changes,
    so the new version is inserted and the old version remains.
    """

    if not os.path.exists(file_path):

        print(
            f"⚠️ File not found: {file_path}. "
            f"Skipping {table_name}..."
        )

        return 0

    print(f"\nReading {file_path}...")

    df = pd.read_csv(file_path)

    print(
        f"Found {len(df)} records "
        f"for bronze.{table_name}"
    )

    # Prepare source data and add Bronze metadata
    df = prepare_dataframe(
        df,
        file_path,
        batch_id
    )
    # Remove duplicate rows within the current CSV
    before_dedup = len(df)

    df = df.drop_duplicates(
        subset="_row_hash",
        keep="first"
    ).reset_index(drop=True)

    duplicates_removed = before_dedup - len(df)

    if duplicates_removed > 0:
        print(
            f"Removed {duplicates_removed} duplicate row(s) "
            f"from {os.path.basename(file_path)}."
        )
    # ---------------------------------------------------------
    # FIRST INGESTION: Create Bronze table
    # ---------------------------------------------------------

    if not bronze_table_exists(conn, table_name):

        print(
            f"Bronze table bronze.{table_name} "
            f"does not exist."
        )

        print(
            f"Creating table and inserting "
            f"{len(df)} records..."
        )

        df.to_sql(
            name=table_name,
            con=conn,
            schema="bronze",
            if_exists="fail",
            index=False,
            chunksize=1000,
            method="multi",
        )

        # Add database-level duplicate protection
        ensure_row_hash_constraint(
            conn,
            table_name
        )

        print(
            f"✅ Created bronze.{table_name} "
            f"and inserted {len(df)} records"
        )

        return len(df)

    # ---------------------------------------------------------
    # EXISTING TABLE: Append only new row hashes
    # ---------------------------------------------------------

    print(
        f"Bronze table bronze.{table_name} "
        f"already exists."
    )

    # Make sure existing Bronze tables have the metadata columns
    ensure_bronze_metadata_columns(
        conn,
        table_name
    )

    # Make sure _row_hash is protected by a UNIQUE constraint
    ensure_row_hash_constraint(
        conn,
        table_name
    )

    incoming_hashes = set(
        df["_row_hash"]
    )

    existing_hashes = get_existing_hashes(
        conn,
        table_name,
        incoming_hashes
    )

    new_df = df[
        ~df["_row_hash"].isin(existing_hashes)
    ].copy()

    duplicate_count = len(df) - len(new_df)

    print(
        f"Found {duplicate_count} duplicate "
        f"records already present in Bronze."
    )

    if new_df.empty:

        print(
            f"ℹ️ No new records to insert "
            f"into bronze.{table_name}"
        )

        return 0

    print(
        f"Appending {len(new_df)} new records..."
    )

    new_df.to_sql(
        name=table_name,
        con=conn,
        schema="bronze",
        if_exists="append",
        index=False,
        chunksize=1000,
        method="multi",
    )

    print(
        f"✅ Appended {len(new_df)} new records "
        f"to bronze.{table_name}"
    )

    return len(new_df)


def load_external_table_to_bronze(
    conn,
    source_query,
    target_bronze_table,
    batch_id
):
    """
    Load data from another database table/query
    into the Bronze schema.

    Exact duplicate rows are skipped using _row_hash.
    """

    print(
        f"\nPulling data into "
        f"bronze.{target_bronze_table}..."
    )

    df = pd.read_sql_query(
        text(source_query),
        conn
    )

    print(
        f"Found {len(df)} records "
        f"from external source."
    )

    # Prepare data and add metadata
    df = prepare_dataframe(
        df,
        source_query,
        batch_id
    )

    # If the Bronze table doesn't exist, create it
    if not bronze_table_exists(
        conn,
        target_bronze_table
    ):

        print(
            f"bronze.{target_bronze_table} "
            f"does not exist. Creating..."
        )

        df.to_sql(
            name=target_bronze_table,
            con=conn,
            schema="bronze",
            if_exists="fail",
            index=False,
            chunksize=1000,
            method="multi",
        )

        ensure_row_hash_constraint(
            conn,
            target_bronze_table
        )

        print(
            f"✅ Created bronze.{target_bronze_table} "
            f"and inserted {len(df)} records"
        )

        return len(df)

    # Existing table
    ensure_bronze_metadata_columns(
        conn,
        target_bronze_table
    )

    ensure_row_hash_constraint(
        conn,
        target_bronze_table
    )

    incoming_hashes = set(
        df["_row_hash"]
    )

    existing_hashes = get_existing_hashes(
        conn,
        target_bronze_table,
        incoming_hashes
    )

    new_df = df[
        ~df["_row_hash"].isin(existing_hashes)
    ].copy()

    duplicate_count = len(df) - len(new_df)

    print(
        f"Found {duplicate_count} duplicate "
        f"records already present in Bronze."
    )

    if new_df.empty:

        print(
            f"ℹ️ No new records to insert "
            f"into bronze.{target_bronze_table}"
        )

        return 0

    new_df.to_sql(
        name=target_bronze_table,
        con=conn,
        schema="bronze",
        if_exists="append",
        index=False,
        chunksize=1000,
        method="multi",
    )

    print(
        f"✅ Appended {len(new_df)} new records "
        f"to bronze.{target_bronze_table}"
    )

    return len(new_df)


def main():

    print("=" * 60)
    print("        CSV ➔ BRONZE INGESTION PIPELINE")
    print("=" * 60)

    # One UUID identifies this complete ingestion run
    batch_id = str(uuid.uuid4())

    print(f"\nIngestion batch ID: {batch_id}")

    with engine.begin() as conn:

        # 1. Ensure Bronze schema exists
        ensure_bronze_schema(conn)

        # 2. Ingest CSV files
        for table_name, csv_path in CSV_MAPPING.items():

            load_csv_to_bronze(
                conn,
                table_name,
                csv_path,
                batch_id
            )

    print("\n" + "=" * 60)
    print("Bronze ingestion completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
