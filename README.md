# FUSE

**FUSE (File Understanding & Semantic Exploration)** is a codebase intelligence and retrieval system that represents a Python repository as a hierarchical knowledge graph, enriches that graph with compact LLM-generated semantic metadata, and performs hierarchical retrieval to identify the most relevant modules, files, and symbols for a user's problem.

> **Core idea:** don't send the entire repository to an LLM and ask it to figure everything out. Build a deterministic structural representation first, enrich it semantically, then progressively narrow the search space.

---

## 1. What FUSE Does

Given a query such as:

```text
Why is login failing?
```

FUSE progressively narrows the repository:

```text
User Query
    │
    ▼
Module Retrieval
    │
    ▼
File Retrieval
    │
    ▼
Dependency Expansion
    │
    ▼
Symbol Retrieval
    │
    ▼
Relevant Code Context
```

The result is a compact, structured representation of the part of the repository that is most relevant to the problem.

For the included Flask repository, a query such as `why login is failing` can return:

- relevant module(s)
- relevant file(s)
- relevant classes/functions/methods
- exact source locations for the selected symbols

---

# 2. Core Architecture

FUSE represents the repository at three semantic levels:

```text
Module
  │
  ├── File
  │     ├── Class
  │     ├── Function
  │     └── Method
  │
  └── File dependencies
```

It combines two different kinds of knowledge.

### Structural knowledge

Generated deterministically from the source code using **Tree-sitter**.

This includes:

- modules
- files
- classes
- functions
- methods
- containment relationships
- import/dependency relationships
- source locations

### Semantic knowledge

Generated using **Gemini**.

Each module, file, and symbol receives a compact natural-language description.

This gives FUSE two complementary views of the repository:

```text
"What structurally exists?"
            +
"What does it mean?"
```

The LLM provides semantic relevance, while the graph remains the structural source of truth.

---

# 3. Knowledge Graph Construction

FUSE first discovers all Python files in the target repository and builds a structural graph.

For the current Flask test repository:

```text
24 Python files
438 nodes
909 edges
```

### Node types

```text
3    modules
24   files
72   functions
52   classes
287  methods
```

The graph also represents internal Python imports/dependencies.

For example:

```text
app.py
 ├── imports → ctx.py
 ├── imports → globals.py
 ├── imports → sessions.py
 ├── imports → wrappers.py
 └── imports → ...
```

Generated structural artifacts:

```text
data/code_graph.json
data/code_graph.graphml
```

---

# 4. Three-Level Semantic Enrichment

FUSE enriches the structural graph at three levels.

```text
Level 1
Module summary
     ↓
Level 2
File summary
     ↓
Level 3
Symbol descriptions
```

## Level 3 — Symbol Semantic Enrichment

Tree-sitter identifies the exact classes, functions, and methods present in each file.

Those exact symbols are sent to Gemini together with the source file.

Gemini is instructed to describe **only those symbols**.

Example:

```json
{
  "name": "open_session",
  "parent": "SecureCookieSessionInterface",
  "line": 323,
  "description": "Opens and loads the session associated with a request."
}
```

The important design decision is:

> **Tree-sitter decides what symbols exist. Gemini only describes them.**

Symbol identity is validated using:

```text
name
parent
line
```

This allows duplicate method names in different classes to remain distinguishable.

---

## Level 2 — File Semantic Enrichment

Every Python source file receives a concise semantic description.

For example:

```text
sessions.py
```

is represented not only by its classes and methods, but also by a higher-level description of the file's overall responsibility.

This gives the retriever a lightweight semantic representation of each file without requiring full source-code reasoning at the file-selection stage.

---

## Level 1 — Module Semantic Enrichment

Files are grouped into modules.

FUSE takes the already-generated file summaries belonging to a module and asks Gemini for one concise description of the module's overall responsibility.

The current graph contains:

```text
flask
json
sansio
```

This creates the hierarchy:

```text
Module summary
      ↓
File summary
      ↓
Symbol summary
```

The final generated graph contains semantic descriptions for all **438 nodes**.

---

# 5. Hierarchical Retrieval

Once the graph is built and enriched, FUSE performs hierarchical retrieval.

The retrieval pipeline uses three LLM decisions combined with deterministic graph traversal.

```text
All Modules
    │
    ▼
Relevant Modules
    │
    ▼
Candidate Files
    │
    ├── dependency expansion
    │
    ▼
Relevant Files
    │
    ▼
Relevant Symbols
    │
    ▼
Final Code Context
```

## Call 1 — Module Retrieval

Gemini receives:

- user query
- available module descriptions

It selects the relevant modules.

Example:

```text
User:
Why is login failing?

Gemini:
{
  "modules": ["flask"]
}
```

Only modules present in the structural graph can be selected.

---

## Dependency Expansion

LLM selection alone is not sufficient.

Suppose the model selects:

```text
app.py
```

but `app.py` internally imports:

```text
ctx.py
sessions.py
wrappers.py
```

FUSE uses the structural graph to expand the candidate context through those internal dependencies.

