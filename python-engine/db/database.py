import sqlite3
import os
import uuid
from pathlib import Path

# We will store app data in ~/.clipforge
def get_db_path():
    home = Path.home()
    app_dir = home / ".clipforge"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / "clipforge.db"

def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Projects Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Projects (
        id TEXT PRIMARY KEY,
        name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        export_path TEXT
    )
    ''')
    
    # MediaFiles Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS MediaFiles (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        file_path TEXT UNIQUE,
        type TEXT,
        duration_sec REAL,
        status TEXT DEFAULT 'pending',
        is_rejected BOOLEAN DEFAULT 0,
        reject_reason TEXT,
        thumbnail_path TEXT,
        FOREIGN KEY(project_id) REFERENCES Projects(id)
    )
    ''')
    
    # Segments Table (Hero Moments)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Segments (
        id TEXT PRIMARY KEY,
        media_file_id TEXT,
        start_time REAL,
        end_time REAL,
        score REAL,
        FOREIGN KEY(media_file_id) REFERENCES MediaFiles(id)
    )
    ''')
    
    # Storyboard Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Storyboard (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        segment_id TEXT,
        order_index INTEGER,
        FOREIGN KEY(project_id) REFERENCES Projects(id),
        FOREIGN KEY(segment_id) REFERENCES Segments(id)
    )
    ''')
    
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(get_db_path(), check_same_thread=False)

def create_project(name="Default Project"):
    conn = get_connection()
    c = conn.cursor()
    project_id = str(uuid.uuid4())
    c.execute("INSERT INTO Projects (id, name) VALUES (?, ?)", (project_id, name))
    conn.commit()
    conn.close()
    return project_id

def get_or_create_default_project():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM Projects LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        return row[0]
    return create_project()

def insert_media_file(project_id, file_path, type="video"):
    conn = get_connection()
    c = conn.cursor()
    media_id = str(uuid.uuid4())
    try:
        c.execute('''
            INSERT INTO MediaFiles (id, project_id, file_path, type, status)
            VALUES (?, ?, ?, ?, 'pending')
        ''', (media_id, project_id, str(file_path), type))
        conn.commit()
    except sqlite3.IntegrityError:
        # File already exists
        c.execute("SELECT id FROM MediaFiles WHERE file_path = ?", (str(file_path),))
        media_id = c.fetchone()[0]
    conn.close()
    return media_id

def update_media_thumbnail(media_id, thumbnail_path):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE MediaFiles SET thumbnail_path = ? WHERE id = ?", (str(thumbnail_path), media_id))
    conn.commit()
    conn.close()

def update_media_rejection(media_id, is_rejected, reason=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE MediaFiles SET is_rejected = ?, reject_reason = ?, status = ? WHERE id = ?", 
              (int(is_rejected), reason, 'rejected' if is_rejected else 'completed', media_id))
    conn.commit()
    conn.close()

def get_all_media():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM MediaFiles ORDER BY rowid DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def insert_segment(media_file_id, start_time, end_time, score):
    conn = get_connection()
    c = conn.cursor()
    segment_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO Segments (id, media_file_id, start_time, end_time, score)
        VALUES (?, ?, ?, ?, ?)
    ''', (segment_id, media_file_id, start_time, end_time, score))
    
    # Get project_id from MediaFiles
    c.execute("SELECT project_id FROM MediaFiles WHERE id = ?", (media_file_id,))
    project_id = c.fetchone()[0]
    
    # Get max order_index in Storyboard
    c.execute("SELECT MAX(order_index) FROM Storyboard WHERE project_id = ?", (project_id,))
    max_order = c.fetchone()[0]
    next_order = (max_order + 1) if max_order is not None else 0
    
    # Add to Storyboard
    storyboard_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO Storyboard (id, project_id, segment_id, order_index)
        VALUES (?, ?, ?, ?)
    ''', (storyboard_id, project_id, segment_id, next_order))
    
    conn.commit()
    conn.close()
    return segment_id

