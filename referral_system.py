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

async def register_user(user_id, username, referrer_id=None):
    """
    Enregistre ou met à jour un utilisateur dans la base de données.
    Si referrer_id est fourni, crée une relation de parrainage.
    
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
            
        # Utiliser MongoDB via l'adaptateur
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données pour enregistrer l'utilisateur")
            return False
        
        # Vérifier si l'utilisateur existe déjà
        existing_user = db.users.find_one({"user_id": str(user_id)})
        current_time = datetime.now().isoformat()
        
        if existing_user is not None:
            # Si l'utilisateur existe, mise à jour
            update_data = {
                "$set": {
                    "username": username or "Inconnu",
                    "last_activity": current_time
                }
            }
            
            # Si un parrain est spécifié et que l'utilisateur n'a pas déjà un parrain
            if referrer_id and referrer_id != user_id and (not existing_user.get("referred_by")):
                update_data["$set"]["referred_by"] = str(referrer_id)
                
                # Créer la relation de parrainage
                await create_referral_relationship(user_id, referrer_id)
            
            db.users.update_one({"user_id": str(user_id)}, update_data)
            logger.info(f"Utilisateur mis à jour: {username} (ID: {user_id})")
        else:
            # Si l'utilisateur n'existe pas, ajout
            new_user = {
                "user_id": str(user_id),
                "username": username or "Inconnu",
                "registration_date": current_time,
                "last_activity": current_time,
                "referred_by": str(referrer_id) if referrer_id and referrer_id != user_id else None
            }
            
            db.users.insert_one(new_user)
            logger.info(f"Nouvel utilisateur enregistré: {username} (ID: {user_id})")
            
            # Si un parrain est spécifié, créer la relation de parrainage
            if referrer_id and referrer_id != user_id:
                await create_referral_relationship(user_id, referrer_id)
        
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de l'utilisateur: {e}")
        return False

async def create_referral_relationship(user_id, referrer_id):
    """
    Crée une relation de parrainage dans la base de données.
    
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
            
            # Lancer la vérification d'abonnement en arrière-plan
            asyncio.create_task(verify_and_update_referral(user_id, referrer_id))
        else:
            logger.info(f"Relation de parrainage déjà existante: {referrer_id} -> {user_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de la création de la relation de parrainage: {e}")

async def verify_and_update_referral(user_id, referrer_id):
    """
    Vérifie si l'utilisateur est abonné au canal et met à jour le statut de parrainage.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        referrer_id (int): ID Telegram du parrain
    """
    try:
        # Attendre 10 secondes avant de vérifier (réduit de 30 à 10 pour améliorer la réactivité)
        await asyncio.sleep(10)
        
        # Vérifier l'abonnement
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
                
                # Notification au parrain
                try:
                    from telegram import Bot
                    
                    bot = Bot(token=TELEGRAM_TOKEN)
                    referral_count = await count_referrals(referrer_id)
                    
                    await bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 *Félicitations!* Un nouvel utilisateur a utilisé votre lien et s'est abonné au canal.\n\n"
                             f"Vous avez maintenant *{referral_count}/{await get_max_referrals()}* parrainages vérifiés.",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Erreur lors de l'envoi de la notification au parrain: {e}")
            else:
                logger.warning(f"Aucune mise à jour du statut de parrainage pour {referrer_id} -> {user_id}")
        else:
            logger.info(f"Utilisateur {user_id} non abonné, parrainage non vérifié")
    
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du parrainage: {e}")

async def has_completed_referrals(user_id, username=None):
    """
    Vérifie si l'utilisateur a atteint le nombre requis de parrainages.
    
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
        
        referral_count = await count_referrals(user_id)
        max_referrals = await get_max_referrals()
        
        completed = referral_count >= max_referrals
        logger.info(f"Utilisateur {user_id} a {referral_count}/{max_referrals} parrainages - Statut: {'Complété' if completed else 'En cours'}")
        
        return completed
    except Exception as e:
        logger.error(f"Erreur lors de la vérification des parrainages: {e}")
        return False

async def get_referred_users(user_id):
    """
    Récupère la liste des utilisateurs parrainés par un utilisateur.
    
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
