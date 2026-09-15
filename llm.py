from openai import OpenAI
import os
import json
import datetime
import time
from dotenv import load_dotenv


# =========================================================
# LOAD ENVIRONMENT
# =========================================================

load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print("======================================")
print("OPENAI KEY CHECK")
print("Key exists:", bool(OPENAI_API_KEY))

if OPENAI_API_KEY:
    print("Prefix:", OPENAI_API_KEY[:7])
    print("Suffix:", OPENAI_API_KEY[-4:])
    print("Length:", len(OPENAI_API_KEY))
else:
    print("❌ OPENAI_API_KEY NOT FOUND")

print("======================================")


client = OpenAI(
    api_key=OPENAI_API_KEY
)


# =========================================================
# TEST LLM CONNECTION
# =========================================================

def test_llm():

    response = client.responses.create(
        model="gpt-5",
        input=(
            "Reply with exactly: "
            "IntelliHire LLM connection successful."
        )
    )

    return response.output_text

# =========================================================
# EXTRACT CANDIDATE DETAILS FROM RESUME - FAST
# =========================================================

def extract_candidate_details(resume_text: str):

    if not resume_text or not resume_text.strip():
        return {
            "fullName": "",
            "email": "",
            "phone": "",
            "experience": "",
            "currentRole": "",
            "currentCompany": "",
            "skills": "",
            "summary": ""
        }

    start_time = time.perf_counter()

    # =====================================================
    # CURRENT DATE
    # =====================================================

    current_date = datetime.date.today().strftime("%B %d, %Y")

    # =====================================================
    # COMPACT PROMPT
    # =====================================================

    prompt = f"""
Extract candidate information from the resume below.

Use ONLY information present in the resume.
Do not invent information.

CURRENT DATE: {current_date}

Extract:

1. fullName
Candidate's actual full name.

2. email
Candidate's email address.

3. phone
Candidate's phone number.

4. experience
Calculate TOTAL PROFESSIONAL EXPERIENCE from employment history.

Rules:
- Include all professional employment.
- Include multiple roles at the same company.
- Do not double-count overlapping periods.
- Treat consecutive roles at the same company as continuous.
- If an employment period says Present/Current/Till Date, calculate until {current_date}.
- Do not count education.
- Do not count university/college attendance.
- Do not count academic projects.
- Do not count internships unless clearly professional employment.
- Do not simply copy an experience value from the resume.
- Never invent missing dates.

Return exactly:
"X years Y months"
or
"X years"

5. currentRole
Most recent/current professional job title.

6. currentCompany
Most recent/current employer.

7. skills
Important technical skills, technologies, tools and professional skills.
Return as one concise comma-separated string.
Do not invent skills.

8. summary
Create a concise 2-3 sentence professional summary based only on the resume.

RESUME:
{resume_text}

Return ONLY valid JSON:

{{
  "fullName": "",
  "email": "",
  "phone": "",
  "experience": "",
  "currentRole": "",
  "currentCompany": "",
  "skills": "",
  "summary": ""
}}
"""

    # =====================================================
    # OPENAI CALL
    # =====================================================

    try:

        print("\n======================================")
        print("FAST LLM RESUME EXTRACTION")
        print("======================================")

        llm_start = time.perf_counter()

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt,
            max_output_tokens=1000
        )

        llm_time = time.perf_counter() - llm_start

        print(
            f"OpenAI response time: {llm_time:.2f} seconds"
        )

        result = response.output_text.strip()

        # =================================================
        # HANDLE ACCIDENTAL MARKDOWN
        # =================================================

        if result.startswith("```"):

            result = result.replace(
                "```json",
                ""
            )

            result = result.replace(
                "```",
                ""
            )

            result = result.strip()

        # =================================================
        # PARSE JSON
        # =================================================

        try:

            candidate = json.loads(result)

        except Exception as e:

            print(
                "Resume extraction JSON parsing failed:",
                str(e)
            )

            return {
                "fullName": "",
                "email": "",
                "phone": "",
                "experience": "",
                "currentRole": "",
                "currentCompany": "",
                "skills": "",
                "summary": ""
            }

        # =================================================
        # NORMALIZE RESULT
        # =================================================

        fields = [
            "fullName",
            "email",
            "phone",
            "experience",
            "currentRole",
            "currentCompany",
            "skills",
            "summary"
        ]

        final_candidate = {}

        for field in fields:

            value = candidate.get(
                field,
                ""
            )

            if value is None:
                value = ""

            if not isinstance(
                value,
                str
            ):
                value = str(value)

            final_candidate[field] = value.strip()

        # =================================================
        # TOTAL TIME
        # =================================================

        total_time = time.perf_counter() - start_time

        print(
            f"TOTAL RESUME ANALYSIS: "
            f"{total_time:.2f} seconds"
        )

        print("\nFINAL EXTRACTED CANDIDATE:")

        print(
            json.dumps(
                final_candidate,
                indent=2,
                ensure_ascii=False
            )
        )

        return final_candidate

    # =====================================================
    # OPENAI ERROR
    # =====================================================

    except Exception as e:
    
        print(
            "Resume extraction JSON parsing failed:",
            str(e)
        )
    
        print("RAW LLM OUTPUT:")
        print(repr(result))
    
        raise ValueError(
            f"Resume extraction returned invalid JSON: {str(e)}"
        )
