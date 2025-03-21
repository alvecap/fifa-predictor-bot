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

# Messages du bot
WELCOME_MESSAGE = """
👋 Bienvenue sur FIFA 4x4 Predictor!

Je vous aide à prédire les résultats de matchs de football FIFA 4x4 en me basant sur des données historiques.

Pour obtenir une prédiction, utilisez la commande:
/predict Équipe1 vs Équipe2

Exemple: /predict Manchester United vs Chelsea
"""

HELP_MESSAGE = """
🔮 *Commandes disponibles*:

/start - Démarrer le bot
/help - Afficher l'aide
/predict [Équipe1] vs [Équipe2] - Obtenir une prédiction de match
/odds [Équipe1] vs [Équipe2] [cote1] [cote2] - Prédiction avec les cotes

Exemple: /predict Manchester United vs Chelsea
Exemple: /odds Manchester United vs Chelsea 1.8 3.5
"""

# États pour la conversation
TEAM_INPUT = 1
ODDS_INPUT = 2
