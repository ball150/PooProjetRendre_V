# Configuration de la base de données
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'cahier_texte'
}

# Configuration du serveur SMTP (exemple avec Gmail)
MAIL_CONFIG = {
    'MAIL_SERVER': 'smtp.gmail.com',
    'MAIL_PORT': 587,
    'MAIL_USE_TLS': True,
    'MAIL_USERNAME': 'votre_email@gmail.com',
    'MAIL_PASSWORD': 'votre_mot_de_passe_app'  # Utilise un mot de passe d'application
}

# Clé secrète pour Flask + Tokens
SECRET_KEY = "une_cle_secrete_tres_longue_et_unique"