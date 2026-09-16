from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Query
)
import json
from fastapi.middleware.cors import CORSMiddleware
import pymupdf
import re
import datetime
import time
from docx import Document
from database import get_connection
from llm import (
    generate_interview_questions,
    evaluate_answer,
    generate_interview_report,
    process_answer_with_ai,
    extract_candidate_details
)

# =========================================================
# AUDIO SERVICE
# =========================================================

from audio_service import (
    start_audio,
    stop_audio,
    get_transcript,
    add_audio_chunk
)


app = FastAPI(title="IntelliHire API")


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {
        "message": "IntelliHire API is running"
    }


# =========================================================
# EXTRACT TEXT FROM PDF
# =========================================================

def extract_pdf_text(file_bytes: bytes) -> str:

    try:

        pdf = pymupdf.open(
            stream=file_bytes,
            filetype="pdf"
        )

        text = ""

        for page in pdf:
            text += page.get_text() + "\n"

        pdf.close()

        return text.strip()

    except Exception as e:

        raise Exception(
            f"Could not extract PDF text: {str(e)}"
        )






# =========================================================
# CLEAN TEXT
# =========================================================

def clean_line(line: str) -> str:

    return re.sub(
        r"\s+",
        " ",
        line.strip()
    )


# =========================================================
# GET NON-EMPTY LINES
# =========================================================

def get_lines(text: str):

    return [
        clean_line(line)
        for line in text.splitlines()
        if clean_line(line)
    ]


# =========================================================
# EXTRACT TEXT FROM DOCX
# =========================================================

def extract_docx_text(file_bytes: bytes) -> str:

    try:

        from io import BytesIO

        document = Document(
            BytesIO(file_bytes)
        )

        text_lines = []

        # -------------------------------------------------
        # Extract normal paragraphs
        # -------------------------------------------------

        for paragraph in document.paragraphs:

            text = paragraph.text.strip()

            if text:
                text_lines.append(text)

        # -------------------------------------------------
        # Extract tables
        # -------------------------------------------------

        for table in document.tables:

            for row in table.rows:

                row_text = []

                for cell in row.cells:

                    cell_text = cell.text.strip()

                    if cell_text:
                        row_text.append(cell_text)

                if row_text:

                    text_lines.append(
                        " | ".join(row_text)
                    )

        return "\n".join(text_lines).strip()

    except Exception as e:

        raise Exception(
            f"Could not extract DOCX text: {str(e)}"
        )


# =========================================================
# EMAIL
# =========================================================

def extract_email(text: str) -> str:

    match = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text
    )

    if match:
        return match.group(0)

    return ""


# =========================================================
# PHONE
# =========================================================

