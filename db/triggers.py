from db.schema import get_connection

def get_pending_triggers():
    """
    Fetch all notion_triggers that haven't been processed yet.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, source_id, diff, change_score, created_at
        FROM notion_triggers
        ORDER BY created_at ASC
    """)
    rows = cur.fetchall()
    conn.close()

    triggers = []
    for row in rows:
        triggers.append({
            "id": row[0],
            "source_id": row[1],
            "diff": row[2],
            "score": row[3],
            "created_at": row[4],
        })
    return triggers

def mark_trigger_processed(trigger_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notion_triggers WHERE id = ?", (trigger_id,))
    conn.commit()
    conn.close()
