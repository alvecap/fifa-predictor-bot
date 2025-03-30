import logging
import os
import time
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from config import USE_MONGODB, CACHE_EXPIRE_SECONDS

# Nouveau système de cache
from cache_system import (
    get_cached_data, set_cached_data,
    get_cached_teams, cache_teams,
    get_cached_matches, cache_matches,
    get_cached_subscription_status, cache_subscription_status,
    get_cached_referral_count, cache_referral_count
)

# Système de file d'attente pour les opérations de base de données
from queue_manager import queue_manager

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

# File d'attente pour les utilisateurs à traiter par lots
_users_batch_queue = []  # Liste des utilisateurs en attente d'enregistrement
_last_batch_processing = time.time()  # Heure du dernier traitement par lots

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

# Traitement par lots des utilisateurs
async def process_users_batch():
    """
    Traite le lot d'utilisateurs en attente.
    Version optimisée qui minimise les requêtes API.
    """
    global _users_batch_queue
    global _last_batch_processing
    
    # Copier et vider la file d'attente (pour éviter les problèmes de concurrence)
    users_to_process = _users_batch_queue.copy()
    _users_batch_queue = []
    _last_batch_processing = time.time()
    
    if not users_to_process:
        logger.debug("Aucun utilisateur à traiter par lots")
        return
    
    logger.info(f"Traitement par lots de {len(users_to_process)} utilisateurs")
    
    try:
        if USE_MONGODB:
            # Pour MongoDB, préparer les opérations par lots
            db_instance = get_database()
            if db_instance is None:
                logger.error("Impossible de se connecter à MongoDB pour le traitement par lots")
                return
            
            # Traiter par lots avec un seul appel à la base de données
            async def process_batch_mongodb():
                # Créer un tableau d'opérations pour une exécution en bulk
                operations = []
                
                for user_data in users_to_process:
                    user_id = str(user_data["user_id"])
                    username = user_data["username"]
                    referrer_id = user_data.get("referrer_id")
                    current_time = datetime.now().isoformat()
                    
                    # Vérifier si l'utilisateur existe déjà
                    user = await db_instance.users.find_one({"user_id": user_id})
                    
                    if user:
                        # Mise à jour
                        operations.append({
                            "update_one": {
                                "filter": {"user_id": user_id},
                                "update": {
                                    "$set": {
                                        "username": username,
                                        "last_activity": current_time
                                    },
                                    "$setOnInsert": {
                                        "registration_date": current_time,
                                        "referred_by": str(referrer_id) if referrer_id and referrer_id != user_id else None
                                    }
                                }
                            }
                        })
                    else:
                        # Insertion
                        operations.append({
                            "insert_one": {
                                "document": {
                                    "user_id": user_id,
                                    "username": username,
                                    "registration_date": current_time,
                                    "last_activity": current_time,
                                    "referred_by": str(referrer_id) if referrer_id and referrer_id != user_id else None
                                }
                            }
                        })
                
                # Exécuter les opérations en une seule requête
                if operations:
                    try:
                        result = await db_instance.users.bulk_write(operations)
                        logger.info(f"Traitement par lots terminé: {result.inserted_count} insérés, {result.modified_count} modifiés")
                    except Exception as e:
                        logger.error(f"Erreur lors de l'opération bulk_write: {e}")
            
            # Ajouter à la file d'attente pour exécution asynchrone
            await queue_manager.add_low_priority(process_batch_mongodb)
        else:
            # Pour Google Sheets, traiter séquentiellement
            for user_data in users_to_process:
                await db.register_user(
                    user_data["user_id"], 
                    user_data["username"], 
                    user_data.get("referrer_id")
                )
                
        logger.info(f"Traitement par lots programmé pour {len(users_to_process)} utilisateurs")
    except Exception as e:
        logger.error(f"Erreur lors du traitement par lots des utilisateurs: {e}")

async def add_user_to_batch_queue(user_id, username, referrer_id=None):
    """
    Ajoute un utilisateur à la file d'attente pour traitement par lots.
    Déclenche le traitement si nécessaire.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str): Nom d'utilisateur Telegram
        referrer_id (int, optional): ID du parrain
        
    Returns:
        bool: True si l'ajout a réussi
    """
    global _users_batch_queue
    global _last_batch_processing
    
    try:
        # Vérifier si l'utilisateur est déjà dans la file d'attente
        for user in _users_batch_queue:
            if user["user_id"] == user_id:
                return True
        
        # Ajouter l'utilisateur à la file d'attente
        _users_batch_queue.append({
            "user_id": user_id,
            "username": username,
            "timestamp": time.time(),
            "referrer_id": referrer_id
        })
        
        # Si la file atteint 20 utilisateurs ou si 30 secondes se sont écoulées,
        # déclencher le traitement par lots
        batch_size_threshold = 20  # Augmenté pour réduire les requêtes
        batch_time_threshold = 30  # secondes
        
        if (len(_users_batch_queue) >= batch_size_threshold or 
                (time.time() - _last_batch_processing) > batch_time_threshold):
            # Traiter le lot en arrière-plan
            asyncio.create_task(process_users_batch())
        
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'ajout de l'utilisateur à la file d'attente: {e}")
        return False

