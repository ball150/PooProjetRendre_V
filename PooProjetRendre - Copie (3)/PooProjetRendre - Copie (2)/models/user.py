import sqlite3
import config_sqlite as config
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, password, email, role_id, confirmed):
        self.id = id
        self.username = username
        self.password = password
        self.email = email
        self.role_id = role_id
        self.confirmed = confirmed

    @staticmethod
    def get_by_username(username):
        conn = config.get_connection()
        conn.row_factory = sqlite3.Row  # permet d'accéder aux colonnes par nom
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(row["id"], row["username"], row["password"], row["email"], row["role_id"], row["confirmed"])

    @staticmethod
    def get_by_id(user_id):
        conn = config.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(row["id"], row["username"], row["password"], row["email"], row["role_id"], row["confirmed"])

    @staticmethod
    def exists(username, email):
        conn = config.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    @staticmethod
    def create(username, password, email, role_id, token=None):
        conn = config.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, password, email, role_id, confirmed)
            VALUES (?, ?, ?, ?, 1)
        """, (username, password, email, role_id))
        conn.commit()
        conn.close()
