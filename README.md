# FUSE

**FUSE** is a codebase intelligence and retrieval system that represents
a Python repository as a hierarchical knowledge graph and uses LLMs to
retrieve the most relevant parts of the codebase for a user's problem.

The project was built as an exploration of a different approach to
repository context: instead of sending large amounts of source code
directly to an LLM, FUSE first builds a structured representation of the
repository, enriches it with compact semantic descriptions, and then
performs hierarchical retrieval.

------------------------------------------------------------------------

## What FUSE Does

Given a question such as:

``` text
Why is login failing?
```

FUSE progressively narrows the repository:

``` text
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

The goal is to return the files and symbols that are useful for
investigating the problem without requiring the LLM to reason over the
entire repository at once.

------------------------------------------------------------------------

## Core Idea

The repository is represented at three semantic levels:

``` text
Module
  │
  ├── File
  │     │
  │     ├── Class
  │     ├── Function
  │     └── Method
  │
  └── File dependencies
```

FUSE combines two types of information:

### Structural knowledge

Generated deterministically from the source code using Tree-sitter.

This includes:

-   modules
-   files
-   classes
-   functions
-   methods
-   containment relationships
-   import/dependency relationships
-   source locations

### Semantic knowledge

Generated using Gemini.

Each module, file, and symbol receives a compact natural-language
description.

This allows retrieval to reason over both:

``` text
"What structurally exists?"
```

and:

``` text
"What does it mean?"
```

------------------------------------------------------------------------

# Architecture

## 1. Structural Graph Construction

Tree-sitter parses every Python file and extracts the repository
structure.

For the current Flask test repository:

``` text
24 Python files
438 nodes
909 edges
```

Node types:

``` text
3   modules
24  files
72  functions
52  classes
287 methods
```

The parser also resolves internal Python imports.

For example:

``` text
app.py
 ├──imports──> ctx.py
 ├──imports──> globals.py
 ├──imports──> sessions.py
 ├──imports──> wrappers.py
 └──imports──> ...
```

The resulting graph is stored in:

``` text
data/code_graph.json
data/code_graph.graphml
```

------------------------------------------------------------------------

## 2. Level 3 --- Symbol Semantic Enrichment

Tree-sitter already knows exactly which classes, functions, and methods
exist.

FUSE sends those symbols to Gemini together with the source file.

Gemini is asked to provide one concise description for every symbol.

For example:

``` json
{
  "name": "open_session",
  "parent": "SecureCookieSessionInterface",
  "line": 323,
  "description": "Opens and loads the session associated with a request."
}
```

The important design decision is that Gemini does **not** decide which
symbols exist.

Tree-sitter provides the authoritative symbol list.

This prevents the LLM from inventing or omitting code entities.

------------------------------------------------------------------------

## 3. Level 2 --- File Semantic Enrichment

Every source file also receives a compact description.

For example:

``` text
sessions.py
```

might be described as the part of Flask responsible for session
interfaces and session handling.

The file description provides a higher-level semantic representation
than individual symbols.

------------------------------------------------------------------------

## 4. Level 1 --- Module Semantic Enrichment

Files are grouped into modules and their file summaries are given to
Gemini.

Gemini produces one summary describing the responsibility of the
complete module.

The current graph contains:

``` text
flask
json
sansio
```

This gives FUSE three semantic levels:

``` text
Module summary
      ↓
File summary
      ↓
Symbol summary
```

All 438 graph nodes in the current generated graph have semantic
descriptions.

------------------------------------------------------------------------

# Hierarchical Retrieval

FUSE uses three LLM calls.

## Call 1 --- Module Retrieval

Gemini receives the available module descriptions and the user's query.

Example:

``` text
User:
"Why is login failing?"