# Fonctions d'accès aux données des matchs (avec cache)
def get_all_matches_data():
    """
    Récupère les données des matchs depuis la base de données active.
    Version optimisée qui utilise le cache.
    """
    # Utiliser asyncio pour permettre l'utilisation du cache
    async def get_matches_async():
        # Vérifier d'abord le cache
        cached_matches = await get_cached_matches()
        if cached_matches:
            logger.info("Utilisation du cache pour les données de matchs")
            return cached_matches
        
        # Si pas en cache, charger depuis la base de données
        try:
            matches = db.get_all_matches_data()
            # Mettre en cache pour les requêtes futures (24h)
            await cache_matches(matches)
            return matches
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des matchs: {e}")
            return []
    
    # Exécuter la fonction asynchrone de manière synchrone
    loop = asyncio.get_event_loop()
    try:
        return loop.run_until_complete(get_matches_async())
    except RuntimeError:
        # Si aucune boucle d'événements n'est disponible, en créer une nouvelle
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(get_matches_async())
        finally:
            new_loop.close()

def get_all_teams():
    """
    Récupère la liste de toutes les équipes.
    Version optimisée qui utilise le cache.
    """
    # Utiliser asyncio pour permettre l'utilisation du cache
    async def get_teams_async():
        # Vérifier d'abord le cache
        cached_teams = await get_cached_teams()
        if cached_teams:
            logger.info("Utilisation du cache pour la liste des équipes")
            return cached_teams
        
        # Si pas en cache, charger depuis la base de données
        try:
            teams = db.get_all_teams()
            # Mettre en cache pour les requêtes futures (24h)
            await cache_teams(teams)
            return teams
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des équipes: {e}")
            return []
    
    # Exécuter la fonction asynchrone de manière synchrone
    loop = asyncio.get_event_loop()
    try:
        return loop.run_until_complete(get_teams_async())
    except RuntimeError:
        # Si aucune boucle d'événements n'est disponible, en créer une nouvelle
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(get_teams_async())
        finally:
            new_loop.close()

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
    """
    Enregistre les prédictions demandées par les utilisateurs.
    Version optimisée qui ajoute la tâche à la file d'attente de basse priorité.
    """
    async def _save_prediction_log_async():
        try:
            return db.save_prediction_log(user_id, username, team1, team2, odds1, odds2, prediction_result)
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de la prédiction: {e}")
            return False
    
    # Ajouter à la file d'attente avec basse priorité (pas critique)
    asyncio.create_task(queue_manager.add_low_priority(_save_prediction_log_async))
    return True

