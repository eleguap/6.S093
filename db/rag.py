import os
import json
import sqlite3
from db.embedding import serialize_embedding
from db.schema import get_connection

def bm25_search(query: str, limit: int = 100) -> dict[int, float]:
    """
    Search using BM25 ranking via FTS5.

    Returns dict mapping embedding_id to raw BM25 score.
    Note: FTS5 BM25 scores are NEGATIVE (more negative = better match).
    """
    conn = get_connection()
    cur = conn.cursor()

    # Escape special FTS5 characters
    safe_query = query.replace('"', '""')

    try:
        cur.execute("""
            SELECT rowid, bm25(embeddings_fts) as score
            FROM embeddings_fts
            WHERE embeddings_fts MATCH ?
            LIMIT ?
        """, (safe_query, limit))

        return {row[0]: row[1] for row in cur.fetchall()}
    except sqlite3.OperationalError:
        # No matches or invalid query
        return {}

def normalize_bm25_scores(bm25_scores: dict[int, float]) -> dict[int, float]:
    """
    Normalize BM25 scores to [0, 1] range.

    FTS5 BM25 scores are negative (more negative = better).
    We invert so that best match gets 1.0, worst gets 0.0.
    """
    if not bm25_scores:
        return {}

    scores = list(bm25_scores.values())
    min_score = min(scores)  # Most negative = best
    max_score = max(scores)  # Least negative = worst

    if min_score == max_score:
        return {id: 1.0 for id in bm25_scores}

    score_range = max_score - min_score
    return {
        id: (max_score - score) / score_range
        for id, score in bm25_scores.items()
    }

def semantic_search(query_embedding: list[float], limit: int = 100) -> dict[int, float]:
    """
    Search using sqlite-vec's native cosine distance.

    Returns dict mapping rowid to cosine distance.
    Note: cosine distance is in [0, 2] where 0 = identical, 2 = opposite.
    """
    conn = get_connection()
    cur = conn.cursor()

    # sqlite-vec requires 'k = ?' in the WHERE clause when using a parameterized limit
    cur.execute("""
        SELECT rowid, distance
        FROM vec_embeddings
        WHERE embedding MATCH ?
          AND k = ?
        ORDER BY distance
    """, (serialize_embedding(query_embedding), limit))

    return {row[0]: row[1] for row in cur.fetchall()}

def normalize_distances(distances: dict[int, float]) -> dict[int, float]:
    """
    Normalize cosine distances to similarity scores in [0, 1].

    Cosine distance is in [0, 2] where 0 = identical.
    We convert to similarity: 1 - (distance / 2)
    Then normalize so best match gets 1.0.
    """
    if not distances:
        return {}

    # Convert distances to similarities
    similarities = {id: 1 - (dist / 2) for id, dist in distances.items()}

    # Normalize to [0, 1] range
    min_sim = min(similarities.values())
    max_sim = max(similarities.values())

    if min_sim == max_sim:
        return {id: 1.0 for id in similarities}

    sim_range = max_sim - min_sim
    return {
        id: (sim - min_sim) / sim_range
        for id, sim in similarities.items()
    }

def get_metadata_by_ids(ids: list[int]) -> dict[int, dict]:
    """Retrieve metadata for given IDs from embeddings_meta table."""
    if not ids:
        return {}

    conn = get_connection()
    cur = conn.cursor()

    placeholders = ",".join("?" * len(ids))
    cur.execute(f"""
        SELECT id, source_type, source_id, content, metadata
        FROM embeddings_meta
        WHERE id IN ({placeholders})
    """, ids)

    results = {}
    for row in cur.fetchall():
        results[row[0]] = {
            "source_type": row[1],
            "source_id": row[2],
            "content": row[3],
            "metadata": json.loads(row[4]) if row[4] else {},
        }
    return results

def hybrid_search(
    query: str,
    query_embedding: list[float],
    keyword_weight: float = 0.5,
    semantic_weight: float = 0.5,
    top_k: int = 10,
) -> list[dict]:
    """
    Perform hybrid search combining BM25 and sqlite-vec cosine similarity.

    Formula: final_score = keyword_weight * bm25 + semantic_weight * cosine_sim

    Args:
        conn: Database connection
        query: Search query text
        query_embedding: Pre-computed embedding of the query
        keyword_weight: Weight for BM25 (0-1)
        semantic_weight: Weight for cosine similarity (0-1)
        top_k: Number of results to return

    Returns:
        List of results sorted by combined score (highest first)
    """
    # Step 1: Get BM25 scores from FTS5
    bm25_raw = bm25_search(query)
    bm25_normalized = normalize_bm25_scores(bm25_raw)

    # Step 2: Get semantic distances from sqlite-vec
    semantic_raw = semantic_search(query_embedding, limit=100)
    semantic_normalized = normalize_distances(semantic_raw)

    # Step 3: Get all unique IDs from both searches
    all_ids = set(bm25_normalized.keys()) | set(semantic_normalized.keys())

    if not all_ids:
        return []

    # Step 4: Get metadata for all candidates
    metadata = get_metadata_by_ids(list(all_ids))

    # Step 5: Compute combined scores
    scored_results = []

    for id in all_ids:
        # BM25 score (0 if no keyword match)
        bm25_score = bm25_normalized.get(id, 0.0)

        # Semantic score (0 if not in top semantic results)
        semantic_score = semantic_normalized.get(id, 0.0)

        # Combined score
        final_score = (keyword_weight * bm25_score) + (semantic_weight * semantic_score)

        meta = metadata.get(id, {})
        scored_results.append({
            "id": id,
            "content": meta.get("content", ""),
            "source_type": meta.get("source_type", ""),
            "source_id": meta.get("source_id", ""),
            "metadata": meta.get("metadata", {}),
            "bm25_score": bm25_score,
            "semantic_score": semantic_score,
            "final_score": final_score,
        })

    # Sort by final score (descending)
    scored_results.sort(key=lambda x: x["final_score"], reverse=True)

    return scored_results[:top_k]