Gemini:
{
  "modules": ["flask"]
}
```

Only modules present in the graph can be selected.

------------------------------------------------------------------------

## Call 2 --- File Retrieval

FUSE loads the files belonging to the selected modules.

Gemini receives:

-   the user's problem
-   selected modules
-   file descriptions

It selects the most relevant files.

Example:

``` text
sessions.py
globals.py
ctx.py
wrappers.py
logging.py
debughelpers.py
```

------------------------------------------------------------------------

## Dependency Expansion

LLM retrieval alone is not sufficient.

A selected file may depend on another file that the LLM did not
explicitly select.

FUSE therefore uses the structural graph to expand the candidate context
through internal file dependencies.

For example:

``` text
app.py
   │
   ├──imports──> ctx.py
   ├──imports──> sessions.py
   └──imports──> wrappers.py
```

This means retrieval can preserve important code relationships instead
of treating every file as an isolated document.

------------------------------------------------------------------------

## Call 3 --- Symbol Retrieval

After the final candidate files are known, FUSE collects the classes,
functions, and methods belonging to those files.

Gemini then selects the most relevant symbols.

The output contains the exact symbol identity from the graph:

``` json
{
  "file": "sessions.py",
  "name": "open_session",
  "type": "method",
  "parent": "SecureCookieSessionInterface",
  "line": 323
}
```

The retriever validates every returned symbol against the graph before
returning it.

------------------------------------------------------------------------

# Retrieval Example

For:

``` text
why login is failing
```

the retrieval process can produce:

``` json
{
  "query": "why login is failing",
  "modules": [
    "flask"
  ],
  "files": [
    "sessions.py",
    "globals.py",
    "ctx.py",
    "wrappers.py",
    "debughelpers.py",
    "logging.py"
  ],
  "symbols": [
    {
      "file": "sessions.py",
      "name": "open_session",
      "type": "method"
    },
    {
      "file": "sessions.py",
      "name": "save_session",
      "type": "method"
    },
    {
      "file": "ctx.py",
      "name": "_get_session",
      "type": "method"
    }
  ]
}
```

The result is a compact, structured representation of the relevant part
of the repository.

------------------------------------------------------------------------

# API

FUSE exposes the retrieval system through an API.

The main endpoint is:

``` text
POST /ask
```

Example request:

``` json
{
  "query": "why login is failing"
}
```

The endpoint runs the hierarchical retrieval pipeline and returns the
relevant modules, files, and symbols.

------------------------------------------------------------------------

# Project Structure

``` text
fuse/
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
│   │
│   ├── parser/
│   │   └── build_graph.py
│   │
│   ├── graph/
│   │   └── enrich_graph.py
│   │
│   ├── retrieval/
│   │   ├── hierarchical_retriever.py
│   │   └── llm.py
│   │
│   └── summarizer/
│       └── summarize_module.py
│
├── test_repo/
│   └── flask/
│
├── requirements.txt
└── README.md
```

------------------------------------------------------------------------

# Pipeline

The complete FUSE pipeline is:

``` text
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
       ├───────────────┐
       │               │
       ▼               ▼
File/Symbol          Import
Extraction           Graph
       │               │
       └───────┬───────┘
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

------------------------------------------------------------------------

# Running Locally

## 1. Create the environment

``` bash
python -m venv .venv
source .venv/bin/activate
```

## 2. Install dependencies

``` bash
pip install -r requirements.txt
```

## 3. Configure Gemini

Create a `.env` file:

``` env
GEMINI_API_KEY=your_api_key
```

Do not commit `.env` or expose the API key.

------------------------------------------------------------------------

## 4. Build the complete graph

Run:

``` bash
python src/fuse.py
```

This performs:

1.  Repository discovery
2.  Tree-sitter graph construction
3.  File and symbol semantic enrichment
4.  Module semantic enrichment
5.  Enriched graph generation

Generated artifacts:

``` text
data/code_graph.json
data/code_graph.graphml
data/enriched_code_graph.json
data/summaries.json
data/module_summaries.json
data/enrichment_report.json
```

------------------------------------------------------------------------

# Run the API

