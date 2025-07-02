from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models.user import User
import config_sqlite as config
import sqlite3
import io
import pandas as pd
from xhtml2pdf import pisa
from flask import make_response
import smtplib
from email.mime.text import MIMEText
import config_mail  # ← le fichier que tu viens de créer

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def date_to_jour(date_str):
    jour_index = datetime.datetime.strptime(date_str, "%Y-%m-%d").weekday()
    jours = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
    return jours[jour_index]


@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.get_by_username(username)
        if user and user.password == password and user.confirmed:
            login_user(user)
            flash("Connexion réussie", "info")
            if user.role_id == 1:
                return redirect(url_for('chef'))
            elif user.role_id == 2:
                return redirect(url_for('enseignant'))
            elif user.role_id == 3:
                return redirect(url_for('responsable'))
        else:
            flash("Échec de la connexion ou compte non activé", "danger")
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role_id = int(request.form['role_id'])

        if role_id not in [2, 3]:
            flash("Rôle non autorisé", "danger")
            return redirect(url_for('register'))

        if User.exists(username, email):
            flash("Nom d'utilisateur ou email déjà utilisé", "danger")
        else:
            User.create(username, password, email, role_id)
            flash("Inscription réussie ! Vous pouvez vous connecter", "success")
            return redirect(url_for('login'))
    return render_template('register.html')



@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/chef')
@login_required
def chef():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Statistiques principales
    cursor.execute("SELECT COUNT(*) FROM users WHERE role_id = 2")
    nb_enseignants = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE role_id = 4")
    nb_etudiants = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE valide = 1")
    seances_valides = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessions")
    total_seances = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE valide = 0")
    en_attente = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM absences a JOIN users u ON a.student_id = u.id WHERE justifie = 0")
    nb_sanctions = cursor.fetchone()[0]

    # Séances du jour
    today = datetime.date.today().isoformat()
    cursor.execute("""
        SELECT s.id, s.heure_debut, s.heure_fin, c.name AS matiere, u.username AS enseignant, s.valide
        FROM sessions s
        JOIN courses c ON s.course_id = c.id
        LEFT JOIN users u ON c.teacher_id = u.id
        WHERE s.date = ?
        ORDER BY s.heure_debut
    """, (today,))
    seances_jour = cursor.fetchall()

    # Alertes
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE valide = 0")
    alertes_attente = cursor.fetchone()[0]
    cursor.execute("""
        SELECT COUNT(DISTINCT a.student_id) FROM absences a
        JOIN users u ON a.student_id = u.id
        WHERE justifie = 0
    """)
    alertes_sanctions = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM courses WHERE teacher_id IS NULL")
    cours_non_assignes = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "chef.html",
        current_user=current_user,
        nb_enseignants=nb_enseignants,
        nb_etudiants=nb_etudiants,
        seances_valides=seances_valides,
        total_seances=total_seances,
        en_attente=en_attente,
        nb_sanctions=nb_sanctions,
        seances_jour=seances_jour,
        alertes_attente=alertes_attente,
        alertes_sanctions=alertes_sanctions,
        cours_non_assignes=cours_non_assignes
    )


@app.route('/chef/assigner_cours', methods=['GET', 'POST'])
@login_required
def assigner_cours():
    if current_user.role_id != 1:
        return "Accès refusé", 403
    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if request.method == 'POST':
        cours_id = request.form['cours_id']
        enseignant_id = request.form['enseignant_id']
        cursor.execute("UPDATE courses SET teacher_id = ? WHERE id = ?", (enseignant_id, cours_id))
        conn.commit()
        flash("Cours assigné avec succès", "success")
    cursor.execute("SELECT * FROM courses")
    cours_list = cursor.fetchall()
    cursor.execute("SELECT * FROM users WHERE role_id = 2")
    enseignants = cursor.fetchall()
    conn.close()
    return render_template('assigner_cours.html', cours_list=cours_list, enseignants=enseignants)

@app.route('/chef/utilisateurs', methods=['GET', 'POST'])
@login_required
def gestion_utilisateurs():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        if User.exists(username, email):
            flash("Nom d'utilisateur ou email déjà utilisé", "danger")
        else:
            # Crée l'utilisateur en base
            User.create(username, password, email, role_id=2)

            # Envoie un email au nouvel enseignant
            from flask import url_for
            lien_login = url_for('login', _external=True)
            sujet = "Votre compte enseignant a été créé"

            message = f"""
Bonjour {username},

Votre compte enseignant vient d'être créé sur la plateforme UFR SI.

Identifiant : {username}
Mot de passe : {password}

Connectez-vous ici : {lien_login}

Merci de modifier votre mot de passe après la première connexion.

Cordialement,
Le Chef de filière
"""
            # Appelle ta fonction d'envoi de mail (doit déjà exister !)
            envoyer_email(email, sujet, message)

            flash("Enseignant ajouté avec succès et email envoyé.", "success")

    cursor.execute("SELECT * FROM users WHERE role_id = 2")
    enseignants = cursor.fetchall()
    conn.close()
    return render_template('gestion_utilisateurs.html', enseignants=enseignants)