def extract_phone(text: str) -> str:

    patterns = [

        r"\+91[\s\-]?\d{5}[\s\-]?\d{5}",

        r"\+91[\s\-]?\d{10}",

        r"\b\d{5}[\s\-]\d{5}\b",

        r"\b\d{10}\b",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            return match.group(0).strip()

    return ""


# =========================================================
# NAME
# =========================================================

# ---------------------------------------------------------
# NAME
# ---------------------------------------------------------

def extract_name(text: str) -> str:
    """
    Extract candidate name from resume.

    Priority:
    1. Explicit Name / Full Name label
    2. First meaningful line near the top of resume
    3. Derive name from email address
    """

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # -----------------------------------------------------
    # A. Explicit name label
    # -----------------------------------------------------

    for line in lines[:20]:

        match = re.match(
            r"^(?:name|full\s*name)\s*[:\-]\s*(.+)$",
            line,
            re.IGNORECASE
        )

        if match:

            value = match.group(1).strip()

            if is_possible_person_name(value):
                return format_person_name(value)

    # -----------------------------------------------------
    # B. Look at first few lines of resume
    # -----------------------------------------------------

    ignored_words = {
        "resume",
        "curriculum",
        "vitae",
        "cv",
        "profile",
        "summary",
        "objective",
        "skills",
        "experience",
        "education",
        "certifications",
        "bangalore",
        "india",
        "hyderabad",
        "chennai",
        "mumbai",
        "delhi",
        "pune",
        "karnataka",
        "telangana",
        "tamil",
        "nadu",
    }

    for line in lines[:15]:

        # Don't use email as name
        if "@" in line:
            continue

        # Don't use phone numbers
        if re.search(r"\d{5,}", line):
            continue

        # Remove URLs
        if re.search(r"(https?://|www\.|github\.com|linkedin\.com)",
                     line,
                     re.IGNORECASE):
            continue

        lower = line.lower()

        # Ignore obvious headings/location/contact lines
        if any(word in lower for word in ignored_words):
            continue

        if is_possible_person_name(line):
            return format_person_name(line)

    # -----------------------------------------------------
    # C. FALLBACK: derive name from email
    # -----------------------------------------------------

    email = extract_email(text)

    if email:

        email_name = email.split("@")[0]

        # Remove numbers
        email_name = re.sub(r"\d+", "", email_name)

        # Replace separators
        email_name = re.sub(
            r"[._\-]+",
            " ",
            email_name
        )

        email_name = email_name.strip()

        if email_name:

            return format_person_name(email_name)

    return ""


# ---------------------------------------------------------
# CHECK WHETHER TEXT LOOKS LIKE A PERSON NAME
# ---------------------------------------------------------

def is_possible_person_name(value: str) -> bool:

    value = value.strip()

    # Too short
    if len(value) < 3:
        return False

    # Too long
    if len(value) > 60:
        return False

    # Must not contain email
    if "@" in value:
        return False

    # Must not contain URL
    if re.search(
        r"(https?://|www\.|github\.com|linkedin\.com)",
        value,
        re.IGNORECASE
    ):
        return False

    # Must not contain lots of numbers
    if re.search(r"\d", value):
        return False

    # Reject common resume/contact/location words
    rejected_words = [
        "bangalore",
        "bengaluru",
        "india",
        "hyderabad",
        "chennai",
        "mumbai",
        "delhi",
        "pune",
        "karnataka",
        "telangana",
        "tamil",
        "nadu",
        "resume",
        "curriculum",
        "vitae",
        "profile",
        "summary",
        "objective",
        "skills",
        "experience",
        "education",
        "certification",
        "phone",
        "email",
        "linkedin",
        "github",
    ]

    lower_value = value.lower()

    if any(
        word in lower_value
        for word in rejected_words
    ):
        return False

    # Names normally contain 2-5 words
    words = value.split()

    if len(words) < 2 or len(words) > 5:
        return False

    # Only alphabetic characters, spaces, apostrophes and dots
    if not re.match(
        r"^[A-Za-z][A-Za-z .'\-]*$",
        value
    ):
        return False

    return True


# ---------------------------------------------------------
# FORMAT PERSON NAME
# ---------------------------------------------------------

def format_person_name(value: str) -> str:

    words = value.split()

    return " ".join(
        word.capitalize()
        for word in words
    )


# =========================================================
# EXPERIENCE DATE HELPERS
# =========================================================

MONTH_PATTERN = (
    r"(?:"
    r"Jan(?:uary)?|"
    r"Feb(?:ruary)?|"
    r"Mar(?:ch)?|"
    r"Apr(?:il)?|"
    r"May|"
    r"Jun(?:e)?|"
    r"Jul(?:y)?|"
    r"Aug(?:ust)?|"
    r"Sep(?:tember)?|"
    r"Oct(?:ober)?|"
    r"Nov(?:ember)?|"
    r"Dec(?:ember)?"
    r")"
)


def month_to_number(month_text: str) -> int:

    month_text = month_text.strip()

    try:

        return datetime.datetime.strptime(
            month_text[:3].title(),
            "%b"
        ).month

    except Exception:

        return 1




# ---------------------------------------------------------
# EXPERIENCE
# ---------------------------------------------------------

def extract_experience(text: str) -> str:

    import datetime

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # -----------------------------------------------------
    # A. Explicit experience statement
    # -----------------------------------------------------

    explicit_patterns = [
        r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:professional\s*)?experience",
        r"(?:total\s*)?experience\s*[:\-]\s*(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)",
        r"(?:professional\s*)?experience\s*[:\-]\s*(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)",
    ]

    for pattern in explicit_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            years = float(match.group(1))

            if years.is_integer():
                return f"{int(years)} Years"

            return f"{years:.1f} Years"

    # -----------------------------------------------------
    # B. Find Work Experience section
    # -----------------------------------------------------

    start_index = None
    end_index = len(lines)

    start_headers = [
        "work experience",
        "professional experience",
        "experience",
        "employment history",
        "work history",
        "employment",
    ]

    stop_headers = [
        "education",
        "skills",
        "technical skills",
        "projects",
        "certifications",
        "achievements",
        "awards",
        "publications",
        "references",
    ]

    for index, line in enumerate(lines):

        normalized = re.sub(
            r"[^a-z ]",
            "",
            line.lower()
        ).strip()

        if normalized in start_headers:

            start_index = index + 1
            break

    if start_index is None:

        return ""

    # -----------------------------------------------------
    # Find end of Work Experience section
    # -----------------------------------------------------

    for index in range(
        start_index,
        len(lines)
    ):

        normalized = re.sub(
            r"[^a-z ]",
            "",
            lines[index].lower()
        ).strip()

        if normalized in stop_headers:

            end_index = index
            break

    experience_lines = lines[
        start_index:end_index
    ]

    experience_text = "\n".join(
        experience_lines
    )

    # -----------------------------------------------------
    # C. Extract work dates
    # -----------------------------------------------------

    date_regex = re.compile(
        r"""
        (?:
            (Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|
             May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|
             Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|
             Dec(?:ember)?)
            [\s\-\/]*
        )?
        (20\d{2})
        \s*
        (?:
            -
            |–
            |—
            |to
        )
        \s*
        (?:
            (Present|Current)
            |
            (?:
                (Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|
                 May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|
                 Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|
                 Dec(?:ember)?)
                [\s\-\/]*
            )?
            (20\d{2})
        )
        """,
        re.IGNORECASE | re.VERBOSE
    )

    date_ranges = []

    for match in date_regex.finditer(
        experience_text
    ):

        start_month_name = match.group(1)
        start_year = int(match.group(2))

        end_value = (
            match.group(3)
            or match.group(5)
            or ""
        )

        end_month_name = match.group(4)

        # -------------------------------------------------
        # Start month
        # -------------------------------------------------

        if start_month_name:

            try:

                start_month = datetime.datetime.strptime(
                    start_month_name[:3],
                    "%b"
                ).month

            except ValueError:

                start_month = 1

        else:

            start_month = 1

        start_date = datetime.datetime(
            start_year,
            start_month,
            1
        )

        # -------------------------------------------------
        # End date
        # -------------------------------------------------

        if end_value.lower() in [
            "present",
            "current"
        ]:

            now = datetime.datetime.now()

            end_date = datetime.datetime(
                now.year,
                now.month,
                1
            )

        else:

            end_year_match = re.search(
                r"20\d{2}",
                end_value
            )

            if not end_year_match:
                continue

            end_year = int(
                end_year_match.group()
            )

            if end_month_name:

                try:

                    end_month = datetime.datetime.strptime(
                        end_month_name[:3],
                        "%b"
                    ).month

                except ValueError:

                    end_month = 12

            else:

                end_month = 12

            end_date = datetime.datetime(
                end_year,
                end_month,
                1
            )

        if end_date >= start_date:

            date_ranges.append(
                (
                    start_date,
                    end_date
                )
            )

    # -----------------------------------------------------
    # D. If no ranges were found
    # -----------------------------------------------------

    if not date_ranges:

        return ""

    # -----------------------------------------------------
    # E. Merge overlapping / continuous employment periods
    # -----------------------------------------------------

    date_ranges.sort(
        key=lambda x: x[0]
    )

    merged_ranges = []

    for start_date, end_date in date_ranges:

        if not merged_ranges:

            merged_ranges.append(
                [start_date, end_date]
            )

            continue

        previous_start, previous_end = (
            merged_ranges[-1]
        )

        # If current job overlaps or is immediately
        # adjacent to previous job, merge them.
        if start_date <= previous_end:

            if end_date > previous_end:

                merged_ranges[-1][1] = end_date

        else:

            merged_ranges.append(
                [start_date, end_date]
            )

    # -----------------------------------------------------
    # F. Calculate total months
    # -----------------------------------------------------

    total_months = 0

    for start_date, end_date in merged_ranges:

        months = (
            (end_date.year - start_date.year) * 12
            + end_date.month
            - start_date.month
        )

        if months > 0:

            total_months += months

    # -----------------------------------------------------
    # G. Return readable value
    # -----------------------------------------------------

    if total_months == 0:

        return ""

    years = total_months // 12
    months = total_months % 12

    if years > 0 and months > 0:

        return f"{years} Years {months} Months"

    if years > 0:

        return f"{years} Years"

    return f"{months} Months"


