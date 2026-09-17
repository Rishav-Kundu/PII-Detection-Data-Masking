import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL not found. Make sure it is present in your .env file."
    )

# SQLAlchemy engine manages PostgreSQL connections and connection pooling.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


def get_connection():
    """
    Return a SQLAlchemy database connection.

    The caller is responsible for closing the connection.
    """
    return engine.connect()


if __name__ == "__main__":
    try:
        with engine.connect() as conn:
            print("Successfully connected to Supabase PostgreSQL!")
    except Exception as e:
        print("Database connection failed:")
        print(e)