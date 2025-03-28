import logging
import os
import time
from typing import Dict, List, Any, Optional, Tuple
from config import USE_MONGODB, CACHE_EXPIRE_SECONDS, DEBUG

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialisation de l'adaptateur
logger.info(f"Initialisation de l'adaptateur de base de données avec {'MongoDB' if USE_MONGODB else 'Google Sheets'}")

# Importer les modules appropriés en fonction de la configuration
if USE_MONGODB:
    try:
        import mongo_db as db
        logger.info("Utilisation de MongoDB comme base de données principale")
    except ImportError as e:
        logger.error(f"Module mongo_db non trouvé, fallback sur Google Sheets: {e}")
        try:
            import database as db
            logger.warning("Fallback sur Google Sheets activé")
        except ImportError:
            logger.critical("ERREUR CRITIQUE: Aucun module de base de données disponible!")
            # Créer un module de secours minimal pour éviter les erreurs
            class EmergencyDB:
                @staticmethod
                async def check_user_subscription(user_id):
                    logger.error("EmergencyDB: check_user_subscription appelé")
                    return True
                
                @staticmethod
                async def register_user(*args, **kwargs):
                    logger.error("EmergencyDB: register_user appelé")
                    return True
                
                @staticmethod
                async def count_referrals(*args):
                    logger.error("EmergencyDB: count_referrals appelé")
                    return 0
                
                @staticmethod
                def get_all_matches_data():
                    logger.error("EmergencyDB: get_all_matches_data appelé")
                    return []
                
                @staticmethod
                def get_all_teams():
                    logger.error("EmergencyDB: get_all_teams appelé")
                    return ["Équipe 1", "Équipe 2"]  # Valeurs minimales pour éviter les crashs
            
            db = EmergencyDB()
            logger.critical("Module de secours minimal activé pour éviter les crashs")
else:
    try:
        import database as db
        logger.info("Utilisation de Google Sheets comme base de données principale (configuration explicite)")
    except ImportError as e:
        logger.error(f"Module database non trouvé: {e}")
        logger.error("Tentative d'utilisation de MongoDB comme solution de secours")
        try:
            import mongo_db as db
            logger.info("MongoDB utilisé comme solution de secours")
        except ImportError:
            logger.critical("ERREUR CRITIQUE: Aucun module de base de données disponible!")
            raise RuntimeError("Aucun module de base de données disponible. Impossible de continuer.")

# Système de cache en mémoire
# Structure des caches: {clé: (timestamp, valeur)}
_user_cache = {}  # Clé: user_id, Valeur: données utilisateur
_referral_cache = {}  # Clé: user_id, Valeur: nombre de parrainages
_team_cache = None  # Cache pour la liste des équipes (rarement modifiée)
_match_cache = None  # Cache pour les données de match (rarement modifiées)
_subscription_cache = {}  # Clé: user_id, Valeur: statut d'abonnement
_last_cache_cleanup = 0

def _clear_expired_cache():
    """Nettoie les entrées de cache expirées"""
    global _last_cache_cleanup
    current_time = time.time()
    
    # Ne nettoyer que toutes les 5 minutes
    if current_time - _last_cache_cleanup < 300:
        return
        
    _last_cache_cleanup = current_time
    
    # Nettoyer les caches
    expired_users = []
    expired_referrals = []
    expired_subscriptions = []
    
    for user_id, (timestamp, _) in _user_cache.items():
        if current_time - timestamp > CACHE_EXPIRE_SECONDS:
            expired_users.append(user_id)
            
    for user_id, (timestamp, _) in _referral_cache.items():
        if current_time - timestamp > CACHE_EXPIRE_SECONDS:
            expired_referrals.append(user_id)
    
    for user_id, (timestamp, _) in _subscription_cache.items():
        if current_time - timestamp > CACHE_EXPIRE_SECONDS:
            expired_subscriptions.append(user_id)
        
    # Supprimer les entrées expirées
    for user_id in expired_users:
        del _user_cache[user_id]
        
    for user_id in expired_referrals:
        del _referral_cache[user_id]
    
    for user_id in expired_subscriptions:
        del _subscription_cache[user_id]
        
    if DEBUG and (expired_users or expired_referrals or expired_subscriptions):
        logger.debug(f"Cache nettoyé: {len(expired_users)} utilisateurs, {len(expired_referrals)} parrainages, {len(expired_subscriptions)} abonnements supprimés")