# =========================================================
# GENERATE INITIAL INTERVIEW QUESTIONS
# =========================================================

def generate_interview_questions(
    candidate_name: str,
    experience: str,
    current_role: str,
    current_company: str,
    skills: str,
    summary: str,
    domain: str,
    reference_questions: list,
    number_of_questions: int = 5
):

    reference_text = "\n".join(
        [
            f"- {q}"
            for q in reference_questions
        ]
    )

    prompt = f"""
You are an expert AI technical interviewer.

You are conducting an interview for IntelliHire.

Candidate information:

Name:
{candidate_name}

Experience:
{experience}

Current Role:
{current_role}

Current Company:
{current_company}

Skills:
{skills}

Summary:
{summary}

Interview Domain:
{domain}


REFERENCE QUESTIONS

The following questions come from our internal interview
question database.

IMPORTANT:

These are ONLY reference questions.

Do NOT copy them exactly.

Use them only to understand:

- the technical area
- expected difficulty
- question style
- concepts that should be tested


Reference questions:

{reference_text}


TASK:

Generate exactly {number_of_questions} NEW technical
interview questions.

Requirements:

1. Questions must be relevant to the candidate's domain.
2. Questions must match the candidate's experience level.
3. Use the reference questions as guidance.
4. Do NOT copy reference questions.
5. Questions should test practical technical knowledge.
6. Questions should progressively become more challenging.
7. Do not provide answers.
8. Do not provide explanations.
9. Return ONLY valid JSON.
10. Return exactly {number_of_questions} questions.

Return exactly this format:

[
    "Question 1",
    "Question 2",
    "Question 3",
    "Question 4",
    "Question 5"
]
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    result = response.output_text.strip()

    try:

        questions = json.loads(result)

        if isinstance(questions, list):
            return questions

    except Exception:

        pass

    return [result]


# =========================================================
# PROCESS ANSWER WITH ONE OPENAI CALL
# =========================================================
#
# This function does EVERYTHING in ONE LLM call:
#
# 1. Evaluate candidate answer
# 2. Give score
# 3. Give feedback
# 4. Decide follow-up / next / complete
# 5. Generate the required question
#
# =========================================================

def process_answer_with_ai(
    question: str,
    answer: str,
    domain: str,
    candidate: dict = None,
    reference_questions: list = None,
    question_number: int = 1,
    total_questions: int = 10,
    is_followup: bool = False
):

    if candidate is None:
        candidate = {}

    if reference_questions is None:
        reference_questions = []

    reference_text = "\n".join(
        [
            f"- {q}"
            for q in reference_questions
        ]
    )

    # =====================================================
    # PROMPT
    # =====================================================

    prompt = f"""

You are an expert technical interviewer conducting an

interview for IntelliHire.
 
Your task is to evaluate the candidate's current answer

AND decide what question should be asked next.
 
IMPORTANT:

You must perform BOTH operations in this SAME response.
 
Do NOT require another AI call.
 
=========================================================

CANDIDATE INFORMATION

=========================================================
 
Candidate Name:

{candidate.get("fullName", "")}
 
Experience:

{candidate.get("experience", "")}
 
Current Role:

{candidate.get("currentRole", "")}
 
Current Company:

{candidate.get("currentCompany", "")}
 
Skills:

{candidate.get("skills", "")}
 
Summary:

{candidate.get("summary", "")}
 
Interview Domain:

{domain}
 
 
=========================================================

CURRENT INTERVIEW QUESTION

=========================================================
 
Question Number:

{question_number}
 
Total Main Questions:

{total_questions}
 
Is Follow-up Question:

{is_followup}
 
Question:

{question}
 
 
=========================================================

CANDIDATE ANSWER

=========================================================
 
{answer}
 
 
=========================================================

REFERENCE QUESTIONS

