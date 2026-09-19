from __future__ import annotations

from sqlalchemy import text

from etl.db import engine


def load_banking_star_schema() -> None:
    """
    Load Silver Banking data into the Banking star schema.

    Source:
        silver.banking

    Targets:
        star_banking.dim_customer
        star_banking.dim_account
        star_banking.dim_location
        star_banking.fact_account

    Incremental behavior:
        - Existing dimension members are not duplicated.
        - Existing fact rows are not duplicated.
        - Fact rows are identified using _bronze_id.
        - Missing optional account/location information does NOT
          prevent a fact row from being inserted.
        - If an optional dimension member does not exist, the
          corresponding foreign key in the fact table is NULL.
    """

    print()
    print("=" * 70)
    print("SILVER -> BANKING STAR SCHEMA")
    print("=" * 70)

    with engine.begin() as conn:

        # ====================================================
        # 1. CUSTOMER DIMENSION
        # ====================================================

        print()
        print("Loading dim_customer...")

        conn.execute(
            text(
                """
                INSERT INTO star_banking.dim_customer
                (
                    customer_id,
                    first_name,
                    last_name,
                    email,
                    phone,
                    date_of_birth
                )
                SELECT DISTINCT
                    s.customer_id,
                    s.first_name,
                    s.last_name,
                    s.email,
                    s.phone,
                    s.date_of_birth
                FROM silver.banking s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_banking.dim_customer d
                    WHERE d.customer_id = s.customer_id
                )
                """
            )
        )

        # ====================================================
        # 2. ACCOUNT DIMENSION
        # ====================================================

        print("Loading dim_account...")

        conn.execute(
            text(
                """
                INSERT INTO star_banking.dim_account
                (
                    account_number,
                    account_type
                )
                SELECT DISTINCT
                    s.account_number,
                    s.account_type
                FROM silver.banking s
                WHERE s.account_number IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1
                    FROM star_banking.dim_account d
                    WHERE d.account_number = s.account_number
                )
                """
            )
        )

        # ====================================================
        # 3. LOCATION DIMENSION
        # ====================================================

        print("Loading dim_location...")

        conn.execute(
            text(
                """
                INSERT INTO star_banking.dim_location
                (
                    address,
                    city,
                    state
                )
                SELECT DISTINCT
                    s.address,
                    s.city,
                    s.state::text
                FROM silver.banking s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_banking.dim_location d
                    WHERE d.address IS NOT DISTINCT FROM s.address
                      AND d.city IS NOT DISTINCT FROM s.city
                      AND d.state IS NOT DISTINCT FROM s.state::text
                )
                """
            )
        )

        # ====================================================
        # 4. FACT TABLE
        # ====================================================

        print("Loading fact_account...")

        conn.execute(
            text(
                """
                INSERT INTO star_banking.fact_account
                (
                    customer_key,
                    account_key,
                    location_key,
                    balance,
                    _bronze_id
                )
                SELECT
                    c.customer_key,
                    a.account_key,
                    l.location_key,
                    s.balance,
                    s._bronze_id
                FROM silver.banking s

                -- Customer is required.
                JOIN star_banking.dim_customer c
                    ON c.customer_id = s.customer_id

                -- Account is optional.
                -- If the Silver account information is missing,
                -- account_key becomes NULL instead of losing the fact row.
                LEFT JOIN star_banking.dim_account a
                    ON a.account_number IS NOT DISTINCT FROM s.account_number
                   AND a.account_type IS NOT DISTINCT FROM s.account_type

                -- Location is optional.
                LEFT JOIN star_banking.dim_location l
                    ON l.address IS NOT DISTINCT FROM s.address
                   AND l.city IS NOT DISTINCT FROM s.city
                   AND l.state IS NOT DISTINCT FROM s.state::text

                -- Prevent the same Bronze record from being loaded
                -- into the fact table more than once.
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_banking.fact_account f
                    WHERE f._bronze_id = s._bronze_id
                )
                """
            )
        )

    print()
    print("Banking star schema load completed.")


def show_banking_counts() -> None:
    """
    Display row counts from all Banking star-schema tables.
    """

    with engine.connect() as conn:

        tables = [
            "dim_customer",
            "dim_account",
            "dim_location",
            "fact_account",
        ]

        print()
        print("BANKING STAR SCHEMA COUNTS")
        print("-" * 40)

        for table in tables:

            result = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM star_banking.{table}
                    """
                )
            )

            count = result.scalar()

            print(
                f"{table:<20} {count}"
            )


if __name__ == "__main__":

    load_banking_star_schema()

    show_banking_counts()