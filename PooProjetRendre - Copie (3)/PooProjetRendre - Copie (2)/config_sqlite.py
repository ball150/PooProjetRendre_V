import sqlite3

DATABASE = 'app.db'
SECRET_KEY = 'clé_super_secrète'

def get_connection():
    return sqlite3.connect(DATABASE)
