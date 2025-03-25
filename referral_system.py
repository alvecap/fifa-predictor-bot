import logging
from typing import Optional, List, Dict, Any
from supabase import create_client, Client

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URL et clé Supabase (à remplacer par vos valeurs)
SUPABASE_URL = "VOTRE_URL_SUPABASE"
SUPABASE_KEY = "VOTRE_CLE_SUPABASE"

# Initialisation du client Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Nombre maximum de parrainages autorisés par utilisateur
MAX_REFERRALS = 1  # Changez à 2 si vous voulez autoriser 2 parrainages

async def register_user(user_id: int, username: str = None, referrer_id: int = None) -> bool:
    """
    Enregistre un nouvel utilisateur dans la base de données.
    Si referrer_id est fourni, établit la relation de parrainage.
    
    Args:
        user_id: ID Telegram de l'utilisateur
        username: Nom d'utilisateur Telegram (optionnel)
        referrer_id: ID de l'utilisateur qui a parrainé (optionnel)
    
    Returns:
        bool: True si l'enregistrement a réussi, False sinon
    """
    try:
        # Vérifier si l'utilisateur existe déjà
        user_exists = await check_user_exists(user_id)
        
        if user_exists:
            # Si l'utilisateur existe déjà et qu'un parrain est fourni, 
            # mettre à jour la relation si aucun parrain n'était défini avant
            if referrer_id is not None:
                existing_user = await get_user_data(user_id)
                if existing_user and existing_user.get('referrer_id') is None:
                    await supabase.table('users').update({
                        'referrer_id': referrer_id
                    }).eq('id', user_id).execute()
                    logger.info(f"Updated user {user_id} with referrer {referrer_id}")
                    return True
            return True  # Utilisateur déjà existant, rien à faire
        
        # Créer un nouvel utilisateur
        data = {
            'id': user_id,
            'username': username,
            'referrer_id': referrer_id,
            'created_at': 'now()'
        }
        
        await supabase.table('users').insert(data).execute()
        logger.info(f"New user registered: {user_id}, referred by: {referrer_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        return False

async def check_user_exists(user_id: int) -> bool:
    """
    Vérifie si un utilisateur existe dans la base de données.
    
    Args:
        user_id: ID Telegram de l'utilisateur
    
    Returns:
        bool: True si l'utilisateur existe, False sinon
    """
    try:
        response = await supabase.table('users').select('id').eq('id', user_id).execute()
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Error checking if user exists: {e}")
        return False

async def get_user_data(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Récupère les données d'un utilisateur.
    
    Args:
        user_id: ID Telegram de l'utilisateur
    
    Returns:
        Dict or None: Données de l'utilisateur ou None si l'utilisateur n'existe pas
    """
    try:
        response = await supabase.table('users').select('*').eq('id', user_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting user data: {e}")
        return None

async def count_referrals(user_id: int) -> int:
    """
    Compte le nombre de parrainages réalisés par un utilisateur.
    
    Args:
        user_id: ID Telegram de l'utilisateur
    
    Returns:
        int: Nombre de parrainages
    """
    try:
        response = await supabase.table('users').select('id').eq('referrer_id', user_id).execute()
        return len(response.data)
    except Exception as e:
        logger.error(f"Error counting referrals: {e}")
        return 0

async def has_completed_referrals(user_id: int) -> bool:
    """
    Vérifie si un utilisateur a atteint le quota de parrainages requis.
    
    Args:
        user_id: ID Telegram de l'utilisateur
    
    Returns:
        bool: True si le quota est atteint, False sinon
    """
    try:
        referral_count = await count_referrals(user_id)
        return referral_count >= MAX_REFERRALS
    except Exception as e:
        logger.error(f"Error checking if referrals completed: {e}")
        return False

async def get_referrer(user_id: int) -> Optional[int]:
    """
    Récupère l'ID du parrain d'un utilisateur.
    
    Args:
        user_id: ID Telegram de l'utilisateur
    
    Returns:
        int ou None: ID du parrain ou None
    """
    user_data = await get_user_data(user_id)
    if user_data:
        return user_data.get('referrer_id')
    return None

async def get_referred_users(user_id: int) -> List[Dict[str, Any]]:
    """
    Récupère la liste des utilisateurs parrainés par un utilisateur.
    
    Args:
        user_id: ID Telegram de l'utilisateur
    
    Returns:
        List: Liste des utilisateurs parrainés
    """
    try:
        response = await supabase.table('users').select('*').eq('referrer_id', user_id).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error getting referred users: {e}")
        return []

async def generate_referral_link(user_id: int, bot_username: str) -> str:
    """
    Génère un lien de parrainage pour un utilisateur.
    
    Args:
        user_id: ID Telegram de l'utilisateur
        bot_username: Nom d'utilisateur du bot Telegram
    
    Returns:
        str: Lien de parrainage
    """
    return f"https://t.me/{bot_username}?start=ref{user_id}"
