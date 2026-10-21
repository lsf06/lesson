with open("app.py", encoding="utf-8") as f:
    data = f.read()
old = "    conn.commit()\n    conn.close()\n    log.info('Database initialized: %s', DB_PATH)"
new = """    c.execute('''CREATE TABLE IF NOT EXISTS captured_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    source TEXT DEFAULT 'precaptured',
                    created_at TEXT
                )''')
    conn.commit()
    conn.close()
    log.info('Database initialized: %s', DB_PATH)"""
data = data.replace(old, new, 1)
with open("app.py", "w", encoding="utf-8") as f:
    f.write(data)
import ast
ast.parse(open("app.py", encoding="utf-8").read())
print("Syntax OK!")