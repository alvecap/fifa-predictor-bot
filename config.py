# Configuration pour le Bot Telegram FIFA 4x4 Predictor

# Token fourni par BotFather
TELEGRAM_TOKEN = '7115420946:AAGGMxo-b4qK9G3cmC2aqscV7hg2comjqxQ'

# Configuration Google Sheets
CREDENTIALS_FILE = 'google_credentials.json'
SPREADSHEET_ID = '1Re49QREKJRIfVxFadgV0bq-bbBLLoQ4fiSxbdLpZ3H0'

# Paramètres de prédiction
MAX_PREDICTIONS_HALF_TIME = 3  # Nombre de prédictions pour la mi-temps
MAX_PREDICTIONS_FULL_TIME = 3  # Nombre de prédictions pour le temps réglementaire

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
