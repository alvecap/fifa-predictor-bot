import requests
from config import TELEGRAM_TOKEN

# URL pour supprimer le webhook et les mises à jour en attente
url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true"

# Faire la requête
try:
    response = requests.get(url)
    if response.status_code == 200:
        print("✅ Réinitialisation réussie! Vous pouvez maintenant démarrer votre bot.")
    else:
        print(f"❌ Erreur: {response.text}")
except Exception as e:
    print(f"❌ Erreur de connexion: {e}")
