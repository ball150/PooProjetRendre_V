# test_envoi.py

import smtplib
from email.mime.text import MIMEText
import config_mail

def envoyer_test_email():
    destinataire = "ballsileymane32@gmail.com"  # remplace ici par ton email
    sujet = "✅ Test d'envoi depuis Flask"
    message = "Bonjour,\n\nCeci est un test d'envoi d'email depuis l'application Flask.\n\nCordialement."

    msg = MIMEText(message)
    msg['Subject'] = sujet
    msg['From'] = config_mail.MAIL_USERNAME
    msg['To'] = destinataire

    try:
        serveur = smtplib.SMTP(config_mail.MAIL_SERVER, config_mail.MAIL_PORT)
        serveur.starttls()
        serveur.login(config_mail.MAIL_USERNAME, config_mail.MAIL_PASSWORD)
        serveur.send_message(msg)
        serveur.quit()
        print(f"✅ Email de test envoyé à {destinataire}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi : {e}")

if __name__ == "__main__":
    envoyer_test_email()
