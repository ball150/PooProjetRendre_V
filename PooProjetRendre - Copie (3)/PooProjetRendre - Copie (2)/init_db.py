import sqlite3

def init_database():
    try:
        # Connexion à la base SQLite
        conn = sqlite3.connect('app.db')
        cursor = conn.cursor()

        # Suppression des tables existantes (dans l'ordre inverse des dépendances)
        cursor.execute("DROP TABLE IF EXISTS emploi_du_temps")
        cursor.execute("DROP TABLE IF EXISTS disponibilites")
        cursor.execute("DROP TABLE IF EXISTS absences")
        cursor.execute("DROP TABLE IF EXISTS sessions")
        cursor.execute("DROP TABLE IF EXISTS courses")
        cursor.execute("DROP TABLE IF EXISTS users")

        # Recréation des tables (dans l'ordre des dépendances)
        # Table des utilisateurs
        cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role_id INTEGER NOT NULL,   -- 1=Chef, 2=Enseignant, 3=Responsable, 4=Étudiant
            confirmed BOOLEAN DEFAULT 0
        )
        """)

        # Table des cours
        cursor.execute("""
        CREATE TABLE courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            volume_horaire INTEGER NOT NULL,
            teacher_id INTEGER,
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        )
        """)

        # Table des séances
        cursor.execute("""
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            heure_debut TEXT,
            heure_fin TEXT,
            duree REAL,
            contenu TEXT,
            valide BOOLEAN DEFAULT 0,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        )
        """)

        # Table des absences
        cursor.execute("""
        CREATE TABLE absences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            student_id INTEGER,
            justifie BOOLEAN DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (student_id) REFERENCES users(id)
        )
        """)

        # Table des disponibilités
        cursor.execute("""
        CREATE TABLE disponibilites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            jour TEXT,
            heure_debut TEXT,
            heure_fin TEXT,
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        )
        """)

        # Table emploi du temps
        cursor.execute("""
        CREATE TABLE emploi_du_temps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jour TEXT NOT NULL,
            heure TEXT NOT NULL,
            course_id INTEGER,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
        """)

        # Insertion des utilisateurs
        users = [
            ('chefdep', 'chef123', 'chef@ufr.sn', 1, 1),  # Chef
            ('prof1', 'pass1', 'sileymaneb628@gmail.com', 2, 1),  # Enseignant 1
            ('prof2', 'pass2', 'prof2@ufr.sn', 2, 1),  # Enseignant 2
        ]
        cursor.executemany("INSERT INTO users (username, password, email, role_id, confirmed) VALUES (?, ?, ?, ?, ?)", users)

        # Insertion des étudiants
        etudiants = [
            ('maimouna.ba', 'pass1', 'maimouna.ba@univ-thies.sn', 4, 1),
            ('ngor.ba', 'pass2', 'ngor.ba@univ-thies.sn', 4, 1),
            ('sileymane.ball', 'pass3', 'sileymane.ball@univ-thies.sn', 4, 1),
            ('diariatou.basse', 'pass4', 'diariatou.basse@univ-thies.sn', 4, 1),
            ('mouhamed.deme', 'pass5', 'mouhamed.deme@univ-thies.sn', 4, 1),
            ('fatoumata.diallo', 'pass7', 'fatoumata.diallo@univ-thies.sn', 4, 1),
            ('code.diaw', 'pass8', 'code.diaw@univ-thies.sn', 4, 1),
            ('gora.diaw', 'pass9', 'gora.diaw@univ-thies.sn', 4, 1),
            ('mouhamed.diaw', 'pass10', 'mouhamed.diaw@univ-thies.sn', 4, 1),
            ('fatou.diene', 'pass11', 'fatou.diene@univ-thies.sn', 4, 1),
            ('abdoul.dione', 'pass13', 'abdoul.dione@univ-thies.sn', 4, 1),
            ('sokhna.dione', 'pass14', 'sokhna.dione@univ-thies.sn', 4, 1),
            ('marieme.keita', 'pass15', 'marieme.keita@univ-thies.sn', 4, 1),
            ('dib.marone', 'pass16', 'dib.marone@univ-thies.sn', 4, 1),
            ('papa.mbaye', 'pass17', 'papa.mbaye@univ-thies.sn', 4, 1),
            ('abdoulaye.ndao', 'pass18', 'abdoulaye.ndao@univ-thies.sn', 4, 1),
            ('fatou.ndiaye', 'pass19', 'fatou.ndiaye@univ-thies.sn', 4, 1),
            ('khadidiatou.ndong', 'pass20', 'khadidiatou.ndong@univ-thies.sn', 4, 1),
            ('aby.niang', 'pass21', 'aby.niang@univ-thies.sn', 4, 1),
            ('adama.sene', 'pass22', 'adama.sene@univ-thies.sn', 4, 1),
            ('mouhamet.sy', 'pass23', 'mouhamet.sy@univ-thies.sn', 4, 1),
            ('nene.thiam', 'pass24', 'nene.thiam@univ-thies.sn', 4, 1),
            ('salla.thiam', 'pass25', 'salla.thiam@univ-thies.sn', 4, 1),
        ]
        cursor.executemany("INSERT INTO users (username, password, email, role_id, confirmed) VALUES (?, ?, ?, ?, ?)", etudiants)

        # Insertion des cours
        cours = [
            ('Programmation Python', 20, 2),  # attribué à prof1 (id=2)
            ('Systèmes d\'Information Géographique', 30, 3)  # attribué à prof2 (id=3)
        ]
        cursor.executemany("INSERT INTO courses (name, volume_horaire, teacher_id) VALUES (?, ?, ?)", cours)

        # Insertion des séances
        seances = [
            (1, '2025-06-01', '08:00', '10:00', 2.0, 'Introduction à Python', 0),
            (1, '2025-06-02', '10:00', '13:00', 3.0, 'Les boucles et conditions', 1)
        ]
        cursor.executemany("INSERT INTO sessions (course_id, date, heure_debut, heure_fin, duree, contenu, valide) VALUES (?, ?, ?, ?, ?, ?, ?)", seances)

        conn.commit()
        print("✅ Base de données initialisée avec succès !")
        print(f"👥 {len(users) + len(etudiants)} utilisateurs insérés")
        print(f"📚 {len(cours)} cours insérés")
        print(f"🗓️ {len(seances)} séances insérées")

    except sqlite3.Error as e:
        print(f"❌ Erreur SQLite: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    init_database()