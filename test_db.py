import sqlite3

def check_db():
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    cursor.execute("SELECT key FROM dashboard_apikey LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"Found API key: {row[0]}")
    else:
        print("No API keys found.")
    conn.close()

if __name__ == "__main__":
    check_db()
