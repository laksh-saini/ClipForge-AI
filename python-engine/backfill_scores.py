import sqlite3
from core.hero_extractor import score_photo
from db.database import get_db_path

conn = sqlite3.connect(get_db_path())
c = conn.cursor()

# Find all photos that have a segment score of 0.0
c.execute("""
    SELECT s.id, m.file_path 
    FROM Segments s 
    JOIN MediaFiles m ON s.media_file_id = m.id 
    WHERE m.type = 'photo' AND s.score = 0.0
""")
rows = c.fetchall()

print(f"Found {len(rows)} photos to backfill...")
for seg_id, path in rows:
    try:
        score = score_photo(path)
        c.execute("UPDATE Segments SET score = ? WHERE id = ?", (score, seg_id))
        print(f"Updated {path} with score {score}")
    except Exception as e:
        print(f"Error on {path}: {e}")

conn.commit()
conn.close()
print("Backfill complete.")
