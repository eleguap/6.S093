import os
import json
import datetime
import struct
from db.schema import get_connection
from fastembed import TextEmbedding

# Suppress Hugging Face token warning
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

# Initialize the embedding model (downloads on first use)
embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

def serialize_embedding(embedding: list[float]) -> bytes:
    """Serialize embedding to binary format for sqlite-vec."""
    return struct.pack(f'{len(embedding)}f', *embedding)

def save_embedding(source_type: str, content: str, embedding: list[float],
                   source_id: str = None, metadata: dict = None) -> int:
    """
    Save an embedding to the database.

    Inserts into:
    1. embeddings_meta - content and metadata (FTS5 updated via trigger)
    2. vec_embeddings - vector for similarity search (matched by rowid)
    """
    conn = get_connection()
    cur = conn.cursor()

    # Insert metadata (FTS5 index updated automatically via trigger)
    cur.execute(
        """
        INSERT INTO embeddings_meta (source_type, source_id, content, metadata, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            source_type,
            source_id,
            content,
            json.dumps(metadata) if metadata else None,
            datetime.now().isoformat(),
        ),
    )
    rowid = cur.lastrowid

    # Insert vector with matching rowid
    cur.execute(
        """
        INSERT INTO vec_embeddings (rowid, embedding)
        VALUES (?, ?)
        """,
        (rowid, serialize_embedding(embedding)),
    )

    conn.commit()
    return rowid

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