@app.route('/chef/supprimer_enseignant/<int:user_id>')
@login_required
def supprimer_enseignant(user_id):
    if current_user.role_id != 1:
        return "Accès refusé", 403
    conn = config.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ? AND role_id = 2", (user_id,))
    conn.commit()
    conn.close()
    flash("Enseignant supprimé", "warning")
    return redirect(url_for('gestion_utilisateurs'))

import re

@app.route('/chef/ajouter_cours', methods=['GET', 'POST'])
@login_required
def ajouter_cours():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    if request.method == 'POST':
        nom = request.form['nom']
        volume_horaire = request.form['volume_horaire']

        # ✅ Vérification du format HH:MM
        if not re.match(r'^\d{1,2}:\d{2}$', volume_horaire):
            flash("⛔ Format du volume horaire invalide. Exemple attendu : 02:30", "danger")
            return redirect(url_for('ajouter_cours'))

        conn = config.get_connection()
        cursor = conn.cursor()

        # 📝 Insérer dans la base de données
        cursor.execute("""
            INSERT INTO courses (name, volume_horaire)
            VALUES (?, ?)
        """, (nom, volume_horaire))

        conn.commit()
        conn.close()
        flash("✅ Cours ajouté avec succès", "success")
        return redirect(url_for('chef'))

    return render_template('ajouter_cours.html')



@app.route('/chef/seances')
@login_required
def voir_seances():
    if current_user.role_id != 1:
        return "Accès refusé", 403
    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.id, s.date, s.heure_debut, s.heure_fin, s.duree, s.valide,
           s.contenu, c.name AS cours, u.username AS enseignant
    FROM sessions s
    JOIN courses c ON s.course_id = c.id
    LEFT JOIN users u ON c.teacher_id = u.id
    ORDER BY s.date DESC
    """)
    seances = cursor.fetchall()
    conn.close()
    return render_template("voir_seances.html", seances=seances)

@app.route('/chef/dashboard')
@login_required
def dashboard():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sessions")
    total_seances = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE valide = 1")
    seances_validees = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE valide = 0")
    seances_non_validees = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM courses")
    total_cours = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE role_id = 2")
    total_enseignants = cursor.fetchone()[0]
    conn.close()

    return render_template("dashboard.html",
        total_seances=total_seances,
        seances_validees=seances_validees,
        seances_non_validees=seances_non_validees,
        total_cours=total_cours,
        total_enseignants=total_enseignants)

@app.route('/chef/generer_emploi')
@login_required
def generer_emploi():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    try:
        conn = config.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 🔄 Vider le planning actuel
        cursor.execute("DELETE FROM emploi_du_temps")

        # 🗓️ Créneaux disponibles
        jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
        heures = ["08:00", "10:00", "14:00", "16:00"]

        # 📚 Récupérer les cours à planifier
        cursor.execute("SELECT id FROM courses")
        cours_ids = [row['id'] for row in cursor.fetchall()]

        # 🧠 Répartition des cours dans les créneaux
        index = 0
        for jour in jours:
            for heure in heures:
                if index >= len(cours_ids):
                    break  # Tous les cours ont été placés

                course_id = cours_ids[index]
                cursor.execute("""
                    INSERT INTO emploi_du_temps (jour, heure, course_id)
                    VALUES (?, ?, ?)
                """, (jour, heure, course_id))

                index += 1

        conn.commit()
        flash("✅ Emploi du temps généré avec succès !", "success")

    except sqlite3.Error as e:
        print(f"❌ Erreur SQLite : {e}")
        flash("⛔ Erreur lors de la génération de l'emploi du temps.", "danger")
    finally:
        if conn:
            conn.close()

    return redirect(url_for('voir_emploi'))


@app.route('/chef/ajouter_seance', methods=['GET', 'POST'])
@login_required
def ajouter_seance():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'POST':
        course_id = request.form['course_id']
        date = request.form['date']
        heure_debut = request.form['heure_debut']
        heure_fin = request.form['heure_fin']
        duree = request.form['duree']

        # 🔹 Vérification de conflit
        cursor.execute("""
            SELECT s.id FROM sessions s
            WHERE s.date = ?
            AND (
                (? BETWEEN s.heure_debut AND s.heure_fin) OR
                (? BETWEEN s.heure_debut AND s.heure_fin) OR
                (s.heure_debut BETWEEN ? AND ?) OR
                (s.heure_fin BETWEEN ? AND ?)
            )
        """, (date, heure_debut, heure_fin, heure_debut, heure_fin, heure_debut, heure_fin))

        conflit = cursor.fetchall()

        if conflit:
            flash("⛔ Une autre séance est déjà prévue à cette date et cet horaire.", "danger")
        else:
            # 🔹 Ajouter la séance
            cursor.execute("""
                INSERT INTO sessions (course_id, date, heure_debut, heure_fin, duree, valide)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (course_id, date, heure_debut, heure_fin, duree))

            # 🔹 Ajouter dans emploi_du_temps
            jour_semaine = datetime.datetime.strptime(date, "%Y-%m-%d").strftime('%A')
            jour_fr = {
                'Monday': 'Lundi', 'Tuesday': 'Mardi', 'Wednesday': 'Mercredi',
                'Thursday': 'Jeudi', 'Friday': 'Vendredi'
            }.get(jour_semaine, jour_semaine)

            cursor.execute("""
                INSERT INTO emploi_du_temps (jour, heure, course_id)
                VALUES (?, ?, ?)
            """, (jour_fr, heure_debut, course_id))

            conn.commit()
            flash("✅ Séance ajoutée et emploi du temps mis à jour", "success")

    cursor.execute("SELECT id, name FROM courses")
    cours = cursor.fetchall()
    conn.close()
    return render_template("ajouter_seances.html", cours=cours)

