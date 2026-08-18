import json
from pathlib import Path


GRAPH_FILE = Path("data/code_graph.json")
SUMMARY_FILE = Path("data/summaries.json")
OUTPUT_FILE = Path("data/enriched_code_graph.json")
LOG_FILE = Path("data/enrichment_report.json")


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


def enrich_file(
    graph_data: dict,
    file_path: str,
    summary_data: dict,
):
    """
    Insert the semantic summary of one file into
    the corresponding file and symbol nodes.
    """

    enriched = []
    missed = []

    file_summary = summary_data.get("file_summary")

    symbols = summary_data.get(
        "symbols",
        {},
    )

    for node in graph_data["nodes"]:

        node_type = node.get("type")

        # --------------------------------------------------
        # FILE NODE
        # --------------------------------------------------

        if (
            node_type == "file"
            and node.get("path") == file_path
        ):

            if not file_summary:

                missed.append({
                    "node_id": node["id"],
                    "type": "file",
                    "name": node["name"],
                    "file": file_path,
                    "reason": "file_summary missing or empty",
                })

            else:

                node["description"] = file_summary

                enriched.append({
                    "node_id": node["id"],
                    "type": "file",
                    "name": node["name"],
                    "file": file_path,
                })

            continue

        # --------------------------------------------------
        # SYMBOL NODES
        # --------------------------------------------------

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

        if parent:
            summary_key = f"{parent}.{name}"
        else:
            summary_key = name

        description = symbols.get(summary_key)

        if not description:

            missed.append({
                "node_id": node["id"],
                "type": node_type,
                "name": name,
                "parent": parent,
                "file": file_path,
                "expected_summary_key": summary_key,
                "available_summary_keys": list(
                    symbols.keys()
                ),
                "reason": "symbol summary key not found",
            })

            continue

        node["description"] = description

        enriched.append({
            "node_id": node["id"],
            "type": node_type,
            "name": name,
            "parent": parent,
            "file": file_path,
            "summary_key": summary_key,
        })

    return {
        "file": file_path,
        "enriched": enriched,
        "missed": missed,
    }


def enrich_and_save(
    file_path: str,
    summary_data: dict,
):
    """
    Load the current graph, enrich one file,
    and persist the updated graph.
    """

    # --------------------------------------------------
    # LOAD CURRENT GRAPH
    # --------------------------------------------------

    if OUTPUT_FILE.exists():

        graph_data = load_json(
            OUTPUT_FILE
        )

    else:

        graph_data = load_json(
            GRAPH_FILE
        )

    # --------------------------------------------------
    # ENRICH
    # --------------------------------------------------

    result = enrich_file(
        graph_data,
        file_path,
        summary_data,
    )

    # --------------------------------------------------
    # SAVE GRAPH
    # --------------------------------------------------

    save_json(
        OUTPUT_FILE,
        graph_data,
    )

    return result


def save_summary(
    file_path: str,
    result: dict,
):
    """
    Save enrichment result to the persistent
    enrichment report.
    """

    if LOG_FILE.exists():

        report = load_json(
            LOG_FILE
        )

    else:

        report = {
            "files": {},
            "totals": {
                "files_processed": 0,
                "nodes_enriched": 0,
                "nodes_missed": 0,
            },
        }

    # Remove previous result if this file
    # is being retried.
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
        result["enriched"]
    )

    report["totals"]["nodes_missed"] += len(
        result["missed"]
    )

    save_json(
        LOG_FILE,
        report,
    )


def main():

    # --------------------------------------------------
    # MANUAL TEST
    # --------------------------------------------------

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

    save_summary(
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