async def check_user_subscription(user_id):
    """
    Vérifie si un utilisateur est abonné au canal.
    Version optimisée qui utilise le cache pour réduire drastiquement les requêtes API.
    
    Args:
        user_id (int): L'ID de l'utilisateur Telegram à vérifier
        
    Returns:
        bool: True si l'utilisateur est abonné, False sinon
    """
    # Convertir en string pour la cohérence
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
    cached_status = await get_cached_subscription_status(user_id)
    if cached_status is not None:
        logger.info(f"Utilisation du cache pour la vérification d'abonnement de l'utilisateur {user_id}")
        return cached_status
    
    # Vérification via la base de données active
    try:
        is_subscribed = await db.check_user_subscription(user_id)
        # Mettre en cache (24h)
        await cache_subscription_status(user_id, is_subscribed)
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
    Version optimisée qui utilise la file d'attente par lots.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str): Nom d'utilisateur Telegram
        referrer_id (int, optional): ID Telegram du parrain
    
    Returns:
        bool: True si l'opération a réussi, False sinon
    """
    # Vérifier si c'est un admin
    try:
        from admin_access import is_admin
        if is_admin(user_id, username):
            logger.info(f"Enregistrement d'un administrateur: {username} (ID: {user_id})")
            return True
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut admin: {e}")
    
    # Ajouter l'utilisateur à la file d'attente pour traitement par lots
    success = await add_user_to_batch_queue(user_id, username, referrer_id)
    return success

async def create_referral_relationship(user_id, referrer_id):
    """
    Crée une relation de parrainage dans la base de données.
    Version optimisée qui utilise la file d'attente pour les opérations non-critiques.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur parrainé
        referrer_id (int): ID Telegram du parrain
    """
    # Vérifier si c'est un admin
    try:
        from admin_access import is_admin
        if is_admin(user_id) or is_admin(referrer_id):
            logger.info(f"Relation de parrainage impliquant un admin. ID Utilisateur: {user_id}, ID Parrain: {referrer_id}")
            return None
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut admin: {e}")
    
    # Créer la relation via la base de données active
    async def _create_referral_async():
        try:
            return await db.create_referral_relationship(user_id, referrer_id)
        except Exception as e:
            logger.error(f"Erreur lors de la création de la relation de parrainage: {e}")
            return None
    
    # Ajouter à la file d'attente avec priorité moyenne
    return await queue_manager.add_medium_priority(_create_referral_async)

async def verify_and_update_referral(user_id, referrer_id):
    """
    Vérifie si l'utilisateur est abonné au canal et met à jour le statut de parrainage.
    Version optimisée qui utilise la file d'attente pour les opérations non-critiques.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        referrer_id (int): ID Telegram du parrain
    """
    # Attendre moins longtemps (2 secondes au lieu de 30)
    await asyncio.sleep(2)
    
    # Vérifier l'abonnement
    is_subscribed = await check_user_subscription(user_id)
    logger.info(f"Vérification d'abonnement pour user {user_id}: {is_subscribed}")
    
    if is_subscribed:
        # Mettre à jour le statut de vérification
        async def _update_referral_async():
            try:
                db_instance = get_database()
                if db_instance is None:
                    logger.error("Impossible de se connecter à la base de données pour vérifier un parrainage")
                    return None
                
                # Mettre à jour le statut de vérification
                current_time = datetime.now().isoformat()
                result = await db_instance.referrals.update_one(
                    {
                        "referrer_id": str(referrer_id),
                        "referred_id": str(user_id)
                    },
                    {
                        "$set": {
                            "verified": True,
                            "verification_date": current_time
                        }
                    }
                )
                
                if result.modified_count > 0:
                    logger.info(f"Parrainage vérifié: {referrer_id} -> {user_id}")
                    
                    # Invalider le cache pour ces utilisateurs
                    await cache_referral_count(referrer_id, None)  # Forcer un rechargement
                    
                    # Notification au parrain
                    try:
                        from telegram import Bot
                        from config import TELEGRAM_TOKEN
                        
                        bot = Bot(token=TELEGRAM_TOKEN)
                        referral_count = await count_referrals(referrer_id)
                        
                        from referral_system import get_max_referrals
                        max_referrals = await get_max_referrals()
                        
                        await bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 *Félicitations!* Un nouvel utilisateur a utilisé votre lien et s'est abonné au canal.\n\n"
                                 f"Vous avez maintenant *{referral_count}/{max_referrals}* parrainages vérifiés.",
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Erreur lors de l'envoi de la notification au parrain: {e}")
                    
                    return True
                else:
                    logger.warning(f"Aucune mise à jour du statut de parrainage pour {referrer_id} -> {user_id}")
                    return False
            except Exception as e:
                logger.error(f"Erreur lors de la vérification du parrainage: {e}")
                return None
        
        # Ajouter à la file d'attente avec priorité moyenne
        return await queue_manager.add_medium_priority(_update_referral_async)
    else:
        logger.info(f"Utilisateur {user_id} non abonné, parrainage non vérifié")
        return False

async def has_completed_referrals(user_id, username=None):
    """
    Vérifie si l'utilisateur a atteint le nombre requis de parrainages.
    Version optimisée qui utilise le cache.
    
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
    
    # Obtenir le nombre de parrainages (via cache)
    referral_count = await count_referrals(user_id)
    
    from referral_system import get_max_referrals
    max_referrals = await get_max_referrals()
    
    # Vérifier si le quota est atteint
    completed = referral_count >= max_referrals
    logger.info(f"Utilisateur {user_id} a {referral_count}/{max_referrals} parrainages - Statut: {'Complété' if completed else 'En cours'}")
    
    return completed