# Fonction pour obtenir une connexion à la base de données
def get_database():
    """Récupère une connexion à la base de données active"""
    if USE_MONGODB:
        try:
            from mongo_db import get_database as get_mongo_db
            return get_mongo_db()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la base de données MongoDB: {e}")
            return None
    else:
        # Pour Google Sheets, retourner None car ce n'est pas une base de données traditionnelle
        return None

# Fonctions d'accès aux données des matchs (avec cache)
def get_all_matches_data():
    """
    Récupère les données des matchs depuis la base de données active.
    Utilise le cache si disponible.
    """
    global _match_cache
    
    # Si le cache est valide, l'utiliser
    if _match_cache is not None:
        timestamp, matches = _match_cache
        if time.time() - timestamp < CACHE_EXPIRE_SECONDS:
            return matches
    
    # Sinon, charger depuis la base de données
    try:
        matches = db.get_all_matches_data()
        # Mettre en cache avec le timestamp actuel
        _match_cache = (time.time(), matches)
        return matches
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des matchs: {e}")
        # En cas d'erreur, retourner le cache même s'il est expiré, ou une liste vide
        return _match_cache[1] if _match_cache else []

def get_all_teams():
    """
    Récupère la liste de toutes les équipes.
    Utilise le cache si disponible.
    """
    global _team_cache
    
    # Si le cache est valide, l'utiliser
    if _team_cache is not None:
        timestamp, teams = _team_cache
        if time.time() - timestamp < CACHE_EXPIRE_SECONDS:
            return teams
    
    # Sinon, charger depuis la base de données
    try:
        teams = db.get_all_teams()
        # Mettre en cache avec le timestamp actuel
        _team_cache = (time.time(), teams)
        return teams
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des équipes: {e}")
        # En cas d'erreur, retourner le cache même s'il est expiré, ou une liste vide
        return _team_cache[1] if _team_cache else []

def get_team_statistics(matches):
    """Calcule les statistiques pour chaque équipe"""
    try:
        return db.get_team_statistics(matches)
    except Exception as e:
        logger.error(f"Erreur lors du calcul des statistiques d'équipe: {e}")
        return {}

def get_match_id_trends(matches):
    """Analyse les tendances par numéro de match"""
    try:
        return db.get_match_id_trends(matches)
    except Exception as e:
        logger.error(f"Erreur lors de l'analyse des tendances par match: {e}")
        return {}

def get_common_scores(scores_list, top_n=5):
    """Retourne les scores les plus communs avec leur fréquence"""
    try:
        return db.get_common_scores(scores_list, top_n)
    except Exception as e:
        logger.error(f"Erreur lors du calcul des scores communs: {e}")
        return []

def get_direct_confrontations(matches, team1, team2):
    """Récupère l'historique des confrontations directes entre deux équipes"""
    try:
        return db.get_direct_confrontations(matches, team1, team2)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des confrontations directes: {e}")
        return []

def save_prediction_log(user_id, username, team1, team2, odds1=None, odds2=None, prediction_result=None):
    """Enregistre les prédictions demandées par les utilisateurs"""
    try:
        return db.save_prediction_log(user_id, username, team1, team2, odds1, odds2, prediction_result)
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de la prédiction: {e}")
        return False

