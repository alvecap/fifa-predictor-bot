import logging
import asyncio
from typing import Dict, Any, Optional
import time

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importer les modules nécessaires
from queue_manager import start_queue_manager, stop_queue_manager
from cache_system import start_cache_monitoring
from predictor import preload_prediction_data

async def initialize_system():
    """
    Initialise tous les systèmes optimisés :
    1. Démarre le gestionnaire de file d'attente
    2. Précharge les données de prédiction
    3. Démarre la surveillance du cache
    """
    logger.info("Initialisation du système optimisé...")
    
    # Démarrer le gestionnaire de file d'attente
    logger.info("Démarrage du gestionnaire de file d'attente...")
    await start_queue_manager()
    
    # Précharger les données de prédiction
    logger.info("Préchargement des données de prédiction...")
    preload_task = asyncio.create_task(preload_prediction_data())
    
    # Démarrer la surveillance du cache
    logger.info("Démarrage de la surveillance du cache...")
    cache_task = asyncio.create_task(start_cache_monitoring())
    
    # Attendre la fin du préchargement des données
    try:
        await asyncio.wait_for(preload_task, timeout=30.0)
        logger.info("Préchargement des données de prédiction terminé avec succès")
    except asyncio.TimeoutError:
        logger.warning("Le préchargement des données de prédiction prend plus de temps que prévu, "
                      "l'application continuera à fonctionner mais avec des performances réduites initialement")
    
    logger.info("Système optimisé initialisé avec succès")

async def shutdown_system():
    """
    Arrête proprement tous les systèmes optimisés.
    """
    logger.info("Arrêt du système optimisé...")
    
    # Arrêter le gestionnaire de file d'attente
    await stop_queue_manager()
    
    # Les autres tâches s'arrêteront automatiquement à la fermeture de l'application
    
    logger.info("Système optimisé arrêté avec succès")

def ensure_initialization():
    """
    S'assure que l'initialisation est effectuée au démarrage de l'application.
    Cette fonction est appelée depuis fifa_bot.py
    """
    try:
        # Création d'une boucle asyncio pour l'initialisation
        loop = asyncio.get_event_loop()
        loop.run_until_complete(initialize_system())
        
        # Enregistrer la fonction de nettoyage pour l'arrêt propre
        import atexit
        atexit.register(lambda: loop.run_until_complete(shutdown_system()))
        
        logger.info("Initialisation du système réussie")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation du système: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# Si ce fichier est exécuté directement, initialiser le système
if __name__ == "__main__":
    ensure_initialization()# Games package
