from fastapi import FastAPI
from pydantic import BaseModel

from src.retrieval.hierarchical_retriever import HierarchicalRetriever


app = FastAPI(
    title="Fuse",
    description="Hierarchical codebase context retrieval",
)


retriever = HierarchicalRetriever()


class AskRequest(BaseModel):
    query: str


@app.get("/")
def root():

    return {
        "name": "Fuse",
        "status": "running",
    }


@app.post("/ask")
def ask(request: AskRequest):

    result = retriever.retrieve(
        request.query
    )

    return result