import logging
import asyncio
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
from config import TELEGRAM_TOKEN, OFFICIAL_CHANNEL, MAX_REFERRALS
from admin_access import is_admin

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importer l'adaptateur de base de données pour MongoDB
# Cela remplace tous les appels directs à Google Sheets
from database_adapter import (
    get_database, check_user_subscription, count_referrals, get_max_referrals
)

# Cache pour les statuts d'abonnement et de parrainage
_subscription_cache = {}  # {"user_id": (timestamp, is_subscribed)}
_referral_cache = {}      # {"user_id": (timestamp, count)}
_CACHE_DURATION = 1800    # 30 minutes en secondes

async def register_user(user_id, username, referrer_id=None):
    """
    Enregistre ou met à jour un utilisateur dans la base de données.
    Cette fonction utilise maintenant le traitement par lots via database_adapter.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str): Nom d'utilisateur Telegram
        referrer_id (int, optional): ID Telegram du parrain
    
    Returns:
        bool: True si l'opération a réussi, False sinon
    """
    try:
        # Vérifier si c'est un admin
        if is_admin(user_id, username):
            logger.info(f"Enregistrement d'un administrateur: {username} (ID: {user_id})")
            # Les admins n'ont pas besoin d'être enregistrés pour les parrainages
            return True
            
        # Utiliser la fonction de l'adaptateur de base de données qui gère le traitement par lots
        from database_adapter import add_user_to_batch_queue
        
        # Ajouter l'utilisateur à la file d'attente pour traitement par lots
        return await add_user_to_batch_queue(user_id, username, referrer_id)
        
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de l'utilisateur: {e}")
        return False

async def create_referral_relationship(user_id, referrer_id):
    """
    Crée une relation de parrainage dans la base de données.
    Version optimisée utilisant MongoDB directement.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur parrainé
        referrer_id (int): ID Telegram du parrain
    """
    try:
        # Vérifier si un des utilisateurs est admin
        if is_admin(user_id) or is_admin(referrer_id):
            logger.info(f"Relation de parrainage impliquant un admin. ID Utilisateur: {user_id}, ID Parrain: {referrer_id}")
            # Les admins n'ont pas besoin de relations de parrainage
            return
            
        # Utiliser MongoDB via l'adaptateur
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données pour créer un parrainage")
            return
        
        # Vérifier si la relation existe déjà
        existing_referral = db.referrals.find_one({
            "referrer_id": str(referrer_id),
            "referred_id": str(user_id)
        })
        
        if existing_referral is None:
            # Vérifier s'il n'y a pas de boucle de parrainage (A parraine B qui parraine A)
            reverse_relation = db.referrals.find_one({
                "referrer_id": str(user_id),
                "referred_id": str(referrer_id)
            })
            
            if reverse_relation is not None:
                logger.warning(f"Boucle de parrainage détectée: {user_id} et {referrer_id} se parrainent mutuellement")
                return
            
            # Vérifier si l'utilisateur est déjà parrainé par quelqu'un d'autre
            other_referrer = db.referrals.find_one({
                "referred_id": str(user_id)
            })
            
            if other_referrer is not None and other_referrer["referrer_id"] != str(referrer_id):
                logger.warning(f"L'utilisateur {user_id} est déjà parrainé par {other_referrer['referrer_id']}")
                return
            
            # Créer la relation de parrainage
            current_time = datetime.now().isoformat()
            new_referral = {
                "referrer_id": str(referrer_id),
                "referred_id": str(user_id),
                "date": current_time,
                "verified": False,
                "verification_date": None
            }
            
            db.referrals.insert_one(new_referral)
            logger.info(f"Relation de parrainage créée: Parrain {referrer_id} -> Filleul {user_id}")
            
            # Lancer la vérification d'abonnement en arrière-plan avec un délai réduit
            asyncio.create_task(verify_and_update_referral(user_id, referrer_id))
        else:
            logger.info(f"Relation de parrainage déjà existante: {referrer_id} -> {user_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de la création de la relation de parrainage: {e}")