=========================================================
 
These questions are only reference material.
 
Do NOT copy them exactly.
 
Use them only to understand the technical area,

difficulty and style.
 
{reference_text}
 
 
=========================================================

STEP 1 — EVALUATE ANSWER

=========================================================
 
Give a score from 0 to 10.
 
The candidate's answer MUST be evaluated against the

CURRENT QUESTION ONLY.
 
The score must be based on the QUALITY of the candidate's

answer, not the length of the answer.
 
IMPORTANT:
 
Answer length MUST NOT influence the score.
 
A short answer can receive a high score if it correctly,

directly, and sufficiently answers the question.
 
A long answer can receive a low score or 0 if it is

incorrect, irrelevant, vague, incomplete, repetitive,

or does not demonstrate understanding.
 
Do NOT give additional points because an answer is longer.
 
Do NOT reduce the score simply because an answer is short.
 
Do NOT reward:
 
- number of words

- number of sentences

- unnecessary explanations

- repetition

- verbosity

- unrelated technical terminology

- information unrelated to the current question
 
Evaluate the actual technical content of the answer.
 
 
=========================================================

RELEVANCE

=========================================================
 
Relevance is mandatory.
 
First determine whether the candidate actually answered

the CURRENT QUESTION.
 
If the answer is completely irrelevant to the current

question, the score MUST be exactly 0.
 
If the answer discusses a different topic and does not

meaningfully answer the current question, the score MUST

be exactly 0.
 
Do NOT give partial credit merely because the answer

contains technical words, programming terms, tools,

frameworks, technologies, or concepts.
 
The candidate's listed skills, experience, job title,

company, or resume information MUST NOT be used as a

reason to give credit.
 
Do NOT give credit simply because the answer sounds

technical.
 
Only the candidate's actual answer to the CURRENT QUESTION

should determine the score.
 
 
=========================================================

SCORING RULES

=========================================================
 
SCORE 0:
 
Give a score of exactly 0 when the answer:
 
- is completely irrelevant to the question

- answers a different question

- does not address the requested technical concept

- contains no meaningful answer to the question

- is meaningless or nonsensical

- is effectively empty

- contains only unrelated information

- demonstrates no understanding of what was asked
 
SCORE 1 TO 3:
 
Use 1 to 3 ONLY when the answer is genuinely relevant to

the current question AND contains at least some meaningful

technical information that attempts to answer the question.
 
Do NOT give 1, 2, or 3 merely because the answer contains

words related to the topic.
 
If the candidate does not provide any specific, meaningful

technical information that answers the question, the score

MUST be 0.
 
An incomplete, vague, unclear, generic, or unfinished

response must still contain some actual relevant technical

content to receive a score above 0.
 
If the answer only contains:
 
- vague statements

- generic statements

- incomplete thoughts

- filler

- conversational phrases

- unrelated information

- technical-sounding words without relevant meaning

- statements that do not identify or explain anything

  related to the question
 
then the score MUST be 0.
 
A score above 0 requires evidence that the candidate has

attempted to answer the CURRENT QUESTION with meaningful

relevant technical content.
 
SCORE 4 TO 6:
 
Use 4 to 6 when the answer is relevant and demonstrates

basic to moderate understanding.
 
The answer addresses the question but may contain:
 
- some technical errors

- missing important details

- limited depth

- incomplete reasoning

- limited practical understanding
 
SCORE 7 TO 8:
 
Use 7 to 8 when the answer is relevant, mostly correct,

clear, and demonstrates good technical understanding.
 
The candidate should demonstrate a solid understanding of

the concept and provide sufficient technical reasoning.
 
SCORE 9 TO 10:
 
Use 9 to 10 only when the answer is highly relevant,

technically accurate, sufficiently complete, clearly

explained, and demonstrates strong technical and practical

understanding.
 
 
=========================================================

QUALITY OVER LENGTH

=========================================================
 
Do NOT use answer length as a scoring criterion.
 
Do NOT assume:
 
long answer = good answer
 
short answer = bad answer
 
Instead evaluate whether the answer contains enough

CORRECT and RELEVANT information to answer the specific

question.
 
A concise but technically correct answer should receive

appropriate credit.
 
A lengthy answer containing irrelevant, incorrect,

repetitive, or unnecessary information must not receive

additional credit because of its length.
 
The amount of detail required depends on the specific

question.
 
Judge whether the candidate provided sufficient relevant

information to answer the question correctly.
 
Never increase or decrease the score based simply on the

number of words or sentences.
 
 
=========================================================

EVALUATION CRITERIA

