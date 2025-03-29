import logging
import asyncio
from typing import Optional, Callable, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
import time

# Utiliser le nouvel adaptateur de base de données
from database_adapter import check_user_subscription, has_completed_referrals, count_referrals, get_max_referrals
from admin_access import is_admin

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Système de gestion des requêtes API
_api_queue = []  # File d'attente des requêtes API
_api_processing = False  # Indique si le traitement de la file est en cours
_MAX_API_REQUESTS_PER_SECOND = 28  # Limite de requêtes par seconde

async def process_api_queue():
    """Traite la file d'attente des requêtes API Telegram en respectant les limites de débit"""
    global _api_processing
    
    if _api_processing:
        return  # Éviter les exécutions parallèles
    
    _api_processing = True
    
    try:
        while _api_queue:
            # Traiter 28 requêtes par seconde maximum
            batch = _api_queue[:_MAX_API_REQUESTS_PER_SECOND]
            _api_queue[:_MAX_API_REQUESTS_PER_SECOND] = []
            
            # Exécuter les requêtes de ce lot
            for func, args, kwargs, future in batch:
                try:
                    result = await func(*args, **kwargs)
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
            
            # Attendre 1 seconde avant le prochain lot
            if _api_queue:
                await asyncio.sleep(1)
    
    finally:
        _api_processing = False
        
        # S'il reste des requêtes, redémarrer le traitement
        if _api_queue:
            asyncio.create_task(process_api_queue())