async def count_referrals(user_id):
    """
    Compte le nombre de parrainages vérifiés pour un utilisateur.
    Version optimisée qui utilise le cache.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        int: Le nombre de parrainages vérifiés
    """
    # Vérifier si c'est un admin
    try:
        from admin_access import is_admin
        if is_admin(user_id):
            logger.info(f"Comptage de parrainage contourné pour l'admin (ID: {user_id})")
            
            from referral_system import get_max_referrals
            max_referrals = await get_max_referrals()
            return max_referrals
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut admin: {e}")
    
    # Vérifier le cache
    cached_count = await get_cached_referral_count(user_id)
    if cached_count is not None:
        logger.info(f"Utilisation du cache pour le comptage des parrainages de l'utilisateur {user_id}")
        return cached_count
    
    # Si pas en cache, récupérer depuis la base de données
    try:
        count = await db.count_referrals(user_id)
        
        # Mettre en cache
        await cache_referral_count(user_id, count)
        
        return count
    except Exception as e:
        logger.error(f"Erreur lors du comptage des parrainages: {e}")
        return 0

# Version légère pour la vérification rapide des parrainages
async def count_referrals_lite(user_id):
    """
    Version allégée du comptage de parrainages pour les vérifications fréquentes.
    Utilise uniquement le cache, sans requête à la base de données.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        int: Le nombre de parrainages vérifiés ou 0 si non trouvé dans le cache
    """
    # Vérifier si c'est un admin
    try:
        from admin_access import is_admin
        if is_admin(user_id):
            from referral_system import get_max_referrals
            max_referrals = await get_max_referrals()
            return max_referrals
    except Exception:
        pass
    
    # Vérifier uniquement le cache
    cached_count = await get_cached_referral_count(user_id)
    if cached_count is not None:
        return cached_count
    
    # Si pas en cache, retourner 0 (forcer une vérification complète)
    return 0

