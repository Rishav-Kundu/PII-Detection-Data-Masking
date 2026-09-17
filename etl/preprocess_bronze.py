import pandas as pd
from sqlalchemy import text

from db import engine
from validators import (
    clean_text,
    clean_email,
    clean_phone,
    clean_date,
    clean_amount,
    clean_int,
    clean_percentage,
    clean_upper,
    clean_blood_group,
    is_valid_email,
    is_valid_phone,
    valid_percentage,
    valid_age,
    is_valid_blood_group,
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def is_empty(value):
    """Check if value is None, NaN, or pd.NA."""
    return value is None or pd.isna(value)


ALLOWED_TABLES = {
    "banking",
    "education",
    "medical",
    "marketing",
}


def validate_table_name(table_name):
    """Allow only the four internal ETL table names."""
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table name: {table_name}")


def read_bronze_table(conn, table_name):
    """
    Read a Bronze table into a Pandas DataFrame using SQLAlchemy.
    """
    validate_table_name(table_name)

    query = text(f"SELECT * FROM bronze.{table_name}")
    return pd.read_sql_query(query, conn)


def clear_silver_table(conn, table_name):
    """
    Clear the corresponding Silver table.

    This runs inside the transaction controlled by main().
    """
    validate_table_name(table_name)

    conn.execute(text(f"TRUNCATE TABLE silver.{table_name}"))


def insert_into_silver(conn, table_name, columns, rows):
    """
    Load processed rows into an existing Silver table using
    Pandas + SQLAlchemy.

    The Silver table is NOT recreated. Its existing PostgreSQL
    types, constraints, primary keys and checks remain intact.
    """
    validate_table_name(table_name)

    if not rows:
        return 0

    df = pd.DataFrame(rows, columns=columns)

    df.to_sql(
        name=table_name,
        con=conn,
        schema="silver",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1000,
    )

    return len(df)


# ============================================================
# BANKING
# ============================================================

def process_banking(conn):

    print("\n" + "=" * 60)
    print("PROCESSING BANKING")
    print("=" * 60)

    df = read_bronze_table(conn, "banking")

    bronze_count = len(df)

    print(f"Bronze records: {bronze_count}")

    # ----------------------------
    # CLEAN / TRANSFORM
    # ----------------------------

    df["customer_id"] = df["customer_id"].apply(clean_int)

    df["first_name"] = df["first_name"].apply(clean_text)
    df["last_name"] = df["last_name"].apply(clean_text)

    df["email"] = df["email"].apply(clean_email)
    df["phone"] = df["phone"].apply(clean_phone)

    df["date_of_birth"] = df["date_of_birth"].apply(clean_date)

    df["account_number"] = df["account_number"].apply(clean_text)

    df["account_type"] = df["account_type"].apply(clean_upper)

    df["balance"] = df["balance"].apply(clean_amount)

    df["address"] = df["address"].apply(clean_text)

    columns = [
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
    ]

    # ----------------------------
    # VALIDATION
    # ----------------------------

    valid_rows = []
    rejected_rows = []

    for _, row in df.iterrows():

        valid = True

        if is_empty(row["customer_id"]):
            valid = False

        if is_empty(row["first_name"]):
            valid = False

        if is_empty(row["last_name"]):
            valid = False

        if is_empty(row["email"]) or not is_valid_email(row["email"]):
            valid = False

        if is_empty(row["phone"]) or not is_valid_phone(row["phone"]):
            valid = False

        if is_empty(row["account_number"]):
            valid = False

        if row["account_type"] not in {
            "SAVINGS",
            "CURRENT",
            "SALARY",
            "FIXED_DEPOSIT",
        }:
            valid = False

        if is_empty(row["balance"]) or row["balance"] < 0:
            valid = False

        row_tuple = tuple(row[col] for col in columns)

        if valid:
            valid_rows.append(row_tuple)
        else:
            rejected_rows.append(row_tuple)

    # ----------------------------
    # LOAD
    # ----------------------------

    clear_silver_table(conn, "banking")

    inserted = insert_into_silver(
        conn,
        "banking",
        columns,
        valid_rows,
    )

    print(f"Valid records: {len(valid_rows)}")
    print(f"Rejected records: {len(rejected_rows)}")
    print(f"Silver records inserted: {inserted}")

    return bronze_count, len(valid_rows), len(rejected_rows)


# ============================================================
# EDUCATION
# ============================================================

def process_education(conn):

    print("\n" + "=" * 60)
    print("PROCESSING EDUCATION")
    print("=" * 60)

    df = read_bronze_table(conn, "education")

    bronze_count = len(df)

    print(f"Bronze records: {bronze_count}")

    # ----------------------------
    # CLEAN / TRANSFORM
    # ----------------------------

    df["student_id"] = df["student_id"].apply(clean_int)

    df["first_name"] = df["first_name"].apply(clean_text)
    df["last_name"] = df["last_name"].apply(clean_text)

    df["email"] = df["email"].apply(clean_email)
    df["phone"] = df["phone"].apply(clean_phone)

    df["date_of_birth"] = df["date_of_birth"].apply(clean_date)

    df["address"] = df["address"].apply(clean_text)

    df["course"] = df["course"].apply(clean_text)
    df["department"] = df["department"].apply(clean_text)

    df["enrollment_date"] = df["enrollment_date"].apply(clean_date)

    df["percentage"] = df["percentage"].apply(clean_percentage)

    columns = [
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
    ]

    # ----------------------------
    # VALIDATION
    # ----------------------------

    valid_rows = []
    rejected_rows = []

    for _, row in df.iterrows():

        valid = True

        if is_empty(row["student_id"]):
            valid = False

        if is_empty(row["first_name"]):
            valid = False

        if is_empty(row["last_name"]):
            valid = False

        if is_empty(row["email"]) or not is_valid_email(row["email"]):
            valid = False

        if is_empty(row["phone"]) or not is_valid_phone(row["phone"]):
            valid = False

        if is_empty(row["course"]):
            valid = False

        if is_empty(row["department"]):
            valid = False

        if is_empty(row["enrollment_date"]):
            valid = False

        if not is_empty(row["percentage"]):
            if not valid_percentage(row["percentage"]):
                valid = False

        row_tuple = tuple(row[col] for col in columns)

        if valid:
            valid_rows.append(row_tuple)
        else:
            rejected_rows.append(row_tuple)

    # ----------------------------
    # LOAD
    # ----------------------------

    clear_silver_table(conn, "education")

    inserted = insert_into_silver(
        conn,
        "education",
        columns,
        valid_rows,
    )

    print(f"Valid records: {len(valid_rows)}")
    print(f"Rejected records: {len(rejected_rows)}")
    print(f"Silver records inserted: {inserted}")

    return bronze_count, len(valid_rows), len(rejected_rows)


# ============================================================
# MEDICAL
# ============================================================

def process_medical(conn):

    print("\n" + "=" * 60)
    print("PROCESSING MEDICAL")
    print("=" * 60)

    df = read_bronze_table(conn, "medical")

    bronze_count = len(df)

    print(f"Bronze records: {bronze_count}")

    # ----------------------------
    # CLEAN / TRANSFORM
    # ----------------------------

    df["patient_id"] = df["patient_id"].apply(clean_int)

    df["first_name"] = df["first_name"].apply(clean_text)
    df["last_name"] = df["last_name"].apply(clean_text)

    df["email"] = df["email"].apply(clean_email)
    df["phone"] = df["phone"].apply(clean_phone)

    df["date_of_birth"] = df["date_of_birth"].apply(clean_date)

    df["address"] = df["address"].apply(clean_text)

    df["blood_group"] = df["blood_group"].apply(clean_blood_group)

    df["diagnosis"] = df["diagnosis"].apply(clean_text)
    df["doctor_name"] = df["doctor_name"].apply(clean_text)

    df["admission_date"] = df["admission_date"].apply(clean_date)

    df["medical_record_number"] = (
        df["medical_record_number"].apply(clean_text)
    )

    columns = [
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
    ]

    # ----------------------------
    # VALIDATION
    # ----------------------------

    valid_rows = []
    rejected_rows = []

    for _, row in df.iterrows():

        valid = True

        if is_empty(row["patient_id"]):
            valid = False

        if is_empty(row["first_name"]):
            valid = False

        if is_empty(row["last_name"]):
            valid = False

        if is_empty(row["email"]) or not is_valid_email(row["email"]):
            valid = False

        if is_empty(row["phone"]) or not is_valid_phone(row["phone"]):
            valid = False

        if not is_empty(row["blood_group"]):
            if not is_valid_blood_group(row["blood_group"]):
                valid = False

        if is_empty(row["medical_record_number"]):
            valid = False

        row_tuple = tuple(row[col] for col in columns)

        if valid:
            valid_rows.append(row_tuple)
        else:
            rejected_rows.append(row_tuple)

    # ----------------------------
    # LOAD
    # ----------------------------

    clear_silver_table(conn, "medical")

    inserted = insert_into_silver(
        conn,
        "medical",
        columns,
        valid_rows,
    )

    print(f"Valid records: {len(valid_rows)}")
    print(f"Rejected records: {len(rejected_rows)}")
    print(f"Silver records inserted: {inserted}")

    return bronze_count, len(valid_rows), len(rejected_rows)


# ============================================================
# MARKETING
# ============================================================

def process_marketing(conn):

    print("\n" + "=" * 60)
    print("PROCESSING MARKETING")
    print("=" * 60)

    df = read_bronze_table(conn, "marketing")

    bronze_count = len(df)

    print(f"Bronze records: {bronze_count}")

    # ----------------------------
    # CLEAN / TRANSFORM
    # ----------------------------

    df["customer_id"] = df["customer_id"].apply(clean_int)

    df["first_name"] = df["first_name"].apply(clean_text)
    df["last_name"] = df["last_name"].apply(clean_text)

    df["email"] = df["email"].apply(clean_email)
    df["phone"] = df["phone"].apply(clean_phone)

    df["address"] = df["address"].apply(clean_text)

    df["age"] = df["age"].apply(clean_int)

    df["gender"] = df["gender"].apply(clean_upper)

    df["campaign_name"] = df["campaign_name"].apply(clean_text)

    df["campaign_date"] = df["campaign_date"].apply(clean_date)

    df["channel"] = df["channel"].apply(clean_text)

    columns = [
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
    ]

    # ----------------------------
    # VALIDATION
    # ----------------------------

    valid_rows = []
    rejected_rows = []

    for _, row in df.iterrows():

        valid = True

        if is_empty(row["customer_id"]):
            valid = False

        if is_empty(row["first_name"]):
            valid = False

        if is_empty(row["last_name"]):
            valid = False

        if is_empty(row["email"]) or not is_valid_email(row["email"]):
            valid = False

        if is_empty(row["phone"]) or not is_valid_phone(row["phone"]):
            valid = False

        if not is_empty(row["age"]):
            if not valid_age(row["age"]):
                valid = False

        if not is_empty(row["gender"]):
            if row["gender"] not in {
                "MALE",
                "FEMALE",
                "OTHER",
            }:
                valid = False

        if is_empty(row["campaign_name"]):
            valid = False

        if is_empty(row["channel"]):
            valid = False

        row_tuple = tuple(row[col] for col in columns)

        if valid:
            valid_rows.append(row_tuple)
        else:
            rejected_rows.append(row_tuple)

    # ----------------------------
    # LOAD
    # ----------------------------

    clear_silver_table(conn, "marketing")

    inserted = insert_into_silver(
        conn,
        "marketing",
        columns,
        valid_rows,
    )

    print(f"Valid records: {len(valid_rows)}")
    print(f"Rejected records: {len(rejected_rows)}")
    print(f"Silver records inserted: {inserted}")

    return bronze_count, len(valid_rows), len(rejected_rows)


# ============================================================
# MAIN ETL PIPELINE
# ============================================================

def main():

    print("\n")
    print("=" * 60)
    print("        BRONZE → SILVER ETL PIPELINE")
    print("=" * 60)

    try:
        # engine.begin() gives us one SQLAlchemy transaction.
        # If anything fails, all Silver changes are rolled back.
        with engine.begin() as conn:

            print("\nConnected to Supabase PostgreSQL!")

            # --------------------------------
            # PROCESS ALL DOMAINS
            # --------------------------------

            results = {}

            results["banking"] = process_banking(conn)

            results["education"] = process_education(conn)

            results["medical"] = process_medical(conn)

            results["marketing"] = process_marketing(conn)

        # The transaction is committed here only if every domain
        # completed successfully.

        # --------------------------------
        # FINAL SUMMARY
        # --------------------------------

        print("\n")
        print("=" * 60)
        print("             ETL SUMMARY")
        print("=" * 60)

        print(
            f"{'Domain':<15}"
            f"{'Bronze':<12}"
            f"{'Valid':<12}"
            f"{'Rejected':<12}"
            f"{'Silver':<12}"
        )

        print("-" * 60)

        for domain, result in results.items():

            bronze_count, valid_count, rejected_count = result

            print(
                f"{domain:<15}"
                f"{bronze_count:<12}"
                f"{valid_count:<12}"
                f"{rejected_count:<12}"
                f"{valid_count:<12}"
            )

        print("=" * 60)

        print("\nETL PIPELINE COMPLETED SUCCESSFULLY!")

    except Exception as e:

        print("\nETL PIPELINE FAILED!")
        print("Error:")
        print(e)


if __name__ == "__main__":
    main()
