import os
import sqlite3
import hashlib
import uuid

DATABASE_PATH = os.environ.get("DATABASE_PATH", "ideasphere.db")

DEFAULT_ADMIN_PASSWORD = "admin123"


def get_db_connection():
    """Open a SQLite connection. One per call — SQLite handles concurrent readers fine,
    and Flask runs request handlers on separate threads."""
    conn = sqlite3.connect(
        DATABASE_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False,
    )
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password, salt=None):
    if salt is None:
        salt = uuid.uuid4().hex
    hashed = hashlib.sha256(salt.encode() + password.encode()).hexdigest()
    return f"{salt}${hashed}"


def check_password(stored_password, provided_password):
    if not stored_password or not provided_password:
        return False
    salt = stored_password.split('$')[0]
    hashed = hashlib.sha256(salt.encode() + provided_password.encode()).hexdigest()
    return stored_password == f"{salt}${hashed}"


def initialize_db():
    """Create necessary tables if they don't exist."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                session_id TEXT PRIMARY KEY,
                openai_api_key TEXT,
                openai_model TEXT,
                system_prompt TEXT,
                combination_prompt TEXT,
                generation_prompt TEXT,
                active_prompt_group_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS prompt_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                combination_prompt TEXT NOT NULL,
                generation_prompt TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS global_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS gold_ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idea_text TEXT NOT NULL,
                headline TEXT NOT NULL,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Ensure image_url exists on gold_ideas (older DBs).
        cur.execute("PRAGMA table_info(gold_ideas)")
        cols = {row[1] for row in cur.fetchall()}
        if 'image_url' not in cols:
            print("Adding image_url column to gold_ideas table...")
            cur.execute("ALTER TABLE gold_ideas ADD COLUMN image_url TEXT")

        cur.execute("SELECT setting_value FROM global_settings WHERE setting_key = 'admin_password'")
        if not cur.fetchone():
            hashed_password = hash_password(DEFAULT_ADMIN_PASSWORD)
            cur.execute(
                "INSERT INTO global_settings (setting_key, setting_value) VALUES ('admin_password', ?)",
                (hashed_password,),
            )
            print("Default admin password set. Please change it!")

        cur.execute("SELECT setting_value FROM global_settings WHERE setting_key = 'rating_prompt'")
        if not cur.fetchone():
            default_rating_prompt = """Rate this idea on a scale of 0-3 stars, where:
0 stars = Not valuable
1 star = Somewhat valuable
2 stars = Valuable
3 stars = Very valuable

