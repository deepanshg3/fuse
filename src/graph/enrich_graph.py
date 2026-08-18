import json
from pathlib import Path


GRAPH_FILE = Path("data/code_graph.json")
SUMMARY_FILE = Path("data/summaries.json")
OUTPUT_FILE = Path("data/enriched_code_graph.json")
LOG_FILE = Path("data/enrichment_report.json")


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# LEVEL 2 + LEVEL 3
# FILE / SYMBOL ENRICHMENT
# ============================================================

def enrich_file(
    graph_data: dict,
    file_path: str,
    summary_data: dict,
):
    """
    Insert semantic descriptions into the corresponding
    file, class, function, and method nodes.
    """

    enriched = []
    missed = []

    # --------------------------------------------------------
    # FILE SUMMARY
    # --------------------------------------------------------

    file_summary = summary_data.get("file_summary")

    if not file_summary:
        missed.append({
            "type": "file",
            "file": file_path,
            "reason": "file_summary missing or empty",
        })

    # --------------------------------------------------------
    # BUILD SYMBOL LOOKUP
    # --------------------------------------------------------

    generated_symbols = summary_data.get(
        "symbols",
        [],
    )

    if not isinstance(generated_symbols, list):
        raise ValueError(
            "'symbols' must be a list in summary data."
        )

    symbol_lookup = {}

    for symbol in generated_symbols:

        name = symbol.get("name")
        parent = symbol.get("parent", "")
        line = symbol.get("line")
        description = symbol.get("description")

        if not name or line is None:
            missed.append({
                "type": "symbol",
                "file": file_path,
                "name": name,
                "parent": parent,
                "line": line,
                "reason": "invalid symbol metadata",
            })
            continue

        if not description:
            missed.append({
                "type": "symbol",
                "file": file_path,
                "name": name,
                "parent": parent,
                "line": line,
                "reason": "symbol description missing or empty",
            })
            continue

        key = (
            name,
            parent,
            line,
        )

        symbol_lookup[key] = description

    # --------------------------------------------------------
    # WALK GRAPH
    # --------------------------------------------------------

    for node in graph_data["nodes"]:

        node_type = node.get("type")

        # ====================================================
        # FILE NODE
        # ====================================================

        if (
            node_type == "file"
            and node.get("path") == file_path
        ):

            if file_summary:

                node["description"] = file_summary

                enriched.append({
                    "node_id": node["id"],
                    "type": "file",
                    "name": node["name"],
                    "file": file_path,
                })

            continue

        # ====================================================
        # SYMBOL NODES
        # ====================================================

        if node_type not in {
            "class",
            "function",
            "method",
        }:
            continue

        if node.get("file") != file_path:
            continue

        name = node.get("name")
        parent = node.get("parent", "")
        line = node.get("line")

        key = (
            name,
            parent,
            line,
        )

        description = symbol_lookup.get(key)

        if not description:

            missed.append({
                "node_id": node["id"],
                "type": node_type,
                "name": name,
                "parent": parent,
                "line": line,
                "file": file_path,
                "reason": "symbol description not found",
            })

            continue

        # ----------------------------------------------------
        # INSERT DESCRIPTION
        # ----------------------------------------------------

        node["description"] = description

        enriched.append({
            "node_id": node["id"],
            "type": node_type,
            "name": name,
            "parent": parent,
            "line": line,
            "file": file_path,
        })

    return {
        "file": file_path,
        "enriched": enriched,
        "missed": missed,
    }


# ============================================================
# LEVEL 1
# MODULE ENRICHMENT
# ============================================================

def enrich_module(
    graph_data: dict,
    module_name: str,
    summary_data: dict,
):
    """
    Insert a Level 1 semantic description into
    the corresponding module node.
    """

    enriched = []
    missed = []

    description = summary_data.get(
        "module_summary"
    )

    if not description:

        return {
            "module": module_name,
            "enriched": [],
            "missed": [{
                "type": "module",
                "name": module_name,
                "reason": "module_summary missing or empty",
            }],
        }

    # --------------------------------------------------------
    # FIND MODULE NODE
    # --------------------------------------------------------

    for node in graph_data["nodes"]:

        if node.get("type") != "module":
            continue

        if node.get("name") != module_name:
            continue

        node["description"] = description

        enriched.append({
            "node_id": node["id"],
            "type": "module",
            "name": module_name,
        })

        break

    else:

        missed.append({
            "type": "module",
            "name": module_name,
            "reason": "module node not found in graph",
        })

    return {
        "module": module_name,
        "enriched": enriched,
        "missed": missed,
    }


# ============================================================
# FILE GRAPH SAVE
# ============================================================

