import sqlite3, os
db = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server', 'sensor_data.db')
conn = sqlite3.connect(db)
rows = conn.execute("SELECT request_id,status FROM collection_requests WHERE status='RECEIVED' AND completed_at IS NULL ORDER BY created_at").fetchall()
print(f"Stale RECEIVED records: {len(rows)}")
for r in rows[:10]:
    print(f"  {r[0]} {r[1]}")
conn.execute("DELETE FROM collection_requests WHERE status='RECEIVED' AND completed_at IS NULL")
conn.commit()
conn.close()
print(f"Cleaned {len(rows)} stale RECEIVED records")