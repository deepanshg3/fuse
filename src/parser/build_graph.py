from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field

import networkx as nx
from tree_sitter import Language, Parser
import tree_sitter_python as tspython


# ============================================================
# CONFIG
# ============================================================

REPO_ROOT = Path("test_repo/flask/src/flask")
OUTPUT_DIR = Path("data")

PYTHON_LANGUAGE = Language(tspython.language())


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class Symbol:
    name: str
    symbol_type: str
    file: str
    line: int
    end_line: int
    parent: str | None = None
    bases: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)


@dataclass
class FileInfo:
    path: str
    module: str
    imports: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)


# ============================================================
# TREE-SITTER
# ============================================================

def create_parser() -> Parser:
    parser = Parser(PYTHON_LANGUAGE)
    return parser


# ============================================================
# NODE HELPERS
# ============================================================

def node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def children_of_type(node, node_type: str):
    return [child for child in node.children if child.type == node_type]


# ============================================================
# IMPORT EXTRACTION
# ============================================================

def extract_imports(root, source: bytes) -> list[str]:
    imports = []

    def walk(node):
        if node.type == "import_statement":
            imports.append(node_text(node, source).strip())

        elif node.type == "import_from_statement":
            imports.append(node_text(node, source).strip())

        for child in node.children:
            walk(child)

    walk(root)
    return imports


# ============================================================
# FUNCTION CALL EXTRACTION
# ============================================================

def extract_calls(function_node, source: bytes) -> list[str]:
    calls = []

    def walk(node):
        if node.type == "call":
            function_part = node.child_by_field_name("function")

            if function_part:
                calls.append(node_text(function_part, source))

        for child in node.children:
            walk(child)

    walk(function_node)

    return sorted(set(calls))


# ============================================================
# CLASS / FUNCTION EXTRACTION
# ============================================================

def extract_symbols(root, source: bytes, file_path: str) -> list[Symbol]:

    symbols = []

    def walk(node, current_class=None):

        # -------------------------
        # CLASS
        # -------------------------

        if node.type == "class_definition":

            name_node = node.child_by_field_name("name")

            if name_node is None:
                return

            class_name = node_text(name_node, source)

            bases = []

            arguments = node.child_by_field_name("superclasses")

            if arguments:
                for child in arguments.children:
                    if child.type not in {"(", ")", ","}:
                        bases.append(node_text(child, source))

            class_symbol = Symbol(
                name=class_name,
                symbol_type="class",
                file=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                bases=bases,
            )

            symbols.append(class_symbol)

            # Continue traversal inside class
            for child in node.children:
                walk(child, current_class=class_name)

            return

        # -------------------------
        # FUNCTION
        # -------------------------

        if node.type == "function_definition":

            name_node = node.child_by_field_name("name")

            if name_node is None:
                return

            function_name = node_text(name_node, source)

            calls = extract_calls(node, source)

            symbol = Symbol(
                name=function_name,
                symbol_type="method" if current_class else "function",
                file=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                parent=current_class,
                calls=calls,
            )

            symbols.append(symbol)

            return

        for child in node.children:
            walk(child, current_class)

    walk(root)

    return symbols


# ============================================================
# FILE PARSING
# ============================================================

def parse_file(
    parser: Parser,
    file_path: Path,
    repo_root: Path,
) -> FileInfo:

    source = file_path.read_bytes()

    tree = parser.parse(source)

    relative_path = file_path.relative_to(repo_root)

    # Module = first directory below repository root
    if relative_path.parent == Path("."):
        module = repo_root.name
    else:
        module = relative_path.parts[0]

    imports = extract_imports(tree.root_node, source)

    symbols = extract_symbols(
        tree.root_node,
        source,
        str(relative_path),
    )

    return FileInfo(
        path=str(relative_path),
        module=module,
        imports=imports,
        symbols=symbols,
    )


# ============================================================
# REPOSITORY DISCOVERY
# ============================================================

