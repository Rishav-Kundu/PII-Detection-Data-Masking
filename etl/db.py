import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """
    Create and return a PostgreSQL connection
    using the DATABASE_URL stored in .env.
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL not found. Make sure it is present in your .env file."
        )

    return psycopg2.connect(database_url)


if __name__ == "__main__":
    try:
        conn = get_connection()

        print("Successfully connected to Supabase PostgreSQL!")

        conn.close()

    except Exception as e:
        print("Database connection failed:")
        print(e)