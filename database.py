import psycopg2


# =========================================================
# POSTGRESQL CONFIGURATION
# =========================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "intellihire",
    "user": "postgres",
    "password": "Tanuja@123",
}


# =========================================================
# GET DATABASE CONNECTION
# =========================================================

def get_connection():

    return psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )


# =========================================================
# TEST CONNECTION
# =========================================================

def test_connection():

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute("SELECT version();")

        result = cursor.fetchone()

        print("PostgreSQL connected successfully.")
        print(result[0])

        cursor.close()

        return True

    except Exception as e:

        print("PostgreSQL connection failed:")
        print(e)

        return False

    finally:

        if connection:
            connection.close()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    test_connection()