``` bash
uvicorn src.api:app --reload
```

The API will be available locally at:

``` text
http://127.0.0.1:8000
```

Then send a request to:

``` text
POST /ask
```

------------------------------------------------------------------------

# Reliability and Validation

FUSE does not blindly trust LLM output.

### Symbol validation

Every symbol returned by Gemini is checked against the symbols extracted
by Tree-sitter.

The identity is matched using:

``` text
name
parent
line
```

This is important because methods can have the same name in different
classes.

### File validation

Retrieved files must exist in the candidate file set.

### Module validation

Retrieved modules must exist in the structural graph.

### Semantic enrichment validation

FUSE verifies that:

-   every expected symbol receives a description
-   no unexpected symbols are added
-   descriptions are not empty
-   graph nodes receive the correct descriptions

### Failure recovery

Gemini calls are retried when an external API failure occurs.

During development, one file received a Gemini `503 UNAVAILABLE`
response. The file was successfully recovered separately without
rebuilding the entire project.

------------------------------------------------------------------------

# Design Decisions

## Why Tree-sitter?

Tree-sitter gives FUSE a deterministic representation of the source
code.

The LLM should not be responsible for deciding whether a function or
class exists. Structural facts come from the parser.

------------------------------------------------------------------------

## Why a knowledge graph?

A repository is not just a collection of independent files.

Files import other files, classes contain methods, and symbols belong to
files and modules.

The graph preserves those relationships so retrieval can traverse them.

------------------------------------------------------------------------

## Why three LLM calls?

A single retrieval prompt over the entire repository would make the
model reason over too much information.

The hierarchical approach progressively reduces the search space:

``` text
All modules
    ↓
Relevant modules
    ↓
Files inside those modules
    ↓
Dependency-aware candidate files
    ↓
Symbols inside those files
```

Each stage has a narrower decision to make.

------------------------------------------------------------------------

## Why semantic summaries?

Sending complete source files for every retrieval decision is expensive
and noisy.

Compact descriptions provide a lightweight semantic index while the
structural graph preserves the actual relationships.

------------------------------------------------------------------------

## Why keep graph traversal deterministic?

The LLM decides what appears semantically relevant.

The graph decides what is structurally connected.

This separation reduces the chance that the LLM will miss an important
dependency simply because it did not select that file directly.

------------------------------------------------------------------------

# Current Results

The current generated Flask graph contains:

``` text
24 Python files
438 total nodes
909 structural edges

3 modules
24 files
72 functions
52 classes
287 methods
```

Semantic enrichment status:

``` text
438 / 438 nodes described
0 missed
```

------------------------------------------------------------------------

# Limitations

FUSE is currently an experimental codebase intelligence system.

Some current limitations include:

-   Retrieval quality depends partly on the quality of semantic
    summaries.
-   Import resolution is currently focused on the analyzed Python
    repository.
-   Dependency expansion is based on relationships represented in the
    structural graph.
-   The current API returns retrieval context rather than automatically
    fixing the underlying issue.
-   The current implementation has been evaluated on the included Flask
    repository rather than a large range of production repositories.

These are deliberate boundaries for the current version rather than
claims of complete repository understanding.

------------------------------------------------------------------------

# What I Would Build Next

Possible next steps include:

-   code-aware reranking of retrieved symbols
-   call-graph relationships in addition to imports
-   better cross-module dependency resolution
-   repository-wide incremental indexing
-   caching semantic summaries
-   retrieval evaluation benchmarks
-   token/latency measurements against full-context baselines
-   using retrieved symbols as context for an actual debugging/fixing
    agent

------------------------------------------------------------------------

# Status

FUSE's current graph construction and semantic enrichment pipeline is
complete for the included Flask repository.

The generated graph contains semantic descriptions for all 438 graph
nodes, and the hierarchical retriever is ready to serve queries through
`/ask`.

The remaining work for the assignment is deployment and submission
documentation.