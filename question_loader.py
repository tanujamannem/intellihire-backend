import os
import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd

from database import get_connection

# ============================================================
# CONFIGURATION
# ============================================================

ROOT_FOLDER = Path(
    r"C:\Users\Tanuja\OneDrive - Mirafra Software Technologies Pvt Ltd"
    r"\Daily_Training_Syncups - Client Interview Questions"
    r"\Client-wise Questions"
)


TABLE_NAME = "interview_questions"


# Excel sheet name -> database difficulty
VALID_SHEETS = {
    "BASIC": "basic",
    "MODERATE": "moderate",
    "ADVANCED": "advanced",
}



# ============================================================
# QUESTION HASH
# ============================================================

def generate_question_hash(
    domain,
    difficulty,
    question,
    source_client
):
    """
    Generate deterministic SHA-256 hash.

    Same client + domain + difficulty + question
    produces the same hash.
    """

    raw_value = "|".join([
        str(source_client).strip().lower(),
        str(domain).strip().lower(),
        str(difficulty).strip().lower(),
        str(question).strip().lower(),
    ])

    return hashlib.sha256(
        raw_value.encode("utf-8")
    ).hexdigest()


# ============================================================
# EXPERIENCE RANGE
# ============================================================

def get_experience_range(difficulty):

    difficulty = difficulty.lower()

    if difficulty == "basic":
        return 0, 2

    if difficulty == "moderate":
        return 2, 5

    if difficulty == "advanced":
        return 5, 15

    return None, None


# ============================================================
# EXCEL FILE READER
# ============================================================

def read_excel_file(file_path):

    questions = []

    try:

        excel_file = pd.ExcelFile(file_path)

        for sheet_name in excel_file.sheet_names:

            sheet_upper = str(sheet_name).strip().upper()

            # Only process BASIC / MODERATE / ADVANCED
            if sheet_upper not in VALID_SHEETS:

                print(
                    f"  Skipping sheet '{sheet_name}'"
                )

                continue

            difficulty = VALID_SHEETS[sheet_upper]

            print(
                f"  Reading sheet: {sheet_name}"
            )

            df = pd.read_excel(
                file_path,
                sheet_name=sheet_name,
                header=None
            )

            if df.empty:

                print(
                    f"  Sheet '{sheet_name}' is empty."
                )

                continue

            print(
                f"  Detected {len(df.columns)} column(s)"
            )

            # ------------------------------------------------
            # Minimum:
            #
            # Column A = S NO.
            # Column B = Questions
            # ------------------------------------------------

            if len(df.columns) < 2:

                print(
                    f"  Sheet '{sheet_name}' does not "
                    f"contain a question column."
                )

                continue

            # ------------------------------------------------
            # Read rows
            # ------------------------------------------------

            for row_number, row in df.iterrows():

                # Skip first row because it is the header
                if row_number == 0:
                    continue

                # ------------------------------------------------
                # Column B = question
                # ------------------------------------------------

                question = row.iloc[1]

                if pd.isna(question):
                    continue

                question = str(question).strip()

                if not question:
                    continue

                # ------------------------------------------------
                # Column C = answer, if available
                # ------------------------------------------------

                answer = None

                if len(df.columns) >= 3:

                    answer_value = row.iloc[2]

                    if not pd.isna(answer_value):

                        answer = str(
                            answer_value
                        ).strip()

                        if not answer:
                            answer = None

                questions.append({

                    "difficulty": difficulty,

                    "question": question,

                    "answer": answer,

                    "source_sheet": str(
                        sheet_name
                    ).strip(),

                    "row_number": row_number + 1,
                })

    except Exception as e:

        print(
            f"  ERROR reading file: {e}"
        )

    return questions


# ============================================================
# DOMAIN + CLIENT EXTRACTION
# ============================================================

def get_domain_and_client(file_path):
    """
    Determine client and domain from the Excel file location.

    Supported structures:

    1. CLIENT / DOMAIN / FILE.xlsx
       Example:
           Analog Device/
               STA/
                   questions.xlsx

    2. CLIENT / FILE.xlsx
       Example:
           ARM/
               ARM_PV_Combined Questions.xlsx

           Microsoft/
               Microsoft_PD & CAD_Combined questions.xlsx
    """

    relative_path = file_path.relative_to(ROOT_FOLDER)
    parts = relative_path.parts

    # ========================================================
    # STRUCTURE 1
    #
    # CLIENT / DOMAIN / FILE
    # ========================================================

    if len(parts) >= 3:

        source_client = parts[0].strip()
        domain = parts[1].strip()

        return domain, source_client

    # ========================================================
    # STRUCTURE 2
    #
    # CLIENT / FILE
    # ========================================================

    if len(parts) == 2:

        source_client = parts[0].strip()
        filename = file_path.stem.strip()

        # Remove client name from beginning
        prefix = source_client + "_"

        if filename.lower().startswith(prefix.lower()):

            domain_part = filename[len(prefix):]

        else:

            domain_part = filename

        # Remove known suffixes
        suffixes = [
            "_Combined Questions",
            "_Combined questions",
            "_Interview Questions",
            "_Interview questions",
            "_Questions",
            "_questions",
        ]

        for suffix in suffixes:

            if domain_part.endswith(suffix):

                domain_part = domain_part[:-len(suffix)]

                break

        domain = domain_part.strip(" _-")

        if not domain:

            raise ValueError(
                f"Could not determine domain from filename: "
                f"{file_path.name}"
            )

        return domain, source_client

    # ========================================================
    # INVALID STRUCTURE
    # ========================================================

    raise ValueError(
        f"Unexpected folder structure: {file_path}"
    )


