import os
 
from dotenv import load_dotenv

from openai import OpenAI

from deepgram import DeepgramClient
 
 
# Load .env

load_dotenv()
 
 
# =========================================================

# OPENAI

# =========================================================
 
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
 
client = OpenAI(

    api_key=OPENAI_API_KEY

)
 
 
def test_llm():

    response = client.responses.create(

        model="gpt-5",

        input="Reply with exactly: IntelliHire LLM connection successful."

    )
 
    return response.output_text
 
 
# =========================================================

# DEEPGRAM

# =========================================================
 
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
 
if not DEEPGRAM_API_KEY:

    print("❌ DEEPGRAM_API_KEY not found in .env")

else:

    deepgram = DeepgramClient(api_key=DEEPGRAM_API_KEY)
 
 
def test_deepgram():

    if not DEEPGRAM_API_KEY:

        return "❌ DEEPGRAM_API_KEY not found in .env"
 
    return "✅ Deepgram API key loaded"
 
 
# =========================================================

# TEST BOTH

# =========================================================
 
if __name__ == "__main__":
 
    print("Testing OpenAI...")

    print(test_llm())
 
    print()
 
    print("Testing Deepgram...")

    print(test_deepgram())
 