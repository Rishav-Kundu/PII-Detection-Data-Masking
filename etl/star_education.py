from __future__ import annotations

from sqlalchemy import text

from etl.db import engine


def load_education_star_schema() -> None:
    """
    Load Silver Education data into the Education star schema.

    Source:
        silver.education

    Targets:
        star_education.dim_student
        star_education.dim_course
        star_education.dim_department
        star_education.dim_location
        star_education.dim_date
        star_education.fact_enrollment

    Incremental behavior:
        - Existing dimension members are not duplicated.
        - Existing fact rows are not duplicated.
        - Fact rows are identified using _bronze_id.
        - Student is required for a fact row.
        - Course, department, location and enrollment date are optional.
        - Missing optional dimensions result in NULL foreign keys
          rather than the fact row being discarded.
    """

    print()
    print("=" * 70)
    print("SILVER -> EDUCATION STAR SCHEMA")
    print("=" * 70)

    with engine.begin() as conn:

        # ====================================================
        # 1. STUDENT DIMENSION
        # ====================================================

        print()
        print("Loading dim_student...")

        conn.execute(
            text(
                """
                INSERT INTO star_education.dim_student
                (
                    student_id,
                    first_name,
                    last_name,
                    email,
                    phone,
                    date_of_birth
                )
                SELECT
                    s.student_id,
                    s.first_name,
                    s.last_name,
                    s.email,
                    s.phone,
                    s.date_of_birth
                FROM silver.education s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_education.dim_student d
                    WHERE d.student_id = s.student_id
                )
                """
            )
        )

        # ====================================================
        # 2. COURSE DIMENSION
        # ====================================================

        print("Loading dim_course...")

        conn.execute(
            text(
                """
                INSERT INTO star_education.dim_course
                (
                    course
                )
                SELECT DISTINCT
                    s.course
                FROM silver.education s
                WHERE s.course IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM star_education.dim_course d
                      WHERE d.course = s.course
                  )
                """
            )
        )

        # ====================================================
        # 3. DEPARTMENT DIMENSION
        # ====================================================

        print("Loading dim_department...")

        conn.execute(
            text(
                """
                INSERT INTO star_education.dim_department
                (
                    department
                )
                SELECT DISTINCT
                    s.department
                FROM silver.education s
                WHERE s.department IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM star_education.dim_department d
                      WHERE d.department = s.department
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
                INSERT INTO star_education.dim_location
                (
                    address,
                    city,
                    state
                )
                SELECT DISTINCT
                    s.address,
                    s.city,
                    s.state::text
                FROM silver.education s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_education.dim_location d
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
                INSERT INTO star_education.dim_date
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
                    TO_CHAR(s.enrollment_date, 'YYYYMMDD')::INTEGER,
                    s.enrollment_date,
                    EXTRACT(DAY FROM s.enrollment_date)::INTEGER,
                    TRIM(TO_CHAR(s.enrollment_date, 'Day')),
                    EXTRACT(WEEK FROM s.enrollment_date)::INTEGER,
                    EXTRACT(MONTH FROM s.enrollment_date)::INTEGER,
                    TRIM(TO_CHAR(s.enrollment_date, 'Month')),
                    EXTRACT(QUARTER FROM s.enrollment_date)::INTEGER,
                    EXTRACT(YEAR FROM s.enrollment_date)::INTEGER,
                    EXTRACT(ISODOW FROM s.enrollment_date)::INTEGER IN (6, 7)
                FROM silver.education s
                WHERE s.enrollment_date IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM star_education.dim_date d
                      WHERE d.date_key =
                            TO_CHAR(s.enrollment_date, 'YYYYMMDD')::INTEGER
                  )
                """
            )
        )

        # ====================================================
        # 6. FACT TABLE
        # ====================================================

        print("Loading fact_enrollment...")

        conn.execute(
            text(
                """
                INSERT INTO star_education.fact_enrollment
                (
                    student_key,
                    course_key,
                    department_key,
                    location_key,
                    enrollment_date_key,
                    percentage,
                    _bronze_id
                )
                SELECT
                    ds.student_key,
                    dc.course_key,
                    dd.department_key,
                    dl.location_key,
                    ddate.date_key,
                    s.percentage,
                    s._bronze_id

                FROM silver.education s

                -- Student is required.
                JOIN star_education.dim_student ds
                    ON ds.student_id = s.student_id

                -- Course is optional.
                -- If course is NULL in Silver, course_key becomes NULL.
                LEFT JOIN star_education.dim_course dc
                    ON dc.course = s.course

                -- Department is optional.
                -- If department is NULL in Silver,
                -- department_key becomes NULL.
                LEFT JOIN star_education.dim_department dd
                    ON dd.department = s.department

                -- Location is optional.
                LEFT JOIN star_education.dim_location dl
                    ON dl.address IS NOT DISTINCT FROM s.address
                   AND dl.city IS NOT DISTINCT FROM s.city
                   AND dl.state IS NOT DISTINCT FROM s.state::text

                -- Enrollment date is optional.
                LEFT JOIN star_education.dim_date ddate
                    ON ddate.date_key =
                       TO_CHAR(s.enrollment_date, 'YYYYMMDD')::INTEGER

                -- Prevent duplicate fact rows.
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM star_education.fact_enrollment f
                    WHERE f._bronze_id = s._bronze_id
                )
                """
            )
        )

    print()
    print("Education star schema load completed.")


def show_education_counts() -> None:
    """
    Display row counts from all Education star-schema tables.
    """

    print()
    print("EDUCATION STAR SCHEMA COUNTS")
    print("-" * 40)

    tables = [
        "dim_student",
        "dim_course",
        "dim_department",
        "dim_location",
        "dim_date",
        "fact_enrollment",
    ]

    with engine.connect() as conn:

        for table in tables:

            result = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM star_education.{table}
                    """
                )
            )

            count = result.scalar()

            print(f"{table:<20} {count}")


if __name__ == "__main__":

    load_education_star_schema()

    show_education_counts()