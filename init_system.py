"""
Script d'initialisation du système
Ce script est exécuté au démarrage pour garantir que tous les composants
nécessaires sont correctement configurés avant le lancement du bot.
"""

import logging
import asyncio
import os
import sys
import importlib.util
from typing import List, Dict, Any, Optional

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_module_exists(module_name: str) -> bool:
    """Vérifie si un module Python existe."""
    return importlib.util.find_spec(module_name) is not None

def check_required_modules() -> bool:
    """Vérifie que tous les modules requis sont disponibles."""
    required_modules = [
        "telegram", "pymongo", "flask", "asyncio", 
        "requests", "json", "datetime", "typing"
    ]
    
    missing_modules = []
    
    for module in required_modules:
        if not check_module_exists(module):
            missing_modules.append(module)
    
    if missing_modules:
        logger.error(f"Modules requis manquants: {', '.join(missing_modules)}")
        logger.error("Veuillez installer les modules manquants avec pip install -r requirements.txt")
        return False
    
    logger.info("Tous les modules requis sont disponibles")
    return True

def check_required_files() -> bool:
    """Vérifie que tous les fichiers requis sont présents."""
    required_files = [
        "fifa_games.py", "queue_manager.py", "cache_system.py", 
        "predictor.py", "database_adapter.py", "admin_access.py",
        "config.py", "verification.py", "referral_system.py"
    ]
    
    missing_files = []
    
    for file in required_files:
        if not os.path.isfile(file):
            missing_files.append(file)
    
    if missing_files:
        logger.error(f"Fichiers requis manquants: {', '.join(missing_files)}")
        return False
    
    logger.info("Tous les fichiers requis sont présents")
    return True

def check_mongodb_connection() -> bool:
    """Vérifie si la connexion à MongoDB est établie."""
    try:
        from config import MONGODB_URI, MONGODB_DB_NAME
        from pymongo import MongoClient
        
        if not MONGODB_URI:
            logger.warning("MONGODB_URI non défini dans la configuration")
            return False
            
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        
        # Vérifier la connexion
        client.admin.command('ping')
        
        # Vérifier si la base de données existe
        db_names = client.list_database_names()
        if MONGODB_DB_NAME not in db_names:
            logger.warning(f"La base de données '{MONGODB_DB_NAME}' n'existe pas encore")
            # Elle sera créée automatiquement lors de la première utilisation
        
        logger.info(f"Connexion à MongoDB établie avec succès (base: {MONGODB_DB_NAME})")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la connexion à MongoDB: {e}")
        return False

def check_telegram_token() -> bool:
    """Vérifie si le token Telegram est valide."""
    try:
        from config import TELEGRAM_TOKEN
        import requests
        
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN non défini dans la configuration")
            return False
            
        # Vérifier le token auprès de l'API Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data["ok"]:
                bot_username = data["result"]["username"]
                logger.info(f"Token Telegram valide pour le bot @{bot_username}")
                return True
            else:
                logger.error(f"Token Telegram invalide: {data.get('description', 'Erreur inconnue')}")
                return False
        else:
            logger.error(f"Erreur lors de la vérification du token Telegram: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du token Telegram: {e}")
        return False

def create_directory_structure() -> bool:
    """Crée la structure de répertoires si nécessaire."""
    required_dirs = ["logs", "tmp"]
    
    for directory in required_dirs:
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
                logger.info(f"Répertoire '{directory}' créé")
            except Exception as e:
                logger.warning(f"Impossible de créer le répertoire '{directory}': {e}")
    
    return True

def check_games_modules() -> bool:
    """Vérifie que les modules de jeux sont présents et valides."""
    try:
        games_dir = "games"
        
        if not os.path.isdir(games_dir):
            logger.error(f"Le répertoire 'games' n'existe pas")
            return False
            
        required_game_files = [
            "__init__.py", "apple_game.py", "baccarat_game.py", "fifa_game.py"
        ]
        
        missing_files = []
        for file in required_game_files:
            full_path = os.path.join(games_dir, file)
            if not os.path.isfile(full_path):
                missing_files.append(file)
        
        if missing_files:
            logger.error(f"Fichiers de jeux manquants: {', '.join(missing_files)}")
            return False
            
        # Vérifier que les modules sont importables
        try:
            from games import apple_game, baccarat_game, fifa_game
            logger.info("Modules de jeux vérifiés avec succès")
            return True
        except ImportError as e:
            logger.error(f"Erreur lors de l'importation des modules de jeux: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Erreur lors de la vérification des modules de jeux: {e}")
        return False

async def ensure_initialization() -> bool:
    """Fonction principale pour garantir l'initialisation du système."""
    logger.info("Démarrage de l'initialisation du système...")
    
    # Vérifications de base
    if not check_required_modules():
        logger.error("Modules requis manquants. Initialisation échouée.")
        return False
        
    if not check_required_files():
        logger.warning("Certains fichiers requis sont manquants. Continuons quand même...")
    
    # Structure de répertoires
    create_directory_structure()
    
    # Vérifier la connexion à MongoDB
    db_ok = check_mongodb_connection()
    if not db_ok:
        logger.warning("Problème de connexion à MongoDB. Le bot pourrait ne pas fonctionner correctement.")
    
    # Vérifier le token Telegram
    token_ok = check_telegram_token()
    if not token_ok:
        logger.error("Token Telegram invalide. Le bot ne pourra pas se connecter à Telegram.")
        return False
    
    # Vérifier les modules de jeux
    games_ok = check_games_modules()
    if not games_ok:
        logger.warning("Problèmes avec les modules de jeux. Certaines fonctionnalités pourraient être indisponibles.")
    
    # Initialisation réussie
    logger.info("Initialisation du système terminée avec succès!")
    return True

def print_system_info() -> None:
    """Affiche les informations système pour le débogage."""
    import platform
    import sys
    
    logger.info("--- Informations système ---")
    logger.info(f"Système d'exploitation: {platform.system()} {platform.release()}")
    logger.info(f"Python version: {platform.python_version()}")
    logger.info(f"Répertoire courant: {os.getcwd()}")
    logger.info(f"Arguments système: {sys.argv}")
    logger.info("---------------------------")

if __name__ == "__main__":
    print_system_info()
    
    # Exécuter la fonction d'initialisation
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(ensure_initialization())
    
    # Code de sortie basé sur le résultat
    if result:
        logger.info("Initialisation réussie!")
        sys.exit(0)
    else:
        logger.error("Échec de l'initialisation!")
        sys.exit(1)
