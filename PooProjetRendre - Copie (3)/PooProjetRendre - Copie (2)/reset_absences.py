import sqlite3

conn = sqlite3.connect('app.db')
c = conn.cursor()
c.execute("DROP TABLE IF EXISTS absences")
conn.commit()
conn.close()
print("Table absences supprimée !")