@app.route('/chef/modifier_responsable', methods=['GET', 'POST'])
@login_required
def modifier_responsable():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Récupérer le responsable actuel
    cursor.execute("SELECT * FROM users WHERE role_id = 3 LIMIT 1")
    responsable = cursor.fetchone()

    if request.method == 'POST':
        nouvel_email = request.form['email']

        # Vérifie si l'email existe déjà dans un autre compte
        cursor.execute("SELECT * FROM users WHERE email = ? AND id != ?", (nouvel_email, responsable["id"]))
        doublon = cursor.fetchone()

        if doublon:
            flash("⛔ Cet email est déjà utilisé par un autre utilisateur.", "danger")
        else:
            cursor.execute("UPDATE users SET email = ? WHERE id = ?", (nouvel_email, responsable["id"]))
            conn.commit()
            flash("✅ Email du responsable mis à jour avec succès", "success")
            return redirect(url_for('chef'))

    conn.close()
    return render_template("modifier_responsable.html", responsable=responsable)






# Route Flask à ajouter dans app.py ou routes/chef.py

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
import config_sqlite as config
import sqlite3
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import datetime

@app.route('/chef/generer_edt', methods=['GET'])
@login_required
def generer_edt():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Récupérer les enseignants
    cursor.execute("SELECT id, username, email FROM users WHERE role_id = 2")
    enseignants = cursor.fetchall()

    # Récupérer les séances par enseignant pour la semaine actuelle
    semaine_actuelle = datetime.date.today().isocalendar()[1]
    annee = datetime.date.today().year

    for ens in enseignants:
        cursor.execute("""
            SELECT s.date, s.heure_debut, s.heure_fin, c.name AS cours
            FROM sessions s
            JOIN courses c ON s.course_id = c.id
            WHERE c.teacher_id = ? AND strftime('%W', s.date) = ? AND strftime('%Y', s.date) = ?
            ORDER BY s.date
        """, (ens['id'], f"{semaine_actuelle:02}", str(annee)))
        seances = cursor.fetchall()

        if seances:
            contenu_html = render_template("email_emploi_enseignant.html", enseignant=ens, seances=seances)
            envoyer_email(destinataire=ens['email'], sujet="Votre emploi du temps de la semaine", html=contenu_html)

    # Email pour le responsable de classe (supposons 1 seul)
    cursor.execute("SELECT email FROM users WHERE role_id = 3 LIMIT 1")
    responsable = cursor.fetchone()

    if responsable:
        cursor.execute("""
            SELECT s.date, s.heure_debut, s.heure_fin, u.username AS enseignant, c.name AS cours
            FROM sessions s
            JOIN courses c ON s.course_id = c.id
            JOIN users u ON c.teacher_id = u.id
            WHERE strftime('%W', s.date) = ? AND strftime('%Y', s.date) = ?
            ORDER BY s.date, s.heure_debut
        """, (f"{semaine_actuelle:02}", str(annee)))
        global_seances = cursor.fetchall()

        contenu_responsable = render_template("email_emploi_responsable.html", seances=global_seances)
        envoyer_email(responsable['email'], "📊 Emploi du temps global", contenu_responsable)



    conn.close()
    flash("Emploi du temps généré et envoyé avec succès", "success")
    return redirect(url_for('chef'))