# =========================================================
# CURRENT ROLE
# =========================================================

def extract_role(text: str) -> str:

    # -----------------------------------------------------
    # Explicit labels
    # -----------------------------------------------------

    patterns = [

        r"current\s*(?:role|position)"
        r"\s*[:\-]\s*(.+)",

        r"role\s*[:\-]\s*(.+)",

        r"position\s*[:\-]\s*(.+)",

        r"title\s*[:\-]\s*(.+)",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            value = clean_line(
                match.group(1)
            )

            if 2 <= len(value) < 100:

                return value

    # -----------------------------------------------------
    # Common job titles
    # -----------------------------------------------------

    job_titles = [

        "Senior Software Engineer",
        "Software Engineer",

        "Senior Frontend Developer",
        "Frontend Developer",

        "Senior Backend Developer",
        "Backend Developer",

        "Senior Full Stack Developer",
        "Full Stack Developer",

        "Senior Data Scientist",
        "Data Scientist",

        "Senior Data Analyst",
        "Data Analyst",

        "Senior Machine Learning Engineer",
        "Machine Learning Engineer",

        "AI/ML Engineer",
        "AI Engineer",

        "DevOps Engineer",

        "Cloud Engineer",

        "Business Analyst",

        "Product Manager",

        "Project Manager",

        "QA Engineer",

        "Test Engineer",

        "Software Developer",

        "Web Developer",

        "System Administrator",

    ]

    # Search senior titles first
    for title in job_titles:

        if re.search(
            rf"\b{re.escape(title)}\b",
            text,
            re.IGNORECASE
        ):

            return title

    return ""


# =========================================================
# POSSIBLE COMPANY
# =========================================================

def is_possible_company(line: str) -> bool:

    line = clean_line(line)

    if not line:
        return False

    lower = line.lower()

    # -----------------------------------------------------
    # Reject obvious non-company text
    # -----------------------------------------------------

    rejected_words = [

        "experience",
        "education",
        "skills",
        "technical skills",
        "projects",
        "certifications",
        "achievements",
        "summary",
        "profile",
        "objective",

        "present",
        "current",

        "responsibilities",
        "description",

        "worked",
        "developed",
        "designed",
        "implemented",

    ]

    if lower in rejected_words:
        return False

    # -----------------------------------------------------
    # Reject lines containing dates
    # -----------------------------------------------------

    if re.search(
        r"\b20\d{2}\b",
        line
    ):
        return False

    # -----------------------------------------------------
    # Reject email / phone / URL
    # -----------------------------------------------------

    if "@" in line:
        return False

    if re.search(
        r"https?://|www\.",
        lower
    ):
        return False

    if re.search(
        r"\d{7,}",
        line
    ):
        return False

    # -----------------------------------------------------
    # Reject very long sentences
    # -----------------------------------------------------

    if len(line) > 100:
        return False

    # -----------------------------------------------------
    # Reject obvious job titles
    # -----------------------------------------------------

    job_words = [

        "engineer",
        "developer",
        "analyst",
        "scientist",
        "manager",
        "consultant",
        "architect",
        "designer",
        "administrator",
        "specialist",
        "intern",
        "lead",
        "director",

    ]

    if any(
        re.search(
            rf"\b{re.escape(word)}\b",
            lower
        )
        for word in job_words
    ):
        return False

    # -----------------------------------------------------
    # Reject common date words
    # -----------------------------------------------------

    if re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
        r"(uary|ruary|ch|il|e|y|ust|tember|ober|ember)?\b",
        lower
    ):
        return False

    # -----------------------------------------------------
    # Company indicators
    # -----------------------------------------------------

    company_indicators = [

        "technologies",
        "technology",
        "solutions",
        "systems",
        "software",
        "services",
        "consulting",
        "consultancy",
        "industries",
        "limited",
        "ltd",
        "llp",
        "inc",
        "corp",
        "corporation",
        "company",
        "pvt",
        "private",
        "labs",
        "laboratories",
        "group",

    ]

    if any(
        indicator in lower
        for indicator in company_indicators
    ):
        return True

    # -----------------------------------------------------
    # Reasonable company-name fallback
    # -----------------------------------------------------

    words = line.split()

    if 1 <= len(words) <= 7:

        # Company names commonly use title case / uppercase
        alpha_words = [
            word for word in words
            if re.search(
                r"[A-Za-z]",
                word
            )
        ]

        if alpha_words:

            uppercase_or_title_count = sum(
                1
                for word in alpha_words
                if (
                    word.isupper()
                    or word[:1].isupper()
                )
            )

            if (
                uppercase_or_title_count
                >= max(
                    1,
                    len(alpha_words) // 2
                )
            ):
                return True

    return False