```text
app.py
   │
   ├── imports → ctx.py
   ├── imports → sessions.py
   └── imports → wrappers.py
```

This keeps retrieval structurally aware rather than treating every file as an isolated document.

---

## Call 2 — File Retrieval

Gemini receives:

- the user's query
- selected modules
- candidate file descriptions

It selects the most relevant files.

---

## Call 3 — Symbol Retrieval

After the final candidate files are known, FUSE collects their classes, functions, and methods.

Gemini selects the most relevant symbols.

A returned symbol contains graph identity such as:

```json
{
  "file": "sessions.py",
  "name": "open_session",
  "type": "method",
  "parent": "SecureCookieSessionInterface",
  "line": 323
}
```

The retriever validates every returned symbol against the graph before returning it.

---

# 6. Retrieval Example

For:

```text
why login is failing
```

the deployed API can return a result similar to:

```json
{
  "query": "why login is failing",
  "modules": [
    "flask"
  ],
  "files": [
    "app.py",
    "ctx.py",
    "debughelpers.py",
    "helpers.py",
    "logging.py",
    "sessions.py",
    "wrappers.py"
  ],
  "symbols": [
    {
      "file": "app.py",
      "type": "method",
      "name": "dispatch_request",
      "parent": "Flask",
      "line": 969
    },
    {
      "file": "app.py",
      "type": "method",
      "name": "full_dispatch_request",
      "parent": "Flask",
      "line": 995
    },
    {
      "file": "sessions.py",
      "type": "method",
      "name": "open_session",
      "parent": "SecureCookieSessionInterface",
      "line": 323
    }
  ]
}
```

The important property is progressive narrowing:

```text
Repository
   ↓
Module
   ↓
Files
   ↓
Dependencies
   ↓
Symbols
```

---

# 7. API

FUSE exposes the retrieval system through **FastAPI**.

## Health endpoint

```http
GET /
```

Response:

```json
{
  "name": "Fuse",
  "status": "running"
}
```

## Retrieval endpoint

```http
POST /ask
```

Request:

```json
{
  "query": "why login is failing"
}
```

Response:

```json
{
  "query": "...",
  "modules": [...],
  "files": [...],
  "symbols": [...]
}
```

---

# 8. Live Deployment

FUSE is deployed on Vercel.

**Production API:**

https://fuse-swart.vercel.app/

**Swagger API documentation:**

https://fuse-swart.vercel.app/docs

The deployed Swagger interface can be used to execute `/ask` directly from the browser.

---

# 9. Project Structure

```text
fuse/
│
├── api/
│   └── index.py
│
├── data/
│   ├── code_graph.json
│   ├── code_graph.graphml
│   ├── enriched_code_graph.json
│   ├── enrichment_report.json
│   ├── module_summaries.json
│   └── summaries.json
│
├── src/
│   ├── api.py
│   ├── fuse.py
│   ├── test.py
│   │
│   ├── parser/
│   │   └── build_graph.py
│   │
│   ├── graph/
│   │   └── enrich_graph.py
│   │
│   ├── retrieval/
│   │   ├── hierarchical_retriever.py
│   │   ├── llm.py
│   │   └── __init__.py
│   │
│   └── summarizer/
│       ├── summarize_file.py
│       └── summarize_module.py
│
├── test_repo/
│   └── flask/
│
├── requirements.txt
└── README.md
```

### Important components

| Component | Responsibility |
|---|---|
| `src/fuse.py` | Main graph-building and semantic-enrichment pipeline |
| `src/parser/build_graph.py` | Tree-sitter parsing and structural graph construction |
| `src/graph/enrich_graph.py` | Inserts semantic descriptions into graph nodes |
| `src/summarizer/summarize_file.py` | Level 2 file + Level 3 symbol semantic summaries |
| `src/summarizer/summarize_module.py` | Level 1 module summaries |
| `src/retrieval/hierarchical_retriever.py` | Hierarchical retrieval orchestration |
| `src/retrieval/llm.py` | LLM retrieval calls |
| `src/api.py` | FastAPI application |
| `api/index.py` | Vercel deployment entry point |

---

# 10. Complete Pipeline

The complete FUSE pipeline is:

```text
Python Repository
       │
       ▼
File Discovery
       │
       ▼
Tree-sitter Parsing
       │
       ▼
Structural Knowledge Graph
       │
       ├──────────────────┐
       │                  │
       ▼                  ▼
File/Symbol           Import Graph
Extraction
       │                  │
       └────────┬─────────┘
                ▼
       Semantic Enrichment
                │
        ┌───────┼────────┐
        ▼       ▼        ▼
     Module    File    Symbol
     Level 1  Level 2  Level 3
        │       │        │
        └───────┼────────┘
                ▼
       Enriched Graph
                │
                ▼
     Hierarchical Retrieval
                │
        ┌───────┼────────┐
        ▼       ▼        ▼
     Modules  Files   Symbols
                │
                ▼
       Relevant Code Context
                │
                ▼
              /ask
```