=========================================================
 
Evaluate the answer using:
 
1. Relevance to the exact current question

2. Technical correctness

3. Technical understanding

4. Completeness

5. Practical understanding

6. Reasoning and problem solving

7. Clarity of explanation
 
Relevance and correctness are more important than answer

length.
 
Do NOT give credit based only on technical terminology.
 
Do NOT give credit based on the candidate profile.
 
Do NOT give credit for information that does not answer

the current question.
 
 
=========================================================

FEEDBACK

=========================================================
 
Give short, professional feedback explaining the reason

for the score.
 
The feedback must focus on the candidate's actual answer

to the current question.
 
Do not mention answer length unless the answer itself is

unclear or incomplete because essential information is

missing.
 
 
=========================================================

FINAL EVALUATION RULE

=========================================================
 
Before assigning the score, determine:
 
1. Did the candidate actually answer the current question?

2. Is the answer relevant to the current question?

3. Is the answer technically correct?

4. Does it demonstrate understanding?

5. Is the explanation sufficient for this specific question?

6. Does it demonstrate practical understanding where

   appropriate?
 
If the answer is completely irrelevant, the final score

MUST be exactly 0.
 
If the answer is relevant, score it according to the

quality of its technical content.
 
Never use answer length as a reason to increase or

decrease the score.
 
 
=========================================================

STEP 2 — DECIDE WHAT HAPPENS NEXT

=========================================================
 
FOLLOW-UP RULE:
 
If:
 
- this is NOT already a follow-up

- AND score is below 4
 
then:
 
action = "followup"
 
Generate ONE follow-up question.
 
The follow-up must:
 
- remain on the same technical topic

- test the candidate's actual understanding

- be different from the original question

- be concise

- not contain the answer
 
 
NEXT QUESTION RULE:
 
If:
 
- this is already a follow-up
 
then:
 
DO NOT generate another follow-up.
 
Instead generate the next MAIN interview question.
 
action = "next"
 
 
Also, if this is a normal main question and score is

4 or above:
 
Generate the next MAIN interview question.
 
action = "next"
 
 
FINAL QUESTION RULE:
 
If question_number >= total_questions:
 
action = "complete"
 
Do not generate another question.
 
next_question must be an empty string.
 
 
=========================================================

NEXT MAIN QUESTION REQUIREMENTS

=========================================================
 
When generating the next main question:
 
1. Keep it relevant to the interview domain.

2. Match the candidate's experience.

3. Test practical technical knowledge.

4. Use the reference questions only as guidance.

5. Do not copy reference questions.

6. Do not repeat the current question.

7. Do not provide an answer.

8. Do not provide an explanation.

9. Keep the question concise.
 
 
=========================================================

OUTPUT

=========================================================
 
Return ONLY valid JSON.
 
No Markdown.
 
