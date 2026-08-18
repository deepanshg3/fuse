import json
import os

from dotenv import load_dotenv
from google import genai


load_dotenv()

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

MODEL = "gemini-3.1-flash-lite"


def call_llm(prompt: str) -> dict:
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )

    text = response.text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    return json.loads(text)