# =========================================================
# CURRENT COMPANY
# =========================================================

def extract_company(text: str) -> str:

    lines = get_lines(text)

    # -----------------------------------------------------
    # A. Explicit company labels
    # -----------------------------------------------------

    explicit_patterns = [

        r"current\s*company\s*[:\-]\s*(.+)",

        r"current\s*employer\s*[:\-]\s*(.+)",

        r"company\s*[:\-]\s*(.+)",

        r"employer\s*[:\-]\s*(.+)",

        r"organization\s*[:\-]\s*(.+)",

        r"organisation\s*[:\-]\s*(.+)",

    ]

    for pattern in explicit_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            value = clean_line(
                match.group(1)
            )

            if is_possible_company(value):

                return value

    # -----------------------------------------------------
    # B. Find Experience section
    # -----------------------------------------------------

    experience_headers = [

        "experience",

        "work experience",

        "professional experience",

        "employment",

        "employment history",

        "work history",

    ]

    stop_headers = [

        "education",

        "skills",

        "technical skills",

        "projects",

        "certifications",

        "achievements",

        "summary",

        "professional summary",

        "profile",

        "objective",

        "interests",

        "references",

    ]

    experience_start = None

    for index, line in enumerate(lines):

        lower = line.lower().strip()

        if any(
            lower == header
            or lower.startswith(header + ":")
            for header in experience_headers
        ):

            experience_start = index + 1
            break

    # -----------------------------------------------------
    # If Experience section exists
    # -----------------------------------------------------

    if experience_start is not None:

        experience_lines = []

        for line in lines[experience_start:]:

            lower = line.lower().strip()

            if any(
                lower == header
                or lower.startswith(header + ":")
                for header in stop_headers
            ):

                break

            experience_lines.append(line)

        # -------------------------------------------------
        # Look for CURRENT / PRESENT
        # -------------------------------------------------

        for index, line in enumerate(
            experience_lines
        ):

            if re.search(
                r"\b(present|current)\b",
                line,
                re.IGNORECASE
            ):

                # Look around the current-job line.
                #
                # Usually resumes have:
                #
                # Company
                # Job Title
                # Jan 2023 - Present
                #
                # or
                #
                # Job Title
                # Company
                # Jan 2023 - Present
                #

                candidates = []

                # Previous lines
                for offset in range(1, 5):

                    previous_index = (
                        index - offset
                    )

                    if previous_index >= 0:

                        candidates.append(
                            experience_lines[
                                previous_index
                            ]
                        )

                # Next lines
                for offset in range(1, 3):

                    next_index = (
                        index + offset
                    )

                    if next_index < len(
                        experience_lines
                    ):

                        candidates.append(
                            experience_lines[
                                next_index
                            ]
                        )

                for candidate in candidates:

                    candidate = clean_line(
                        candidate
                    )

                    if is_possible_company(
                        candidate
                    ):

                        return candidate

        # -------------------------------------------------
        # Look for company-like line near latest job
        # -------------------------------------------------

        # The first job in many resumes is the latest job.
        #
        # Search first 10-15 lines of Experience section.

        for line in experience_lines[:15]:

            if is_possible_company(line):

                return line

    # -----------------------------------------------------
    # C. Search entire resume around Present/Current
    # -----------------------------------------------------

    for index, line in enumerate(lines):

        if re.search(
            r"\b(present|current)\b",
            line,
            re.IGNORECASE
        ):

            candidates = []

            for offset in range(1, 5):

                previous_index = index - offset

                if previous_index >= 0:

                    candidates.append(
                        lines[previous_index]
                    )

            for offset in range(1, 3):

                next_index = index + offset

                if next_index < len(lines):

                    candidates.append(
                        lines[next_index]
                    )

            for candidate in candidates:

                if is_possible_company(
                    candidate
                ):

                    return candidate

    # -----------------------------------------------------
    # D. Search for company indicators
    # -----------------------------------------------------

    company_indicators = [

        "technologies",
        "technology",
        "solutions",
        "systems",
        "software",
        "services",
        "consulting",
        "consultancy",
        "industries",
        "limited",
        "ltd",
        "llp",
        "inc",
        "corp",
        "corporation",
        "pvt",
        "private",
        "labs",
        "laboratories",

    ]

    for line in lines:

        lower = line.lower()

        if any(
            indicator in lower
            for indicator in company_indicators
        ):

            if is_possible_company(line):

                return line

    return ""


# =========================================================
# SKILLS
# =========================================================

def extract_skills(text: str) -> str:

    lines = get_lines(text)

    skill_headers = [

        "skills",

        "technical skills",

        "key skills",

        "technical expertise",

        "core skills",

        "core competencies",

    ]

    stop_headers = [

        "experience",

        "work experience",

        "professional experience",

        "education",

        "projects",

        "certifications",

        "achievements",

        "summary",

        "professional summary",

        "profile",

    ]

    for index, line in enumerate(lines):

        lower = line.lower()

        if any(
            lower == header
            or lower.startswith(header + ":")
            for header in skill_headers
        ):

            skills = []

            # -------------------------------------------------
            # If skills are on same line
            # -------------------------------------------------

            parts = re.split(
                r"[:\-]",
                line,
                maxsplit=1
            )

            if len(parts) == 2:

                same_line = clean_line(
                    parts[1]
                )

                if same_line:
                    skills.append(
                        same_line
                    )

            # -------------------------------------------------
            # Following lines
            # -------------------------------------------------

            for next_line in lines[
                index + 1:index + 10
            ]:

                clean = clean_line(
                    next_line
                )

                if not clean:
                    continue

                if any(
                    clean.lower() == header
                    or clean.lower().startswith(
                        header + ":"
                    )
                    for header in stop_headers
                ):
                    break

                skills.append(clean)

            if skills:

                result = ", ".join(skills)

                return result[:1000]

    return ""


# =========================================================
# SUMMARY
# =========================================================

