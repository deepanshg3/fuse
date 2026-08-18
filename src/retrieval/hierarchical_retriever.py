import json
from pathlib import Path

from src.retrieval.llm import call_llm


GRAPH_FILE = Path(
    "data/enriched_code_graph.json"
)


class HierarchicalRetriever:

    def __init__(self):
        with GRAPH_FILE.open(
            "r",
            encoding="utf-8",
        ) as f:
            self.graph = json.load(f)

        self.nodes = self.graph["nodes"]
        self.edges = self.graph["edges"]

    # ======================================================
    # GRAPH HELPERS
    # ======================================================

    def get_modules(self):
        return [
            node
            for node in self.nodes
            if node.get("type") == "module"
        ]

    def get_files(self, module_name):
        return [
            node
            for node in self.nodes
            if (
                node.get("type") == "file"
                and node.get("module") == module_name
            )
        ]

    def get_symbols(self, file_path):
        return [
            node
            for node in self.nodes
            if (
                node.get("type")
                in {"class", "function", "method"}
                and node.get("file") == file_path
            )
        ]

    def expand_module_files(self, modules):
        """
        Get files belonging to the selected modules
        and expand them by one file-to-file relationship hop.
        """

        # --------------------------------------------------
        # Primary files belonging to selected modules
        # --------------------------------------------------

        primary_files = []

        for module in modules:
            primary_files.extend(
                self.get_files(module)
            )

        primary_paths = {
            file["path"]
            for file in primary_files
        }

        expanded_paths = set(
            primary_paths
        )

        primary_ids = {
            f"file:{path}"
            for path in primary_paths
        }

        # --------------------------------------------------
        # One-hop file-to-file expansion
        # --------------------------------------------------

        for edge in self.edges:

            source = edge.get("source")
            target = edge.get("target")

            # Only consider relationships between
            # file nodes. This excludes:
            #
            # module -> file
            # class -> method
            # function -> function
            #
            if not (
                isinstance(source, str)
                and isinstance(target, str)
                and source.startswith("file:")
                and target.startswith("file:")
            ):
                continue

            # Selected file -> dependency file
            if source in primary_ids:

                target_path = target.removeprefix(
                    "file:"
                )

                expanded_paths.add(
                    target_path
                )

            # Dependency file -> selected file
            if target in primary_ids:

                source_path = source.removeprefix(
                    "file:"
                )

                expanded_paths.add(
                    source_path
                )

        # --------------------------------------------------
        # Convert paths back into file nodes
        # --------------------------------------------------

        return [
            node
            for node in self.nodes
            if (
                node.get("type") == "file"
                and node.get("path") in expanded_paths
            )
        ]

    # ======================================================
    # LLM CALL 1
    # MODULE RETRIEVAL
    # ======================================================

    def retrieve_modules(self, query):

        modules = self.get_modules()

        module_context = []

        for module in modules:

            module_context.append({
                "name": module["name"],
                "description": module.get(
                    "description",
                    ""
                ),
            })

        prompt = f"""
You are the first-stage retrieval engine for a
codebase knowledge graph.

The user has asked:

"{query}"

Select the modules that are most relevant to solving
the user's problem.

MODULES:

{json.dumps(module_context, indent=2)}

Rules:
- Select only modules from the provided list.
- Do not invent module names.
- Select one or more modules only if relevant.
- Return ONLY valid JSON.

Format:

{{
  "modules": ["module_name"]
}}
"""

        result = call_llm(prompt)

        selected = result.get(
            "modules",
            []
        )

        valid_modules = {
            module["name"]
            for module in modules
        }

        return [
            name
            for name in selected
            if name in valid_modules
        ]

    # ======================================================
    # LLM CALL 2
    # FILE RETRIEVAL
    # ======================================================

    def retrieve_files(
        self,
        query,
        modules,
        candidate_files,
    ):

        file_context = []

        for file in candidate_files:

            file_context.append({
                "path": file["path"],
                "module": file.get(
                    "module",
                    ""
                ),
                "description": file.get(
                    "description",
                    ""
                ),
            })

        prompt = f"""
You are the second-stage retrieval engine for a
codebase knowledge graph.

The user's problem is:

"{query}"

The first retrieval stage selected these modules:

{json.dumps(modules, indent=2)}

The candidate files include files directly inside
those modules and files structurally connected to them.

Select the files that are most relevant to solving
the user's problem.

FILES:

{json.dumps(file_context, indent=2)}

Rules:
- Select only files from the provided list.
- Do not invent paths.
- Dependency files are included because they are
  structurally connected to files in the selected modules.
- Return only genuinely relevant files.
- Return ONLY valid JSON.

Format:

{{
  "files": ["path/to/file.py"]
}}
"""

        result = call_llm(prompt)

        selected = result.get(
            "files",
            []
        )

        valid_files = {
            file["path"]
            for file in candidate_files
        }

        return [
            path
            for path in selected
            if path in valid_files
        ]

    # ======================================================
    # LLM CALL 3
    # SYMBOL RETRIEVAL
    # ======================================================

    def retrieve_symbols(
        self,
        query,
        files,
    ):

        symbols = []

        for file_path in files:
            symbols.extend(
                self.get_symbols(file_path)
            )

        symbol_context = []

        for symbol in symbols:

            symbol_context.append({
                "file": symbol["file"],
                "type": symbol["type"],
                "name": symbol["name"],
                "parent": symbol.get(
                    "parent",
                    ""
                ),
                "line": symbol.get(
                    "line"
                ),
                "description": symbol.get(
                    "description",
                    ""
                ),
            })

        prompt = f"""
You are the third-stage retrieval engine for a
codebase knowledge graph.

The user's problem is:

"{query}"

The relevant files identified by the previous stage are:

{json.dumps(files, indent=2)}

Select the classes, functions and methods that are
most relevant to understanding or solving the problem.

SYMBOLS:

{json.dumps(symbol_context, indent=2)}

Rules:
- Select only symbols from the provided list.
- Do not invent symbols.
- Return the exact file, name, type, parent, and line
  information from the provided symbol.
- Do not modify or simplify these fields.
- Every selected symbol must correspond to exactly one
  symbol from the provided list.
- Prefer specific methods/functions over selecting an
  entire class unless the class itself is relevant.
- Return ONLY valid JSON.

Format:

{{
  "symbols": [
    {{
      "file": "app.py",
      "name": "dispatch_request",
      "type": "method",
      "parent": "Flask",
      "line": 1200
    }}
  ]
}}
"""

        result = call_llm(prompt)

        selected = result.get(
            "symbols",
            []
        )

        # Exact identity now includes parent + line.
        valid_symbols = {
            (
                symbol["file"],
                symbol["name"],
                symbol["type"],
                symbol.get("parent", ""),
                symbol.get("line"),
            )
            for symbol in symbols
        }

        final_symbols = []

        for symbol in selected:

            key = (
                symbol.get("file"),
                symbol.get("name"),
                symbol.get("type"),
                symbol.get("parent", ""),
                symbol.get("line"),
            )

            if key in valid_symbols:
                final_symbols.append(symbol)

        return final_symbols

    # ======================================================
    # COMPLETE 3-STAGE RETRIEVAL
    # ======================================================

    def retrieve(self, query):

        # --------------------------------------------------
        # CALL 1
        # --------------------------------------------------

        modules = self.retrieve_modules(
            query
        )

        # --------------------------------------------------
        # GRAPH EXPANSION
        # --------------------------------------------------

        candidate_files = self.expand_module_files(
            modules
        )

        # --------------------------------------------------
        # CALL 2
        # --------------------------------------------------

        files = self.retrieve_files(
            query,
            modules,
            candidate_files,
        )

        # --------------------------------------------------
        # CALL 3
        # --------------------------------------------------

        symbols = self.retrieve_symbols(
            query,
            files,
        )

        return {
            "query": query,
            "modules": modules,
            "candidate_files": [
                file["path"]
                for file in candidate_files
            ],
            "files": files,
            "symbols": symbols,
        }