@app.route('/chef/emploi')
@login_required
def voir_emploi():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT e.jour, e.heure, c.name AS cours, u.username AS enseignant
        FROM emploi_du_temps e
        JOIN courses c ON e.course_id = c.id
        LEFT JOIN users u ON c.teacher_id = u.id
        ORDER BY 
            CASE e.jour
                WHEN 'Lundi' THEN 1
                WHEN 'Mardi' THEN 2
                WHEN 'Mercredi' THEN 3
                WHEN 'Jeudi' THEN 4
                WHEN 'Vendredi' THEN 5
                ELSE 6
            END,
            e.heure
    """)
    emploi = cursor.fetchall()
    conn.close()

    return render_template("emploi_du_temps.html", emploi=emploi)




@app.route('/chef/generer_emploi')
@login_required
def generer_emploi_automatique():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Récupérer tous les cours avec heures restantes
    cursor.execute("""
        SELECT c.id, c.name, c.volume_horaire, IFNULL(SUM(s.duree), 0) AS realisees
        FROM courses c
        LEFT JOIN sessions s ON s.course_id = c.id
        GROUP BY c.id
        HAVING (c.volume_horaire - IFNULL(SUM(s.duree), 0)) > 0
    """)
    cours_restants = cursor.fetchall()

    # Nettoyer l'ancien emploi du temps
    cursor.execute("DELETE FROM emploi_du_temps")

    # Jours et heures disponibles
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
    heures = ["08:00", "10:00", "12:00", "14:00", "16:00"]
    emploi_utilise = set()

    index = 0
    for cours in cours_restants:
        heures_restantes = cours["volume_horaire"] - cours["realisees"]

        while heures_restantes > 0 and index < len(jours) * len(heures):
            jour = jours[index // len(heures)]
            heure = heures[index % len(heures)]
            index += 1

            # Vérifier si ce créneau est déjà utilisé
            if (jour, heure) in emploi_utilise:
                continue

            emploi_utilise.add((jour, heure))

            # Ajouter au planning (1 séance de 2h par défaut)
            cursor.execute("""
                INSERT INTO emploi_du_temps (jour, heure, course_id)
                VALUES (?, ?, ?)
            """, (jour, heure, cours["id"]))

            heures_restantes -= 2

    conn.commit()
    conn.close()
    flash("Emploi du temps généré avec succès", "success")
    return redirect(url_for('voir_emploi'))



def envoyer_email(destinataire, sujet, message):
    from email.mime.text import MIMEText
    import smtplib
    import config_mail

    msg = MIMEText(message)  # Texte brut
    msg['Subject'] = sujet
    msg['From'] = config_mail.MAIL_USERNAME
    msg['To'] = destinataire

    try:
        server = smtplib.SMTP(config_mail.MAIL_SERVER, config_mail.MAIL_PORT)
        server.starttls()
        server.login(config_mail.MAIL_USERNAME, config_mail.MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ Email envoyé à {destinataire}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de l'email : {e}")






@app.route('/chef/fiche_suivi_cours/<int:cours_id>')
@login_required
def fiche_suivi_cours(cours_id):
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""SELECT c.id, c.name AS nom, c.volume_horaire, 
                             u.username AS enseignant 
                      FROM courses c LEFT JOIN users u ON c.teacher_id = u.id 
                      WHERE c.id = ?""", (cours_id,))
    cours = cursor.fetchone()

    cursor.execute("""SELECT date, heure_debut, heure_fin, duree, contenu, valide 
                      FROM sessions WHERE course_id = ? ORDER BY date""", (cours_id,))
    seances = cursor.fetchall()

    conn.close()

    # Données à adapter selon ton organisation
    return render_template("fiche_suivi_cours.html",
                           cours=cours,
                           seances=seances,
                           filiere="Nom de la filière",
                           annee="2023-2024",
                           option="Nom de l'option")

@app.route('/chef/export_pdf/<int:cours_id>')
@login_required
def export_pdf(cours_id):
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""SELECT c.id, c.name AS nom, c.volume_horaire, 
                             u.username AS enseignant 
                      FROM courses c LEFT JOIN users u ON c.teacher_id = u.id 
                      WHERE c.id = ?""", (cours_id,))
    cours = cursor.fetchone()

    cursor.execute("""SELECT date, heure_debut, heure_fin, duree, contenu, valide 
                      FROM sessions WHERE course_id = ? ORDER BY date""", (cours_id,))
    seances = cursor.fetchall()
    conn.close()

    rendered = render_template("fiche_suivi_cours.html",
                              cours=cours,
                              seances=seances,
                              filiere="Nom de la filière",
                              annee="2023-2024",
                              option="Nom de l'option")

    # Utilisation de xhtml2pdf pour générer le PDF
    from xhtml2pdf import pisa
    result = io.BytesIO()
    pdf = pisa.pisaDocument(io.StringIO(rendered), dest=result)
    if not pdf.err:
        response = make_response(result.getvalue())
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f"attachment; filename=fiche_suivi_{cours['nom']}.pdf"
        return response
    else:
        return "Erreur lors de la génération du PDF", 500

@app.route('/chef/export_excel/<int:cours_id>')
@login_required
def export_excel(cours_id):
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Récupérer les infos du cours
    cursor.execute("""SELECT c.name AS nom, u.username AS enseignant
                      FROM courses c
                      LEFT JOIN users u ON c.teacher_id = u.id
                      WHERE c.id = ?""", (cours_id,))
    cours = cursor.fetchone()

    # Récupérer les séances
    cursor.execute("""SELECT date, heure_debut, heure_fin, duree, contenu, valide
                      FROM sessions WHERE course_id = ? ORDER BY date""", (cours_id,))
    seances = cursor.fetchall()
    conn.close()

    # Convertir en DataFrame pour pandas
    df = pd.DataFrame(seances, columns=["Date", "Heure début", "Heure fin", "Durée", "Contenu", "Validée"])

    # Mise en forme colonne Validée
    df["Validée"] = df["Validée"].apply(lambda v: "Oui" if v else "Non")

    # Préparation du fichier Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="Fiche de Suivi")
        worksheet = writer.sheets["Fiche de Suivi"]

        # Ajout des infos du cours en haut du fichier
        infos = [
            f"Intitulé du cours : {cours['nom'] if cours else ''}",
            f"Enseignant : {cours['enseignant'] if cours else ''}",
        ]
        for idx, info in enumerate(infos):
            worksheet.write(idx, 0, info)

        # Ajout d’un espace pour la signature à la fin
        worksheet.write(df.shape[0] + 4, 0, "Signature de l'enseignant : __________________________")

    output.seek(0)
    filename = f"fiche_suivi_{cours['nom'] if cours else cours_id}.xlsx"
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )
@app.route('/chef/fiches_suivi_cours')
@login_required
def liste_fiches_suivi():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.volume_horaire, 
               u.username AS enseignant
        FROM courses c
        LEFT JOIN users u ON c.teacher_id = u.id
        ORDER BY c.name
    """)
    cours_list = cursor.fetchall()
    conn.close()
    return render_template("liste_fiches_suivi.html", cours_list=cours_list)