---

# 11. Reliability & Validation

FUSE does not blindly trust LLM output.

## Symbol validation

Every symbol returned by Gemini is checked against the Tree-sitter-generated symbol inventory.

The identity is matched using:

```text
name
parent
line
```

This prevents:

- invented symbols
- omitted symbols
- ambiguous duplicate names

## File validation

Retrieved files must exist in the candidate file set.

## Module validation

Retrieved modules must exist in the structural graph.

## Semantic enrichment validation

FUSE verifies that:

- every expected symbol receives a description
- no unexpected symbols are added
- descriptions are not empty
- graph nodes receive the correct descriptions

## Failure recovery

Gemini calls are retried when an external API failure occurs.

During the final build, `sansio/scaffold.py` temporarily received a Gemini `503 UNAVAILABLE` response. It was recovered separately without rebuilding the entire project.

Final validation confirmed:

```text
438 / 438 nodes described
0 missing descriptions
```

---

# 12. Design Decisions

## Why Tree-sitter?

Structural facts should be deterministic.

The LLM should not be responsible for deciding whether a function, class, or method exists. Tree-sitter provides the authoritative structural inventory.

---

## Why a knowledge graph?

A repository is not just a collection of independent documents.

Files import other files, classes contain methods, and symbols belong to files and modules.

The graph preserves these relationships so retrieval can traverse them.

---

## Why three LLM calls?

A single retrieval prompt over the entire repository would require the model to reason over too much information.

FUSE progressively reduces the search space:

```text
All modules
    ↓
Relevant modules
    ↓
Files inside those modules
    ↓
Dependency-aware candidate files
    ↓
Relevant symbols
```

Each stage therefore has a narrower decision to make.

---

## Why semantic summaries?

Sending complete source files for every retrieval decision is noisy and expensive.

Compact descriptions provide a lightweight semantic index while the structural graph preserves the actual repository relationships.

---

## Why deterministic dependency expansion?

The LLM decides what appears semantically relevant.

The graph decides what is structurally connected.

This separation reduces the chance that retrieval misses an important dependency simply because the model did not explicitly select it.

---

# 13. Generated Artifacts

After running the indexing pipeline, FUSE generates:

```text
data/code_graph.json
```

The raw structural knowledge graph.

```text
data/code_graph.graphml
```

Graph representation suitable for graph inspection/tools.

```text
data/enriched_code_graph.json
```

The structural graph with semantic descriptions attached to nodes.

```text
data/summaries.json
```

Level 2 file summaries and Level 3 symbol descriptions.

```text
data/module_summaries.json
```

Level 1 module summaries.

```text
data/enrichment_report.json
```

Semantic enrichment and recovery report.

---

# 14. Running Locally

## 1. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Configure Gemini

Create a `.env` file:

```env
GEMINI_API_KEY=your_api_key
```

Do not commit `.env` or expose the API key.

## 4. Build the graph

```bash
python src/fuse.py
```

This performs:

1. Repository discovery
2. Tree-sitter graph construction
3. File and symbol semantic enrichment
4. Module semantic enrichment
5. Enriched graph generation

## 5. Run the API

```bash
uvicorn src.api:app --reload
```

The local API will be available at:

```text
http://127.0.0.1:8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

---

# 15. Current Results

The final generated Flask graph contains:

```text
24 Python files
438 total nodes
909 structural edges

3 modules
24 files
72 functions
52 classes
287 methods
```

Semantic enrichment:

```text
438 / 438 nodes described
0 missed
```

The complete indexing and enrichment pipeline is operational for the included Flask repository.

The hierarchical retriever is exposed through the deployed `/ask` API.

---

# 16. Limitations

FUSE is currently an experimental codebase intelligence system.

Current limitations include:

- Retrieval quality depends partly on the quality of semantic summaries.
- Import resolution is focused on the analyzed Python repository.
- Dependency expansion is based on relationships represented in the structural graph.
- The current API returns retrieval context rather than automatically fixing the underlying issue.
- The current implementation has been evaluated on the included Flask repository rather than a broad production-repository benchmark.

These are deliberate boundaries of the current version rather than claims of complete repository understanding.

---

# 17. Future Work

Potential next steps include:

- Code-aware reranking of retrieved symbols
- Call-graph relationships in addition to imports
- Better cross-module dependency resolution
- Repository-wide incremental indexing
- Caching semantic summaries
- Retrieval evaluation benchmarks
- Token and latency measurements against full-context baselines
- Using retrieved symbols as context for an actual debugging/fixing agent

---

# 18. Status

**FUSE is complete for the included Flask repository.**

The final graph contains:

```text
438 nodes
909 structural edges
438 / 438 semantic descriptions
0 missed descriptions
```

The system is deployed and accessible through:

```text
https://fuse-swart.vercel.app/
```

Interactive API documentation:

```text
https://fuse-swart.vercel.app/docs
```

The current system's responsibility is **codebase retrieval and context selection**. Automatic issue fixing is intentionally outside the current scope.