async def verify_and_update_referral(user_id, referrer_id):
    """
    Vérifie si l'utilisateur est abonné au canal et met à jour le statut de parrainage.
    Version optimisée avec délai réduit et utilisation du cache.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        referrer_id (int): ID Telegram du parrain
    """
    try:
        # Attendre 2 secondes seulement avant de vérifier (réduit de 30/10 à 2 pour améliorer la réactivité)
        await asyncio.sleep(2)
        
        # Vérifier l'abonnement (utilise le cache via database_adapter)
        is_subscribed = await check_user_subscription(user_id)
        logger.info(f"Vérification d'abonnement pour user {user_id}: {is_subscribed}")
        
        if is_subscribed:
            db = get_database()
            if db is None:
                logger.error("Impossible de se connecter à la base de données pour vérifier un parrainage")
                return
            
            # Mettre à jour le statut de vérification
            current_time = datetime.now().isoformat()
            result = db.referrals.update_one(
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
                if str(referrer_id) in _referral_cache:
                    del _referral_cache[str(referrer_id)]
                    
                # Notification au parrain (en arrière-plan pour ne pas bloquer)
                asyncio.create_task(send_referral_notification(referrer_id))
            else:
                logger.warning(f"Aucune mise à jour du statut de parrainage pour {referrer_id} -> {user_id}")
        else:
            logger.info(f"Utilisateur {user_id} non abonné, parrainage non vérifié")
    
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du parrainage: {e}")

async def send_referral_notification(referrer_id):
    """
    Envoie une notification au parrain concernant un nouveau parrainage validé.
    Fonction séparée pour éviter de bloquer la vérification.
    
    Args:
        referrer_id (int): ID Telegram du parrain
    """
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        referral_count = await count_referrals(referrer_id)
        
        await bot.send_message(
            chat_id=referrer_id,
            text=f"🎉 *Félicitations!* Un nouvel utilisateur a utilisé votre lien et s'est abonné au canal.\n\n"
                 f"Vous avez maintenant *{referral_count}/{MAX_REFERRALS}* parrainages vérifiés.",
            parse_mode='Markdown'
        )
        logger.info(f"Notification envoyée au parrain {referrer_id}")
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de la notification au parrain: {e}")

async def has_completed_referrals(user_id, username=None):
    """
    Vérifie si l'utilisateur a atteint le nombre requis de parrainages.
    Utilise le cache pour éviter les requêtes répétées.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str, optional): Nom d'utilisateur Telegram pour vérification admin
        
    Returns:
        bool: True si l'utilisateur a complété ses parrainages ou est admin, False sinon
    """
    try:
        # Vérifier si c'est un admin
        if is_admin(user_id, username):
            logger.info(f"Vérification de parrainage contournée pour l'admin {username} (ID: {user_id})")
            return True
        
        # Utiliser la fonction database_adapter qui gère le cache
        referral_count = await count_referrals(user_id)
        max_referrals = MAX_REFERRALS
        
        completed = referral_count >= max_referrals
        logger.info(f"Utilisateur {user_id} a {referral_count}/{max_referrals} parrainages - Statut: {'Complété' if completed else 'En cours'}")
        
        return completed
    except Exception as e:
        logger.error(f"Erreur lors de la vérification des parrainages: {e}")
        return False

async def get_referred_users(user_id):
    """
    Récupère la liste des utilisateurs parrainés par un utilisateur.
    Version optimisée utilisant MongoDB directement.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        list: Liste des utilisateurs parrainés avec leurs informations
    """
    try:
        # Vérifier si c'est un admin
        if is_admin(user_id):
            logger.info(f"Récupération des parrainages contournée pour l'admin (ID: {user_id})")
            return []
        
        # Utiliser MongoDB via l'adaptateur
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données pour récupérer les parrainages")
            return []
        
        # Récupérer les parrainages
        referrals = list(db.referrals.find({"referrer_id": str(user_id)}))
        
        referred_users = []
        for referral in referrals:
            referred_id = referral.get("referred_id")
            if referred_id:
                # Récupérer l'information de l'utilisateur parrainé
                user_info = db.users.find_one({"user_id": referred_id})
                
                username = "Inconnu"
                if user_info is not None and "username" in user_info:
                    username = user_info["username"]
                
                referred_users.append({
                    'id': referred_id,
                    'username': username,
                    'is_verified': referral.get("verified", False)
                })
        
        return referred_users
    
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
    return f"https://t.me/{bot_username}?start=ref{user_id}"

# Fonction pour obtenir les instructions de parrainage
def get_referral_instructions():
    """
    Retourne les instructions pour qu'un parrainage soit validé.
    
    Returns:
        str: Message formaté avec les instructions
    """
    return (
        "*📋 Conditions pour qu'un parrainage soit validé:*\n\n"
        "1️⃣ *L'invité doit cliquer sur votre lien de parrainage*\n"
        "2️⃣ *L'invité doit démarrer le bot* avec la commande /start\n"
        "3️⃣ *L'invité doit s'abonner* au canal [AL VE CAPITAL](https://t.me/alvecapitalofficiel)\n\n"
        "_Note: Le parrainage sera automatiquement vérifié et validé une fois ces conditions remplies_"
    )

async def count_referrals(user_id):
    """
    Compte le nombre de parrainages vérifiés pour un utilisateur.
    Version optimisée avec mise en cache.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        int: Le nombre de parrainages vérifiés
    """
    try:
        # Vérifier si c'est un admin
        if is_admin(user_id):
            logger.info(f"Comptage de parrainage contourné pour l'admin (ID: {user_id})")
            return MAX_REFERRALS
        
        # Vérifier le cache
        user_id_str = str(user_id)
        current_time = time.time()
        
        if user_id_str in _referral_cache:
            timestamp, count = _referral_cache[user_id_str]
            if current_time - timestamp < _CACHE_DURATION:
                logger.info(f"Utilisation du cache pour le comptage des parrainages de l'utilisateur {user_id}")
                return count
        
        # Si pas dans le cache ou expiré, compter directement dans MongoDB
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données pour compter les parrainages")
            return 0
            
        # Compter les parrainages vérifiés
        count = db.referrals.count_documents({
            "referrer_id": user_id_str,
            "verified": True
        })
        
        # Mettre en cache
        _referral_cache[user_id_str] = (current_time, count)
        
        logger.info(f"Utilisateur {user_id} a {count} parrainages vérifiés")
        return count
        
    except Exception as e:
        logger.error(f"Erreur lors du comptage des parrainages: {e}")
        return 0

async def check_channel_subscription(user_id, channel_id=None):
    """
    Vérifie si un utilisateur est abonné à un canal Telegram spécifique.
    Version optimisée avec cache.
    
    Args:
        user_id (int): ID de l'utilisateur Telegram
        channel_id (str): ID du canal à vérifier (utilise OFFICIAL_CHANNEL par défaut)
        
    Returns:
        bool: True si l'utilisateur est abonné ou admin, False sinon
    """
    try:
        # Vérifier si c'est un admin
        if is_admin(user_id):
            logger.info(f"Vérification d'abonnement contournée pour l'admin (ID: {user_id})")
            return True
            
        # Utiliser le canal défini dans la configuration
        if channel_id is None:
            channel_id = OFFICIAL_CHANNEL
        
        # Vérifier le cache
        user_id_str = str(user_id)
        current_time = time.time()
        
        if user_id_str in _subscription_cache:
            timestamp, is_subscribed = _subscription_cache[user_id_str]
            if current_time - timestamp < _CACHE_DURATION:
                logger.info(f"Utilisation du cache pour la vérification d'abonnement de l'utilisateur {user_id}")
                return is_subscribed
        
        # Si pas dans le cache ou expiré, vérifier via API Telegram
        bot = Bot(token=TELEGRAM_TOKEN)
        
        # Vérifier si l'utilisateur est membre du canal
        chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        
        # Les statuts qui indiquent une adhésion active au canal
        valid_statuses = ['creator', 'administrator', 'member']
        
        is_member = chat_member.status in valid_statuses
        logger.info(f"Utilisateur {user_id} est{'' if is_member else ' non'} abonné au canal {channel_id}")
        
        # Mettre en cache
        _subscription_cache[user_id_str] = (current_time, is_member)
        
        return is_member
    
    except TelegramError as e:
        logger.error(f"Erreur lors de la vérification de l'abonnement: {e}")
        return False
