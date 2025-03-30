import logging
import asyncio
from typing import Optional, Union, Dict
from telegram import Message, Bot, InlineKeyboardMarkup
from queue_manager import send_message_queued, edit_message_queued

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Catalogue des emojis animés Telegram pour différentes animations
# Ces valeurs sont les identifiants des stickers/animations Telegram
# NOTE: Ces valeurs sont fictives et doivent être remplacées par de vraies valeurs
ANIMATION_CATALOG = {
    # Animations de vérification
    "verification": {
        "loading": "CgACAgQAAxkDAAImemXXdBn4ztMhmfxDHBRJ3wY9mwAD1g2AUa1cYsYWTAACZQ",  # Animation chargement
        "success": "CgACAgQAAxkDAAIme2XXdDaPQHZb28avvGw_gV1TFgAC9g2AUf0qWX4ZqAACZQ",  # Animation succès
        "failure": "CgACAgQAAxkDAAImdGXXdDGdAudZEVJG1TspXXVEBgAC_AuAUbbJoLJeKAACZQ"   # Animation échec
    },
    
    # Animations de prédiction
    "prediction": {
        "loading": "CgACAgQAAxkDAAImdWXXdDb3Bxx51pqbSCvxcKHnBAADUw6AUcYc4FjRGAACZQ",  # Calcul en cours
        "success": "CgACAgQAAxkDAAImdmXXdDlYU35H7t8DQ97hPcf_BgACGg-AUQDNiY4EJAACZQ",  # Prédiction réussie
        "randomizing": "CgACAgQAAxkDAAImd2XXdDxR7TnCsXbYxRZXXh4UGwACohGAUVQNe82slAACZQ"  # Animation d'aléatoire
    },
    
    # Animations de jeux
    "games": {
        "apple": "CgACAgQAAxkDAAImeGXXdECMYdNAJGw7iGNHtdBK-QACbBGAUWR5bvDO1QACZQ",     # Animation pomme
        "baccarat": "CgACAgQAAxkDAAImeWXXdEPsNyQK9oTqnJ3c94H_BgACnhOAUU3T06jEOAACZQ",  # Animation cartes
        "fifa": "CgACAgQAAxkDAAImB2XXdE0hZwGrYvmTDN9qGN85BwACrxCAUYIlZUgTQAACZQ"       # Animation football
    }
}

# Textes alternatifs pour les animations (utilisés si le GIF n'est pas disponible)
ANIMATION_TEXT = {
    "verification": {
        "loading": "🔍 *Vérification en cours...*",
        "success": "✅ *Vérification réussie!*",
        "failure": "❌ *Vérification échouée!*"
    },
    "prediction": {
        "loading": "🧠 *Analyse des données en cours...*",
        "success": "🎯 *Prédiction générée!*",
        "randomizing": "🎲 *Génération aléatoire...*" 
    },
    "games": {
        "apple": "🍎 *Apple of Fortune en cours...*",
        "baccarat": "🃏 *Baccarat en cours...*",
        "fifa": "⚽ *FIFA 4x4 en cours...*"
    }
}

