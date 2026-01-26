import os
from db.embedding import save_embedding
from fastembed import TextEmbedding

# Suppress Hugging Face token warning
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

# Initialize the embedding model (downloads on first use)
embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

def generate_embeddings_batch(chunks: list[dict]):
    """Generate embeddings for multiple texts in a batch (more efficient)."""
    if not chunks:
        return

    texts = [c["content"] for c in chunks]
    embeddings = list(embedding_model.embed(texts))

    for chunk, emb in zip(chunks, embeddings):
        save_embedding(
            source_type=chunk["source_type"],
            content=chunk["content"],
            embedding=emb.tolist(),
            source_id=chunk["source_id"],
            metadata=chunk["metadata"]
        )