# Réutilise ta fonction utilitaire d’envoi d’email !
from flask import url_for

@app.route('/chef/choisir_responsable', methods=['GET', 'POST'])
@login_required
def choisir_responsable():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = sqlite3.connect('app.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Liste des étudiants
    cursor.execute("SELECT * FROM users WHERE role_id = 4")
    etudiants = cursor.fetchall()
    # Responsable actuel
    cursor.execute("SELECT * FROM users WHERE role_id = 3")
    actuel_responsable = cursor.fetchone()

    if request.method == 'POST':
        etu_id = request.form.get('etudiant_id')
        if etu_id:
            # Retire le rôle de responsable à l'ancien si besoin
            cursor.execute("UPDATE users SET role_id = 4 WHERE role_id = 3")
            # Attribue le rôle à l’étudiant choisi
            cursor.execute("SELECT password FROM users WHERE id = ?", (etu_id,))
            mdp = cursor.fetchone()['password']  # On récupère le mot de passe d'origine
            cursor.execute("UPDATE users SET role_id = 3 WHERE id = ?", (etu_id,))
            conn.commit()

            # Infos de l'étudiant choisi
            cursor.execute("SELECT email, username FROM users WHERE id = ?", (etu_id,))
            etu = cursor.fetchone()

            # Générer le lien absolu vers la page login
            lien_login = url_for('login', _external=True)

            # Email personnalisé
            message = (
                f"Bonjour {etu['username']},\n\n"
                "Vous venez d'être désigné(e) Responsable de Classe par le chef de filière.\n"
                f"Votre mot de passe : {mdp}\n\n"
                f"Connectez-vous ici : {lien_login}\n\n"
                "Merci de remplir ce rôle avec sérieux.\n\n"
                "Cordialement,\nL'administration"
            )
            envoyer_email(
                etu['email'],
                "Félicitations ! Vous êtes le Responsable de Classe",
                message
            )
            flash(f"L'étudiant {etu['username']} a bien été désigné responsable et informé par email.", "success")
            return redirect(url_for('chef'))

    conn.close()
    return render_template(
        "choisir_responsable.html",
        etudiants=etudiants,
        actuel_responsable=actuel_responsable
    )



@app.route('/chef/envoyer_emploi_par_mail')
@login_required
def envoyer_emploi_par_mail():
    if current_user.role_id != 1:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    semaine = datetime.date.today().isocalendar()[1]
    annee = datetime.date.today().year

    # Pour chaque enseignant
    cursor.execute("SELECT id, username, email FROM users WHERE role_id=2")
    enseignants = cursor.fetchall()
    for ens in enseignants:
        cursor.execute("""
            SELECT s.date, s.heure_debut, s.heure_fin, c.name AS cours
            FROM sessions s
            JOIN courses c ON s.course_id = c.id
            WHERE c.teacher_id = ? AND strftime('%W', s.date) = ? AND strftime('%Y', s.date) = ?
            ORDER BY s.date
        """, (ens['id'], f"{semaine:02}", str(annee)))
        seances = cursor.fetchall()
        if seances:
            texte_emploi = "\n".join([
                f"- {s['date']} de {s['heure_debut']} à {s['heure_fin']} : {s['cours']}"
                for s in seances
            ])
            message = f"""Bonjour {ens['username']},

Voici votre emploi du temps de la semaine :

{texte_emploi}

Cordialement,
UFR SI
"""
            envoyer_email(ens['email'], "📅 Votre emploi du temps de la semaine", message)

    # -------- Ici tu ajoutes l'envoi pour le responsable --------
    cursor.execute("SELECT username, email FROM users WHERE role_id=3 LIMIT 1")
    responsable = cursor.fetchone()
    if responsable:
        cursor.execute("""
            SELECT s.date, s.heure_debut, s.heure_fin, u.username AS enseignant, c.name AS cours
            FROM sessions s
            JOIN courses c ON s.course_id = c.id
            JOIN users u ON c.teacher_id = u.id
            WHERE strftime('%W', s.date) = ? AND strftime('%Y', s.date) = ?
            ORDER BY s.date, s.heure_debut
        """, (f"{semaine:02}", str(annee)))
        global_seances = cursor.fetchall()
        texte_emploi = "\n".join([
            f"- {s['date']} de {s['heure_debut']} à {s['heure_fin']} : {s['cours']} avec {s['enseignant']}"
            for s in global_seances
        ])
        message_resp = f"""Bonjour {responsable['username']},

Voici l'emploi du temps global de la semaine :

{texte_emploi}

Cordialement,
UFR SI
"""
        envoyer_email(responsable['email'], "📅 Emploi du temps global", message_resp)

    conn.close()
    flash("📧 L'emploi du temps a été envoyé par email aux enseignants et au responsable.", "success")
    return redirect(url_for('chef'))




# (export_pdf et export_excel seront ajoutés ensuite)

@app.route('/enseignant')
@login_required
def enseignant():
    if current_user.role_id != 2:
        return "Accès refusé", 403
    return render_template('enseignant.html')


@app.route('/enseignant/seances/<int:cours_id>', methods=['GET', 'POST'])
@login_required
def seances_cours(cours_id):
    if current_user.role_id != 2:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Vérifie que le cours appartient à l'enseignant connecté
    cursor.execute("SELECT * FROM courses WHERE id = ? AND teacher_id = ?", (cours_id, current_user.id))
    cours = cursor.fetchone()
    if not cours:
        return "Cours introuvable ou accès refusé", 403

    if request.method == 'POST':
        session_id = request.form['session_id']
        contenu = request.form['contenu']
        cursor.execute("UPDATE sessions SET contenu = ? WHERE id = ?", (contenu, session_id))
        conn.commit()
        flash("Contenu pédagogique ajouté. Un email a été envoyé au responsable.", "success")

        # Envoi de l'email au responsable
        cursor.execute("SELECT email FROM users WHERE role_id = 3 LIMIT 1")
        responsable = cursor.fetchone()
        if responsable:
            from flask import url_for
            destinataire = responsable['email']
            sujet = "Nouvelle séance à valider"
            lien_valider = url_for('login', _external=True)

            # Tu peux personnaliser le message ici
            message = f"""
Bonjour,

Une nouvelle séance a été complétée par l'enseignant {current_user.username} pour le cours : {cours['name']}.

Merci de vous connecter pour la valider :
{lien_valider}

Cordialement,
Cahier de Texte Numérique
"""
            envoyer_email(destinataire, sujet, message)

    cursor.execute("SELECT * FROM sessions WHERE course_id = ? ORDER BY date", (cours_id,))
    seances = cursor.fetchall()
    conn.close()

    return render_template("enseignant_seances.html", cours=cours, seances=seances)


@app.route('/enseignant/mes_cours')
@login_required
def mes_cours():
    if current_user.role_id != 2:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.*, 
            (SELECT SUM(duree) FROM sessions s WHERE s.course_id = c.id) as heures_realisees
        FROM courses c
        WHERE c.teacher_id = ?
    """, (current_user.id,))
    cours = cursor.fetchall()
    conn.close()

    return render_template("enseignant_cours.html", cours=cours)




@app.route('/enseignant/suivi_heures')
@login_required
def suivi_heures():
    if current_user.role_id != 2:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.name, c.volume_horaire,
               IFNULL(SUM(s.duree), 0) AS heures_realisees
        FROM courses c
        LEFT JOIN sessions s ON c.id = s.course_id
        WHERE c.teacher_id = ?
        GROUP BY c.id
    """, (current_user.id,))
    cours_heures = cursor.fetchall()
    conn.close()

    # Conversion du volume_horaire (HH:MM ou float/int) en float
    def heure_to_float(horaire):
        if isinstance(horaire, (int, float)):
            return float(horaire)
        if ':' in str(horaire):
            h, m = str(horaire).split(':')
            return float(h) + float(m) / 60
        return float(horaire)

    labels = [c['name'] for c in cours_heures]
    attribuees = [heure_to_float(c['volume_horaire']) for c in cours_heures]
    realisees = [float(c['heures_realisees']) for c in cours_heures]

    # Tu peux afficher ça dans la console pour debug
    print("labels:", labels)
    print("attribuees:", attribuees)
    print("realisees:", realisees)

    return render_template(
        'suivi_heures.html',
        labels=labels,
        attribuees=attribuees,
        realisees=realisees
    )