def enrich_and_save(
    file_path: str,
    summary_data: dict,
):
    """
    Load the current graph, enrich one file,
    and persist the updated graph.
    """

    # --------------------------------------------------------
    # LOAD CURRENT GRAPH
    # --------------------------------------------------------

    if OUTPUT_FILE.exists():

        graph_data = load_json(
            OUTPUT_FILE
        )

    else:

        graph_data = load_json(
            GRAPH_FILE
        )

    # --------------------------------------------------------
    # ENRICH
    # --------------------------------------------------------

    result = enrich_file(
        graph_data,
        file_path,
        summary_data,
    )

    # --------------------------------------------------------
    # SAVE GRAPH
    # --------------------------------------------------------

    save_json(
        OUTPUT_FILE,
        graph_data,
    )

    return result


# ============================================================
# MODULE GRAPH SAVE
# ============================================================

def enrich_module_and_save(
    module_name: str,
    summary_data: dict,
):
    """
    Load the current graph, enrich one module,
    and persist the updated graph.
    """

    if OUTPUT_FILE.exists():

        graph_data = load_json(
            OUTPUT_FILE
        )

    else:

        graph_data = load_json(
            GRAPH_FILE
        )

    result = enrich_module(
        graph_data,
        module_name,
        summary_data,
    )

    save_json(
        OUTPUT_FILE,
        graph_data,
    )

    return result


# ============================================================
# ENRICHMENT REPORT HELPERS
# ============================================================

def _load_or_create_report():
    """
    Load the persistent enrichment report or create
    an empty report with separate file/module sections.
    """

    if LOG_FILE.exists():

        report = load_json(
            LOG_FILE
        )

    else:

        report = {
            "files": {},
            "modules": {},
            "totals": {
                "files_processed": 0,
                "modules_processed": 0,
                "nodes_enriched": 0,
                "nodes_missed": 0,
            },
        }

    # --------------------------------------------------------
    # Backward compatibility with older reports
    # --------------------------------------------------------

    report.setdefault(
        "files",
        {},
    )

    report.setdefault(
        "modules",
        {},
    )

    report.setdefault(
        "totals",
        {},
    )

    report["totals"].setdefault(
        "files_processed",
        0,
    )

    report["totals"].setdefault(
        "modules_processed",
        0,
    )

    report["totals"].setdefault(
        "nodes_enriched",
        0,
    )

    report["totals"].setdefault(
        "nodes_missed",
        0,
    )

    return report


def save_file_enrichment_report(
    file_path: str,
    result: dict,
):
    """
    Save enrichment results for one file.

    If the file is retried, its previous contribution
    is removed before storing the new result.
    """

    report = _load_or_create_report()

    previous = report["files"].get(
        file_path
    )

    if previous:

        report["totals"]["nodes_enriched"] -= len(
            previous.get("enriched", [])
        )

        report["totals"]["nodes_missed"] -= len(
            previous.get("missed", [])
        )

        report["totals"]["files_processed"] -= 1

    report["files"][file_path] = result

    report["totals"]["files_processed"] += 1

    report["totals"]["nodes_enriched"] += len(
        result.get("enriched", [])
    )

    report["totals"]["nodes_missed"] += len(
        result.get("missed", [])
    )

    save_json(
        LOG_FILE,
        report,
    )


def save_module_enrichment_report(
    module_name: str,
    result: dict,
):
    """
    Save enrichment results for one module.

    If the module is retried, its previous contribution
    is removed before storing the new result.
    """

    report = _load_or_create_report()

    previous = report["modules"].get(
        module_name
    )

    if previous:

        report["totals"]["nodes_enriched"] -= len(
            previous.get("enriched", [])
        )

        report["totals"]["nodes_missed"] -= len(
            previous.get("missed", [])
        )

        report["totals"]["modules_processed"] -= 1

    report["modules"][module_name] = result

    report["totals"]["modules_processed"] += 1

    report["totals"]["nodes_enriched"] += len(
        result.get("enriched", [])
    )

    report["totals"]["nodes_missed"] += len(
        result.get("missed", [])
    )

    save_json(
        LOG_FILE,
        report,
    )


# ============================================================
# MANUAL TEST
# ============================================================

def main():

    summaries = load_json(
        SUMMARY_FILE
    )

    file_path = "app.py"

    if file_path not in summaries:

        raise ValueError(
            f"No summary found for {file_path}"
        )

    result = enrich_and_save(
        file_path,
        summaries[file_path],
    )

    save_file_enrichment_report(
        file_path,
        result,
    )

    print(
        f"Enriched: {len(result['enriched'])}"
    )

    print(
        f"Missed: {len(result['missed'])}"
    )


if __name__ == "__main__":
    main()