async def queue_api_request(func, *args, **kwargs):
    """
    Ajoute une requête API à la file d'attente et retourne un future pour le résultat.
    
    Args:
        func: Fonction de l'API Telegram à appeler
        *args, **kwargs: Arguments pour la fonction
        
    Returns:
        Future: Future qui sera complété avec le résultat de la requête
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    
    # Ajouter à la file d'attente
    _api_queue.append((func, args, kwargs, future))
    
    # Démarrer le traitement s'il n'est pas déjà en cours
    if not _api_processing:
        asyncio.create_task(process_api_queue())
    
    # Calculer la position et le délai estimé
    position = len(_api_queue)
    estimated_seconds = (position / _MAX_API_REQUESTS_PER_SECOND) + 1
    
    # Si la requête est loin dans la file, informer l'utilisateur
    if position > _MAX_API_REQUESTS_PER_SECOND:
        # Chercher l'argument message ou update s'il existe
        message = None
        for arg in args:
            if hasattr(arg, 'message'):
                message = arg.message
                break
                elif hasattr(arg, 'effective_message'):
                message = arg.effective_message
                break
        
        # Si on a trouvé un message et que le délai est significatif (plus de 2 secondes)
        if message and estimated_seconds > 2:
            try:
                asyncio.create_task(
                    message.reply_text(
                        f"⏳ *File d'attente active*\n\n"
                        f"Votre requête est en position *{position}*.\n"
                        f"Temps d'attente estimé: *{estimated_seconds:.1f} secondes*\n\n"
                        f"Merci de votre patience! Nous traitons un maximum de {_MAX_API_REQUESTS_PER_SECOND} requêtes par seconde.",
                        parse_mode='Markdown'
                    )
                )
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi du message d'attente: {e}")
    
    return await future

# Vérification d'abonnement simplifiée
async def verify_subscription(message, user_id, username, context=None, edit=False) -> bool:
    """
    Vérifie si l'utilisateur est abonné au canal.
    Version optimisée avec moins d'animations et utilisation du cache.
    
    Args:
        message: Message Telegram (pour répondre)
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
            await message.edit_text(
                "🔑 *Accès administrateur*\n\n"
                "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text(
                "🔑 *Accès administrateur*\n\n"
                "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown'
            )
        return True
    
    # Message initial avec animation simplifiée (une seule étape)
    verify_text = "🔍 *Vérification de votre abonnement en cours...*"
    
    if edit and hasattr(message, 'edit_text'):
        msg = await message.edit_text(verify_text, parse_mode='Markdown')
    else:
        msg = await message.reply_text(verify_text, parse_mode='Markdown')
    
    # Effectuer la vérification avec le cache
    is_subscribed = await check_user_subscription(user_id)
    
    if is_subscribed:
        # Message de succès sans animation
        await msg.edit_text(
            "✅ *Abonnement vérifié!*\n\n"
            "Vous êtes bien abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Lancer la vérification du parrainage si le contexte est fourni
        if context:
            await verify_referral(message, user_id, username, context)
            
        return True
    else:
        # Message d'erreur sans animation
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
            [InlineKeyboardButton("🔍 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            "❌ *Abonnement non détecté*\n\n"
            "Vous n'êtes pas encore abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).\n\n"
            "*Instructions:*\n"
            "1️⃣ Cliquez sur le bouton 'Rejoindre le canal'\n"
            "2️⃣ Abonnez-vous au canal\n"
            "3️⃣ Revenez ici et cliquez sur 'Vérifier à nouveau'",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        return False

# Vérification de parrainage simplifiée
async def verify_referral(message, user_id, username, context=None, edit=False) -> bool:
    """
    Vérifie si l'utilisateur a complété ses parrainages.
    Version optimisée avec moins d'animations et utilisation du cache.
    
    Args:
        message: Message Telegram (pour répondre)
        user_id (int): ID de l'utilisateur
        username (str): Nom d'utilisateur
        context: Contexte de conversation Telegram (optionnel)
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        
    Returns:
        bool: True si l'utilisateur a complété ses parrainages ou est admin, False sinon
    """
    # Récupérer MAX_REFERRALS
    MAX_REFERRALS = await get_max_referrals()
    
    # Vérifier si c'est un admin
    if is_admin(user_id, username):
        if edit and hasattr(message, 'edit_text'):
            await message.edit_text(
                "🔑 *Accès administrateur*\n\n"
                "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text(
                "🔑 *Accès administrateur*\n\n"
                "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown'
            )
            
        # Créer un bouton direct pour chaque jeu
        keyboard = [
            [InlineKeyboardButton("🏆 FIFA 4x4 Predictor", callback_data="game_fifa")],
            [InlineKeyboardButton("🍎 Apple of Fortune", callback_data="game_apple")],
            [InlineKeyboardButton("🃏 Baccarat", callback_data="game_baccarat")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message avec boutons directs pour les administrateurs
        try:
            await message.reply_text(
                "🎮 *Menu des jeux disponibles*\n\n"
                "Sélectionnez un jeu pour commencer:",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage des boutons de jeu: {e}")
            
        return True
    
    # Message initial simplifié
    verify_text = "🔍 *Vérification de votre parrainage...*"
    
    if edit and hasattr(message, 'edit_text'):
        msg = await message.edit_text(verify_text, parse_mode='Markdown')
    else:
        msg = await message.reply_text(verify_text, parse_mode='Markdown')
    
    # Effectuer la vérification (utilise déjà le cache via has_completed_referrals)
    has_completed = await has_completed_referrals(user_id, username)
    
    if has_completed:
        # Message de succès sans animation
        await msg.edit_text(
            "✅ *Parrainage complété!*\n\n"
            f"Vous avez atteint votre objectif de {MAX_REFERRALS} parrainage(s).\n"
            "Toutes les fonctionnalités sont désormais débloquées.",
            parse_mode='Markdown'
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
            await message.reply_text(
                "🎮 *Menu des jeux disponibles*\n\n"
                "Sélectionnez un jeu pour commencer:",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage des boutons de jeu: {e}")
        
        return True
    else:
        # Obtenir le nombre actuel de parrainages
        referral_count = await count_referrals(user_id)
        
        # Message indiquant le nombre actuel de parrainages
        keyboard = [
            [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
            [InlineKeyboardButton("✅ Vérifier à nouveau", callback_data="verify_referral")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"⏳ *Parrainage en cours - {referral_count}/{MAX_REFERRALS}*\n\n"
            f"Vous avez actuellement {referral_count} parrainage(s) sur {MAX_REFERRALS} requis.\n\n"
            f"Partagez votre lien de parrainage pour débloquer toutes les fonctionnalités.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return False

# Message standard quand l'abonnement est requis
async def send_subscription_required(message) -> None:
    """Envoie un message indiquant que l'abonnement est nécessaire."""
    keyboard = [
        [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
        [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "⚠️ *Abonnement requis*\n\n"
        "Pour utiliser cette fonctionnalité, vous devez être abonné à notre canal.\n\n"
        "*Instructions:*\n"
        "1️⃣ Rejoignez [AL VE CAPITAL](https://t.me/alvecapitalofficiel)\n"
        "2️⃣ Cliquez sur '🔍 Vérifier mon abonnement'",
        reply_markup=reply_markup,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

# Message standard quand le parrainage est requis
async def send_referral_required(message) -> None:
    """Envoie un message indiquant que le parrainage est nécessaire."""
    MAX_REFERRALS = await get_max_referrals()
    
    keyboard = [
        [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
        [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "⚠️ *Parrainage requis*\n\n"
        f"Pour utiliser cette fonctionnalité, vous devez parrainer {MAX_REFERRALS} personne(s).\n\n"
        "Partagez votre lien de parrainage avec vos amis pour débloquer toutes les fonctionnalités.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Vérification complète avant d'accéder à une fonctionnalité
async def verify_all_requirements(user_id, username, message, context=None) -> bool:
    """
    Vérifie toutes les conditions d'accès (abonnement + parrainage).
    Version optimisée utilisant le cache.
    
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
    
    # Vérifier l'abonnement (avec cache)
    is_subscribed = await check_user_subscription(user_id)
    if not is_subscribed:
        await send_subscription_required(message)
        return False
    
    # Vérifier le parrainage (avec cache)
    has_completed = await has_completed_referrals(user_id, username)
    if not has_completed:
        await send_referral_required(message)
        return False
    
    return True

# Fonction pour afficher le menu principal des jeux
async def show_games_menu(message, context) -> None:
    """
    Affiche le menu principal avec tous les jeux disponibles.
    Version simplifiée et robuste pour éviter les erreurs.
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
            await message.edit_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await message.reply_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        # Log complet de l'erreur
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Erreur détaillée dans show_games_menu: {error_trace}")
        
        # Message d'erreur avec plus de détails
        error_message = f"Une erreur s'est produite lors du chargement du menu: {str(e)}"
        logger.error(error_message)
        
        try:
            await message.reply_text(
                "Désolé, une erreur s'est produite lors du chargement du menu des jeux. Veuillez réessayer."
            )
        except Exception:
            logger.error("Impossible d'envoyer le message d'erreur")
