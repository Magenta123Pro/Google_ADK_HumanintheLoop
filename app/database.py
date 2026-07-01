import os
import sqlite3
import json
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "perimeter_db.db")
COACH_USERNAME = os.getenv("COACH_USERNAME", "health_coach")
COACH_PASSWORD = os.getenv("COACH_PASSWORD", "CoachSecure2026!")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL,
        age INTEGER NOT NULL,
        gender TEXT NOT NULL,
        perimenopause_status TEXT NOT NULL
    )
    """)
    
    # safe migration to add email column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    
    # Create daily_logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        score INTEGER NOT NULL,
        answers TEXT NOT NULL, -- JSON string of selected options
        coach_note TEXT DEFAULT '',
        jokes TEXT NOT NULL, -- JSON list of jokes
        girl_talk TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(user_id, date)
    )
    """)
    
    # Delete old coach user if it exists to avoid legacy access
    cursor.execute("DELETE FROM users WHERE username = 'coach'")
    
    # Insert default coach if not exists, or update password if it exists
    cursor.execute("SELECT id FROM users WHERE username = ?", (COACH_USERNAME,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
        INSERT INTO users (username, password, email, name, age, gender, perimenopause_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (COACH_USERNAME, COACH_PASSWORD, 'coach@perimeter.ai', 'Health Coach', 40, 'female', 'yes'))
    else:
        cursor.execute("""
        UPDATE users SET password = ? WHERE username = ?
        """, (COACH_PASSWORD, COACH_USERNAME))

    
    conn.commit()
    conn.close()

def register_user(username, password, email, name, age, gender, perimenopause_status):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if username exists and if it belongs to an ineligible user
        cursor.execute("SELECT id, age, gender, perimenopause_status FROM users WHERE username = ?", (username,))
        existing = cursor.fetchone()
        if existing:
            try:
                ext_age = int(existing["age"])
            except (ValueError, TypeError):
                ext_age = 0
            ext_gender = (existing["gender"] or "").lower()
            ext_peri = (existing["perimenopause_status"] or "").lower()
            
            is_ineligible = (ext_age < 35 or ext_age > 80 or ext_gender != "female" or ext_peri != "yes")
            if is_ineligible:
                cursor.execute("DELETE FROM users WHERE id = ?", (existing["id"],))
            else:
                return {"success": False, "error": "Username already exists."}

        cursor.execute("""
        INSERT INTO users (username, password, email, name, age, gender, perimenopause_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, password, email, name, age, gender, perimenopause_status))
        conn.commit()
        user_id = cursor.lastrowid
        return {"success": True, "user_id": user_id}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "Username already exists."}
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {
            "success": True,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "name": user["name"],
                "age": user["age"],
                "gender": user["gender"],
                "perimenopause_status": user["perimenopause_status"],
                "is_coach": user["username"] == COACH_USERNAME
            }
        }
    return {"success": False, "error": "Invalid username or password."}

def verify_coach_credentials(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    return user is not None and username == COACH_USERNAME


def get_user_email(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row["email"] if row else ""

def save_daily_log(user_id, date, score, answers, jokes, girl_talk):
    conn = get_db_connection()
    cursor = conn.cursor()
    answers_str = json.dumps(answers)
    jokes_str = json.dumps(jokes)
    try:
        cursor.execute("""
        INSERT INTO daily_logs (user_id, date, score, answers, jokes, girl_talk)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET
            score=excluded.score,
            answers=excluded.answers,
            jokes=excluded.jokes,
            girl_talk=excluded.girl_talk
        """, (user_id, date, score, answers_str, jokes_str, girl_talk))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving daily log: {e}")
        return False
    finally:
        conn.close()

def save_coach_note(user_id, date, coach_note):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        UPDATE daily_logs SET coach_note = ? WHERE user_id = ? AND date = ?
        """, (coach_note, user_id, date))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving coach note: {e}")
        return False
    finally:
        conn.close()

def get_user_logs(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT date, score, answers, coach_note, jokes, girl_talk FROM daily_logs WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for row in rows:
        logs.append({
            "date": row["date"],
            "score": row["score"],
            "answers": json.loads(row["answers"]),
            "coach_note": row["coach_note"],
            "jokes": json.loads(row["jokes"]),
            "girl_talk": row["girl_talk"]
        })
    return logs

def get_user_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, password, email FROM users WHERE LOWER(email) = LOWER(?)", (email,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {
            "username": user["username"],
            "password": user["password"],
            "email": user["email"]
        }
    return None

# Initialize tables
init_db()