def extract_summary(text: str) -> str:

    lines = get_lines(text)

    summary_headers = [

        "summary",

        "professional summary",

        "profile",

        "professional profile",

        "objective",

        "career objective",

    ]

    stop_headers = [

        "experience",

        "work experience",

        "professional experience",

        "education",

        "skills",

        "technical skills",

        "projects",

        "certifications",

        "achievements",

    ]

    for index, line in enumerate(lines):

        lower = line.lower()

        if any(
            lower == header
            or lower.startswith(header + ":")
            for header in summary_headers
        ):

            summary_lines = []

            # -------------------------------------------------
            # Same-line summary
            # -------------------------------------------------

            parts = re.split(
                r"[:\-]",
                line,
                maxsplit=1
            )

            if len(parts) == 2:

                same_line = clean_line(
                    parts[1]
                )

                if same_line:

                    summary_lines.append(
                        same_line
                    )

            # -------------------------------------------------
            # Following lines
            # -------------------------------------------------

            for next_line in lines[
                index + 1:index + 8
            ]:

                clean = clean_line(
                    next_line
                )

                if not clean:
                    continue

                if any(
                    clean.lower() == header
                    or clean.lower().startswith(
                        header + ":"
                    )
                    for header in stop_headers
                ):

                    break

                summary_lines.append(
                    clean
                )

            if summary_lines:

                return " ".join(
                    summary_lines
                )[:2000]

    return ""


# =========================================================
# ANALYZE RESUME API - OPTIMIZED
# =========================================================

@app.post("/api/analyze-resume")
async def analyze_resume(
    resume: UploadFile = File(...)
):

    total_start = time.perf_counter()

    # -----------------------------------------------------
    # Validate filename
    # -----------------------------------------------------

    if not resume.filename:
        raise HTTPException(
            status_code=400,
            detail="No file uploaded"
        )

    filename_lower = resume.filename.lower()

    # -----------------------------------------------------
    # Validate file type
    # -----------------------------------------------------

    if not filename_lower.endswith((".pdf", ".docx")):
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF or DOCX resume."
        )

    # -----------------------------------------------------
    # Read file
    # -----------------------------------------------------

    file_start = time.perf_counter()

    file_bytes = await resume.read()

    file_time = time.perf_counter() - file_start

    print(
        f"FILE READ: {file_time:.3f} seconds"
    )

    # -----------------------------------------------------
    # Size validation
    # -----------------------------------------------------

    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="File size should not exceed 10MB"
        )

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty."
        )

    # -----------------------------------------------------
    # Extract resume text
    # -----------------------------------------------------

    extraction_start = time.perf_counter()

    try:

        if filename_lower.endswith(".pdf"):

            resume_text = extract_pdf_text(
                file_bytes
            )

        else:

            resume_text = extract_docx_text(
                file_bytes
            )

    except Exception as e:

        print(
            "RESUME TEXT EXTRACTION ERROR:",
            str(e)
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to extract text from resume."
        )

    extraction_time = (
        time.perf_counter() - extraction_start
    )

    print(
        f"TEXT EXTRACTION: "
        f"{extraction_time:.3f} seconds"
    )

    print(
        f"RESUME TEXT LENGTH: "
        f"{len(resume_text)} characters"
    )
    
    print("========== EXTRACTED RESUME TEXT ==========")
    print(resume_text[:5000])
    print("============================================")

    # -----------------------------------------------------
    # Validate extracted text
    # -----------------------------------------------------

    if not resume_text or not resume_text.strip():

        raise HTTPException(
            status_code=400,
            detail="Could not extract text from this resume."
        )

    resume_text = resume_text.strip()

    # =====================================================
    # LLM CANDIDATE EXTRACTION
    # =====================================================

    llm_start = time.perf_counter()

    try:

        candidate = extract_candidate_details(
            resume_text
        )

    except Exception as e:

        print(
            "LLM CANDIDATE EXTRACTION ERROR:",
            str(e)
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to extract candidate details using AI."
        )

    llm_time = (
        time.perf_counter() - llm_start
    )

    print(
        f"LLM EXTRACTION: "
        f"{llm_time:.3f} seconds"
    )

    # =====================================================
    # TOTAL TIME
    # =====================================================

    total_time = (
        time.perf_counter() - total_start
    )

    print(
        "======================================"
    )

    print(
        f"TOTAL RESUME ANALYSIS: "
        f"{total_time:.3f} seconds"
    )

    print(
        "======================================"
    )

    # =====================================================
    # RETURN RESPONSE
    # =====================================================

    return {
        "success": True,
        "filename": resume.filename,
        "candidate": candidate
    }

# =========================================================
# SAMPLE QUESTIONS
# =========================================================

