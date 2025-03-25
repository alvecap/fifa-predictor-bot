import os
import logging
import asyncio
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
from supabase import create_client, Client
from config import TELEGRAM_TOKEN

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Nombre maximum de parrainages requis
MAX_REFERRALS = 1

# Initialisation de la connexion Supabase (utilise les variables d'environnement)
def get_supabase_client() -> Client:
    """Crée et retourne un client Supabase en utilisant les variables d'environnement"""
    try:
        # Les variables d'environnement sont définies sur Render
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            logger.error("Variables d'environnement SUPABASE_URL ou SUPABASE_KEY non définies")
            return None
        
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        logger.error(f"Erreur lors de la création du client Supabase: {e}")
        return None

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
        supabase = get_supabase_client()
        if not supabase:
            return False
        
        # Vérifier si l'utilisateur existe déjà
        response = supabase.table("users").select("*").eq("telegram_id", user_id).execute()
        
        current_time = datetime.now().isoformat()
        
        # Si l'utilisateur n'existe pas encore, l'ajouter
        if not response.data:
            user_data = {
                "telegram_id": user_id,
                "username": username,
                "created_at": current_time,
                "last_active": current_time
            }
            
            supabase.table("users").insert(user_data).execute()
            logger.info(f"Nouvel utilisateur enregistré: {user_id} ({username})")
        else:
            # Mettre à jour l'utilisateur existant
            supabase.table("users").update({
                "username": username, 
                "last_active": current_time
            }).eq("telegram_id", user_id).execute()
        
        # Si un parrain est spécifié et que ce n'est pas l'utilisateur lui-même
        if referrer_id and referrer_id != user_id:
            # Vérifier si la relation de parrainage existe déjà
            ref_response = supabase.table("referrals").select("*").eq("user_id", user_id).execute()
            
            if not ref_response.data:
                # Vérifier si le parrain existe
                referrer_response = supabase.table("users").select("*").eq("telegram_id", referrer_id).execute()
                
                if referrer_response.data:
                    # Créer la relation de parrainage
                    referral_data = {
                        "user_id": user_id,
                        "referrer_id": referrer_id,
                        "created_at": current_time,
                        "is_verified": False
                    }
                    
                    supabase.table("referrals").insert(referral_data).execute()
                    logger.info(f"Relation de parrainage créée: {referrer_id} -> {user_id}")
                    
                    # Envoyer en parallèle la vérification d'abonnement
                    asyncio.create_task(verify_and_update_referral(user_id, referrer_id))
                    
                    return True
        
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de l'utilisateur: {e}")
        return False

async def verify_and_update_referral(user_id, referrer_id):
    """
    Vérifie si l'utilisateur est abonné au canal et met à jour le statut de parrainage.
    Cette fonction est appelée en arrière-plan lors de l'enregistrement d'un parrainage.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        referrer_id (int): ID Telegram du parrain
    """
    try:
        # Attendre un peu avant de vérifier (laisser le temps à l'utilisateur de s'abonner)
        await asyncio.sleep(5)
        
        # Vérifier l'abonnement
        is_subscribed = await check_channel_subscription(user_id)
        
        if is_subscribed:
            # Mettre à jour le statut de vérification dans la base de données
            supabase = get_supabase_client()
            if supabase:
                supabase.table("referrals").update({
                    "is_verified": True,
                    "verified_at": datetime.now().isoformat()
                }).eq("user_id", user_id).eq("referrer_id", referrer_id).execute()
                
                logger.info(f"Parrainage vérifié: {referrer_id} -> {user_id}")
        else:
            logger.info(f"Utilisateur {user_id} non abonné, parrainage non vérifié")
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du parrainage: {e}")

async def check_channel_subscription(user_id, channel_id="@alvecapitalofficiel"):
    """
    Vérifie si un utilisateur est abonné à un canal Telegram spécifique.
    
    Args:
        user_id (int): ID de l'utilisateur Telegram
        channel_id (str): ID du canal à vérifier (par défaut "@alvecapitalofficiel")
        
    Returns:
        bool: True si l'utilisateur est abonné, False sinon
    """
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        
        # Vérifier si l'utilisateur est membre du canal
        chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        
        # Les statuts qui indiquent une adhésion active au canal
        valid_statuses = ['creator', 'administrator', 'member']
        
        return chat_member.status in valid_statuses
    
    except TelegramError as e:
        logger.error(f"Erreur lors de la vérification de l'abonnement: {e}")
        return False

async def has_completed_referrals(user_id):
    """
    Vérifie si l'utilisateur a atteint le nombre requis de parrainages.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        bool: True si l'utilisateur a complété ses parrainages, False sinon
    """
    try:
        referral_count = await count_referrals(user_id)
        return referral_count >= MAX_REFERRALS
    except Exception as e:
        logger.error(f"Erreur lors de la vérification des parrainages: {e}")
        return False

async def count_referrals(user_id):
    """
    Compte le nombre de parrainages vérifiés pour un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        int: Le nombre de parrainages vérifiés
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return 0
        
        # Récupérer uniquement les parrainages vérifiés où l'utilisateur est le parrain
        response = supabase.table("referrals").select("count").eq("referrer_id", user_id).eq("is_verified", True).execute()
        
        # Retourner le nombre de parrainages
        if response.data and isinstance(response.data, list) and len(response.data) > 0:
            return response.data[0].get("count", 0)
        
        return 0
    except Exception as e:
        logger.error(f"Erreur lors du comptage des parrainages: {e}")
        return 0

async def get_referred_users(user_id):
    """
    Récupère la liste des utilisateurs parrainés par un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        list: Liste des utilisateurs parrainés
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return []
        
        # Jointure entre les tables referrals et users pour obtenir les détails des filleuls
        query = """
            SELECT u.telegram_id as id, u.username, r.created_at, r.is_verified
            FROM referrals r
            JOIN users u ON r.user_id = u.telegram_id
            WHERE r.referrer_id = ?
            ORDER BY r.created_at DESC
        """
        
        # Exécuter la requête SQL
        response = supabase.rpc("get_referred_users", {"user_id_param": user_id}).execute()
        
        # Retourner la liste des utilisateurs parrainés
        if response.data:
            return response.data
        
        return []
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
