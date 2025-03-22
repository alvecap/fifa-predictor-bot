import os
import json
import tempfile
from pathlib import Path

# Chargement des variables d'environnement
def get_env_variable(name, default=None):
    """Récupère une variable d'environnement ou renvoie la valeur par défaut"""
    return os.environ.get(name, default)

# Token fourni par BotFather (utilise la variable d'environnement)
TELEGRAM_TOKEN = get_env_variable('TELEGRAM_TOKEN', '')

# Configuration Google Sheets
# Pour le déploiement, nous pouvons recevoir les credentials sous forme de JSON string
GOOGLE_CREDENTIALS_JSON = get_env_variable('GOOGLE_CREDENTIALS_JSON')
if GOOGLE_CREDENTIALS_JSON:
    # Crée un fichier temporaire pour stocker les credentials
    temp_dir = tempfile.gettempdir()
    CREDENTIALS_FILE = Path(temp_dir) / "google_credentials.json"
    with open(CREDENTIALS_FILE, 'w') as f:
        f.write(GOOGLE_CREDENTIALS_JSON)
else:
    # En local, utilise le fichier
    CREDENTIALS_FILE = 'google_credentials.json'

# ID de la feuille Google Sheets
SPREADSHEET_ID = get_env_variable('SPREADSHEET_ID', '')

# Paramètres de prédiction
MAX_PREDICTIONS_HALF_TIME = int(get_env_variable('MAX_PREDICTIONS_HALF_TIME', 3))
MAX_PREDICTIONS_FULL_TIME = int(get_env_variable('MAX_PREDICTIONS_FULL_TIME', 3))

# Configuration du canal officiel
OFFICIAL_CHANNEL = "@alvecapital1"

# États pour la conversation
TEAM_INPUT = 1
ODDS_INPUT = 2
ENTERING_ODDS = 3

# Messages du bot
WELCOME_MESSAGE = """
👋 Bienvenue sur FIFA 4x4 Predictor!

Je vous aide à prédire les résultats de matchs de football FIFA 4x4 en me basant sur des données historiques.

⚠️ Pour utiliser toutes les fonctionnalités, vous devez être abonné à notre canal {channel}.

Pour obtenir une prédiction, utilisez la commande:
/predict Équipe1 vs Équipe2

Exemple: /predict Manchester United vs Chelsea
""".format(channel=OFFICIAL_CHANNEL)

HELP_MESSAGE = """
🔮 *Commandes disponibles*:

/start - Démarrer le bot et vérifier l'abonnement
/help - Afficher l'aide
/predict [Équipe1] vs [Équipe2] - Obtenir une prédiction de match
/odds [Équipe1] vs [Équipe2] [cote1] [cote2] - Prédiction avec les cotes
/teams - Voir toutes les équipes disponibles
/check - Vérifier l'abonnement au canal

*Exemples:*
/predict Manchester United vs Chelsea
/odds Manchester United vs Chelsea 1.8 3.5

⚠️ L'abonnement au canal {channel} est requis pour utiliser ces fonctionnalités.
""".format(channel=OFFICIAL_CHANNEL)