def discover_python_files(repo_root: Path) -> list[Path]:

    return sorted(
        path
        for path in repo_root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


# ============================================================
# GRAPH CONSTRUCTION
# ============================================================

def build_graph(repo_root: Path) -> nx.MultiDiGraph:

    graph = nx.MultiDiGraph()

    parser = create_parser()

    files = discover_python_files(repo_root)

    print(f"Found {len(files)} Python files")

    parsed_files = []

    # ----------------------------------------
    # PARSE FILES
    # ----------------------------------------

    for file_path in files:

        print(f"Parsing: {file_path}")

        info = parse_file(
            parser,
            file_path,
            repo_root,
        )

        parsed_files.append(info)

    # ----------------------------------------
    # MODULE NODES
    # ----------------------------------------

    modules = sorted(
        {info.module for info in parsed_files}
    )

    for module in modules:

        module_id = f"module:{module}"

        graph.add_node(
            module_id,
            type="module",
            name=module,
        )

    # ----------------------------------------
    # FILE + SYMBOL NODES
    # ----------------------------------------

    for info in parsed_files:

        file_id = f"file:{info.path}"

        graph.add_node(
            file_id,
            type="file",
            name=Path(info.path).name,
            path=info.path,
            module=info.module,
        )

        # module -> file
        graph.add_edge(
            f"module:{info.module}",
            file_id,
            relation="contains",
        )

        # symbols
        for symbol in info.symbols:

            symbol_id = (
                f"symbol:{info.path}:{symbol.name}:{symbol.line}"
            )

            graph.add_node(
                symbol_id,
                type=symbol.symbol_type,
                name=symbol.name,
                file=info.path,
                line=symbol.line,
                end_line=symbol.end_line,
                parent=symbol.parent or "",
            )

            # file -> symbol
            graph.add_edge(
                file_id,
                symbol_id,
                relation="contains",
            )

            # class -> method
            if symbol.parent:

                parent_line = symbol.line

                for candidate in info.symbols:
                    if (
                        candidate.name == symbol.parent
                        and candidate.symbol_type == "class"
                    ):
                        parent_line = candidate.line
                        break

                parent_id = (
                    f"symbol:{info.path}:{symbol.parent}:{parent_line}"
                )

                if parent_id in graph:

                    graph.add_edge(
                        parent_id,
                        symbol_id,
                        relation="contains",
                    )

    # ----------------------------------------
    # IMPORT RELATIONSHIPS
    # ----------------------------------------

    for info in parsed_files:

        source_file_id = f"file:{info.path}"

        for import_statement in info.imports:

            target_file = resolve_import(
                import_statement,
                info,
                parsed_files,
            )

            if target_file:

                target_id = f"file:{target_file}"

                graph.add_edge(
                    source_file_id,
                    target_id,
                    relation="imports",
                    statement=import_statement,
                )

    # ----------------------------------------
    # INHERITANCE RELATIONSHIPS
    # ----------------------------------------

    for info in parsed_files:

        for symbol in info.symbols:

            if symbol.symbol_type != "class":
                continue

            child_id = find_symbol_id(
                graph,
                info.path,
                symbol.name,
                symbol.line,
            )

            if not child_id:
                continue

            for base in symbol.bases:

                base_id = find_class_by_name(
                    graph,
                    base,
                )

                if base_id:

                    graph.add_edge(
                        child_id,
                        base_id,
                        relation="inherits",
                    )

    # ----------------------------------------
    # CALL RELATIONSHIPS
    # ----------------------------------------

    for info in parsed_files:

        for symbol in info.symbols:

            if not symbol.calls:
                continue

            source_id = find_symbol_id(
                graph,
                info.path,
                symbol.name,
                symbol.line,
            )

            if not source_id:
                continue

            for call in symbol.calls:

                target_id = find_symbol_by_name(
                    graph,
                    call,
                )

                if target_id:

                    graph.add_edge(
                        source_id,
                        target_id,
                        relation="calls",
                    )

    return graph


# ============================================================
# IMPORT RESOLUTION
# ============================================================

def resolve_import(
    import_statement: str,
    current_file: FileInfo,
    parsed_files: list[FileInfo],
) -> str | None:

    statement = (
        import_statement
        .replace("from ", "")
        .replace("import ", "")
        .strip()
    )

    statement = statement.split(" as ")[0]
    statement = statement.split(",")[0].strip()

    # Convert Python module path to filesystem path
    module_path = statement.replace(".", "/")

    for info in parsed_files:

        normalized = info.path.replace("\\", "/")

        if (
            normalized.endswith(module_path + ".py")
            or normalized.endswith(module_path + "/__init__.py")
        ):
            return info.path

    # Relative fallback
    basename = statement.split(".")[-1]

    for info in parsed_files:

        if Path(info.path).stem == basename:

            return info.path

    return None


# ============================================================
# GRAPH SEARCH HELPERS
# ============================================================

def find_symbol_id(
    graph,
    file_path,
    name,
    line,
):

    candidate = (
        f"symbol:{file_path}:{name}:{line}"
    )

    return candidate if candidate in graph else None


def find_symbol_by_name(graph, name):

    for node, data in graph.nodes(data=True):

        if (
            data.get("type") in
            {"function", "method", "class"}
            and data.get("name") == name
        ):
            return node

    return None


def find_class_by_name(graph, name):

    name = name.split(".")[-1]

    for node, data in graph.nodes(data=True):

        if (
            data.get("type") == "class"
            and data.get("name") == name
        ):
            return node

    return None


# ============================================================
# EXPORT
# ============================================================

def export_graph(graph: nx.MultiDiGraph):

    OUTPUT_DIR.mkdir(exist_ok=True)

    # JSON
    nodes = []

    for node, data in graph.nodes(data=True):

        nodes.append({
            "id": node,
            **data,
        })

    edges = []

    for source, target, data in graph.edges(data=True):

        edges.append({
            "source": source,
            "target": target,
            **data,
        })

    graph_data = {
        "nodes": nodes,
        "edges": edges,
    }

    with open(
        OUTPUT_DIR / "code_graph.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            graph_data,
            f,
            indent=2,
        )

    for node, data in graph.nodes(data=True):
        for key, value in data.items():
            if value is None:
                data[key] = ""

    for source, target, data in graph.edges(data=True):
        for key, value in data.items():
            if value is None:
                data[key] = ""

    # GraphML
    nx.write_graphml(
        graph,
        OUTPUT_DIR / "code_graph.graphml",
    )

    print()
    print("=" * 60)
    print("GRAPH CREATED")
    print("=" * 60)

    print(f"Nodes : {graph.number_of_nodes()}")
    print(f"Edges : {graph.number_of_edges()}")

    print()
    print("Node types:")

    counts = {}

    for _, data in graph.nodes(data=True):

        node_type = data.get("type")

        counts[node_type] = (
            counts.get(node_type, 0) + 1
        )

    for node_type, count in counts.items():

        print(f"  {node_type:<12} {count}")

    print()
    print("Files:")
    print("  data/code_graph.json")
    print("  data/code_graph.graphml")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    if not REPO_ROOT.exists():

        raise FileNotFoundError(
            f"Repository not found: {REPO_ROOT}"
        )

    graph = build_graph(REPO_ROOT)

    export_graph(graph)