import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Liste des administrateurs (accès complet sans vérifications)
ADMIN_USERNAMES = ["alve08"]  # Noms d'utilisateur des admins
ADMIN_IDS = [6054768666]  # ID des administrateurs

def is_admin(user_id: int, username: str = None) -> bool:
    """
    Vérifie si l'utilisateur est un administrateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str, optional): Nom d'utilisateur Telegram
        
    Returns:
        bool: True si l'utilisateur est admin, False sinon
    """
    # Vérification par ID (plus fiable)
    if user_id in ADMIN_IDS:
        logger.info(f"Accès administrateur accordé à l'utilisateur ID: {user_id}")
        return True
    
    # Vérification par nom d'utilisateur (backup)
    if username and username.lower() in [admin.lower() for admin in ADMIN_USERNAMES]:
        logger.info(f"Accès administrateur accordé à l'utilisateur {username} (ID: {user_id})")
        return True
    
    return False
