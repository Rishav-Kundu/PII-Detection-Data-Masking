import pandas as pd
from psycopg2.extras import execute_batch

from db import get_connection
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
    is_valid_blood_group
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def read_bronze_table(conn, table_name):
    """
    Read a Bronze table into a Pandas DataFrame.
    """

    query = f"SELECT * FROM bronze.{table_name}"

    return pd.read_sql_query(query, conn)


def clear_silver_table(conn, table_name):
    """
    Clear the corresponding Silver table before loading.

    This makes the ETL repeatable and prevents duplicate rows
    when we run the script again.
    """

    with conn.cursor() as cursor:
        cursor.execute(f"TRUNCATE TABLE silver.{table_name}")

    conn.commit()


def insert_into_silver(conn, table_name, columns, rows):
    """
    Batch insert processed rows into a Silver table.
    """

    if not rows:
        return 0

    column_string = ", ".join(columns)

    placeholders = ", ".join(["%s"] * len(columns))

    query = f"""
        INSERT INTO silver.{table_name}
        ({column_string})
        VALUES ({placeholders})
    """

    with conn.cursor() as cursor:
        execute_batch(
            cursor,
            query,
            rows,
            page_size=100
        )

    conn.commit()

    return len(rows)


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

    # ----------------------------
    # VALIDATION
    # ----------------------------

    valid_rows = []
    rejected_rows = []

    for _, row in df.iterrows():

        valid = True

        # Required fields
        if row["customer_id"] is None:
            valid = False

        if row["first_name"] is None:
            valid = False

        if row["last_name"] is None:
            valid = False

        if row["email"] is None or not is_valid_email(row["email"]):
            valid = False

        if row["phone"] is None or not is_valid_phone(row["phone"]):
            valid = False

        if row["account_number"] is None:
            valid = False

        if row["account_type"] not in {
            "SAVINGS",
            "CURRENT",
            "SALARY",
            "FIXED_DEPOSIT"
        }:
            valid = False

        if row["balance"] is None or row["balance"] < 0:
            valid = False

        if valid:
            valid_rows.append(tuple(row))
        else:
            rejected_rows.append(tuple(row))

    # ----------------------------
    # LOAD
    # ----------------------------

    clear_silver_table(conn, "banking")

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
        "address"
    ]

    inserted = insert_into_silver(
        conn,
        "banking",
        columns,
        valid_rows
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

    # ----------------------------
    # VALIDATION
    # ----------------------------

    valid_rows = []
    rejected_rows = []

    for _, row in df.iterrows():

        valid = True

        if row["student_id"] is None:
            valid = False

        if row["first_name"] is None:
            valid = False

        if row["last_name"] is None:
            valid = False

        if row["email"] is None or not is_valid_email(row["email"]):
            valid = False

        if row["phone"] is None or not is_valid_phone(row["phone"]):
            valid = False

        if row["course"] is None:
            valid = False

        if row["department"] is None:
            valid = False

        if row["enrollment_date"] is None:
            valid = False

        if row["percentage"] is not None:
            if not valid_percentage(row["percentage"]):
                valid = False

        if valid:
            valid_rows.append(tuple(row))
        else:
            rejected_rows.append(tuple(row))

    # ----------------------------
    # LOAD
    # ----------------------------

    clear_silver_table(conn, "education")

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
        "percentage"
    ]

    inserted = insert_into_silver(
        conn,
        "education",
        columns,
        valid_rows
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
        df["medical_record_number"]
        .apply(clean_text)
    )

    # ----------------------------
    # VALIDATION
    # ----------------------------

    valid_rows = []
    rejected_rows = []

    for _, row in df.iterrows():

        valid = True

        if row["patient_id"] is None:
            valid = False

        if row["first_name"] is None:
            valid = False

        if row["last_name"] is None:
            valid = False

        if row["email"] is None or not is_valid_email(row["email"]):
            valid = False

        if row["phone"] is None or not is_valid_phone(row["phone"]):
            valid = False

        if row["blood_group"] is not None:
            if not is_valid_blood_group(row["blood_group"]):
                valid = False

        if row["medical_record_number"] is None:
            valid = False

        if valid:
            valid_rows.append(tuple(row))
        else:
            rejected_rows.append(tuple(row))

    # ----------------------------
    # LOAD
    # ----------------------------

    clear_silver_table(conn, "medical")

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
        "medical_record_number"
    ]

    inserted = insert_into_silver(
        conn,
        "medical",
        columns,
        valid_rows
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

    # ----------------------------
    # VALIDATION
    # ----------------------------

    valid_rows = []
    rejected_rows = []

    for _, row in df.iterrows():

        valid = True

        if row["customer_id"] is None:
            valid = False

        if row["first_name"] is None:
            valid = False

        if row["last_name"] is None:
            valid = False

        if row["email"] is None or not is_valid_email(row["email"]):
            valid = False

        if row["phone"] is None or not is_valid_phone(row["phone"]):
            valid = False

        if row["age"] is not None:
            if not valid_age(row["age"]):
                valid = False

        if row["gender"] is not None:
            if row["gender"] not in {
                "MALE",
                "FEMALE",
                "OTHER"
            }:
                valid = False

        if row["campaign_name"] is None:
            valid = False

        if row["channel"] is None:
            valid = False

        if valid:
            valid_rows.append(tuple(row))
        else:
            rejected_rows.append(tuple(row))

    # ----------------------------
    # LOAD
    # ----------------------------

    clear_silver_table(conn, "marketing")

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
        "channel"
    ]

    inserted = insert_into_silver(
        conn,
        "marketing",
        columns,
        valid_rows
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

    conn = None

    try:

        # --------------------------------
        # CONNECT TO SUPABASE
        # --------------------------------

        conn = get_connection()

        print("\nConnected to Supabase PostgreSQL!")

        # --------------------------------
        # PROCESS ALL DOMAINS
        # --------------------------------

        results = {}

        results["banking"] = process_banking(conn)

        results["education"] = process_education(conn)

        results["medical"] = process_medical(conn)

        results["marketing"] = process_marketing(conn)

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

        if conn:
            conn.rollback()

        print("\nETL PIPELINE FAILED!")
        print("Error:")
        print(e)

    finally:

        if conn:
            conn.close()
            print("\nDatabase connection closed.")


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()