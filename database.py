import os
import psycopg2
from dotenv import load_dotenv

# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


# =========================================================
# GET DATABASE CONNECTION
# =========================================================

def get_connection():

    if not DATABASE_URL:
        raise ValueError(
            "DATABASE_URL is not configured."
        )

    return psycopg2.connect(
        DATABASE_URL
    )


# =========================================================
# TEST DATABASE CONNECTION
# =========================================================

def test_connection():

    connection = None
    cursor = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        print("PostgreSQL connected successfully.")

        # =================================================
        # CHECK DATABASE / USER / SCHEMA
        # =================================================

        cursor.execute("""
            SELECT
                current_database(),
                current_user,
                current_schema();
        """)

        result = cursor.fetchone()

        print()
        print("Database :", result[0])
        print("User     :", result[1])
        print("Schema   :", result[2])

        # =================================================
        # CHECK interview_questions TABLE
        # =================================================

        cursor.execute("""
            SELECT
                table_schema,
                table_name
            FROM information_schema.tables
            WHERE table_name = 'interview_questions';
        """)

        tables = cursor.fetchall()

        print()
        print("Checking interview_questions table...")

        if tables:

            print("interview_questions table found:")

            for table in tables:

                print(
                    f"  Schema: {table[0]} | "
                    f"Table: {table[1]}"
                )

        else:

            print(
                "WARNING: interview_questions table "
                "was NOT found."
            )

        # =================================================
        # CHECK QUESTION COUNT
        # =================================================

        if tables:

            cursor.execute("""
                SELECT COUNT(*)
                FROM public.interview_questions;
            """)

            count = cursor.fetchone()[0]

            print()
            print(
                "Questions currently in database:",
                count
            )

        # =================================================
        # SHOW TABLES IN PUBLIC SCHEMA
        # =================================================

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)

        public_tables = cursor.fetchall()

        print()
        print("Tables in public schema:")

        if public_tables:

            for table in public_tables:

                print(f"  - {table[0]}")

        else:

            print("  No tables found.")

        print()
        print("Database test completed successfully.")

        return True

    except Exception as e:

        print()
        print("PostgreSQL connection/test failed:")
        print(e)

        return False

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    test_connection()