# ============================================================
# CHECK IF QUESTION ALREADY EXISTS
# ============================================================

def question_exists(cursor, question_hash):

    query = f"""
        SELECT id
        FROM {TABLE_NAME}
        WHERE question_hash = %s
    """

    cursor.execute(
        query,
        (question_hash,)
    )

    result = cursor.fetchone()

    return result is not None


# ============================================================
# INSERT / UPDATE QUESTION
# ============================================================

def upsert_question(
    cursor,
    question_data
):
    """
    Insert a new question or update an existing question.

    Returns:
        "inserted"
        "updated"
    """

    exists = question_exists(
        cursor,
        question_data["question_hash"]
    )

    if exists:

        query = f"""
            UPDATE {TABLE_NAME}
            SET
                domain = %s,
                difficulty = %s,
                experience_min = %s,
                experience_max = %s,
                question = %s,
                answer = %s,
                source_client = %s,
                source_file = %s,
                source_sheet = %s,
                updated_at = CURRENT_TIMESTAMP,
                is_active = TRUE
            WHERE question_hash = %s
        """

        cursor.execute(
            query,
            (
                question_data["domain"],
                question_data["difficulty"],
                question_data["experience_min"],
                question_data["experience_max"],
                question_data["question"],
                question_data["answer"],
                question_data["source_client"],
                question_data["source_file"],
                question_data["source_sheet"],
                question_data["question_hash"],
            )
        )

        return "updated"

    else:

        query = f"""
            INSERT INTO {TABLE_NAME} (
                domain,
                difficulty,
                experience_min,
                experience_max,
                question,
                answer,
                source_client,
                source_file,
                source_sheet,
                created_at,
                updated_at,
                question_hash,
                is_active
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                %s,
                TRUE
            )
        """

        cursor.execute(
            query,
            (
                question_data["domain"],
                question_data["difficulty"],
                question_data["experience_min"],
                question_data["experience_max"],
                question_data["question"],
                question_data["answer"],
                question_data["source_client"],
                question_data["source_file"],
                question_data["source_sheet"],
                question_data["question_hash"],
            )
        )

        return "inserted"


# ============================================================
# MAIN LOADER
# ============================================================

