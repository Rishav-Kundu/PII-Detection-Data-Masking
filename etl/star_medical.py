from __future__ import annotations

from sqlalchemy import text

from etl.db import engine


def load_medical_star_schema() -> None:
    """
    Load Silver Medical data into the Medical star schema.

    Source:
        silver.medical

    Targets:
        star_medical.dim_patient
        star_medical.dim_doctor
        star_medical.dim_diagnosis
        star_medical.dim_location
        star_medical.dim_date
        star_medical.fact_admission

    Incremental behavior:
        - Existing dimension members are not duplicated.
        - Existing fact rows are not duplicated.
        - Fact rows are identified using _bronze_id.
        - Patient is required for a fact row.
        - Doctor, diagnosis, location and admission date are optional.
        - Missing optional dimensions result in NULL foreign keys
          rather than the fact row being discarded.
    """

    print()
    print("=" * 70)
    print("SILVER -> MEDICAL STAR SCHEMA")
    print("=" * 70)

    with engine.begin() as conn:

        # ====================================================
        # 1. PATIENT DIMENSION
        # ====================================================

        print()
        print("Loading dim_patient...")

        conn.execute(
            text(
                """
                INSERT INTO star_medical.dim_patient
                (
                    patient_id,
                    first_name,
                    last_name,
                    email,
                    phone,
                    date_of_birth,
                    blood_group,
                    medical_record_number
                )
                SELECT
                    s.patient_id,
                    s.first_name,
                    s.last_name,
                    s.email,
                    s.phone,
                    s.date_of_birth,
                    s.blood_group,
                    s.medical_record_number
                FROM silver.medical s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_medical.dim_patient d
                    WHERE d.patient_id = s.patient_id
                )
                """
            )
        )

        # ====================================================
        # 2. DOCTOR DIMENSION
        # ====================================================

        print("Loading dim_doctor...")

        conn.execute(
            text(
                """
                INSERT INTO star_medical.dim_doctor
                (
                    doctor_name
                )
                SELECT DISTINCT
                    s.doctor_name
                FROM silver.medical s
                WHERE s.doctor_name IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM star_medical.dim_doctor d
                      WHERE d.doctor_name = s.doctor_name
                  )
                """
            )
        )

        # ====================================================
        # 3. DIAGNOSIS DIMENSION
        # ====================================================

        print("Loading dim_diagnosis...")

        conn.execute(
            text(
                """
                INSERT INTO star_medical.dim_diagnosis
                (
                    diagnosis
                )
                SELECT DISTINCT
                    s.diagnosis
                FROM silver.medical s
                WHERE s.diagnosis IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM star_medical.dim_diagnosis d
                      WHERE d.diagnosis = s.diagnosis
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
                INSERT INTO star_medical.dim_location
                (
                    address,
                    city,
                    state
                )
                SELECT DISTINCT
                    s.address,
                    s.city,
                    s.state::text
                FROM silver.medical s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_medical.dim_location d
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
                INSERT INTO star_medical.dim_date
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
                    TO_CHAR(s.admission_date, 'YYYYMMDD')::INTEGER,
                    s.admission_date,
                    EXTRACT(DAY FROM s.admission_date)::INTEGER,
                    TRIM(TO_CHAR(s.admission_date, 'Day')),
                    EXTRACT(WEEK FROM s.admission_date)::INTEGER,
                    EXTRACT(MONTH FROM s.admission_date)::INTEGER,
                    TRIM(TO_CHAR(s.admission_date, 'Month')),
                    EXTRACT(QUARTER FROM s.admission_date)::INTEGER,
                    EXTRACT(YEAR FROM s.admission_date)::INTEGER,
                    EXTRACT(ISODOW FROM s.admission_date)::INTEGER IN (6, 7)
                FROM silver.medical s
                WHERE s.admission_date IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM star_medical.dim_date d
                      WHERE d.date_key =
                            TO_CHAR(s.admission_date, 'YYYYMMDD')::INTEGER
                  )
                """
            )
        )

        # ====================================================
        # 6. FACT TABLE
        # ====================================================

        print("Loading fact_admission...")

        conn.execute(
            text(
                """
                INSERT INTO star_medical.fact_admission
                (
                    patient_key,
                    doctor_key,
                    diagnosis_key,
                    location_key,
                    admission_date_key,
                    admission_count,
                    _bronze_id
                )
                SELECT
                    dp.patient_key,
                    dd.doctor_key,
                    dg.diagnosis_key,
                    dl.location_key,
                    ddate.date_key,
                    1,
                    s._bronze_id

                FROM silver.medical s

                -- Patient is required.
                JOIN star_medical.dim_patient dp
                    ON dp.patient_id = s.patient_id

                -- Doctor is optional.
                -- If doctor_name is NULL in Silver,
                -- doctor_key becomes NULL.
                LEFT JOIN star_medical.dim_doctor dd
                    ON dd.doctor_name = s.doctor_name

                -- Diagnosis is optional.
                -- If diagnosis is NULL in Silver,
                -- diagnosis_key becomes NULL.
                LEFT JOIN star_medical.dim_diagnosis dg
                    ON dg.diagnosis = s.diagnosis

                -- Location is optional.
                LEFT JOIN star_medical.dim_location dl
                    ON dl.address IS NOT DISTINCT FROM s.address
                   AND dl.city IS NOT DISTINCT FROM s.city
                   AND dl.state IS NOT DISTINCT FROM s.state::text

                -- Admission date is optional.
                LEFT JOIN star_medical.dim_date ddate
                    ON ddate.date_key =
                       TO_CHAR(s.admission_date, 'YYYYMMDD')::INTEGER

                -- Prevent duplicate fact rows.
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_medical.fact_admission f
                    WHERE f._bronze_id = s._bronze_id
                )
                """
            )
        )

    print()
    print("Medical star schema load completed.")


def show_medical_counts() -> None:
    """
    Display row counts from all Medical star-schema tables.
    """

    print()
    print("MEDICAL STAR SCHEMA COUNTS")
    print("-" * 40)

    tables = [
        "dim_patient",
        "dim_doctor",
        "dim_diagnosis",
        "dim_location",
        "dim_date",
        "fact_admission",
    ]

    with engine.connect() as conn:

        for table in tables:

            result = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM star_medical.{table}
                    """
                )
            )

            count = result.scalar()

            print(f"{table:<20} {count}")


if __name__ == "__main__":

    load_medical_star_schema()

    show_medical_counts()