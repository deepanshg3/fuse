import time
from pathlib import Path

from parser.build_graph import build_graph, export_graph
from summarizer.summarize_module import summarize_file, save_summary
from graph.enrich_graph import enrich_and_save, save_summary as save_enrichment_report


# ============================================================
# CONFIG
# ============================================================

REPO_ROOT = Path("test_repo/flask/src/flask")

MAX_RETRIES = 2


# ============================================================
# FILE DISCOVERY
# ============================================================

def discover_files():
    """
    Find all Python source files in the target repository.
    """

    return sorted(
        file
        for file in REPO_ROOT.rglob("*.py")
        if "__pycache__" not in file.parts
    )


# ============================================================
# GRAPH INITIALIZATION
# ============================================================

def initialize_graph():
    """
    Build the structural knowledge graph before
    semantic enrichment begins.
    """

    print("[FUSE] Building structural knowledge graph...")

    graph = build_graph(REPO_ROOT)

    export_graph(graph)

    print(
        f"[FUSE] Structural graph ready: "
        f"{graph.number_of_nodes()} nodes, "
        f"{graph.number_of_edges()} edges"
    )


# ============================================================
# SUMMARIZATION
# ============================================================

def process_file(
    file_path: Path,
    index: int,
    total: int,
):
    """
    Summarize and enrich one source file.
    """

    relative_path = file_path.relative_to(
        REPO_ROOT
    )

    print(
        f"[{index}/{total}] "
        f"Gemini → {relative_path}",
        end=" ",
        flush=True,
    )

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            # --------------------------------------------
            # GEMINI
            # --------------------------------------------

            result = summarize_file(
                file_path
            )

            # --------------------------------------------
            # SAVE SUMMARY
            # --------------------------------------------

            save_summary(
                file_path,
                result,
            )

            # --------------------------------------------
            # ENRICH GRAPH
            # --------------------------------------------

            enrichment = enrich_and_save(
                str(relative_path),
                result,
            )

            # --------------------------------------------
            # SAVE ENRICHMENT REPORT
            # --------------------------------------------

            save_enrichment_report(
                str(relative_path),
                enrichment,
            )

            enriched = len(
                enrichment["enriched"]
            )

            missed = len(
                enrichment["missed"]
            )

            print(
                f"✓ "
                f"({enriched} enriched"
                f", {missed} missed)"
            )

            return {
                "status": "success",
                "file": str(relative_path),
                "enriched": enriched,
                "missed": missed,
                "attempts": attempt,
            }

        except Exception as error:

            last_error = error

            if attempt < MAX_RETRIES:

                print(
                    f"retry {attempt}...",
                    end=" ",
                    flush=True,
                )

                time.sleep(2)

            else:

                print(
                    f"✗ FAILED: {error}"
                )

    return {
        "status": "failed",
        "file": str(relative_path),
        "error": str(last_error),
        "attempts": MAX_RETRIES,
    }


# ============================================================
# ORCHESTRATOR
# ============================================================

def run():

    print("=" * 60)
    print("FUSE — CODEBASE KNOWLEDGE GRAPH BUILDER")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. DISCOVER REPOSITORY
    # --------------------------------------------------------

    files = discover_files()

    print(
        f"[FUSE] Found {len(files)} Python files"
    )

    if not files:
        raise RuntimeError(
            f"No Python files found in {REPO_ROOT}"
        )

    print()

    # --------------------------------------------------------
    # 2. BUILD STRUCTURAL GRAPH
    # --------------------------------------------------------

    initialize_graph()

    print()

    # --------------------------------------------------------
    # 3. SEMANTIC ENRICHMENT
    # --------------------------------------------------------

    print(
        "[FUSE] Starting semantic enrichment..."
    )

    start_time = time.time()

    results = []

    for index, file_path in enumerate(
        files,
        start=1,
    ):

        result = process_file(
            file_path,
            index,
            len(files),
        )

        results.append(result)

    elapsed = time.time() - start_time

    # --------------------------------------------------------
    # 4. FINAL REPORT
    # --------------------------------------------------------

    successful = [
        result
        for result in results
        if result["status"] == "success"
    ]

    failed = [
        result
        for result in results
        if result["status"] == "failed"
    ]

    total_enriched = sum(
        result.get("enriched", 0)
        for result in successful
    )

    total_missed = sum(
        result.get("missed", 0)
        for result in successful
    )

    print()
    print("=" * 60)
    print("FUSE COMPLETE")
    print("=" * 60)

    print(
        f"Files discovered : {len(files)}"
    )

    print(
        f"Files processed  : {len(successful)}"
    )

    print(
        f"Files failed     : {len(failed)}"
    )

    print(
        f"Nodes enriched   : {total_enriched}"
    )

    print(
        f"Nodes missed     : {total_missed}"
    )

    print(
        f"Time             : {elapsed:.1f}s"
    )

    print()
    print(
        "Output:"
    )

    print(
        "  data/enriched_code_graph.json"
    )

    print(
        "  data/summaries.json"
    )

    print(
        "  data/enrichment_report.json"
    )

    # --------------------------------------------------------
    # FAILED FILES
    # --------------------------------------------------------

    if failed:

        print()
        print("Failed files:")

        for result in failed:

            print(
                f"  ✗ {result['file']}"
            )

            print(
                f"    {result['error']}"
            )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run()