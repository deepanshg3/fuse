import time
from pathlib import Path

from parser.build_graph import build_graph

from summarizer.summarize_file import (
    summarize_file,
    save_summary,
)

from graph.enrich_graph import (
    enrich_and_save,
    save_file_enrichment_report,
)


# ============================================================
# CONFIG
# ============================================================

REPO_ROOT = Path(
    "test_repo/flask/src/flask"
)

FAILED_FILE = REPO_ROOT / "sansio/scaffold.py"

MAX_RETRIES = 3


# ============================================================
# GET SYMBOLS
# ============================================================

def get_file_symbols(
    graph,
    file_path: Path,
):
    """
    Extract the exact Tree-sitter symbols for the failed file.
    """

    relative_path = str(
        file_path.relative_to(
            REPO_ROOT
        )
    )

    symbols = []

    for node_id, data in graph.nodes(
        data=True
    ):

        if data.get("type") not in {
            "class",
            "function",
            "method",
        }:
            continue

        if data.get("file") != relative_path:
            continue

        symbols.append({
            "name": data.get("name"),
            "type": data.get("type"),
            "parent": data.get(
                "parent",
                "",
            ),
            "line": data.get("line"),
            "end_line": data.get(
                "end_line"
            ),
        })

    return symbols


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("FUSE — FAILED FILE RECOVERY")
    print("=" * 60)

    # --------------------------------------------------------
    # Validate file
    # --------------------------------------------------------

    if not FAILED_FILE.exists():

        raise FileNotFoundError(
            f"File not found: {FAILED_FILE}"
        )

    print(
        f"Target: {FAILED_FILE}"
    )

    # --------------------------------------------------------
    # Load existing structural graph
    #
    # IMPORTANT:
    # We do NOT need to rebuild the graph.
    # --------------------------------------------------------

    print(
        "\nLoading structural graph..."
    )

    graph = build_graph(
        REPO_ROOT
    )

    print(
        f"Graph loaded: "
        f"{graph.number_of_nodes()} nodes, "
        f"{graph.number_of_edges()} edges"
    )

    # --------------------------------------------------------
    # Get Tree-sitter symbols
    # --------------------------------------------------------

    symbols = get_file_symbols(
        graph,
        FAILED_FILE,
    )

    print(
        f"Tree-sitter symbols: "
        f"{len(symbols)}"
    )

    if not symbols:

        raise RuntimeError(
            "No symbols found for failed file."
        )

    # --------------------------------------------------------
    # Gemini recovery
    # --------------------------------------------------------

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        print(
            f"\nGemini attempt "
            f"{attempt}/{MAX_RETRIES}..."
        )

        try:

            # --------------------------------------------
            # LEVEL 2 + LEVEL 3
            # --------------------------------------------

            result = summarize_file(
                FAILED_FILE,
                symbols,
            )

            print(
                "✓ Gemini summary generated"
            )

            # --------------------------------------------
            # SAVE SUMMARY
            # --------------------------------------------

            save_summary(
                FAILED_FILE,
                result,
            )

            print(
                "✓ summaries.json updated"
            )

            # --------------------------------------------
            # ENRICH EXISTING GRAPH
            # --------------------------------------------

            relative_path = str(
                FAILED_FILE.relative_to(
                    REPO_ROOT
                )
            )

            enrichment = enrich_and_save(
                relative_path,
                result,
            )

            print(
                f"✓ Graph enriched: "
                f"{len(enrichment['enriched'])} nodes"
            )

            print(
                f"  Missed: "
                f"{len(enrichment['missed'])}"
            )

            # --------------------------------------------
            # SAVE REPORT
            # --------------------------------------------

            save_file_enrichment_report(
                relative_path,
                enrichment,
            )

            print(
                "✓ enrichment_report.json updated"
            )

            # --------------------------------------------
            # FINAL
            # --------------------------------------------

            print()
            print("=" * 60)
            print("RECOVERY SUCCESSFUL")
            print("=" * 60)

            print(
                f"File     : {relative_path}"
            )

            print(
                f"Symbols  : {len(symbols)}"
            )

            print(
                f"Enriched : "
                f"{len(enrichment['enriched'])}"
            )

            print(
                f"Missed   : "
                f"{len(enrichment['missed'])}"
            )

            return

        except Exception as error:

            last_error = error

            print(
                f"✗ Attempt failed: {error}"
            )

            if attempt < MAX_RETRIES:

                print(
                    "Waiting 5 seconds before retry..."
                )

                time.sleep(5)

    # --------------------------------------------------------
    # FAILED
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("RECOVERY FAILED")
    print("=" * 60)

    print(
        f"Last error: {last_error}"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()