async def send_animated_message(
    message: Message,
    animation_type: str,
    animation_subtype: str,
    text: str = None,
    final_text: str = None,
    reply_markup: InlineKeyboardMarkup = None,
    edit: bool = False,
    user_id: int = None,
    animation_duration: float = 3.0
) -> Message:
    """
    Envoie un message avec une animation GIF Telegram, puis le remplace par le texte final.
    
    Args:
        message (Message): Message Telegram pour répondre ou éditer
        animation_type (str): Type d'animation ('verification', 'prediction', 'games')
        animation_subtype (str): Sous-type d'animation ('loading', 'success', etc.)
        text (str, optional): Texte à afficher avec l'animation
        final_text (str, optional): Texte final à afficher après l'animation
        reply_markup (InlineKeyboardMarkup, optional): Markup pour les boutons
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        user_id (int, optional): ID de l'utilisateur pour le suivi
        animation_duration (float): Durée de l'animation en secondes
        
    Returns:
        Message: Le message final
    """
    try:
        # Obtenir l'identifiant du GIF
        animation_id = ANIMATION_CATALOG.get(animation_type, {}).get(animation_subtype)
        
        # Obtenir le texte alternatif
        if text is None:
            text = ANIMATION_TEXT.get(animation_type, {}).get(animation_subtype, "Traitement en cours...")
        
        # Si l'animation n'est pas disponible, utiliser uniquement le texte
        if not animation_id:
            if edit and hasattr(message, 'edit_text'):
                return await edit_message_queued(
                    message=message,
                    text=text,
                    parse_mode='Markdown',
                    user_id=user_id,
                    high_priority=True
                )
            else:
                return await send_message_queued(
                    chat_id=message.chat_id,
                    text=text,
                    parse_mode='Markdown',
                    user_id=user_id,
                    high_priority=True
                )
        
        # Envoyer ou éditer le message avec l'animation
        if edit and hasattr(message, 'edit_text'):
            # Pour l'édition, on ne peut pas ajouter de GIF, donc utiliser le texte
            animation_msg = await edit_message_queued(
                message=message,
                text=text,
                parse_mode='Markdown',
                user_id=user_id,
                high_priority=True
            )
        else:
            # Envoyer un nouveau message avec l'animation
            from telegram import Bot, Animation
            from config import TELEGRAM_TOKEN
            
            bot = Bot(token=TELEGRAM_TOKEN)
            
            async def _send_animation():
                try:
                    return await bot.send_animation(
                        chat_id=message.chat_id,
                        animation=animation_id,
                        caption=text,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.warning(f"Erreur lors de l'envoi de l'animation: {e}. Utilisation du texte uniquement.")
                    return await bot.send_message(
                        chat_id=message.chat_id,
                        text=text,
                        parse_mode='Markdown'
                    )
            
            # Utiliser la file d'attente pour l'envoi de l'animation
            from queue_manager import queue_manager
            future = queue_manager.add_high_priority(_send_animation, user_id=user_id)
            animation_msg = await future
        
        # Si un texte final est fourni, attendre puis remplacer par le texte final
        if final_text:
            await asyncio.sleep(animation_duration)
            
            # Éditer le message pour afficher le texte final
            final_msg = await edit_message_queued(
                message=animation_msg,
                text=final_text,
                parse_mode='Markdown',
                reply_markup=reply_markup,
                user_id=user_id,
                high_priority=True
            )
            return final_msg
        
        return animation_msg
        
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi du message animé: {e}")
        
        # Fallback en cas d'erreur: envoyer un message texte simple
        if edit and hasattr(message, 'edit_text'):
            return await message.edit_text(
                text=final_text or text or "Traitement terminé",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            return await message.reply_text(
                text=final_text or text or "Traitement terminé",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

# Fonctions spécifiques pour les différentes animations

async def send_verification_animation(
    message: Message,
    success: bool,
    final_text: str = None,
    reply_markup: InlineKeyboardMarkup = None,
    edit: bool = False,
    user_id: int = None,
    loading_duration: float = 2.0
) -> Message:
    """
    Envoie une animation de vérification (succès ou échec).
    
    Args:
        message (Message): Message Telegram pour répondre ou éditer
        success (bool): Si True, affiche une animation de succès, sinon d'échec
        final_text (str, optional): Texte final à afficher après l'animation
        reply_markup (InlineKeyboardMarkup, optional): Markup pour les boutons
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        user_id (int, optional): ID de l'utilisateur pour le suivi
        loading_duration (float): Durée de l'animation de chargement en secondes
        
    Returns:
        Message: Le message final
    """
    # D'abord afficher l'animation de chargement
    loading_msg = await send_animated_message(
        message=message,
        animation_type="verification",
        animation_subtype="loading",
        text="🔍 *Vérification en cours...*",
        edit=edit,
        user_id=user_id,
        animation_duration=loading_duration
    )
    
    # Puis afficher l'animation de succès ou d'échec
    subtype = "success" if success else "failure"
    
    if not final_text:
        final_text = "✅ *Vérification réussie!*" if success else "❌ *Vérification échouée!*"
    
    return await send_animated_message(
        message=loading_msg,
        animation_type="verification",
        animation_subtype=subtype,
        text=None,
        final_text=final_text,
        reply_markup=reply_markup,
        edit=True,
        user_id=user_id,
        animation_duration=1.0  # Plus court pour cette seconde phase
    )

async def send_prediction_animation(
    message: Message,
    final_text: str,
    reply_markup: InlineKeyboardMarkup = None,
    edit: bool = False,
    user_id: int = None,
    game_type: str = "fifa",
    loading_duration: float = 3.0
) -> Message:
    """
    Envoie une animation de prédiction pour un jeu spécifique.
    
    Args:
        message (Message): Message Telegram pour répondre ou éditer
        final_text (str): Texte final avec la prédiction à afficher
        reply_markup (InlineKeyboardMarkup, optional): Markup pour les boutons
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        user_id (int, optional): ID de l'utilisateur pour le suivi
        game_type (str): Type de jeu ('fifa', 'apple', 'baccarat')
        loading_duration (float): Durée de l'animation de chargement en secondes
        
    Returns:
        Message: Le message final
    """
    # Déterminer le type d'animation en fonction du jeu
    animation_subtype = "loading"  # Par défaut
    
    # Si c'est Apple ou Baccarat, utiliser l'animation de randomisation
    if game_type in ['apple', 'baccarat']:
        animation_subtype = "randomizing"
    
    # D'abord afficher l'animation de chargement/analyse
    loading_text = f"🧠 *Analyse des données pour {game_type.upper()}...*"
    loading_msg = await send_animated_message(
        message=message,
        animation_type="prediction",
        animation_subtype=animation_subtype,
        text=loading_text,
        edit=edit,
        user_id=user_id,
        animation_duration=loading_duration
    )
    
    # Puis afficher l'animation de succès avec le résultat
    return await send_animated_message(
        message=loading_msg,
        animation_type="prediction",
        animation_subtype="success",
        text=None,
        final_text=final_text,
        reply_markup=reply_markup,
        edit=True,
        user_id=user_id,
        animation_duration=1.0  # Plus court pour cette seconde phase
    )

async def send_game_animation(
    message: Message,
    game_type: str,
    final_text: str = None,
    reply_markup: InlineKeyboardMarkup = None,
    edit: bool = False,
    user_id: int = None,
    animation_duration: float = 2.0
) -> Message:
    """
    Envoie une animation spécifique à un jeu.
    
    Args:
        message (Message): Message Telegram pour répondre ou éditer
        game_type (str): Type de jeu ('fifa', 'apple', 'baccarat')
        final_text (str, optional): Texte final à afficher après l'animation
        reply_markup (InlineKeyboardMarkup, optional): Markup pour les boutons
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        user_id (int, optional): ID de l'utilisateur pour le suivi
        animation_duration (float): Durée de l'animation en secondes
        
    Returns:
        Message: Le message final
    """
    # Vérifier si le type de jeu est valide
    if game_type not in ['fifa', 'apple', 'baccarat']:
        game_type = 'fifa'  # Type par défaut
    
    # Texte spécifique au jeu
    game_texts = {
        'fifa': "⚽ *FIFA 4x4 Predictor*",
        'apple': "🍎 *Apple of Fortune*",
        'baccarat': "🃏 *Baccarat*"
    }
    
    text = game_texts.get(game_type, "🎮 *Jeu en cours...*")
    
    return await send_animated_message(
        message=message,
        animation_type="games",
        animation_subtype=game_type,
        text=text,
        final_text=final_text,
        reply_markup=reply_markup,
        edit=edit,
        user_id=user_id,
        animation_duration=animation_duration
    )

async def show_waiting_animation(
    message: Message,
    position: int,
    estimated_wait: float,
    edit: bool = True,
    user_id: int = None
) -> Message:
    """
    Affiche une animation d'attente pour les utilisateurs en file d'attente.
    
    Args:
        message (Message): Message Telegram pour répondre ou éditer
        position (int): Position dans la file d'attente
        estimated_wait (float): Temps d'attente estimé en secondes
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        user_id (int, optional): ID de l'utilisateur pour le suivi
        
    Returns:
        Message: Le message d'attente
    """
    # Formater le temps d'attente
    if estimated_wait < 60:
        wait_str = f"{estimated_wait:.1f} secondes"
    else:
        wait_str = f"{estimated_wait / 60:.1f} minutes"
    
    # Texte d'attente
    waiting_text = (
        f"⏳ *File d'attente active*\n\n"
        f"Position: *{position}*\n"
        f"Temps d'attente estimé: *{wait_str}*\n\n"
        f"Merci de votre patience!"
    )
    
    # Utiliser simplement un message texte pour l'attente
    # (pas besoin d'animation coûteuse pour ce cas)
    if edit and hasattr(message, 'edit_text'):
        return await edit_message_queued(
            message=message,
            text=waiting_text,
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=False  # Priorité plus basse pour les notifications d'attente
        )
    else:
        return await send_message_queued(
            chat_id=message.chat_id,
            text=waiting_text,
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=False  # Priorité plus basse pour les notifications d'attente
        )
