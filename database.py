import logging
import os
from typing import Dict, List, Any, Optional, Tuple
from config import USE_MONGODB

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importer les modules appropriés en fonction de la configuration
if USE_MONGODB:
    try:
        import mongo_db as db
        logger.info("Utilisation de MongoDB comme base de données")
    except ImportError:
        logger.error("Module mongo_db non trouvé, fallback sur Google Sheets")
        import database as db
else:
    import database as db
    logger.info("Utilisation de Google Sheets comme base de données")

# Fonctions d'accès aux données des matchs
def get_all_matches_data():
    """Récupère les données des matchs depuis la base de données active"""
    return db.get_all_matches_data()

def get_all_teams():
    """Récupère la liste de toutes les équipes"""
    return db.get_all_teams()

def get_team_statistics(matches):
    """Calcule les statistiques pour chaque équipe"""
    return db.get_team_statistics(matches)

def get_match_id_trends(matches):
    """Analyse les tendances par numéro de match"""
    return db.get_match_id_trends(matches)

def get_common_scores(scores_list, top_n=5):
    """Retourne les scores les plus communs avec leur fréquence"""
    return db.get_common_scores(scores_list, top_n)

def get_direct_confrontations(matches, team1, team2):
    """Récupère l'historique des confrontations directes entre deux équipes"""
    return db.get_direct_confrontations(matches, team1, team2)

def save_prediction_log(user_id, username, team1, team2, odds1=None, odds2=None, prediction_result=None):
    """Enregistre les prédictions demandées par les utilisateurs"""
    return db.save_prediction_log(user_id, username, team1, team2, odds1, odds2, prediction_result)

async def check_user_subscription(user_id):
    """
    Vérifie si un utilisateur est abonné au canal.
    
    Args:
        user_id (int): L'ID de l'utilisateur Telegram à vérifier
        
    Returns:
        bool: True si l'utilisateur est abonné, False sinon
    """
    return await db.check_user_subscription(user_id)

# Fonctions pour le système de parrainage
async def register_user(user_id, username, referrer_id=None):
    """
    Enregistre ou met à jour un utilisateur dans la base de données.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str): Nom d'utilisateur Telegram
        referrer_id (int, optional): ID Telegram du parrain
    
    Returns:
        bool: True si l'opération a réussi, False sinon
    """
    if hasattr(db, 'register_user'):
        return await db.register_user(user_id, username, referrer_id)
    else:
        from referral_system import register_user as old_register_user
        return await old_register_user(user_id, username, referrer_id)

async def create_referral_relationship(user_id, referrer_id):
    """
    Crée une relation de parrainage dans la base de données.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur parrainé
        referrer_id (int): ID Telegram du parrain
    """
    if hasattr(db, 'create_referral_relationship'):
        return await db.create_referral_relationship(user_id, referrer_id)
    else:
        from referral_system import create_referral_relationship as old_create_referral
        return await old_create_referral(user_id, referrer_id)

async def verify_and_update_referral(user_id, referrer_id):
    """
    Vérifie si l'utilisateur est abonné au canal et met à jour le statut de parrainage.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        referrer_id (int): ID Telegram du parrain
    """
    if hasattr(db, 'verify_and_update_referral'):
        return await db.verify_and_update_referral(user_id, referrer_id)
    else:
        from referral_system import verify_and_update_referral as old_verify
        return await old_verify(user_id, referrer_id)

async def has_completed_referrals(user_id, username=None):
    """
    Vérifie si l'utilisateur a atteint le nombre requis de parrainages.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str, optional): Nom d'utilisateur Telegram pour vérification admin
        
    Returns:
        bool: True si l'utilisateur a complété ses parrainages ou est admin, False sinon
    """
    if hasattr(db, 'has_completed_referrals'):
        return await db.has_completed_referrals(user_id, username)
    else:
        from referral_system import has_completed_referrals as old_has_completed
        return await old_has_completed(user_id, username)

async def count_referrals(user_id):
    """
    Compte le nombre de parrainages vérifiés pour un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        int: Le nombre de parrainages vérifiés
    """
    if hasattr(db, 'count_referrals'):
        return await db.count_referrals(user_id)
    else:
        from referral_system import count_referrals as old_count
        return await old_count(user_id)

async def get_referred_users(user_id):
    """
    Récupère la liste des utilisateurs parrainés par un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        list: Liste des utilisateurs parrainés avec leurs informations
    """
    if hasattr(db, 'get_referred_users'):
        return await db.get_referred_users(user_id)
    else:
        from referral_system import get_referred_users as old_get_users
        return await old_get_users(user_id)

async def generate_referral_link(user_id, bot_username):
    """
    Génère un lien de parrainage pour un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        bot_username (str): Nom d'utilisateur du bot
        
    Returns:
        str: Lien de parrainage
    """
    if hasattr(db, 'generate_referral_link'):
        return await db.generate_referral_link(user_id, bot_username)
    else:
        from referral_system import generate_referral_link as old_generate_link
        return await old_generate_link(user_id, bot_username)

async def get_max_referrals():
    """
    Récupère le nombre maximum de parrainages requis.
    
    Returns:
        int: Nombre maximum de parrainages requis
    """
    if hasattr(db, 'get_max_referrals'):
        return await db.get_max_referrals()
    else:
        from config import MAX_REFERRALS
        return MAX_REFERRALS

def get_referral_instructions():
    """
    Retourne les instructions pour qu'un parrainage soit validé.
    
    Returns:
        str: Message formaté avec les instructions
    """
    if hasattr(db, 'get_referral_instructions'):
        return db.get_referral_instructions()
    else:
        from referral_system import get_referral_instructions as old_get_instructions
        return old_get_instructions()
