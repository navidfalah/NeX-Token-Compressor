import sqlite3
import pprint

conn = sqlite3.connect('db.sqlite3')
c = conn.cursor()
c.execute("SELECT id, filename, file_size FROM dashboard_maskeddocument")
rows = c.fetchall()
print("NUMBER OF ROWS:", len(rows))
for r in rows:
    print(repr(r))
conn.close()
