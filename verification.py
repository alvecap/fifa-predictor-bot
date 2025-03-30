import logging
import asyncio
import time
from typing import Optional, Dict, Any, Union, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes

# Importer les nouveaux modules optimisés
from queue_manager import send_message_queued, edit_message_queued, get_system_load_status
from gif_animations import send_verification_animation, send_game_animation
from cache_system import (
    get_cached_subscription_status, cache_subscription_status,
    get_cached_referral_count, cache_referral_count
)

# Importer depuis les modules existants pour assurer la compatibilité
from admin_access import is_admin
from config import OFFICIAL_CHANNEL, MAX_REFERRALS

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Vérification d'abonnement - version optimisée
async def verify_subscription(message, user_id, username, context=None, edit=False) -> bool:
    """
    Vérifie si l'utilisateur est abonné au canal avec animation GIF et mise en cache.
    Version optimisée qui réduit significativement les requêtes API.
    
    Args:
        message: Message Telegram pour répondre
        user_id (int): ID de l'utilisateur
        username (str): Nom d'utilisateur
        context: Contexte de conversation Telegram (optionnel)
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        
    Returns:
        bool: True si l'utilisateur est abonné ou admin, False sinon
    """
    # Vérifier si c'est un admin
    if is_admin(user_id, username):
        if edit and hasattr(message, 'edit_text'):
            await edit_message_queued(
                message=message,
                text="🔑 *Accès administrateur*\n\n"
                    "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown',
                user_id=user_id
            )
        else:
            await send_message_queued(
                chat_id=message.chat_id,
                text="🔑 *Accès administrateur*\n\n"
                    "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown',
                user_id=user_id
            )
        return True
    
    # Vérifier d'abord le cache
    cached_status = await get_cached_subscription_status(user_id)
    if cached_status is not None:
        logger.info(f"Statut d'abonnement trouvé en cache pour {user_id}: {cached_status}")
        
        if cached_status:
            # Statut positif en cache, afficher directement la confirmation
            if edit and hasattr(message, 'edit_text'):
                await edit_message_queued(
                    message=message,
                    text="✅ *Abonnement vérifié!*\n\n"
                        "Vous êtes bien abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).",
                    parse_mode='Markdown',
                    disable_web_page_preview=True,
                    user_id=user_id
                )
            else:
                await send_message_queued(
                    chat_id=message.chat_id,
                    text="✅ *Abonnement vérifié!*\n\n"
                        "Vous êtes bien abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).",
                    parse_mode='Markdown',
                    disable_web_page_preview=True,
                    user_id=user_id
                )
            
            # Passer à la vérification du parrainage si le contexte est fourni
            if context:
                await verify_referral(message, user_id, username, context)
                
            return True
        else:
            # Statut négatif en cache, afficher message d'erreur
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
                [InlineKeyboardButton("🔍 Vérifier à nouveau", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if edit and hasattr(message, 'edit_text'):
                await edit_message_queued(
                    message=message,
                    text="❌ *Abonnement non détecté*\n\n"
                        "Vous n'êtes pas encore abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).\n\n"
                        "*Instructions:*\n"
                        "1️⃣ Cliquez sur le bouton 'Rejoindre le canal'\n"
                        "2️⃣ Abonnez-vous au canal\n"
                        "3️⃣ Revenez ici et cliquez sur 'Vérifier à nouveau'",
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                    disable_web_page_preview=True,
                    user_id=user_id
                )
            else:
                await send_message_queued(
                    chat_id=message.chat_id,
                    text="❌ *Abonnement non détecté*\n\n"
                        "Vous n'êtes pas encore abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).\n\n"
                        "*Instructions:*\n"
                        "1️⃣ Cliquez sur le bouton 'Rejoindre le canal'\n"
                        "2️⃣ Abonnez-vous au canal\n"
                        "3️⃣ Revenez ici et cliquez sur 'Vérifier à nouveau'",
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                    disable_web_page_preview=True,
                    user_id=user_id
                )
            return False
    
    # Si pas en cache, faire la vérification effective avec animation GIF
    # Utiliser l'animation GIF optimisée au lieu de l'animation textuelle
    final_text_success = (
        "✅ *Abonnement vérifié!*\n\n"
        "Vous êtes bien abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel)."
    )
    
    final_text_failure = (
        "❌ *Abonnement non détecté*\n\n"
        "Vous n'êtes pas encore abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).\n\n"
        "*Instructions:*\n"
        "1️⃣ Cliquez sur le bouton 'Rejoindre le canal'\n"
        "2️⃣ Abonnez-vous au canal\n"
        "3️⃣ Revenez ici et cliquez sur 'Vérifier à nouveau'"
    )
    
    # Effectuer la vérification API réelle
    from database_adapter import check_user_subscription
    is_subscribed = await check_user_subscription(user_id)
    
    # Mettre en cache le résultat pour 24 heures (ou la durée configurée)
    await cache_subscription_status(user_id, is_subscribed)
    
    if is_subscribed:
        # Animation de succès
        keyboard = None  # Pas de boutons pour le succès

        # Envoi du message animé
        await send_verification_animation(
            message=message,
            success=True,
            final_text=final_text_success,
            reply_markup=keyboard,
            edit=edit,
            user_id=user_id,
            loading_duration=1.0  # Réduit la durée d'animation
        )
        
        # Lancer la vérification du parrainage si le contexte est fourni
        if context:
            await verify_referral(message, user_id, username, context)
            
        return True
    else:
        # Animation d'échec
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
            [InlineKeyboardButton("🔍 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Envoi du message animé
        await send_verification_animation(
            message=message,
            success=False,
            final_text=final_text_failure,
            reply_markup=reply_markup,
            edit=edit,
            user_id=user_id,
            loading_duration=1.0  # Réduit la durée d'animation
        )
        return False

# Vérification de parrainage - version optimisée
async def verify_referral(message, user_id, username, context=None, edit=False) -> bool:
    """
    Vérifie si l'utilisateur a complété ses parrainages avec animation GIF et mise en cache.
    Version optimisée qui réduit significativement les requêtes API.
    
    Args:
        message: Message Telegram pour répondre
        user_id (int): ID de l'utilisateur
        username (str): Nom d'utilisateur
        context: Contexte de conversation Telegram (optionnel)
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        
    Returns:
        bool: True si l'utilisateur a complété ses parrainages ou est admin, False sinon
    """
    # Récupérer MAX_REFERRALS
    from referral_system import get_max_referrals
    max_referrals = await get_max_referrals()
    
    # Vérifier si c'est un admin
    if is_admin(user_id, username):
        if edit and hasattr(message, 'edit_text'):
            await edit_message_queued(
                message=message,
                text="🔑 *Accès administrateur*\n\n"
                    "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown',
                user_id=user_id
            )
        else:
            await send_message_queued(
                chat_id=message.chat_id,
                text="🔑 *Accès administrateur*\n\n"
                    "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown',
                user_id=user_id
            )
            
        # Créer un bouton direct pour chaque jeu (contournement pour éviter les erreurs)
        keyboard = [
            [InlineKeyboardButton("🏆 FIFA 4x4 Predictor", callback_data="game_fifa")],
            [InlineKeyboardButton("🍎 Apple of Fortune", callback_data="game_apple")],
            [InlineKeyboardButton("🃏 Baccarat", callback_data="game_baccarat")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message avec boutons directs pour les administrateurs
        try:
            await send_message_queued(
                chat_id=message.chat_id,
                text="🎮 *Menu des jeux disponibles*\n\n"
                    "Sélectionnez un jeu pour commencer:",
                parse_mode='Markdown',
                reply_markup=reply_markup,
                user_id=user_id
            )
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage des boutons de jeu: {e}")
            
        return True
    
    # Vérifier d'abord le cache
    cached_count = await get_cached_referral_count(user_id)
    if cached_count is not None:
        logger.info(f"Nombre de parrainages trouvé en cache pour {user_id}: {cached_count}")
        
        has_completed = cached_count >= max_referrals
        
        if has_completed:
            # Nombre suffisant en cache, afficher directement la confirmation
            if edit and hasattr(message, 'edit_text'):
                await edit_message_queued(
                    message=message,
                    text="✅ *Parrainage complété!*\n\n"
                        f"Vous avez atteint votre objectif de {max_referrals} parrainage(s).\n"
                        "Toutes les fonctionnalités sont désormais débloquées.",
                    parse_mode='Markdown',
                    user_id=user_id
                )
            else:
                await send_message_queued(
                    chat_id=message.chat_id,
                    text="✅ *Parrainage complété!*\n\n"
                        f"Vous avez atteint votre objectif de {max_referrals} parrainage(s).\n"
                        "Toutes les fonctionnalités sont désormais débloquées.",
                    parse_mode='Markdown',
                    user_id=user_id
                )
            
            # Créer un bouton direct pour chaque jeu
            keyboard = [
                [InlineKeyboardButton("🏆 FIFA 4x4 Predictor", callback_data="game_fifa")],
                [InlineKeyboardButton("🍎 Apple of Fortune", callback_data="game_apple")],
                [InlineKeyboardButton("🃏 Baccarat", callback_data="game_baccarat")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Message avec boutons directs
            try:
                await send_message_queued(
                    chat_id=message.chat_id,
                    text="🎮 *Menu des jeux disponibles*\n\n"
                        "Sélectionnez un jeu pour commencer:",
                    parse_mode='Markdown',
                    reply_markup=reply_markup,
                    user_id=user_id
                )
            except Exception as e:
                logger.error(f"Erreur lors de l'affichage des boutons de jeu: {e}")
            
            return True
        else:
            # Nombre insuffisant en cache, afficher message en cours
            keyboard = [
                [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
                [InlineKeyboardButton("✅ Vérifier à nouveau", callback_data="verify_referral")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if edit and hasattr(message, 'edit_text'):
                await edit_message_queued(
                    message=message,
                    text=f"⏳ *Parrainage en cours - {cached_count}/{max_referrals}*\n\n"
                        f"Vous avez actuellement {cached_count} parrainage(s) sur {max_referrals} requis.\n\n"
                        f"Partagez votre lien de parrainage pour débloquer toutes les fonctionnalités.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                    user_id=user_id
                )
            else:
                await send_message_queued(
                    chat_id=message.chat_id,
                    text=f"⏳ *Parrainage en cours - {cached_count}/{max_referrals}*\n\n"
                        f"Vous avez actuellement {cached_count} parrainage(s) sur {max_referrals} requis.\n\n"
                        f"Partagez votre lien de parrainage pour débloquer toutes les fonctionnalités.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                    user_id=user_id
                )
            return False
    
    # Si pas en cache, faire la vérification effective avec animation GIF
    try:
        # Obtenir le nombre actuel de parrainages
        from referral_system import count_referrals
        referral_count = await count_referrals(user_id)
        
        # Mettre en cache le résultat
        await cache_referral_count(user_id, referral_count)
        
        # Vérifier si le quota est atteint
        has_completed = referral_count >= max_referrals
        
        if has_completed:
            # Message final de succès
            final_text_success = (
                "✅ *Parrainage complété!*\n\n"
                f"Vous avez atteint votre objectif de {max_referrals} parrainage(s).\n"
                "Toutes les fonctionnalités sont désormais débloquées."
            )
            
            # Animation de succès
            await send_verification_animation(
                message=message,
                success=True,
                final_text=final_text_success,
                edit=edit,
                user_id=user_id,
                loading_duration=1.0  # Réduit la durée d'animation
            )
            
            # Créer un bouton direct pour chaque jeu
            keyboard = [
                [InlineKeyboardButton("🏆 FIFA 4x4 Predictor", callback_data="game_fifa")],
                [InlineKeyboardButton("🍎 Apple of Fortune", callback_data="game_apple")],
                [InlineKeyboardButton("🃏 Baccarat", callback_data="game_baccarat")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Message avec boutons directs
            try:
                await send_message_queued(
                    chat_id=message.chat_id,
                    text="🎮 *Menu des jeux disponibles*\n\n"
                        "Sélectionnez un jeu pour commencer:",
                    parse_mode='Markdown',
                    reply_markup=reply_markup,
                    user_id=user_id
                )
            except Exception as e:
                logger.error(f"Erreur lors de l'affichage des boutons de jeu: {e}")
            
            return True
        else:
            # Message indiquant le nombre actuel de parrainages
            keyboard = [
                [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
                [InlineKeyboardButton("✅ Vérifier à nouveau", callback_data="verify_referral")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            final_text_failure = (
                f"⏳ *Parrainage en cours - {referral_count}/{max_referrals}*\n\n"
                f"Vous avez actuellement {referral_count} parrainage(s) sur {max_referrals} requis.\n\n"
                f"Partagez votre lien de parrainage pour débloquer toutes les fonctionnalités."
            )
            
            # Animation d'attente
            await send_verification_animation(
                message=message,
                success=False,
                final_text=final_text_failure,
                reply_markup=reply_markup,
                edit=edit,
                user_id=user_id,
                loading_duration=1.0  # Réduit la durée d'animation
            )
            return False
            
    except Exception as e:
        logger.error(f"Erreur lors de la vérification des parrainages: {e}")
        if edit and hasattr(message, 'edit_text'):
            await edit_message_queued(
                message=message,
                text="❌ *Erreur lors de la vérification*\n\n"
                    "Une erreur est survenue lors de la vérification de votre parrainage. Veuillez réessayer.",
                parse_mode='Markdown',
                user_id=user_id
            )
        else:
            await send_message_queued(
                chat_id=message.chat_id,
                text="❌ *Erreur lors de la vérification*\n\n"
                    "Une erreur est survenue lors de la vérification de votre parrainage. Veuillez réessayer.",
                parse_mode='Markdown',
                user_id=user_id
            )
        return False

# Message standard quand l'abonnement est requis - version optimisée
async def send_subscription_required(message) -> None:
    """
    Envoie un message indiquant que l'abonnement est nécessaire.
    Version optimisée utilisant la file d'attente.
    """
    keyboard = [
        [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
        [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_message_queued(
        chat_id=message.chat_id,
        text="⚠️ *Abonnement requis*\n\n"
            "Pour utiliser cette fonctionnalité, vous devez être abonné à notre canal.\n\n"
            "*Instructions:*\n"
            "1️⃣ Rejoignez [AL VE CAPITAL](https://t.me/alvecapitalofficiel)\n"
            "2️⃣ Cliquez sur '🔍 Vérifier mon abonnement'",
        reply_markup=reply_markup,
        parse_mode='Markdown',
        disable_web_page_preview=True,
        user_id=None,  # No user tracking for standard messages
        high_priority=False  # Lower priority for standard messages
    )

# Message standard quand le parrainage est requis - version optimisée
async def send_referral_required(message) -> None:
    """
    Envoie un message indiquant que le parrainage est nécessaire.
    Version optimisée utilisant la file d'attente.
    """
    from referral_system import get_max_referrals
    max_referrals = await get_max_referrals()
    
    keyboard = [
        [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
        [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_message_queued(
        chat_id=message.chat_id,
        text="⚠️ *Parrainage requis*\n\n"
            f"Pour utiliser cette fonctionnalité, vous devez parrainer {max_referrals} personne(s).\n\n"
            "Partagez votre lien de parrainage avec vos amis pour débloquer toutes les fonctionnalités.",
        reply_markup=reply_markup,
        parse_mode='Markdown',
        user_id=None,  # No user tracking for standard messages
        high_priority=False  # Lower priority for standard messages
    )

# Vérification complète avant d'accéder à une fonctionnalité - version optimisée
async def verify_all_requirements(user_id, username, message, context=None) -> bool:
    """
    Vérifie toutes les conditions d'accès (abonnement + parrainage) de manière optimisée.
    Utilise le cache et minimise les requêtes API.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str): Nom d'utilisateur Telegram
        message: Message Telegram pour répondre
        context: Contexte de conversation Telegram (optionnel)
        
    Returns:
        bool: True si l'utilisateur a accès (admin ou abonné+parrainé), False sinon
    """
    # Vérifier d'abord si c'est un admin
    if is_admin(user_id, username):
        logger.info(f"Vérification contournée pour l'administrateur {username} (ID: {user_id})")
        return True
    
    # Vérifier l'abonnement en utilisant le cache
    cached_status = await get_cached_subscription_status(user_id)
    if cached_status is not None:
        is_subscribed = cached_status
    else:
        # Si pas en cache, faire la vérification API et mettre en cache
        from database_adapter import check_user_subscription
        is_subscribed = await check_user_subscription(user_id)
        await cache_subscription_status(user_id, is_subscribed)
    
    if not is_subscribed:
        await send_subscription_required(message)
        return False
    
    # Vérifier le parrainage en utilisant le cache
    cached_count = await get_cached_referral_count(user_id)
    if cached_count is not None:
        has_completed = cached_count >= MAX_REFERRALS
    else:
        # Si pas en cache, faire la vérification API et mettre en cache
        from referral_system import count_referrals
        referral_count = await count_referrals(user_id)
        await cache_referral_count(user_id, referral_count)
        has_completed = referral_count >= MAX_REFERRALS
    
    if not has_completed:
        await send_referral_required(message)
        return False
    
    return True

# Fonction pour afficher le menu principal des jeux - version optimisée
async def show_games_menu(message, context) -> None:
    """
    Affiche le menu principal avec tous les jeux disponibles.
    Version optimisée utilisant la file d'attente.
    """
    try:
        # Texte du menu simplifié
        menu_text = (
            "🎮 *FIFA GAMES - Menu Principal* 🎮\n\n"
            "Choisissez un jeu pour obtenir des prédictions :\n\n"
            "🏆 *FIFA 4x4 Predictor*\n"
            "_Prédictions précises basées sur des statistiques réelles_\n\n"
            "🍎 *Apple of Fortune*\n"
            "_Trouvez la bonne pomme grâce à notre système prédictif_\n\n"
            "🃏 *Baccarat*\n"
            "_Anticipez le gagnant avec notre technologie d'analyse_"
        )
        
        # Boutons pour accéder aux différents jeux
        keyboard = [
            [InlineKeyboardButton("🏆 FIFA 4x4 Predictor", callback_data="game_fifa")],
            [InlineKeyboardButton("🍎 Apple of Fortune", callback_data="game_apple")],
            [InlineKeyboardButton("🃏 Baccarat", callback_data="game_baccarat")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message avec le menu
        if hasattr(message, 'edit_text'):
            await edit_message_queued(
                message=message,
                text=menu_text,
                reply_markup=reply_markup,
                parse_mode='Markdown',
                user_id=None
            )
        else:
            await send_message_queued(
                chat_id=message.chat_id,
                text=menu_text,
                reply_markup=reply_markup,
                parse_mode='Markdown',
                user_id=None
            )
            
    except Exception as e:
        # Log complet de l'erreur
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Erreur détaillée dans show_games_menu: {error_trace}")
        
        # Message d'erreur avec plus de détails
        error_message = f"Une erreur s'est produite lors du chargement du menu: {str(e)}"
        logger.error(error_message)
        
        try:
            await send_message_queued(
                chat_id=message.chat_id,
                text="Désolé, une erreur s'est produite lors du chargement du menu des jeux. Veuillez réessayer.",
                user_id=None
            )
        except Exception:
            logger.error("Impossible d'envoyer le message d'erreur")
