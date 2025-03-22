import requests
import os
from config import TELEGRAM_TOKEN

def reset_telegram_session():
    """Réinitialise la session Telegram du bot"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true"
    try:
        response = requests.get(url)
        print(f"Réponse: {response.json()}")
        if response.status_code == 200:
            print("Webhook et sessions Telegram réinitialisés avec succès")
            return True
        else:
            print(f"Échec de réinitialisation: {response.text}")
            return False
    except Exception as e:
        print(f"Erreur lors de la réinitialisation: {e}")
        return False

if __name__ == "__main__":
    reset_telegram_session()