@app.get("/api/sample-questions")
def get_sample_questions(
    domain: str = Query(...),
    experience: float = Query(...)
):

    connection = None
    cursor = None

    try:

        # -------------------------------------------------
        # Validate domain
        # -------------------------------------------------

        if not domain or not domain.strip():

            raise HTTPException(
                status_code=400,
                detail="Interview domain is required."
            )

        # -------------------------------------------------
        # Clean domain
        # -------------------------------------------------

        requested_domain = domain.strip()

        # -------------------------------------------------
        # Debug
        # -------------------------------------------------

        print(
            "\n========================================"
        )

        print(
            "SAMPLE QUESTIONS REQUEST"
        )

        print(
            f"Domain received     : [{requested_domain}]"
        )

        print(
            f"Experience received : [{experience}]"
        )

        print(
            "========================================\n"
        )

        # -------------------------------------------------
        # PostgreSQL connection
        # -------------------------------------------------

        connection = get_connection()

        cursor = connection.cursor()

        # -------------------------------------------------
        # IMPORTANT
        #
        # Normalize domain:
        #
        # PD
        # pd
        # PD
        # " PD "
        #
        # will all match.
        # -------------------------------------------------

        normalized_domain = requested_domain.lower().strip()

        # -------------------------------------------------
        # STEP 1
        #
        # Get questions matching DOMAIN + EXPERIENCE
        #
        # We use overlap logic:
        #
        # experience_min <= candidate experience
        # AND
        # experience_max >= candidate experience
        #
        # Example:
        #
        # Candidate = 3.5 years
        #
        # DB:
        # 2 - 5  -> MATCH
        # 0 - 2  -> NO MATCH
        # 5 - 8  -> NO MATCH
        # -------------------------------------------------

        query = """
            SELECT
                id,
                domain,
                difficulty,
                experience_min,
                experience_max,
                question
            FROM interview_questions
            WHERE
                is_active = TRUE
                AND LOWER(TRIM(domain)) = %s
                AND experience_min <= %s
                AND experience_max >= %s
            ORDER BY RANDOM()
            LIMIT 4
        """

        cursor.execute(
            query,
            (
                normalized_domain,
                experience,
                experience
            )
        )

        rows = cursor.fetchall()

        # -------------------------------------------------
        # DEBUG
        # -------------------------------------------------

        print(
            f"Matching questions found: {len(rows)}"
        )

        # -------------------------------------------------
        # Convert database rows
        # -------------------------------------------------

        questions = []

        for row in rows:

            questions.append({

                "id": row[0],

                "domain": row[1],

                "difficulty": row[2],

                "experienceMin": row[3],

                "experienceMax": row[4],

                "question": row[5],

            })

        # -------------------------------------------------
        # Return
        # -------------------------------------------------

        return {

            "success": True,

            "domain": requested_domain,

            "experience": experience,

            "questions": questions

        }

    except HTTPException:

        raise

    except Exception as e:

        print(
            "\n========================================"
        )

        print(
            "ERROR FETCHING SAMPLE QUESTIONS"
        )

        print(
            str(e)
        )

        print(
            "========================================\n"
        )

        raise HTTPException(
            status_code=500,
            detail="Could not fetch sample questions."
        )

    finally:

        if cursor:

            cursor.close()

        if connection:

            connection.close()
            
            
            
            
# =========================================================
# GENERATE AI INTERVIEW QUESTIONS
# =========================================================

@app.post("/api/generate-interview-questions")
async def generate_ai_interview_questions(data: dict):

    connection = None
    cursor = None

    try:

        candidate = data.get("candidate", {})
        form_data = data.get("formData", {})

        candidate_name = (
            candidate.get("fullName")
            or "Candidate"
        )

        experience = (
            candidate.get("experience")
            or form_data.get("domainExperience")
            or "0"
        )

        current_role = (
            candidate.get("currentRole")
            or form_data.get("role")
            or ""
        )

        current_company = (
            candidate.get("currentCompany")
            or ""
        )

        skills = (
            candidate.get("skills")
            or ""
        )

        summary = (
            candidate.get("summary")
            or ""
        )

        domain = (
            form_data.get("domain")
            or ""
        )

        if not domain:

            raise HTTPException(
                status_code=400,
                detail="Interview domain is required."
            )

        # -------------------------------------------------
        # Convert experience
        # -------------------------------------------------

        experience_number = 0

        match = re.search(
            r"\d+(?:\.\d+)?",
            str(experience)
        )

        if match:

            experience_number = float(
                match.group()
            )

        # -------------------------------------------------
        # Get reference questions from PostgreSQL
        # -------------------------------------------------

        connection = get_connection()
        cursor = connection.cursor()

        normalized_domain = (
            domain.strip().lower()
        )

        query = """
            SELECT question
            FROM interview_questions
            WHERE
                is_active = TRUE
                AND LOWER(TRIM(domain)) = %s
                AND experience_min <= %s
                AND experience_max >= %s
            ORDER BY RANDOM()
            LIMIT 5
        """

        cursor.execute(
            query,
            (
                normalized_domain,
                experience_number,
                experience_number
            )
        )

        rows = cursor.fetchall()

        reference_questions = [
            row[0]
            for row in rows
        ]

        print("\n========================================")
        print("REFERENCE QUESTIONS")
        print("========================================")

        for q in reference_questions:
            print(q)

        # -------------------------------------------------
        # If database has no reference questions
        # -------------------------------------------------

        if not reference_questions:

            raise HTTPException(
                status_code=404,
                detail=(
                    "No reference questions found "
                    "for this domain and experience level."
                )
            )

        # -------------------------------------------------
        # Generate NEW questions using OpenAI
        # -------------------------------------------------

        questions = generate_interview_questions(

            candidate_name=candidate_name,

            experience=str(experience),

            current_role=current_role,

            current_company=current_company,

            skills=skills,

            summary=summary,

            domain=domain,

            reference_questions=reference_questions,

            number_of_questions=5
        )

        print("\n========================================")
        print("GENERATED AI QUESTIONS")
        print("========================================")

        for index, question in enumerate(
            questions,
            start=1
        ):

            print(
                f"{index}. {question}"
            )

        print("========================================\n")

        return {

            "success": True,

            "questions": questions,

            "reference_questions_used":
                reference_questions

        }

    except HTTPException:
        raise

    except Exception as e:

        print("\n========================================")
        print("LLM QUESTION GENERATION ERROR")
        print(str(e))
        print("========================================\n")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()
        