async def get_referred_users(user_id):
    """
    Récupère la liste des utilisateurs parrainés par un utilisateur.
    Version optimisée qui utilise la file d'attente pour les requêtes non-critiques.
    
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
    async def _get_referred_users_async():
        try:
            return await db.get_referred_users(user_id)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des utilisateurs parrainés: {e}")
            return []
    
    # Ajouter à la file d'attente avec priorité moyenne
    return await queue_manager.add_medium_priority(_get_referred_users_async)

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
            "2️⃣ *L'invité doit démarrer le bot* avec la commande /start\n"
            "3️⃣ *L'invité doit s'abonner* au canal [AL VE CAPITAL](https://t.me/alvecapitalofficiel)\n\n"
            "_Note: Le parrainage sera automatiquement vérifié et validé une fois ces conditions remplies_"
        )

# Fonctions d'optimisation des performances

async def preload_static_data():
    """
    Précharge les données statiques (équipes, matchs) au démarrage pour améliorer les performances.
    Cette fonction doit être appelée au démarrage du bot.
    """
    logger.info("Préchargement des données statiques...")
    
    try:
        # Précharger les matchs
        matches = db.get_all_matches_data()
        if matches:
            # Mettre en cache
            await cache_matches(matches)
            logger.info(f"Préchargement de {len(matches)} matchs terminé")
            
            # Précharger les équipes
            teams = []
            team_set = set()
            
            for match in matches:
                team_home = match.get('team_home', '')
                team_away = match.get('team_away', '')
                
                if team_home and team_home not in team_set:
                    team_set.add(team_home)
                    teams.append(team_home)
                
                if team_away and team_away not in team_set:
                    team_set.add(team_away)
                    teams.append(team_away)
            
            # Trier les équipes
            teams.sort()
            
            # Mettre en cache
            await cache_teams(teams)
            logger.info(f"Préchargement de {len(teams)} équipes terminé")
        else:
            logger.warning("Aucun match trouvé pour le préchargement")
            
            # Essayer de charger directement les équipes
            teams = db.get_all_teams()
            if teams:
                await cache_teams(teams)
                logger.info(f"Préchargement de {len(teams)} équipes terminé")
            else:
                logger.warning("Aucune équipe trouvée pour le préchargement")
        
        return True
    except Exception as e:
        logger.error(f"Erreur lors du préchargement des données statiques: {e}")
        return False

async def monitor_database_performance():
    """
    Surveille les performances de la base de données et journalise les statistiques.
    Cette fonction doit être démarrée en arrière-plan au démarrage du bot.
    """
    try:
        # Métriques de performance
        metrics = {
            "operations": 0,
            "successes": 0,
            "failures": 0,
            "response_times": [],
            "batch_operations": 0,
            "avg_response_time": 0
        }
        
        # Boucle de surveillance
        while True:
            # Attendre 15 minutes
            await asyncio.sleep(900)
            
            # Journaliser les statistiques
            total_operations = metrics["operations"]
            if total_operations > 0:
                success_rate = (metrics["successes"] / total_operations) * 100
                logger.info(f"Statistiques de base de données - Opérations: {total_operations}, "
                           f"Succès: {metrics['successes']} ({success_rate:.1f}%), "
                           f"Échecs: {metrics['failures']}, "
                           f"Lots: {metrics['batch_operations']}")
                
                if metrics["response_times"]:
                    avg_time = sum(metrics["response_times"]) / len(metrics["response_times"])
                    logger.info(f"Temps de réponse moyen: {avg_time:.3f}s")
                
                # Réinitialiser les compteurs
                metrics["operations"] = 0
                metrics["successes"] = 0
                metrics["failures"] = 0
                metrics["response_times"] = []
                metrics["batch_operations"] = 0
    except asyncio.CancelledError:
        logger.info("Surveillance de la base de données arrêtée")
    except Exception as e:
        logger.error(f"Erreur lors de la surveillance de la base de données: {e}")

async def initialize_database():
    """
    Initialise la base de données et précharge les données.
    Cette fonction doit être appelée au démarrage de l'application.
    """
    logger.info("Initialisation de la base de données...")
    
    try:
        # Précharger les données statiques
        await preload_static_data()
        
        # Démarrer la surveillance des performances en arrière-plan
        asyncio.create_task(monitor_database_performance())
        
        # Créer les index MongoDB si nécessaire
        if USE_MONGODB:
            db_instance = get_database()
            if db_instance:
                # Index pour les matchs
                db_instance.matches.create_index("match_id")
                db_instance.matches.create_index("team_home")
                db_instance.matches.create_index("team_away")
                
                # Index pour les utilisateurs
                db_instance.users.create_index("user_id", unique=True)
                db_instance.users.create_index("username")
                db_instance.users.create_index("referred_by")
                
                # Index pour les parrainages
                db_instance.referrals.create_index([("referrer_id", 1), ("referred_id", 1)], unique=True)
                db_instance.referrals.create_index("verified")
                
                # Index pour les logs de prédictions
                db_instance.prediction_logs.create_index("user_id")
                db_instance.prediction_logs.create_index("date")
                
                logger.info("Création des index MongoDB terminée avec succès")
        
        logger.info("Initialisation de la base de données terminée avec succès")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")
        return False

# Fonctions pour les tests et l'administration

async def get_database_status():
    """
    Récupère le statut de la base de données pour le monitoring.
    Utile pour les commandes administratives.
    
    Returns:
        dict: Statistiques de la base de données
    """
    try:
        db_status = {
            "type": "MongoDB" if USE_MONGODB else "Google Sheets",
            "active": False,
            "collections": {},
            "cache_hit_rate": 0,
            "last_batch_size": len(_users_batch_queue),
            "time_since_last_batch": round(time.time() - _last_batch_processing)
        }
        
        if USE_MONGODB:
            try:
                db_instance = get_database()
                if db_instance:
                    # Vérifier la connexion
                    db_instance.command("ping")
                    db_status["active"] = True
                    
                    # Compter les documents dans chaque collection
                    for collection_name in ["matches", "users", "referrals", "prediction_logs"]:
                        collection = getattr(db_instance, collection_name)
                        db_status["collections"][collection_name] = collection.count_documents({})
            except Exception as e:
                logger.error(f"Erreur lors de la vérification de MongoDB: {e}")
                db_status["error"] = str(e)
        else:
            # Pour Google Sheets, simplement marquer comme actif
            db_status["active"] = True
        
        # Statistiques de cache
        from cache_system import cache
        cache_stats = cache.get_stats()
        db_status["cache_stats"] = cache_stats
        
        if cache_stats.get("hits", 0) + cache_stats.get("misses", 0) > 0:
            total = cache_stats.get("hits", 0) + cache_stats.get("misses", 0)
            db_status["cache_hit_rate"] = round((cache_stats.get("hits", 0) / total) * 100, 1)
        
        return db_status
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du statut de la base de données: {e}")
        return {"error": str(e), "active": False}

async def admin_force_preload():
    """
    Force le préchargement des données statiques.
    Utile pour les commandes administratives.
    
    Returns:
        bool: True si l'opération a réussi
    """
    try:
        # Vider les caches existants
        from cache_system import cache
        await cache.clear_all()
        
        # Précharger les données
        success = await preload_static_data()
        
        return success
    except Exception as e:
        logger.error(f"Erreur lors du préchargement forcé: {e}")
        return False

async def admin_clear_cache():
    """
    Vide entièrement le cache.
    Utile pour les commandes administratives.
    
    Returns:
        bool: True si l'opération a réussi
    """
    try:
        from cache_system import cache
        await cache.clear_all()
        logger.info("Cache vidé avec succès")
        return True
    except Exception as e:
        logger.error(f"Erreur lors du vidage du cache: {e}")
        return False
