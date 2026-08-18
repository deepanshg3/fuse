import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


load_dotenv()

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)


REPO_ROOT = Path("test_repo/flask/src/flask")
OUTPUT_FILE = Path("data/summaries.json")


PROMPT = """
You are creating compact semantic metadata for a code knowledge graph.

Analyze the COMPLETE Python source file.

Tree-sitter has already analyzed this file and identified the exact
classes, functions, and methods that need descriptions.

Your job is ONLY to describe the symbols provided below.

IMPORTANT:
- You MUST provide exactly one description for EVERY symbol in the list.
- Do NOT omit any symbol.
- Do NOT create additional symbols.
- Use the provided name, parent, and line exactly as given.
- The line number identifies the exact symbol when names are duplicated.

Return ONLY valid JSON:

{{
  "file_summary": "Short description.",
  "symbols": [
    {{
      "name": "SymbolName",
      "parent": "ParentClass",
      "line": 123,
      "description": "Short description."
    }}
  ]
}}

STRICT LENGTH LIMITS:
- file_summary: maximum 25 words.
- class description: maximum 15 words.
- function/method description: maximum 12 words.
- Every description MUST be exactly one sentence.
- Keep descriptions factual and information-dense.
- Describe WHAT the symbol does, not HOW it implements it.
- Do not mention parameters, return values, examples, implementation details,
  error handling, or internal steps unless essential to its purpose.
- Do not repeat the symbol name in its description.
- Do not invent functionality.
- Do not create descriptions for symbols not present in the provided list.

FILE PATH:
{file_path}

SYMBOLS IDENTIFIED BY TREE-SITTER:
{symbols}

SOURCE CODE:
{source_code}
"""


def summarize_file(
    file_path: Path,
    symbols: list[dict],
) -> dict:
    """
    Generate semantic metadata for one Python source file.
    """

    source_code = file_path.read_text(
        encoding="utf-8"
    )

    symbol_text = json.dumps(
        symbols,
        indent=2,
        ensure_ascii=False,
    )

    prompt = PROMPT.format(
        file_path=file_path,
        symbols=symbol_text,
        source_code=source_code,
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

    # --------------------------------------------------------
    # BASIC RESPONSE VALIDATION
    # --------------------------------------------------------

    if "file_summary" not in result:
        raise ValueError(
            "Gemini response missing 'file_summary'."
        )

    if "symbols" not in result:
        raise ValueError(
            "Gemini response missing 'symbols'."
        )

    if not isinstance(result["symbols"], list):
        raise ValueError(
            "'symbols' must be a JSON list."
        )

    # --------------------------------------------------------
    # VALIDATE SYMBOL COUNT
    # --------------------------------------------------------

    if len(result["symbols"]) != len(symbols):
        raise ValueError(
            f"Gemini returned {len(result['symbols'])} symbols, "
            f"but Tree-sitter provided {len(symbols)}."
        )

    # --------------------------------------------------------
    # VALIDATE SYMBOL IDENTITIES
    # --------------------------------------------------------

    expected = {
        (
            symbol["name"],
            symbol.get("parent", ""),
            symbol["line"],
        )
        for symbol in symbols
    }

    returned = {
        (
            symbol["name"],
            symbol.get("parent", ""),
            symbol["line"],
        )
        for symbol in result["symbols"]
    }

    missing = expected - returned
    unexpected = returned - expected

    if missing:
        raise ValueError(
            f"Gemini omitted symbols: {sorted(missing)}"
        )

    if unexpected:
        raise ValueError(
            f"Gemini returned unexpected symbols: {sorted(unexpected)}"
        )

    # --------------------------------------------------------
    # VALIDATE DESCRIPTIONS
    # --------------------------------------------------------

    for symbol in result["symbols"]:

        if not symbol.get("description"):
            raise ValueError(
                f"Empty description for symbol: "
                f"{symbol.get('name')} "
                f"at line {symbol.get('line')}"
            )

    return result


def save_summary(
    file_path: Path,
    result: dict,
):
    """
    Save or update one file's summary without
    deleting summaries generated for other files.
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

    relative_path = str(
        file_path.relative_to(REPO_ROOT)
    )

    summaries[relative_path] = result

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