@app.post("/api/process-answer")
async def process_answer(data: dict):

    try:

        question = data.get("question", "")
        answer = data.get("answer", "")
        domain = data.get("domain", "")
        question_number = data.get("question_number", 1)
        total_questions = data.get("total_questions", 10)

        is_followup = data.get(
            "is_followup",
            False
        )

        reference_questions = data.get(
            "reference_questions",
            []
        )

        if not question:
            raise HTTPException(
                status_code=400,
                detail="Question is required."
            )

        if not answer:
            raise HTTPException(
                status_code=400,
                detail="Answer is required."
            )

        print("\n======================================")
        print("PROCESSING CANDIDATE ANSWER")
        print("======================================")

        print("Question:", question)
        print("Answer:", answer)
        print("Question Number:", question_number)
        print("Is Follow-up:", is_followup)

        # =====================================================
        # ONE OPENAI CALL
        # =====================================================

        print("\n========== AI PROCESSING START ==========")

        import time

        start_time = time.time()

        result = process_answer_with_ai(
            question=question,
            answer=answer,
            domain=domain,
            question_number=question_number,
            total_questions=total_questions,
            is_followup=is_followup,
            reference_questions=reference_questions
        )

        total_time = time.time() - start_time

        print(
            "Total OpenAI processing time:",
            total_time,
            "seconds"
        )

        print("AI RESULT:")
        print(result)

        print("========== AI PROCESSING END ==========\n")

        # =====================================================
        # PARSE RESULT
        # =====================================================

        import json

        if isinstance(result, dict):

            evaluation = result

        else:

            try:

                evaluation = json.loads(result)

            except Exception:

                print(
                    "Could not parse AI response."
                )

                evaluation = {
                    "score": 0,
                    "feedback": "",
                    "action": "next",
                    "next_question": ""
                }

        # =====================================================
        # SCORE
        # =====================================================

        score = evaluation.get(
            "score",
            0
        )

        feedback = evaluation.get(
            "feedback",
            ""
        )

        action = evaluation.get(
            "action",
            "next"
        )

        next_question = evaluation.get(
            "next_question",
            ""
        )

        # =====================================================
        # NORMALIZE SCORE
        # =====================================================

        try:

            score = float(score)

        except Exception:

            score = 0

        score = max(
            0,
            min(10, score)
        )

        print("SCORE:", score)
        print("ACTION:", action)
        print("NEXT QUESTION:", next_question)

        # =====================================================
        # FOLLOW-UP ANSWER
        # =====================================================

        if is_followup:

            print(
                "Follow-up answer evaluated."
            )

            # Follow-up should NEVER generate another
            # follow-up.

            if question_number >= total_questions:

                print(
                    "Interview completed."
                )

                return {

                    "success": True,

                    "action": "complete",

                    "score": score,

                    "feedback": feedback,

                    "question_number":
                        question_number,

                    "total_questions":
                        total_questions
                }

            return {

                "success": True,

                "action": "next",

                "score": score,

                "feedback": feedback,

                "next_question":
                    next_question,

                "question_number":
                    question_number + 1,

                "total_questions":
                    total_questions
            }

        # =====================================================
        # NORMAL MAIN QUESTION
        # =====================================================

        # LOW SCORE
        if score < 4:

            print(
                "Low score - follow-up generated."
            )

            return {

                "success": True,

                "action": "followup",

                "score": score,

                "feedback": feedback,

                "followup_question":
                    next_question,

                # Same question number because
                # this is a follow-up.
                "question_number":
                    question_number,

                "total_questions":
                    total_questions
            }

        # =====================================================
        # GOOD SCORE
        # =====================================================

        print(
            "Good score - moving to next question."
        )

        if question_number >= total_questions:

            print(
                "Interview completed."
            )

            return {

                "success": True,

                "action": "complete",

                "score": score,

                "feedback": feedback,

                "question_number":
                    question_number,

                "total_questions":
                    total_questions
            }

        return {

            "success": True,

            "action": "next",

            "score": score,

            "feedback": feedback,

            "next_question":
                next_question,

            "question_number":
                question_number + 1,

            "total_questions":
                total_questions
        }

    except HTTPException:

        raise

    except Exception as e:

        print(
            "PROCESS ANSWER ERROR:",
            str(e)
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ============================================================
# AUDIO START
# ============================================================

@app.post("/api/audio/start")
def api_audio_start():

    print("\n>>> API AUDIO START CALLED <<<")

    result = start_audio()

    print(
        ">>> AUDIO START RESULT:",
        result
    )

    return result

# ============================================================
# AUDIO CHUNK
# ============================================================


@app.post("/api/audio/chunk")
async def api_audio_chunk(
    audio: UploadFile = File(...)
):

    audio_data = await audio.read()

    result = add_audio_chunk(
        audio_data
    )

    return result



# ============================================================
# AUDIO STOP
# ============================================================

@app.post("/api/audio/stop")
def api_audio_stop():

    print("\n>>> API AUDIO STOP CALLED <<<")

    result = stop_audio()

    print(
        ">>> AUDIO STOP RESULT:",
        result
    )

    return result


# ============================================================
# GET TRANSCRIPT
# ============================================================

@app.get("/api/audio/transcript")
def api_audio_transcript():

    result = get_transcript()

    print(
        ">>> TRANSCRIPT:",
        result
    )

    return result







# ============================================================
# GENERATE INTERVIEW REPORT
# ============================================================

@app.post("/api/generate-report")
async def generate_report(data: dict):

    try:

        # =====================================================
        # GET COMPLETE INTERVIEW DATA
        # =====================================================

        interview_data = data.get(
            "interview_data",
            {}
        )

        if not interview_data:

            raise HTTPException(
                status_code=400,
                detail="Interview data is required."
            )

        # =====================================================
        # CANDIDATE DETAILS
        # =====================================================

        candidate = interview_data.get(
            "candidate",
            {}
        )

        candidate_name = candidate.get(
            "fullName",
            ""
        )

        candidate_email = candidate.get(
            "email",
            ""
        )

        candidate_phone = candidate.get(
            "phone",
            ""
        )

        candidate_experience = candidate.get(
            "experience",
            ""
        )

        candidate_role = candidate.get(
            "currentRole",
            ""
        )

        candidate_company = candidate.get(
            "currentCompany",
            ""
        )

        candidate_skills = candidate.get(
            "skills",
            ""
        )

        candidate_summary = candidate.get(
            "summary",
            ""
        )

        # =====================================================
        # INTERVIEW DETAILS
        # =====================================================

        experience = interview_data.get(
            "experience",
            candidate_experience
        )

        role = interview_data.get(
            "role",
            candidate_role
        )

        domain = interview_data.get(
            "domain",
            ""
        )

        total_questions = interview_data.get(
            "totalQuestions",
            0
        )

        answers = interview_data.get(
            "answers",
            []
        )

        # =====================================================
        # LOG
        # =====================================================

        print("\n======================================")
        print("GENERATING AI INTERVIEW REPORT")
        print("======================================")

        print(
            "Candidate:",
            candidate_name
        )

        print(
            "Email:",
            candidate_email
        )

        print(
            "Phone:",
            candidate_phone
        )

        print(
            "Role:",
            role
        )

        print(
            "Company:",
            candidate_company
        )

        print(
            "Domain:",
            domain
        )

        print(
            "Experience:",
            experience
        )

        print(
            "Skills:",
            candidate_skills
        )

        print(
            "Total Questions:",
            total_questions
        )

        print(
            "Total Answers:",
            len(answers)
        )

        # =====================================================
        # PRINT ANSWERS
        # =====================================================

        for answer in answers:

            print(
                "\n--------------------------------------"
            )

            print(
                "Question Number:",
                answer.get(
                    "questionNumber"
                )
            )

            print(
                "Question:",
                answer.get(
                    "question",
                    ""
                )
            )

            print(
                "Answer:",
                answer.get(
                    "answer",
                    ""
                )
            )

            print(
                "Score:",
                answer.get(
                    "score",
                    0
                )
            )

            print(
                "Feedback:",
                answer.get(
                    "feedback",
                    ""
                )
            )

            print(
                "Follow-up:",
                answer.get(
                    "isFollowup",
                    False
                )
            )

        # =====================================================
        # GENERATE REPORT USING LLM
        # =====================================================

        report = generate_interview_report(

            candidate_name=
                candidate_name,

            candidate_email=
                candidate_email,

            candidate_phone=
                candidate_phone,

            experience=
                experience,

            role=
                role,

            company=
                candidate_company,

            skills=
                candidate_skills,

            candidate_summary=
                candidate_summary,

            domain=
                domain,

            answers=
                answers,

            total_questions=
                total_questions
        )

        # =====================================================
        # CHECK REPORT
        # =====================================================

        if not report:

            raise HTTPException(
                status_code=500,
                detail=
                    "AI report generation failed."
            )

        print(
            "\n======================================"
        )

        print(
            "AI REPORT GENERATED"
        )

        print(
            "======================================"
        )

        print(report)

        # =====================================================
        # RETURN REPORT TO REACT
        # =====================================================

        return {

            "success": True,

            "report": report,

            "candidate": {

                "fullName":
                    candidate_name,

                "email":
                    candidate_email,

                "phone":
                    candidate_phone,

                "experience":
                    experience,

                "role":
                    role,

                "company":
                    candidate_company,

                "skills":
                    candidate_skills
            },

            "domain":
                domain,

            "total_questions":
                total_questions,

            "total_answers":
                len(answers)
        }

    except HTTPException:

        raise

    except Exception as e:

        print(
            "\nREPORT GENERATION ERROR:",
            str(e)
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
        
        
        
        
        
        # ============================================================
# SUBMIT INTERVIEW REPORT
# ============================================================

@app.post("/api/submit-report")
async def submit_report(data: dict):

    try:

        # =====================================================
        # GET SUBMISSION DATA
        # =====================================================

        report = data.get(
            "report",
            {}
        )

        candidate_name = data.get(
            "candidate_name",
            report.get("candidate_name", "")
        )

        manager_email = data.get(
            "manager_email",
            report.get("manager_email", "")
        )

        session_id = data.get(
            "session_id",
            ""
        )

        send_email = data.get(
            "send_email",
            False
        )

        # =====================================================
        # VALIDATE REPORT
        # =====================================================

        if not report:

            raise HTTPException(
                status_code=400,
                detail="Report data is required."
            )

        # =====================================================
        # LOG SUBMISSION
        # =====================================================

        print("\n======================================")
        print("SUBMITTING INTERVIEW REPORT")
        print("======================================")

        print(
            "Candidate:",
            candidate_name
        )

        print(
            "Manager Email:",
            manager_email
        )

        print(
            "Session ID:",
            session_id
        )

        print(
            "Send Email:",
            send_email
        )

        # =====================================================
        # REPORT DATA
        # =====================================================

        print(
            "Overall Score:",
            report.get(
                "overall_score",
                0
            )
        )

        print(
            "Recommendation:",
            report.get(
                "recommendation",
                ""
            )
        )

        print(
            "Answers:",
            len(
                report.get(
                    "answers",
                    []
                )
            )
        )

        # =====================================================
        # EMAIL
        # =====================================================

        email_sent = False

        if send_email and manager_email:

            try:

                # -------------------------------------------------
                # PUT YOUR EXISTING EMAIL-SENDING LOGIC HERE
                # -------------------------------------------------
                #
                # If you already have an email function in main.py,
                # call it here.
                #
                # Example:
                #
                # send_report_email(
                #     manager_email,
                #     candidate_name,
                #     report
                # )
                #
                # email_sent = True
                #
                # -------------------------------------------------

                print(
                    "Manager email requested:",
                    manager_email
                )

                # Do not mark as sent unless your
                # actual email function succeeds.

            except Exception as email_error:

                print(
                    "Email sending error:",
                    str(email_error)
                )

        # =====================================================
        # SUCCESS
        # =====================================================

        print(
            "\n======================================"
        )

        print(
            "INTERVIEW REPORT SUBMITTED"
        )

        print(
            "======================================"
        )

        return {

            "success": True,

            "message":
                "Interview report submitted successfully.",

            "email_sent":
                email_sent,

            "session_id":
                session_id,

            "candidate_name":
                candidate_name
        }

    except HTTPException:

        raise

    except Exception as e:

        print(
            "\nREPORT SUBMISSION ERROR:",
            str(e)
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