No ```json.
 
No explanation outside JSON.
 
Use exactly this structure:
 
{{

    "score": 0,

    "feedback": "Short professional feedback.",

    "action": "next",

    "next_question": "Next question here"

}}
 
The action MUST be exactly one of:
 
"next"
 
"followup"
 
"complete"
 
 
For "complete":
 
{{

    "score": 0,

    "feedback": "Short professional feedback.",

    "action": "complete",

    "next_question": ""

}}

"""


    # =====================================================
    # OPENAI — ONLY ONE CALL
    # =====================================================

    import time

    start_time = time.time()

    print("\n========== AI PROCESSING START ==========")
    print("Calling OpenAI ONCE...")
    print("Evaluating answer + generating next question...")

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        api_time = time.time() - start_time

        print(
            f"OpenAI API time: {api_time:.2f} seconds"
        )

        result = response.output_text.strip()

        print("\nRAW AI RESULT:")
        print(result)

        # =================================================
        # PARSE JSON
        # =================================================

        try:

            evaluation = json.loads(result)

        except Exception:

            print(
                "Could not parse AI JSON."
            )

            evaluation = {
                "score": 0,
                "feedback": result,
                "action": "complete",
                "next_question": ""
            }

        # =================================================
        # SCORE
        # =================================================

        score = evaluation.get(
            "score",
            0
        )

        try:

            score = float(score)

        except Exception:

            score = 0

        score = max(
            0,
            min(10, score)
        )

        # =================================================
        # FEEDBACK
        # =================================================

        feedback = evaluation.get(
            "feedback",
            ""
        )

        if not isinstance(
            feedback,
            str
        ):

            feedback = str(
                feedback
            )

        # =================================================
        # ACTION
        # =================================================

        action = evaluation.get(
            "action",
            "next"
        )

        if action not in [
            "next",
            "followup",
            "complete"
        ]:

            action = "next"

        # =================================================
        # NEXT QUESTION
        # =================================================

        next_question = evaluation.get(
            "next_question",
            ""
        )

        if not isinstance(
            next_question,
            str
        ):

            next_question = str(
                next_question
            )

        next_question = next_question.strip()

        # =================================================
        # SAFETY RULE
        # =================================================

        # If this is the final main question,
        # force completion.

        if question_number >= total_questions:

            action = "complete"
            next_question = ""

        # If this is a follow-up, AI must not create
        # another follow-up.

        if is_followup and action == "followup":

            action = "next"

        # =================================================
        # FINAL RESULT
        # =================================================

        final_result = {

            "score": score,

            "feedback":
                feedback,

            "action":
                action,

            "next_question":
                next_question
        }

        total_time = time.time() - start_time

        print(
            f"\nTotal AI processing time: "
            f"{total_time:.2f} seconds"
        )

        print("\nFINAL AI RESULT:")
        print(
            json.dumps(
                final_result,
                indent=4
            )
        )

        print("========== AI PROCESSING END ==========\n")

        return final_result

    except Exception as e:

        print(
            "\nAI PROCESSING ERROR:",
            str(e)
        )

        print(
            "========== AI PROCESSING END ==========\n"
        )

        return {

            "score": 0,

            "feedback":
                "Unable to evaluate answer.",

            "action":
                "complete",

            "next_question":
                ""
        }


# =========================================================
# OLD EVALUATE FUNCTION
# =========================================================
#
# Kept only for compatibility with any other code that
# might still import evaluate_answer.
#
# DO NOT USE THIS FROM /api/process-answer.
#
# =========================================================

def evaluate_answer(
    question: str,
    answer: str
):

    prompt = f"""
Evaluate this technical interview answer.

Question:
{question}

Answer:
{answer}

Give a score from 0 to 10 based on:
- correctness
- technical understanding
- relevance

Return ONLY JSON:

{{
    "score": 0,
    "feedback": "one short sentence"
}}
"""

    response = client.responses.create(
        model="gpt-4o-mini",
        input=prompt
    )

    result = response.output_text.strip()

    try:

        evaluation = json.loads(
            result
        )

        score = float(
            evaluation.get(
                "score",
                0
            )
        )

        score = max(
            0,
            min(10, score)
        )

        return {

            "score":
                score,

            "feedback":
                str(
                    evaluation.get(
                        "feedback",
                        ""
                    )
                )
        }

    except Exception:

        return {

            "score":
                0,

            "feedback":
                result
        }


# =========================================================
# OLD FOLLOW-UP FUNCTION
# =========================================================
#
# Kept only for compatibility.
#
# DO NOT USE THIS FROM /api/process-answer.
#
# =========================================================

def generate_followup_question(
    question: str,
    answer: str,
    domain: str
):

    prompt = f"""
You are an expert technical interviewer.

Interview Domain:
{domain}

Original Question:
{question}

Candidate Answer:
{answer}

Generate ONE concise follow-up technical question.

Return ONLY valid JSON:

{{
    "followup_question": "Follow-up question here"
}}
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    result = response.output_text.strip()

    try:

        followup = json.loads(
            result
        )

        if isinstance(
            followup,
            dict
        ):

            return followup.get(
                "followup_question",
                ""
            )

    except Exception:

        pass

    return ""


# =========================================================
# GENERATE COMPLETE INTERVIEW REPORT - FAST
# =========================================================

def generate_interview_report(
    candidate_name: str = "",
    candidate_email: str = "",
    candidate_phone: str = "",
    role: str = "",
    company: str = "",
    domain: str = "",
    experience: str = "",
    skills: str = "",
    candidate_summary: str = "",
    answers: list = None,
    total_questions: int = 0
):

    if answers is None:
        answers = []

    print("\n======================================")
    print("GENERATING FAST INTERVIEW REPORT")
    print("======================================")

    start_time = time.perf_counter()

    # ---------------------------------------------------------
    # PREPARE ONLY REQUIRED DATA
    # ---------------------------------------------------------

    interview_data = []

    scores = []

    for index, item in enumerate(answers, start=1):

        question = str(
            item.get("question", "")
        ).strip()

        answer = str(
            item.get("answer", "")
        ).strip()

        score = item.get("score", 0)

        feedback = str(
            item.get("feedback", "")
        ).strip()

        # Store score for Python-side calculation
        try:
            numeric_score = float(score)
            numeric_score = max(0, min(10, numeric_score))
            scores.append(numeric_score)
        except Exception:
            numeric_score = 0

        interview_data.append({
            "q": index,
            "question": question,
            "answer": answer,
            "score": numeric_score,
            "feedback": feedback
        })

    # ---------------------------------------------------------
    # CALCULATE OVERALL SCORE IN PYTHON
    # ---------------------------------------------------------
    # This avoids asking the LLM to calculate the score.

    if scores:
        overall_score = round(
            sum(scores) / len(scores),
            1
        )
    else:
        overall_score = 0.0

    # ---------------------------------------------------------
    # CALCULATE RECOMMENDATION IN PYTHON
    # ---------------------------------------------------------

    if overall_score >= 9.0:
        recommendation = "Strong Hire"
    elif overall_score >= 7.5:
        recommendation = "Hire"
    elif overall_score >= 5.0:
        recommendation = "Consider"
    else:
        recommendation = "No Hire"

    # ---------------------------------------------------------
    # COMPACT JSON
    # ---------------------------------------------------------

    interview_json = json.dumps(
        interview_data,
        ensure_ascii=False,
        separators=(",", ":")
    )

    # ---------------------------------------------------------
    # MUCH SHORTER PROMPT
    # ---------------------------------------------------------

    prompt = f"""
You are a technical interview evaluator.

Create a concise professional interview report.

Use ONLY the interview information provided.
Do not invent information.

Candidate:
Name: {candidate_name}
Role: {role}
Domain: {domain}
Experience: {experience}

Interview data:
{interview_json}

The overall score is already calculated as:
{overall_score}

The recommendation is already calculated as:
{recommendation}

Return ONLY valid JSON in exactly this format:

{{
  "summary_text": "3 concise sentences summarizing interview performance.",
  "strengths": [
    "strength 1",
    "strength 2"
  ],
  "areas_of_improvement": [
    "improvement 1",
    "improvement 2"
  ],
  "interviewer_feedback": "2 concise sentences.",
  "detailed_feedback": {{
    "technical_skills": "Concise assessment.",
    "communication": "Concise assessment.",
    "problem_solving": "Concise assessment."
  }}
}}

Keep every field concise.
Do not repeat candidate profile information.
No markdown.
No explanation outside JSON.
"""

    # ---------------------------------------------------------
    # ONE FAST OPENAI CALL
    # ---------------------------------------------------------

    try:

        llm_start = time.perf_counter()

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt,
            max_output_tokens=450,
            text={
                "format": {
                    "type": "json_object"
                }
            }
        )

        result = response.output_text.strip()

        llm_time = time.perf_counter() - llm_start

        print(
            f"LLM REPORT TIME: {llm_time:.2f} seconds"
        )

    except Exception as e:

        print(
            "\nOPENAI REPORT GENERATION ERROR:",
            str(e)
        )

        return {
            "overall_score": overall_score,
            "summary_text": "",
            "strengths": [],
            "areas_of_improvement": [],
            "interviewer_feedback": "",
            "recommendation": recommendation,
            "detailed_feedback": {
                "technical_skills": "",
                "communication": "",
                "problem_solving": ""
            }
        }

    # ---------------------------------------------------------
    # PARSE RESPONSE
    # ---------------------------------------------------------

    try:

        # Remove accidental markdown fences

        if result.startswith("```"):

            result = result.replace(
                "```json",
                ""
            )

            result = result.replace(
                "```",
                ""
            )

            result = result.strip()

        report = json.loads(result)

        if not isinstance(report, dict):
            raise ValueError(
                "LLM returned invalid report."
            )

        # -----------------------------------------------------
        # FORCE PYTHON-CALCULATED SCORE
        # -----------------------------------------------------

        report["overall_score"] = overall_score

        # -----------------------------------------------------
        # FORCE PYTHON-CALCULATED RECOMMENDATION
        # -----------------------------------------------------

        report["recommendation"] = recommendation

        # -----------------------------------------------------
        # SUMMARY
        # -----------------------------------------------------

        summary = report.get(
            "summary_text",
            ""
        )

        report["summary_text"] = str(
            summary
        ).strip()

        # -----------------------------------------------------
        # STRENGTHS
        # -----------------------------------------------------

        strengths = report.get(
            "strengths",
            []
        )

        if not isinstance(strengths, list):
            strengths = []

        report["strengths"] = [
            str(item).strip()
            for item in strengths
            if str(item).strip()
        ][:3]

        # -----------------------------------------------------
        # AREAS OF IMPROVEMENT
        # -----------------------------------------------------

        improvements = report.get(
            "areas_of_improvement",
            []
        )

        if not isinstance(improvements, list):
            improvements = []

        report["areas_of_improvement"] = [
            str(item).strip()
            for item in improvements
            if str(item).strip()
        ][:3]

        # -----------------------------------------------------
        # INTERVIEWER FEEDBACK
        # -----------------------------------------------------

        interviewer_feedback = report.get(
            "interviewer_feedback",
            ""
        )

        report["interviewer_feedback"] = str(
            interviewer_feedback
        ).strip()

        # -----------------------------------------------------
        # DETAILED FEEDBACK
        # -----------------------------------------------------

        detailed = report.get(
            "detailed_feedback",
            {}
        )

        if not isinstance(detailed, dict):
            detailed = {}

        report["detailed_feedback"] = {
            "technical_skills": str(
                detailed.get(
                    "technical_skills",
                    ""
                )
            ).strip(),

            "communication": str(
                detailed.get(
                    "communication",
                    ""
                )
            ).strip(),

            "problem_solving": str(
                detailed.get(
                    "problem_solving",
                    ""
                )
            ).strip()
        }

        # -----------------------------------------------------
        # TOTAL TIME
        # -----------------------------------------------------

        total_time = time.perf_counter() - start_time

        print(
            f"TOTAL REPORT GENERATION TIME: "
            f"{total_time:.2f} seconds"
        )

        print("\n======================================")
        print("FINAL INTERVIEW REPORT")
        print("======================================")

        print(
            json.dumps(
                report,
                indent=2,
                ensure_ascii=False
            )
        )

        return report

    except Exception as e:

        print(
            "\nREPORT JSON PARSE ERROR:",
            str(e)
        )

        print("\nRAW RESULT:")
        print(result)

        return {
            "overall_score": overall_score,
            "summary_text": (
                "Unable to generate the interview summary."
            ),
            "strengths": [],
            "areas_of_improvement": [],
            "interviewer_feedback": (
                "Unable to generate interviewer feedback."
            ),
            "recommendation": recommendation,
            "detailed_feedback": {
                "technical_skills": "",
                "communication": "",
                "problem_solving": ""
            }
        }         
            
            
            # =========================================================
