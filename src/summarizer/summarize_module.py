import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


load_dotenv()

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)


OUTPUT_FILE = Path("data/module_summaries.json")


PROMPT = """
You are creating compact semantic metadata for a
codebase knowledge graph.

You are analyzing ONE Python module.

The module contains the following files and their
already-generated summaries.

Your task is to write ONE concise description of
what the entire module is responsible for.

Do NOT analyze the source code.
Use only the provided file summaries.

Return ONLY valid JSON:

{{
  "module_summary": "Short description."
}}

STRICT LENGTH LIMIT:
- module_summary: maximum 35 words.
- Exactly one sentence.
- Describe the overall responsibility of the module.
- Capture the major functionality represented by its files.
- Keep it factual and information-dense.
- Do not list individual files.
- Do not mention implementation details.
- Do not invent functionality.
- Return JSON only.

MODULE:
{module_name}

FILE SUMMARIES:
{file_summaries}
"""


def summarize_module(
    module_name: str,
    file_summaries: list[dict],
) -> dict:
    """
    Generate a semantic description for one module
    from its Level 2 file summaries.
    """

    summaries_text = json.dumps(
        file_summaries,
        indent=2,
        ensure_ascii=False,
    )

    prompt = PROMPT.format(
        module_name=module_name,
        file_summaries=summaries_text,
    )

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
    )

    text = response.text.strip()

    # Remove accidental markdown fences.
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    result = json.loads(text)

    # --------------------------------------------------
    # VALIDATION
    # --------------------------------------------------

    if not isinstance(result, dict):
        raise ValueError(
            "Gemini module response must be a JSON object."
        )

    if "module_summary" not in result:
        raise ValueError(
            "Gemini response missing 'module_summary'."
        )

    if not isinstance(
        result["module_summary"],
        str,
    ):
        raise ValueError(
            "'module_summary' must be a string."
        )

    if not result["module_summary"].strip():
        raise ValueError(
            "'module_summary' cannot be empty."
        )

    return result


def save_module_summary(
    module_name: str,
    result: dict,
):
    """
    Save or update one module summary without
    deleting summaries for other modules.
    """

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if OUTPUT_FILE.exists():

        with OUTPUT_FILE.open(
            "r",
            encoding="utf-8",
        ) as f:
            summaries = json.load(f)

    else:

        summaries = {}

    summaries[module_name] = result

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            summaries,
            f,
            indent=2,
            ensure_ascii=False,
        )