def load_questions():

    print("=" * 70)
    print("Excel → PostgreSQL Question Loader")
    print("=" * 70)

    print("\nRoot folder:")
    print(ROOT_FOLDER)

    # --------------------------------------------------------
    # Validate root folder
    # --------------------------------------------------------

    if not ROOT_FOLDER.exists():

        print(
            "\nERROR: Root folder does not exist."
        )

        return

    # --------------------------------------------------------
    # Find Excel files
    # --------------------------------------------------------

    excel_files = []

    excel_files.extend(
        ROOT_FOLDER.rglob("*.xlsx")
    )

    excel_files.extend(
        ROOT_FOLDER.rglob("*.xls")
    )

    print(
        f"\nFound {len(excel_files)} Excel file(s)."
    )

    if not excel_files:

        print(
            "No Excel files found."
        )

        return

    # --------------------------------------------------------
    # Connect
    # --------------------------------------------------------

    connection = None
    cursor = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        print(
            "\nPostgreSQL connected successfully."
        )

    except Exception as e:

        print(
            f"\nERROR connecting to PostgreSQL: {e}"
        )

        return

    # ========================================================
    # STATISTICS
    # ========================================================

    total_files = 0

    total_questions_read = 0

    total_inserted = 0

    total_updated = 0

    total_errors = 0

    failed_rows = []

    # ========================================================
    # PROCESS FILES
    # ========================================================

    try:

        for file_path in excel_files:

            total_files += 1

            print("\n" + "-" * 70)

            print(
                f"Processing: {file_path}"
            )

            try:

                # ------------------------------------------------
                # Get client/domain
                # ------------------------------------------------

                domain, source_client = (
                    get_domain_and_client(
                        file_path
                    )
                )

                print(
                    f"Client : {source_client}"
                )

                print(
                    f"Domain : {domain}"
                )

                # ------------------------------------------------
                # Read Excel
                # ------------------------------------------------

                questions = read_excel_file(
                    file_path
                )

                print(
                    f"Questions found: {len(questions)}"
                )

                # ------------------------------------------------
                # Process each question
                # ------------------------------------------------

                for question in questions:

                    total_questions_read += 1

                    difficulty = (
                        question["difficulty"]
                    )

                    experience_min, experience_max = (
                        get_experience_range(
                            difficulty
                        )
                    )

                    question_hash = (
                        generate_question_hash(
                            domain=domain,
                            difficulty=difficulty,
                            question=question["question"],
                            source_client=source_client,
                        )
                    )

                    question_data = {

                        "domain": domain,

                        "difficulty": difficulty,

                        "experience_min":
                            experience_min,

                        "experience_max":
                            experience_max,

                        "question":
                            question["question"],

                        "answer":
                            question["answer"],

                        "source_client":
                            source_client,

                        "source_file":
                            file_path.name,

                        "source_sheet":
                            question["source_sheet"],

                        "question_hash":
                            question_hash,
                    }

                    # ------------------------------------------------
                    # SAVEPOINT
                    #
                    # If this question fails, only this question
                    # is rolled back.
                    # ------------------------------------------------

                    savepoint_name = (
                        "question_savepoint"
                    )

                    try:

                        cursor.execute(
                            f"SAVEPOINT {savepoint_name}"
                        )

                        result = upsert_question(
                            cursor,
                            question_data
                        )

                        cursor.execute(
                            f"RELEASE SAVEPOINT {savepoint_name}"
                        )

                        if result == "inserted":

                            total_inserted += 1

                        elif result == "updated":

                            total_updated += 1

                    except Exception as e:

                        total_errors += 1

                        try:

                            cursor.execute(
                                f"ROLLBACK TO SAVEPOINT {savepoint_name}"
                            )

                            cursor.execute(
                                f"RELEASE SAVEPOINT {savepoint_name}"
                            )

                        except Exception:
                            pass

                        failed_rows.append({

                            "file":
                                str(file_path),

                            "client":
                                source_client,

                            "domain":
                                domain,

                            "sheet":
                                question["source_sheet"],

                            "row":
                                question["row_number"],

                            "question":
                                question["question"],

                            "error":
                                str(e),
                        })

                        print(
                            f"  ERROR inserting row "
                            f"{question['row_number']}: {e}"
                        )

                # ------------------------------------------------
                # Commit entire successfully processed file
                # ------------------------------------------------

                connection.commit()

                print(
                    "  File committed successfully."
                )

            except Exception as e:

                total_errors += 1
            
                error_message = str(e)
            
                print(
                    f"ERROR processing file: {e}"
                )
            
                failed_rows.append({
                    "file": str(file_path),
                    "client": source_client if "source_client" in locals() else "UNKNOWN",
                    "domain": domain if "domain" in locals() else "UNKNOWN",
                    "sheet": "FILE LEVEL",
                    "row": "-",
                    "question": "-",
                    "error": error_message,
                })
            
                connection.rollback()

    except Exception as e:

        print(
            f"\nFATAL ERROR: {e}"
        )

        connection.rollback()

    finally:

        if cursor:

            cursor.close()

        if connection:

            connection.close()

    # ========================================================
    # FINAL REPORT
    # ========================================================

    print("\n")

    print("=" * 70)

    print("IMPORT COMPLETE")

    print("=" * 70)

    print(
        f"Excel files processed : {total_files}"
    )

    print(
        f"Questions read        : {total_questions_read}"
    )

    print(
        f"New questions inserted: {total_inserted}"
    )

    print(
        f"Existing updated      : {total_updated}"
    )

    print(
        f"Errors                : {total_errors}"
    )

    print("=" * 70)

    # ========================================================
    # FAILED ROW DETAILS
    # ========================================================

    if failed_rows:

        print("\n")

        print("=" * 70)

        print("FAILED ROWS")

        print("=" * 70)

        for index, failure in enumerate(
            failed_rows,
            start=1
        ):

            print(f"\nFailure #{index}")

            print(
                f"Client   : {failure['client']}"
            )

            print(
                f"Domain   : {failure['domain']}"
            )

            print(
                f"File     : {failure['file']}"
            )

            print(
                f"Sheet    : {failure['sheet']}"
            )

            print(
                f"Row      : {failure['row']}"
            )

            print(
                f"Question : {failure['question']}"
            )

            print(
                f"Error    : {failure['error']}"
            )

        print("\n" + "=" * 70)

    else:

        if total_errors == 0:

            print(
                "\nNo errors. Import completed successfully."
            )
    
        else:
    
            print(
                f"\nWARNING: {total_errors} error(s) occurred, "
                "but no failure details were captured."
            )
    
        print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    load_questions()