async def check_user_subscription(user_id):
    """
    Vérifie si un utilisateur est abonné au canal.
    Utilise le cache si disponible pour éviter trop d'appels API Telegram.
    
    Args:
        user_id (int): L'ID de l'utilisateur Telegram à vérifier
        
    Returns:
        bool: True si l'utilisateur est abonné, False sinon
    """
    # Convertir en string pour le cache
    user_id_str = str(user_id)
    
    # Vérifier si c'est un admin (toujours en direct, pas de cache)
    try:
        from admin_access import is_admin
        if is_admin(user_id):
            logger.info(f"Vérification d'abonnement contournée pour l'admin (ID: {user_id})")
            return True
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut admin: {e}")
    
    # Vérifier le cache
    if user_id_str in _subscription_cache:
        timestamp, is_subscribed = _subscription_cache[user_id_str]
        if time.time() - timestamp < CACHE_EXPIRE_SECONDS:
            return is_subscribed
    
    # Vérification via la base de données active
    try:
        is_subscribed = await db.check_user_subscription(user_id)
        # Mettre en cache
        _subscription_cache[user_id_str] = (time.time(), is_subscribed)
        # Nettoyer le cache périodiquement
        _clear_expired_cache()
        return is_subscribed
    except Exception as e:
        logger.error(f"Erreur lors de la vérification d'abonnement: {e}")
        # En cas d'erreur, supposer que l'utilisateur est abonné pour éviter le blocage
        # Cette logique peut être modifiée selon votre politique
        return True

# Fonctions pour le système de parrainage avec mise en cache
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
    # Convertir en string pour la cohérence
    user_id_str = str(user_id)
    
    # Invalider le cache pour cet utilisateur
    if user_id_str in _user_cache:
        del _user_cache[user_id_str]
        
    # Vérifier si c'est un admin
    try:
        from admin_access import is_admin
        if is_admin(user_id, username):
            logger.info(f"Enregistrement d'un administrateur: {username} (ID: {user_id})")
            return True
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut admin: {e}")
    
    # Enregistrer via la base de données active
    try:
        return await db.register_user(user_id, username, referrer_id)
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de l'utilisateur: {e}")
        # En cas d'erreur, supposer que l'enregistrement a réussi pour éviter le blocage
        return True

async def create_referral_relationship(user_id, referrer_id):
    """
    Crée une relation de parrainage dans la base de données.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur parrainé
        referrer_id (int): ID Telegram du parrain
    """
    # Convertir en string pour la cohérence
    user_id_str = str(user_id)
    referrer_id_str = str(referrer_id)
    
    # Invalider les caches pour les deux utilisateurs
    if user_id_str in _referral_cache:
        del _referral_cache[user_id_str]
        
    if referrer_id_str in _referral_cache:
        del _referral_cache[referrer_id_str]
    
    # Créer la relation via la base de données active
    try:
        return await db.create_referral_relationship(user_id, referrer_id)
    except Exception as e:
        logger.error(f"Erreur lors de la création de la relation de parrainage: {e}")
        return None

async def verify_and_update_referral(user_id, referrer_id):
    """
    Vérifie si l'utilisateur est abonné au canal et met à jour le statut de parrainage.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        referrer_id (int): ID Telegram du parrain
    """
    # Convertir en string pour la cohérence
    user_id_str = str(user_id)
    referrer_id_str = str(referrer_id)
    
    # Invalider les caches pour les deux utilisateurs
    if user_id_str in _referral_cache:
        del _referral_cache[user_id_str]
        
    if referrer_id_str in _referral_cache:
        del _referral_cache[referrer_id_str]
    
    # Vérifier et mettre à jour via la base de données active
    try:
        return await db.verify_and_update_referral(user_id, referrer_id)
    except Exception as e:
        logger.error(f"Erreur lors de la vérification et mise à jour du parrainage: {e}")
        return None

