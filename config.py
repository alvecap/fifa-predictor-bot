import os
import json
import tempfile
from pathlib import Path
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Chargement des variables d'environnement
def get_env_variable(name, default=None):
    """Récupère une variable d'environnement ou renvoie la valeur par défaut"""
    return os.environ.get(name, default)

# Token fourni par BotFather (utilise la variable d'environnement)
TELEGRAM_TOKEN = get_env_variable('TELEGRAM_TOKEN', '')

# Configuration MongoDB (principale)
MONGODB_URI = get_env_variable('MONGODB_URI', '')
MONGODB_DB_NAME = get_env_variable('MONGODB_DB_NAME', 'fifa_predictor_db')

# Config pour utiliser MongoDB ou Google Sheets
USE_MONGODB = True  # Toujours utiliser MongoDB en premier choix

# Vérification de la connexion MongoDB au démarrage
if USE_MONGODB and MONGODB_URI:
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # Vérifier la connexion en exécutant une commande simple
        client.admin.command('ping')
        logger.info("Connexion à MongoDB établie avec succès!")
    except Exception as e:
        logger.error(f"Impossible de se connecter à MongoDB: {e}")
        logger.warning("Retour à Google Sheets comme solution de secours.")
        USE_MONGODB = False

# Configuration Google Sheets (secondaire, conservée pour migration/compatibilité)
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

# ID de la feuille Google Sheets (pour la migration/compatibilité)
SPREADSHEET_ID = get_env_variable('SPREADSHEET_ID', '')

# Paramètres de prédiction
MAX_PREDICTIONS_HALF_TIME = int(get_env_variable('MAX_PREDICTIONS_HALF_TIME', 3))
MAX_PREDICTIONS_FULL_TIME = int(get_env_variable('MAX_PREDICTIONS_FULL_TIME', 3))

# Configuration du canal officiel
OFFICIAL_CHANNEL = "@alvecapitalofficiel"  # Uniformisé pour éviter les confusions

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
/games - Menu des jeux disponibles

*Exemples:*
/predict Manchester United vs Chelsea
/odds Manchester United vs Chelsea 1.8 3.5

⚠️ L'abonnement au canal {channel} est requis pour utiliser ces fonctionnalités.
""".format(channel=OFFICIAL_CHANNEL)

# Nombre maximum de parrainages requis
MAX_REFERRALS = 1  # Un seul parrainage par utilisateur

# Limites et paramètres de performance
CACHE_EXPIRE_SECONDS = 300  # 5 minutes de cache pour réduire les appels à la BD
REQUEST_THROTTLE_MS = 500  # Limiter les requêtes fréquentes (en millisecondes)
MAX_CONCURRENT_USERS = 200  # Limite théorique d'utilisateurs simultanés

# Paramètres d'animation pour l'interface
ANIMATION_FAST = True  # Réduit les délais d'animation pour une meilleure réactivité

# Paramètres de timeouts et de tentatives
REQUEST_TIMEOUT_SECONDS = 10  # Timeout pour les requêtes externes
MAX_RETRIES = 3  # Nombre maximal de tentatives pour les opérations externes

# Mode de développement/débogage
DEBUG = get_env_variable('DEBUG', 'False').lower() == 'true'

# Informations affichées au démarrage du bot
logger.info(f"Configuration chargée: Mode DEBUG={DEBUG}")
logger.info(f"Base de données principale: {'MongoDB' if USE_MONGODB else 'Google Sheets'}")
logger.info(f"Canal officiel: {OFFICIAL_CHANNEL}")
logger.info(f"Parrainages requis: {MAX_REFERRALS}")

# Vérification de la configuration au démarrage
if not TELEGRAM_TOKEN:
    logger.error("ERREUR CRITIQUE: Token Telegram non défini!")

if not MONGODB_URI and USE_MONGODB:
    logger.error("ERREUR: URI MongoDB non définie alors que MongoDB est activé!")

# Affichage condensé de la configuration pour débogage
if DEBUG:
    config_summary = {
        "USE_MONGODB": USE_MONGODB,
        "MONGODB_DB": MONGODB_DB_NAME,
        "MAX_REFERRALS": MAX_REFERRALS,
        "ANIMATION_FAST": ANIMATION_FAST,
        "CACHE_EXPIRE_SECONDS": CACHE_EXPIRE_SECONDS
    }
    logger.debug(f"Résumé de la configuration: {json.dumps(config_summary)}")
