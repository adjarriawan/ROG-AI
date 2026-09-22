from functools import lru_cache

from langchain_ollama import OllamaEmbeddings

from config import get_settings


@lru_cache
def get_embeddings() -> OllamaEmbeddings:
    s = get_settings()
    return OllamaEmbeddings(model=s.ollama_embedding_model, base_url=s.ollama_base_url)


def embed_query(text: str) -> list[float]:
    return get_embeddings().embed_query(text)


def embed_documents(texts: list[str]) -> list[list[float]]:
    return get_embeddings().embed_documents(texts)