async def has_completed_referrals(user_id, username=None):
    """
    Vérifie si l'utilisateur a atteint le nombre requis de parrainages.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str, optional): Nom d'utilisateur Telegram pour vérification admin
        
    Returns:
        bool: True si l'utilisateur a complété ses parrainages ou est admin, False sinon
    """
    # Vérifier si c'est un admin
    try:
        from admin_access import is_admin
        if is_admin(user_id, username):
            logger.info(f"Vérification de parrainage contournée pour l'admin {username} (ID: {user_id})")
            return True
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut admin: {e}")
    
    # Obtenir le nombre de parrainages
    referral_count = await count_referrals(user_id)
    max_referrals = await get_max_referrals()
    
    # Vérifier si le quota est atteint
    completed = referral_count >= max_referrals
    logger.info(f"Utilisateur {user_id} a {referral_count}/{max_referrals} parrainages - Statut: {'Complété' if completed else 'En cours'}")
    
    return completed

async def count_referrals(user_id):
    """
    Compte le nombre de parrainages vérifiés pour un utilisateur.
    Utilise le cache si disponible.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        int: Le nombre de parrainages vérifiés
    """
    # Convertir en string pour la cohérence
    user_id_str = str(user_id)
    
    # Vérifier si c'est un admin
    try:
        from admin_access import is_admin
        if is_admin(user_id):
            logger.info(f"Comptage de parrainage contourné pour l'admin (ID: {user_id})")
            max_referrals = await get_max_referrals()
            return max_referrals
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut admin: {e}")
        
    # Vérifier le cache
    if user_id_str in _referral_cache:
        timestamp, count = _referral_cache[user_id_str]
        if time.time() - timestamp < CACHE_EXPIRE_SECONDS:
            return count
    
    # Si pas dans le cache ou expiré, récupérer depuis la base de données
    try:
        count = await db.count_referrals(user_id)
        
        # Mettre en cache
        _referral_cache[user_id_str] = (time.time(), count)
        
        # Nettoyer le cache périodiquement
        _clear_expired_cache()
        
        return count
    except Exception as e:
        logger.error(f"Erreur lors du comptage des parrainages: {e}")
        return 0

async def get_referred_users(user_id):
    """
    Récupère la liste des utilisateurs parrainés par un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        list: Liste des utilisateurs parrainés avec leurs informations
    """
    # Vérifier si c'est un admin
    try:
        from admin_access import is_admin
        if is_admin(user_id):
            logger.info(f"Récupération des parrainages contournée pour l'admin (ID: {user_id})")
            return []
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut admin: {e}")
    
    # Récupérer via la base de données active
    try:
        return await db.get_referred_users(user_id)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des utilisateurs parrainés: {e}")
        return []

async def generate_referral_link(user_id, bot_username):
    """
    Génère un lien de parrainage pour un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        bot_username (str): Nom d'utilisateur du bot
        
    Returns:
        str: Lien de parrainage
    """
    try:
        return await db.generate_referral_link(user_id, bot_username)
    except Exception as e:
        logger.error(f"Erreur lors de la génération du lien de parrainage: {e}")
        # Fallback au cas où la fonction de la base de données échoue
        return f"https://t.me/{bot_username}?start=ref{user_id}"

async def get_max_referrals():
    """
    Récupère le nombre maximum de parrainages requis.
    
    Returns:
        int: Nombre maximum de parrainages requis
    """
    try:
        from config import MAX_REFERRALS
        return MAX_REFERRALS
    except ImportError:
        try:
            return await db.get_max_referrals()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du nombre max de parrainages: {e}")
            return 1  # Valeur par défaut

def get_referral_instructions():
    """
    Retourne les instructions pour qu'un parrainage soit validé.
    
    Returns:
        str: Message formaté avec les instructions
    """
    try:
        return db.get_referral_instructions()
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des instructions de parrainage: {e}")
        # Texte par défaut si la fonction échoue
        return (
            "*📋 Conditions pour qu'un parrainage soit validé:*\n\n"
            "1️⃣ *L'invité doit cliquer sur votre lien de parrainage*\n"
            "2️⃣ *L'invité doit démarrer le bot*\n"
            "3️⃣ *L'invité doit s'abonner* au canal [AL VE CAPITAL](https://t.me/alvecapitalofficiel)\n\n"
            "_Note: Le parrainage sera automatiquement vérifié et validé une fois ces conditions remplies_"
        )