@app.route('/enseignant/toutes_seances')
@login_required
def toutes_seances_enseignant():
    if current_user.role_id != 2:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id, s.date, s.heure_debut, s.heure_fin, s.duree, s.valide, s.contenu,
               c.name AS cours
        FROM sessions s
        JOIN courses c ON s.course_id = c.id
        WHERE c.teacher_id = ?
        ORDER BY s.date DESC, s.heure_debut ASC
    """, (current_user.id,))
    seances = cursor.fetchall()
    conn.close()

    return render_template("enseignant_toutes_seances.html", seances=seances)

@app.route('/enseignant/absences/<int:session_id>', methods=['GET', 'POST'])
@login_required
def gerer_absences(session_id):
    if current_user.role_id != 2:
        return "Accès refusé", 403

    conn = sqlite3.connect('app.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Liste des étudiants
    cursor.execute("SELECT * FROM users WHERE role_id = 4")
    etudiants = cursor.fetchall()

    if request.method == 'POST':
        absents = request.form.getlist('absents')
        justifies = request.form.getlist('justifies')
        for etu_id in absents:
            justifie = 1 if etu_id in justifies else 0
            # On ne double pas une absence si elle existe déjà pour cette séance
            cursor.execute("""SELECT COUNT(*) FROM absences WHERE session_id=? AND student_id=?""",
                           (session_id, etu_id))
            if cursor.fetchone()[0] == 0:
                cursor.execute("""INSERT INTO absences (session_id, student_id, justifie)
                                  VALUES (?, ?, ?)""", (session_id, etu_id, justifie))
                # Après chaque absence ajoutée, vérifie le total non justifiées
                cursor.execute("""SELECT username, email FROM users WHERE id=?""", (etu_id,))
                etu = cursor.fetchone()
                cursor.execute("""SELECT COUNT(*) FROM absences WHERE student_id=? AND justifie=0""", (etu_id,))
                total_non_just = cursor.fetchone()[0]

                if total_non_just >= 3:
                    # Trouver l'email du chef de filière
                    cursor.execute("SELECT email FROM users WHERE role_id=1 LIMIT 1")
                    chef = cursor.fetchone()
                    if chef:
                        # Email auto au chef
                        from config_mail import MAIL_USERNAME, MAIL_SERVER, MAIL_PORT, MAIL_PASSWORD
                        import smtplib
                        from email.mime.text import MIMEText
                        msg = MIMEText(
                            f"L'étudiant {etu['username']} ({etu['email']}) a atteint {total_non_just} absences non justifiées.\n"
                            "Merci de procéder à une sanction selon le règlement."
                        )
                        msg['Subject'] = f"Alerte : Absences non justifiées pour {etu['username']}"
                        msg['From'] = MAIL_USERNAME
                        msg['To'] = chef['email']
                        try:
                            server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
                            server.starttls()
                            server.login(MAIL_USERNAME, MAIL_PASSWORD)
                            server.send_message(msg)
                            server.quit()
                        except Exception as e:
                            print(f"Erreur lors de l'envoi du mail au chef : {e}")

        conn.commit()
        flash("Absences enregistrées et notifications envoyées si nécessaire.", "success")
        return redirect(url_for('enseignant'))

    # Pour l'affichage GET
    cursor.execute("SELECT * FROM sessions WHERE id=?", (session_id,))
    session = cursor.fetchone()
    # Voir absences déjà saisies
    cursor.execute("SELECT * FROM absences WHERE session_id=?", (session_id,))
    absences = cursor.fetchall()
    conn.close()
    return render_template("gerer_absences.html", etudiants=etudiants, session=session, absences=absences)

@app.route('/enseignant/modifier_justification/<int:absence_id>', methods=['POST'])
@login_required
def modifier_justification(absence_id):
    if current_user.role_id != 2:
        return "Accès refusé", 403

    justifie = int(request.form.get('justifie', 0))
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE absences SET justifie=? WHERE id=?", (justifie, absence_id))
    conn.commit()
    conn.close()
    flash("La justification a bien été modifiée.", "success")
    return redirect(request.referrer or url_for('enseignant'))


from flask import jsonify


@app.route('/enseignant/ajouter_absence', methods=['POST'])
@login_required
def ajouter_absence_ajax():
    if current_user.role_id != 2:
        return jsonify({"success": False, "error": "Accès refusé"}), 403

    data = request.get_json()
    session_id = data.get('session_id')
    etudiant_id = data.get('etudiant_id')
    justifie = data.get('justifie', 0)

    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()

    # Vérifie s'il y a déjà une absence pour cette séance/étudiant
    cursor.execute("SELECT id FROM absences WHERE session_id=? AND student_id=?", (session_id, etudiant_id))
    result = cursor.fetchone()
    if result:
        # Si déjà absent, on peut juste mettre à jour le justificatif
        if justifie:
            cursor.execute("UPDATE absences SET justifie=1 WHERE id=?", (result[0],))
        else:
            cursor.execute("UPDATE absences SET justifie=0 WHERE id=?", (result[0],))
    else:
        cursor.execute("INSERT INTO absences (session_id, student_id, justifie) VALUES (?, ?, ?)",
                       (session_id, etudiant_id, justifie))

    conn.commit()

    # Vérifie nombre d’absences non justifiées de l’étudiant
    cursor.execute("SELECT username, email FROM users WHERE id=?", (etudiant_id,))
    etu = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM absences WHERE student_id=? AND justifie=0", (etudiant_id,))
    total_non_just = cursor.fetchone()[0]

    if total_non_just >= 3 and not justifie:
        # Envoi email chef de filière
        cursor.execute("SELECT email FROM users WHERE role_id=1 LIMIT 1")
        chef = cursor.fetchone()
        if chef:
            from config_mail import MAIL_USERNAME, MAIL_SERVER, MAIL_PORT, MAIL_PASSWORD
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(
                f"L'étudiant {etu[0]} ({etu[1]}) a atteint {total_non_just} absences non justifiées.\n"
                "Merci de procéder à une sanction selon le règlement."
            )
            msg['Subject'] = f"Alerte : Absences non justifiées pour {etu[0]}"
            msg['From'] = MAIL_USERNAME
            msg['To'] = chef[0]
            try:
                server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
                server.starttls()
                server.login(MAIL_USERNAME, MAIL_PASSWORD)
                server.send_message(msg)
                server.quit()
            except Exception as e:
                print(f"Erreur lors de l'envoi du mail au chef : {e}")

    conn.close()
    return jsonify({"success": True, "total_non_just": total_non_just})

def heure_to_float(horaire):
    """
    Convertit une chaîne HH:MM (ou un float/int déjà correct) en float.
    '20:00' → 20.0 ; '02:30' → 2.5 ; 18 → 18.0 ; 18.0 → 18.0
    """
    try:
        if isinstance(horaire, (int, float)):
            return float(horaire)
        if ':' in str(horaire):
            h, m = str(horaire).split(':')
            return float(h) + float(m)/60
        return float(horaire)
    except Exception:
        return 0.0  # par défaut si problème

@app.route('/enseignant/enregistrer_absences', methods=['POST'])
@login_required
def enregistrer_absences_enseignant():
    if current_user.role_id != 2:
        return jsonify({"success": False, "error": "Accès refusé"}), 403

    data = request.get_json()
    absents = data.get('absents', [])
    session_id = data.get('session_id')

    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()

    # Efface les absences existantes de la séance
    cursor.execute("DELETE FROM absences WHERE session_id = ?", (session_id,))
    # Insère les nouveaux absents
    for etu_id in absents:
        cursor.execute("""INSERT INTO absences (session_id, student_id, justifie) VALUES (?, ?, ?)""",
                       (session_id, etu_id, 0))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "nb": len(absents)})

@app.route('/enseignant/ajouter_seance', methods=['GET', 'POST'])
@login_required
def ajouter_seance_enseignant():
    if current_user.role_id != 2:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Liste des cours attribués avec le quota et les heures réalisées
    cursor.execute("""
        SELECT c.id, c.name, c.volume_horaire,
            IFNULL((SELECT SUM(s.duree) FROM sessions s WHERE s.course_id = c.id), 0) AS heures_realisees
        FROM courses c
        WHERE c.teacher_id = ?
    """, (current_user.id,))
    cours_list = cursor.fetchall()

    # Préselection du cours depuis le paramètre GET
    course_id = request.args.get('course_id', type=int)

    if request.method == 'POST':
        # Récupération des données du formulaire
        course_id_post = int(request.form['course_id'])
        date = request.form['date']
        heure_debut = request.form['heure_debut']
        heure_fin = request.form['heure_fin']
        duree = float(request.form['duree'])

        # Récupérer le cours sélectionné dans la liste
        selected_cours = next((c for c in cours_list if c['id'] == course_id_post), None)
        if not selected_cours:
            flash("⛔ Cours invalide.", "danger")
            return render_template("ajouter_seances_enseignant.html", cours=cours_list, course_id=course_id)

        # 👉 Conversion HH:MM → float (pour les calculs !)
        volume_horaire = heure_to_float(selected_cours['volume_horaire'])
        heures_realisees = float(selected_cours['heures_realisees'] or 0)

        # Vérification du dépassement d'heures
        if heures_realisees + duree > volume_horaire:
            flash(f"⛔ Impossible d'ajouter cette séance : cela dépasserait le volume horaire ({heures_realisees}/{volume_horaire}h déjà réalisées).", "danger")
            return render_template("ajouter_seances_enseignant.html", cours=cours_list, course_id=course_id_post)

        # Ajout de la séance si tout est OK
        cursor.execute("""
            INSERT INTO sessions (course_id, date, heure_debut, heure_fin, duree, valide)
            VALUES (?, ?, ?, ?, ?, 0)
        """, (course_id_post, date, heure_debut, heure_fin, duree))
        conn.commit()
        flash("✅ Séance ajoutée avec succès", "success")
        return redirect(url_for('toutes_seances_enseignant'))

    conn.close()
    return render_template("ajouter_seances_enseignant.html", cours=cours_list, course_id=course_id)






@app.route('/responsable')
@login_required
def responsable():
    if current_user.role_id != 3:
        return "Accès refusé", 403
    return render_template('responsable.html')


@app.route('/responsable/cahier', methods=['GET', 'POST'])
@login_required
def cahier_responsable():
    if current_user.role_id != 3:
        return "Accès refusé", 403

    conn = config.get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Traitement de validation/rejet
    if request.method == 'POST':
        seance_id = request.form['seance_id']
        action = request.form['action']
        if action == 'valider':
            cursor.execute("UPDATE sessions SET valide = 1 WHERE id = ?", (seance_id,))
        elif action == 'rejeter':
            cursor.execute("UPDATE sessions SET valide = 0 WHERE id = ?", (seance_id,))
        conn.commit()
        flash("Action effectuée avec succès", "success")

    # Affichage des séances
    cursor.execute("""
        SELECT s.id, s.date, s.heure_debut, s.heure_fin, s.duree, s.contenu, s.valide,
               c.name AS cours, u.username AS enseignant
        FROM sessions s
        JOIN courses c ON s.course_id = c.id
        LEFT JOIN users u ON c.teacher_id = u.id
        ORDER BY s.date DESC
    """)
    seances = cursor.fetchall()
    conn.close()

    return render_template("cahier_responsable.html", seances=seances)

def envoyer_email(destinataire, sujet, contenu_texte):
    from config_mail import MAIL_USERNAME, MAIL_SERVER, MAIL_PORT, MAIL_PASSWORD
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(contenu_texte, "plain")
    msg['Subject'] = sujet
    msg['From'] = MAIL_USERNAME
    msg['To'] = destinataire

    try:
        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ Email envoyé à {destinataire}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de l'email : {e}")



import os
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/a_propos')
def a_propos():
    return render_template('a_propos.html')

@app.route('/comment_ca_marche')
def comment_ca_marche():
    return render_template('comment_ca_marche.html')




if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