# PROCESS ANSWER WITH AI
# ONE OPENAI CALL
# =========================================================

def process_answer_with_ai(
    question: str,
    answer: str,
    domain: str,
    question_number: int,
    total_questions: int,
    candidate_name: str = "",
    experience: str = "",
    current_role: str = "",
    current_company: str = "",
    skills: str = "",
    summary: str = "",
    reference_questions: list = None,
    is_followup: bool = False
):

    if reference_questions is None:
        reference_questions = []

    print("\n========== AI PROCESSING START ==========")

    # -----------------------------------------------------
    # REFERENCE QUESTIONS
    # -----------------------------------------------------

    reference_text = "\n".join(
        f"- {q}"
        for q in reference_questions
    )

    # -----------------------------------------------------
    # PROMPT
    # -----------------------------------------------------

    prompt = f"""
You are an expert AI technical interviewer.

You are conducting a technical interview for IntelliHire.

Your task is to evaluate the candidate's answer AND,
in the SAME RESPONSE, decide what question should come next.

IMPORTANT:
This must be completed in ONE AI response.

Do NOT make another AI call.

=========================================================
CANDIDATE INFORMATION
=========================================================

Candidate Name:
{candidate_name}

Experience:
{experience}

Current Role:
{current_role}

Current Company:
{current_company}

Skills:
{skills}

Summary:
{summary}

Interview Domain:
{domain}

=========================================================
CURRENT QUESTION
=========================================================

Question:
{question}

Candidate Answer:
{answer}

Question Number:
{question_number}

Total Main Questions:
{total_questions}

Is This A Follow-up Answer:
{is_followup}

=========================================================
REFERENCE QUESTIONS
=========================================================

{reference_text}

These questions are ONLY references.

Do not copy them exactly.

=========================================================
STEP 1 — EVALUATE THE ANSWER
=========================================================

Give a score from 0 to 10.

Consider:

- correctness
- technical understanding
- relevance
- completeness
- practical knowledge
- clarity

Return a short feedback sentence.

=========================================================
STEP 2 — DECIDE NEXT ACTION
=========================================================

If this is a FOLLOW-UP answer:

DO NOT generate another follow-up.

The next action MUST be:

"next"

Generate ONE new main technical interview question.

The main question number should increase by 1.

---------------------------------------------------------

If this is a NORMAL MAIN QUESTION:

If score is BELOW 4:

The action MUST be:

"followup"

Generate ONE follow-up question related to the
same technical topic.

The question number MUST NOT increase.

---------------------------------------------------------

If this is a NORMAL MAIN QUESTION and score is 4 or above:

The action MUST be:

"next"

Generate ONE new main technical interview question.

The question number should increase by 1.

---------------------------------------------------------

If the current main question is the FINAL question:

If this is a normal question and:

score < 4:
    generate a follow-up.

Otherwise:
    action = "complete"

If this is already a follow-up answer:
    action = "complete"

=========================================================
NEXT QUESTION RULES
=========================================================

For "followup":

- Stay on the same technical topic.
- Test whether the candidate understands the concept.
- Do not repeat the original question.
- Keep it concise.
- Do not provide an answer.

For "next":

- Generate a NEW technical interview question.
- Match the candidate's domain and experience.
- Use the reference questions only as guidance.
- Do not copy reference questions.
- Test practical technical knowledge.
- Do not provide an answer.
- Do not provide explanations.

For "complete":

next_question must be an empty string.

=========================================================
OUTPUT
=========================================================

Return ONLY valid JSON.

Use exactly this structure:

{{
    "score": 0,
    "feedback": "",

    "action": "next",

    "next_question": "",

    "question_number": 1
}}

Allowed actions:

"followup"
"next"
"complete"

Rules:

- If action = "followup":
    next_question contains the follow-up question.
    question_number stays the same.

- If action = "next":
    next_question contains the next main question.
    question_number increases by 1.

- If action = "complete":
    next_question is "".
    question_number stays unchanged.
"""

    # -----------------------------------------------------
    # SINGLE OPENAI CALL
    # -----------------------------------------------------

    try:

        print("Calling OpenAI ONCE...")

        import time

        api_start = time.time()

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        api_time = time.time() - api_start

        print(
            f"OpenAI API time: {api_time:.2f} seconds"
        )

        result = response.output_text.strip()

        print("\n========== RAW AI RESULT ==========")
        print(result)
        print("====================================")

        # -------------------------------------------------
        # PARSE JSON
        # -------------------------------------------------

        try:

            data = json.loads(result)

        except Exception:

            print("AI JSON parsing failed.")

            return {
                "score": 0,
                "feedback": result,
                "action": "complete",
                "next_question": "",
                "question_number": question_number
            }

        # -------------------------------------------------
        # SCORE
        # -------------------------------------------------

        try:

            score = float(
                data.get("score", 0)
            )

        except Exception:

            score = 0

        score = max(
            0,
            min(10, score)
        )

        # -------------------------------------------------
        # FEEDBACK
        # -------------------------------------------------

        feedback = data.get(
            "feedback",
            ""
        )

        if not isinstance(
            feedback,
            str
        ):
            feedback = str(feedback)

        # -------------------------------------------------
        # ACTION
        # -------------------------------------------------

        action = data.get(
            "action",
            "complete"
        )

        if action not in [
            "followup",
            "next",
            "complete"
        ]:

            action = "complete"

        # -------------------------------------------------
        # NEXT QUESTION
        # -------------------------------------------------

        next_question = data.get(
            "next_question",
            ""
        )

        if not isinstance(
            next_question,
            str
        ):
            next_question = str(
                next_question
            )

        # -------------------------------------------------
        # QUESTION NUMBER
        # -------------------------------------------------

        try:

            returned_question_number = int(
                data.get(
                    "question_number",
                    question_number
                )
            )

        except Exception:

            returned_question_number = question_number

        # -------------------------------------------------
        # SAFETY CHECKS
        # -------------------------------------------------

        if action == "followup":

            returned_question_number = (
                question_number
            )

        elif action == "next":

            returned_question_number = (
                question_number + 1
            )

        elif action == "complete":

            next_question = ""

            returned_question_number = (
                question_number
            )

        # -------------------------------------------------
        # FINAL RESULT
        # -------------------------------------------------

        final_result = {

            "score": score,

            "feedback": feedback,

            "action": action,

            "next_question":
                next_question.strip(),

            "question_number":
                returned_question_number
        }

        print("\n========== AI PROCESSING RESULT ==========")
        print(
            json.dumps(
                final_result,
                indent=4
            )
        )
        print("==========================================")

        return final_result

    except Exception as e:

        print(
            "AI PROCESSING ERROR:",
            str(e)
        )

        return {

            "score": 0,

            "feedback":
                "Unable to evaluate the answer.",

            "action": "complete",

            "next_question": "",

            "question_number":
                question_number
        }