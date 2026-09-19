from __future__ import annotations

from sqlalchemy import text

from etl.db import engine


def load_marketing_star_schema() -> None:
    """
    Load Silver Marketing data into the Marketing star schema.

    Source:
        silver.marketing

    Targets:
        star_marketing.dim_customer
        star_marketing.dim_campaign
        star_marketing.dim_channel
        star_marketing.dim_location
        star_marketing.dim_date
        star_marketing.fact_campaign

    Incremental behavior:
        - Existing dimension members are not duplicated.
        - Existing fact rows are not duplicated.
        - Fact rows are identified using _bronze_id.
        - Customer is required for a fact row.
        - Campaign, channel, location and campaign date are optional.
        - Missing optional dimensions result in NULL foreign keys
          rather than the fact row being discarded.
    """

    print()
    print("=" * 70)
    print("SILVER -> MARKETING STAR SCHEMA")
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
                INSERT INTO star_marketing.dim_customer
                (
                    customer_id,
                    first_name,
                    last_name,
                    email,
                    phone,
                    age,
                    gender
                )
                SELECT
                    s.customer_id,
                    s.first_name,
                    s.last_name,
                    s.email,
                    s.phone,
                    s.age,
                    s.gender
                FROM silver.marketing s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_marketing.dim_customer d
                    WHERE d.customer_id = s.customer_id
                )
                """
            )
        )

        # ====================================================
        # 2. CAMPAIGN DIMENSION
        # ====================================================

        print("Loading dim_campaign...")

        conn.execute(
            text(
                """
                INSERT INTO star_marketing.dim_campaign
                (
                    campaign_name
                )
                SELECT DISTINCT
                    s.campaign_name
                FROM silver.marketing s
                WHERE s.campaign_name IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM star_marketing.dim_campaign d
                      WHERE d.campaign_name = s.campaign_name
                  )
                """
            )
        )

        # ====================================================
        # 3. CHANNEL DIMENSION
        # ====================================================

        print("Loading dim_channel...")

        conn.execute(
            text(
                """
                INSERT INTO star_marketing.dim_channel
                (
                    channel
                )
                SELECT DISTINCT
                    s.channel
                FROM silver.marketing s
                WHERE s.channel IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM star_marketing.dim_channel d
                      WHERE d.channel = s.channel
                  )
                """
            )
        )

        # ====================================================
        # 4. LOCATION DIMENSION
        # ====================================================

        print("Loading dim_location...")

        conn.execute(
            text(
                """
                INSERT INTO star_marketing.dim_location
                (
                    address,
                    city,
                    state
                )
                SELECT DISTINCT
                    s.address,
                    s.city,
                    s.state::text
                FROM silver.marketing s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_marketing.dim_location d
                    WHERE d.address IS NOT DISTINCT FROM s.address
                      AND d.city IS NOT DISTINCT FROM s.city
                      AND d.state IS NOT DISTINCT FROM s.state::text
                )
                """
            )
        )

        # ====================================================
        # 5. DATE DIMENSION
        # ====================================================

        print("Loading dim_date...")

        conn.execute(
            text(
                """
                INSERT INTO star_marketing.dim_date
                (
                    date_key,
                    full_date,
                    day,
                    day_name,
                    week,
                    month,
                    month_name,
                    quarter,
                    year,
                    is_weekend
                )
                SELECT DISTINCT
                    TO_CHAR(s.campaign_date, 'YYYYMMDD')::INTEGER,
                    s.campaign_date,
                    EXTRACT(DAY FROM s.campaign_date)::INTEGER,
                    TRIM(TO_CHAR(s.campaign_date, 'Day')),
                    EXTRACT(WEEK FROM s.campaign_date)::INTEGER,
                    EXTRACT(MONTH FROM s.campaign_date)::INTEGER,
                    TRIM(TO_CHAR(s.campaign_date, 'Month')),
                    EXTRACT(QUARTER FROM s.campaign_date)::INTEGER,
                    EXTRACT(YEAR FROM s.campaign_date)::INTEGER,
                    EXTRACT(ISODOW FROM s.campaign_date)::INTEGER IN (6, 7)
                FROM silver.marketing s
                WHERE s.campaign_date IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM star_marketing.dim_date d
                      WHERE d.date_key =
                            TO_CHAR(s.campaign_date, 'YYYYMMDD')::INTEGER
                  )
                """
            )
        )

        # ====================================================
        # 6. FACT TABLE
        # ====================================================

        print("Loading fact_campaign...")

        conn.execute(
            text(
                """
                INSERT INTO star_marketing.fact_campaign
                (
                    customer_key,
                    campaign_key,
                    channel_key,
                    location_key,
                    campaign_date_key,
                    campaign_count,
                    _bronze_id
                )
                SELECT
                    dcust.customer_key,
                    dcamp.campaign_key,
                    dchan.channel_key,
                    dloc.location_key,
                    ddate.date_key,
                    1,
                    s._bronze_id

                FROM silver.marketing s

                -- Customer is required.
                JOIN star_marketing.dim_customer dcust
                    ON dcust.customer_id = s.customer_id

                -- Campaign is optional.
                -- If campaign_name is NULL in Silver,
                -- campaign_key becomes NULL.
                LEFT JOIN star_marketing.dim_campaign dcamp
                    ON dcamp.campaign_name = s.campaign_name

                -- Channel is optional.
                -- If channel is NULL in Silver,
                -- channel_key becomes NULL.
                LEFT JOIN star_marketing.dim_channel dchan
                    ON dchan.channel = s.channel

                -- Location is optional.
                LEFT JOIN star_marketing.dim_location dloc
                    ON dloc.address IS NOT DISTINCT FROM s.address
                   AND dloc.city IS NOT DISTINCT FROM s.city
                   AND dloc.state IS NOT DISTINCT FROM s.state::text

                -- Campaign date is optional.
                LEFT JOIN star_marketing.dim_date ddate
                    ON ddate.date_key =
                       TO_CHAR(s.campaign_date, 'YYYYMMDD')::INTEGER

                -- Prevent duplicate fact rows.
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_marketing.fact_campaign f
                    WHERE f._bronze_id = s._bronze_id
                )
                """
            )
        )

    print()
    print("Marketing star schema load completed.")


def show_marketing_counts() -> None:
    """
    Display row counts from all Marketing star-schema tables.
    """

    print()
    print("MARKETING STAR SCHEMA COUNTS")
    print("-" * 40)

    tables = [
        "dim_customer",
        "dim_campaign",
        "dim_channel",
        "dim_location",
        "dim_date",
        "fact_campaign",
    ]

    with engine.connect() as conn:

        for table in tables:

            result = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM star_marketing.{table}
                    """
                )
            )

            count = result.scalar()

            print(f"{table:<20} {count}")


if __name__ == "__main__":

    load_marketing_star_schema()

    show_marketing_counts()