def ensure_storyboard_segments_for_ready_media(project_id):
    """
    Backfill default storyboard segments for completed, accepted media that has
    no segment yet. This lets photos participate in the montage timeline.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT m.id, m.type
        FROM MediaFiles m
        LEFT JOIN Segments s ON m.id = s.media_file_id
        WHERE m.project_id = ?
          AND m.status = 'completed'
          AND m.is_rejected = 0
          AND s.id IS NULL
        ORDER BY m.rowid ASC
    ''', (project_id,))
    rows = c.fetchall()
    conn.close()

    created = 0
    for row in rows:
        default_duration = 3.0 if row["type"] == "photo" else 3.0
        insert_segment(row["id"], 0.0, default_duration, 0.0)
        created += 1

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM Storyboard WHERE project_id = ?", (project_id,))
    storyboard_count = c.fetchone()[0]

    if storyboard_count == 0:
        c.execute('''
            SELECT s.id
            FROM Segments s
            JOIN MediaFiles m ON s.media_file_id = m.id
            LEFT JOIN Storyboard sb ON sb.segment_id = s.id
            WHERE m.project_id = ?
              AND m.status = 'completed'
              AND m.is_rejected = 0
              AND sb.id IS NULL
            ORDER BY m.rowid ASC
        ''', (project_id,))
        orphan_segments = [row[0] for row in c.fetchall()]
        for idx, segment_id in enumerate(orphan_segments):
            c.execute('''
                INSERT INTO Storyboard (id, project_id, segment_id, order_index)
                VALUES (?, ?, ?, ?)
            ''', (str(uuid.uuid4()), project_id, segment_id, idx))
            created += 1
        conn.commit()
    conn.close()
    return created

def media_has_segments(media_file_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT 1 FROM Segments WHERE media_file_id = ? LIMIT 1", (media_file_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_segments_for_media(media_file_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM Segments WHERE media_file_id = ? ORDER BY score DESC", (media_file_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_good_media_with_segments():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Join MediaFiles and Segments
    query = '''
    SELECT m.id, m.file_path, m.type, s.start_time, s.end_time, s.score
    FROM MediaFiles m
    LEFT JOIN Segments s ON m.id = s.media_file_id
    WHERE m.is_rejected = 0
    ORDER BY m.rowid DESC
    '''
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_storyboard():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    query = '''
    SELECT sb.id as storyboard_id, sb.order_index, 
           s.id as segment_id, s.start_time, s.end_time, s.score,
           m.id as media_id, m.file_path, m.thumbnail_path, m.type
    FROM Storyboard sb
    JOIN Segments s ON sb.segment_id = s.id
    JOIN MediaFiles m ON s.media_file_id = m.id
    ORDER BY sb.order_index ASC
    '''
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def dedupe_storyboard_by_media(project_id):
    """
    Keep one storyboard segment per media file. Prefer the highest-scoring
    AI segment over default backfill segments.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT sb.id AS storyboard_id, sb.order_index, s.id AS segment_id,
               s.media_file_id, s.score
        FROM Storyboard sb
        JOIN Segments s ON sb.segment_id = s.id
        WHERE sb.project_id = ?
        ORDER BY sb.order_index ASC
    ''', (project_id,))
    rows = c.fetchall()

    best_by_media = {}
    duplicate_storyboard_ids = []
    duplicate_segment_ids = []
    for row in rows:
        media_id = row["media_file_id"]
        current = best_by_media.get(media_id)
        if current is None:
            best_by_media[media_id] = row
            continue

        current_score = current["score"] or 0
        row_score = row["score"] or 0
        if row_score > current_score:
            duplicate_storyboard_ids.append(current["storyboard_id"])
            duplicate_segment_ids.append(current["segment_id"])
            best_by_media[media_id] = row
        else:
            duplicate_storyboard_ids.append(row["storyboard_id"])
            duplicate_segment_ids.append(row["segment_id"])

    for storyboard_id in duplicate_storyboard_ids:
        c.execute("DELETE FROM Storyboard WHERE id = ?", (storyboard_id,))

    for segment_id in duplicate_segment_ids:
        c.execute('''
            DELETE FROM Segments
            WHERE id = ?
              AND NOT EXISTS (SELECT 1 FROM Storyboard WHERE segment_id = ?)
        ''', (segment_id, segment_id))

    c.execute('''
        SELECT id FROM Storyboard
        WHERE project_id = ?
        ORDER BY order_index ASC
    ''', (project_id,))
    remaining = [row[0] for row in c.fetchall()]
    for idx, storyboard_id in enumerate(remaining):
        c.execute("UPDATE Storyboard SET order_index = ? WHERE id = ?", (idx, storyboard_id))

    conn.commit()
    conn.close()
    return {"removed": len(duplicate_storyboard_ids), "remaining": len(remaining)}

def reorder_storyboard(storyboard_ids: list):
    conn = get_connection()
    c = conn.cursor()
    for idx, sb_id in enumerate(storyboard_ids):
        c.execute("UPDATE Storyboard SET order_index = ? WHERE id = ?", (idx, sb_id))
    conn.commit()
    conn.close()

def delete_from_storyboard(storyboard_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Storyboard WHERE id = ?", (storyboard_id,))
    conn.commit()
    conn.close()

def clear_current_project(delete_staged_files=True):
    project_id = get_or_create_default_project()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT file_path, thumbnail_path FROM MediaFiles WHERE project_id = ?", (project_id,))
    file_rows = c.fetchall()

    c.execute("SELECT id FROM MediaFiles WHERE project_id = ?", (project_id,))
    media_ids = [row[0] for row in c.fetchall()]
    if media_ids:
        placeholders = ",".join("?" for _ in media_ids)
        c.execute(f"DELETE FROM Storyboard WHERE segment_id IN (SELECT id FROM Segments WHERE media_file_id IN ({placeholders}))", media_ids)
        c.execute(f"DELETE FROM Segments WHERE media_file_id IN ({placeholders})", media_ids)
        c.execute(f"DELETE FROM MediaFiles WHERE id IN ({placeholders})", media_ids)
    else:
        c.execute("DELETE FROM Storyboard WHERE project_id = ?", (project_id,))
    conn.commit()
    conn.close()

    deleted_files = 0
    if delete_staged_files:
        safe_roots = [
            Path.home() / ".clipforge",
            Path.home() / "Library" / "Application Support" / "com.clipforge.app" / "staged_media",
        ]
        for row in file_rows:
            for value in (row["file_path"], row["thumbnail_path"]):
                if not value:
                    continue
                path = Path(value)
                try:
                    resolved = path.resolve()
                    if any(resolved.is_relative_to(root.resolve()) for root in safe_roots) and resolved.is_file():
                        resolved.unlink()
                        deleted_files += 1
                except Exception:
                    pass
    return {"status": "ok", "project_id": project_id, "media_deleted": len(file_rows), "files_deleted": deleted_files}