Please consider the idea's originality, practicality, and potential impact when assigning your rating."""
            cur.execute(
                "INSERT INTO global_settings (setting_key, setting_value) VALUES ('rating_prompt', ?)",
                (default_rating_prompt,),
            )
            print("Default rating prompt set.")

        cur.execute("SELECT COUNT(*) FROM prompt_groups")
        if cur.fetchone()[0] == 0:
            cur.execute(
                """
                INSERT INTO prompt_groups (name, system_prompt, combination_prompt, generation_prompt, is_default)
                VALUES (?, ?, ?, ?, 1)
                """,
                (
                    'Default',
                    'You are a brilliant inventor that generates ideas.',
                    'Generate 1 possible combination, focusing on how these ideas could work together',
                    'Generate 3 related ideas for the concept',
                ),
            )
            print("Default prompt group created.")

        conn.commit()
        print(f"Database initialized successfully at {DATABASE_PATH}.")
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_user_settings(session_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT openai_api_key, openai_model, active_prompt_group_id
            FROM user_settings
            WHERE session_id = ?
            """,
            (session_id,),
        )
        result = cur.fetchone()

        if result:
            user_settings = {
                "openai_api_key": result[0],
                "openai_model": result[1],
                "active_prompt_group_id": result[2],
            }

            if result[2]:
                cur.execute(
                    """
                    SELECT id, name, system_prompt, combination_prompt, generation_prompt
                    FROM prompt_groups WHERE id = ?
                    """,
                    (result[2],),
                )
                prompt_group = cur.fetchone()
                if prompt_group:
                    user_settings.update({
                        "prompt_group_id": prompt_group[0],
                        "prompt_group_name": prompt_group[1],
                        "system_prompt": prompt_group[2],
                        "combination_prompt": prompt_group[3],
                        "generation_prompt": prompt_group[4],
                    })
            else:
                cur.execute(
                    """
                    SELECT id, name, system_prompt, combination_prompt, generation_prompt
                    FROM prompt_groups WHERE is_default = 1 LIMIT 1
                    """
                )
                default_group = cur.fetchone()
                if default_group:
                    user_settings.update({
                        "prompt_group_id": default_group[0],
                        "prompt_group_name": default_group[1],
                        "system_prompt": default_group[2],
                        "combination_prompt": default_group[3],
                        "generation_prompt": default_group[4],
                    })
            return user_settings

        cur.execute(
            """
            SELECT id, name, system_prompt, combination_prompt, generation_prompt
            FROM prompt_groups WHERE is_default = 1 LIMIT 1
            """
        )
        default_group = cur.fetchone()
        if default_group:
            return {
                "openai_api_key": "",
                "openai_model": "openai/gpt-4o-mini",
                "prompt_group_id": default_group[0],
                "prompt_group_name": default_group[1],
                "system_prompt": default_group[2],
                "combination_prompt": default_group[3],
                "generation_prompt": default_group[4],
            }
        return None
    except Exception as e:
        print(f"Error getting user settings: {str(e)}")
        return None
    finally:
        conn.close()


def save_user_settings(session_id, settings):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM user_settings WHERE session_id = ?", (session_id,))
        exists = cur.fetchone() is not None

        if exists:
            cur.execute(
                """
                UPDATE user_settings
                SET openai_api_key = ?, openai_model = ?, active_prompt_group_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (
                    settings.get('openai_api_key', ''),
                    settings.get('openai_model', 'openai/gpt-4o-mini'),
                    settings.get('active_prompt_group_id'),
                    session_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO user_settings (session_id, openai_api_key, openai_model, active_prompt_group_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    settings.get('openai_api_key', ''),
                    settings.get('openai_model', 'openai/gpt-4o-mini'),
                    settings.get('active_prompt_group_id'),
                ),
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving user settings: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()


def set_user_prompt_group(session_id, prompt_group_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM prompt_groups WHERE id = ?", (prompt_group_id,))
        if not cur.fetchone():
            print(f"Prompt group ID {prompt_group_id} not found")
            return False

        cur.execute("SELECT 1 FROM user_settings WHERE session_id = ?", (session_id,))
        exists = cur.fetchone() is not None

        if exists:
            cur.execute(
                """
                UPDATE user_settings
                SET active_prompt_group_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (prompt_group_id, session_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO user_settings (session_id, openai_api_key, openai_model, active_prompt_group_id)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, '', 'openai/gpt-4o-mini', prompt_group_id),
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error setting user prompt group: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_all_prompt_groups():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, system_prompt, combination_prompt, generation_prompt, is_default
            FROM prompt_groups ORDER BY name
            """
        )
        return [
            {
                "id": r[0],
                "name": r[1],
                "system_prompt": r[2],
                "combination_prompt": r[3],
                "generation_prompt": r[4],
                "is_default": bool(r[5]),
            }
            for r in cur.fetchall()
        ]
    except Exception as e:
        print(f"Error getting prompt groups: {str(e)}")
        return []
    finally:
        conn.close()


def create_prompt_group(name, system_prompt, combination_prompt, generation_prompt, is_default=False):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if is_default:
            cur.execute("UPDATE prompt_groups SET is_default = 0")
        cur.execute(
            """
            INSERT INTO prompt_groups (name, system_prompt, combination_prompt, generation_prompt, is_default)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, system_prompt, combination_prompt, generation_prompt, 1 if is_default else 0),
        )
        new_id = cur.lastrowid
        conn.commit()
        return new_id
    except Exception as e:
        print(f"Error creating prompt group: {str(e)}")
        conn.rollback()
        return None
    finally:
        conn.close()


def update_prompt_group(group_id, name, system_prompt, combination_prompt, generation_prompt, is_default=False):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM prompt_groups WHERE id = ?", (group_id,))
        if not cur.fetchone():
            print(f"Prompt group ID {group_id} not found")
            return False

        if is_default:
            cur.execute("UPDATE prompt_groups SET is_default = 0")

        cur.execute(
            """
            UPDATE prompt_groups
            SET name = ?, system_prompt = ?, combination_prompt = ?,
                generation_prompt = ?, is_default = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, system_prompt, combination_prompt, generation_prompt,
             1 if is_default else 0, group_id),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating prompt group: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()


def delete_prompt_group(group_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_default FROM prompt_groups WHERE id = ?", (group_id,))
        result = cur.fetchone()
        if not result:
            print(f"Prompt group ID {group_id} not found")
            return False
        if result[0]:
            print("Cannot delete the default prompt group")
            return False

        cur.execute(
            """
            UPDATE user_settings
            SET active_prompt_group_id = (SELECT id FROM prompt_groups WHERE is_default = 1 LIMIT 1)
            WHERE active_prompt_group_id = ?
            """,
            (group_id,),
        )
        cur.execute("DELETE FROM prompt_groups WHERE id = ?", (group_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting prompt group: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()


def verify_admin_password(password):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT setting_value FROM global_settings WHERE setting_key = 'admin_password'")
        result = cur.fetchone()
        if not result:
            conn.close()
            initialize_db()
            return password == DEFAULT_ADMIN_PASSWORD
        return check_password(result[0], password)
    except Exception as e:
        print(f"Error verifying admin password: {str(e)}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def update_admin_password(new_password):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        hashed_password = hash_password(new_password)
        cur.execute(
            """
            INSERT INTO global_settings (setting_key, setting_value, updated_at)
            VALUES ('admin_password', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(setting_key) DO UPDATE
                SET setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            """,
            (hashed_password,),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating admin password: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_default_prompt_group():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, system_prompt, combination_prompt, generation_prompt, is_default
            FROM prompt_groups WHERE is_default = 1 LIMIT 1
            """
        )
        result = cur.fetchone()
        if not result:
            return None
        return {
            "id": result[0],
            "name": result[1],
            "system_prompt": result[2],
            "combination_prompt": result[3],
            "generation_prompt": result[4],
            "is_default": bool(result[5]),
        }
    except Exception as e:
        print(f"Error getting default prompt group: {str(e)}")
        return None
    finally:
        conn.close()


_DEFAULT_RATING_PROMPT = """Rate this idea on a scale of 0-3 stars, where:
0 stars = Not valuable
1 star = Somewhat valuable
2 stars = Valuable
3 stars = Very valuable

Please consider the idea's originality, practicality, and potential impact when assigning your rating."""


def get_rating_prompt():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT setting_value FROM global_settings WHERE setting_key = 'rating_prompt'")
        result = cur.fetchone()
        return result[0] if result else _DEFAULT_RATING_PROMPT
    except Exception as e:
        print(f"Error getting rating prompt: {str(e)}")
        return _DEFAULT_RATING_PROMPT
    finally:
        conn.close()


def update_rating_prompt(prompt_text):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO global_settings (setting_key, setting_value, updated_at)
            VALUES ('rating_prompt', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(setting_key) DO UPDATE
                SET setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            """,
            (prompt_text,),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating rating prompt: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()


def save_gold_idea(idea_text, headline, image_url=None):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO gold_ideas (idea_text, headline, image_url) VALUES (?, ?, ?)",
            (idea_text, headline, image_url),
        )
        idea_id = cur.lastrowid
        conn.commit()
        return idea_id
    except Exception as e:
        print(f"Error saving gold idea: {str(e)}")
        conn.rollback()
        return None
    finally:
        conn.close()


def get_gold_ideas(limit=50):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, idea_text, headline, image_url, created_at
            FROM gold_ideas ORDER BY created_at DESC, id DESC LIMIT ?
            """,
            (limit,),
        )
        ideas = []
        for row in cur.fetchall():
            created_at = row[4]
            if created_at is not None and hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            ideas.append({
                "id": row[0],
                "idea_text": row[1],
                "headline": row[2],
                "image_url": row[3],
                "created_at": created_at,
            })
        return ideas
    except Exception as e:
        print(f"Error getting gold ideas: {str(e)}")
        return []
    finally:
        conn.close()
