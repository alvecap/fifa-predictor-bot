import logging
import re
import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

from config import TELEGRAM_TOKEN, WELCOME_MESSAGE, HELP_MESSAGE, TEAM_INPUT, ODDS_INPUT
from database_adapter import get_all_teams, save_prediction_log, check_user_subscription
from predictor import MatchPredictor, format_prediction_message
# Importer les fonctions du système de parrainage
from referral_system import (
    register_user, has_completed_referrals, generate_referral_link,
    count_referrals, get_referred_users, MAX_REFERRALS, get_referral_instructions
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialisation du prédicteur
predictor = MatchPredictor()

# États de conversation
VERIFY_SUBSCRIPTION = 1
TEAM_SELECTION = 2
ODDS_INPUT_TEAM1 = 3
ODDS_INPUT_TEAM2 = 4

# Constantes pour la pagination des équipes
TEAMS_PER_PAGE = 8

# File d'attente pour les requêtes API
_api_queue = []
_MAX_API_REQUESTS_PER_SECOND = 20  # Limite de requêtes API par seconde

# Cache global partagé pour réduire les requêtes API
_subscription_cache = {}  # {user_id: (timestamp, is_subscribed)}
_referral_cache = {}      # {user_id: (timestamp, count)}
_CACHE_DURATION = 300     # 5 minutes en secondes (réduit de 30 à 5 minutes)

# Fonctions de base
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message quand la commande /start est envoyée. Version optimisée."""
    user = update.effective_user
    user_id = user.id
    username = user.username
    context.user_data["username"] = username
    
    # Répondre IMMÉDIATEMENT avec un message simple pour confirmer que le bot fonctionne
    welcome_message = await update.message.reply_text(
        f"👋 *Bienvenue {username} sur FIFA 4x4 Predictor!*\n\n"
        "Je suis en train d'activer votre compte...",
        parse_mode='Markdown'
    )
    
    # Vérifier si l'utilisateur vient d'un lien de parrainage
    referrer_id = None
    if context.args and len(context.args) > 0 and context.args[0].startswith('ref'):
        try:
            referrer_id = int(context.args[0][3:])  # Extraire l'ID du parrain
            logger.info(f"User {user_id} came from referral link of user {referrer_id}")
        except (ValueError, IndexError):
            referrer_id = None
    
    # Enregistrer l'utilisateur en arrière-plan sans attendre le résultat
    asyncio.create_task(register_user(user_id, username, referrer_id))
    
    # Message de bienvenue complet avec boutons
    welcome_text = f"✅ *Compte activé!*\n\n"
    welcome_text += "🏆 Bienvenue sur *FIFA 4x4 Predictor*!\n\n"
    welcome_text += "⚠️ Pour utiliser toutes les fonctionnalités, vous devez être abonné "
    welcome_text += f"à notre canal [AL VE CAPITAL](https://t.me/alvecapitalofficiel)."
    
    # Vérifier si l'utilisateur a déjà complété son quota de parrainages (en arrière-plan)
    has_completed = False
    try:
        from admin_access import is_admin
        if is_admin(user_id, username):
            has_completed = True
        else:
            # Utiliser le cache si disponible
            user_id_str = str(user_id)
            current_time = time.time()
            if user_id_str in _referral_cache:
                timestamp, count = _referral_cache[user_id_str]
                if current_time - timestamp < _CACHE_DURATION:
                    has_completed = count >= MAX_REFERRALS
    except Exception as e:
        logger.error(f"Erreur lors de la vérification rapide du parrainage: {e}")
    
    # Créer les boutons
    buttons = [
        [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    
    # Ajouter un bouton pour obtenir le lien de parrainage si nécessaire
    if not has_completed:
        buttons.append([InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    # Mettre à jour le message précédent avec les informations complètes
    await welcome_message.edit_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message d'aide quand la commande /help est envoyée."""
    # Vérifier l'abonnement avant tout
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.effective_message)
        return
    
    # Vérifier aussi le parrainage
    has_completed = await has_completed_referrals(user_id)
    if not has_completed:
        await send_referral_required(update.effective_message)
        return
    
    help_text = "*🔮 FIFA 4x4 Predictor - Aide*\n\n"
    help_text += "*Commandes disponibles:*\n"
    help_text += "• `/start` - Démarrer le bot\n"
    help_text += "• `/help` - Afficher ce message d'aide\n"
    help_text += "• `/predict` - Commencer une prédiction\n"
    help_text += "• `/teams` - Voir toutes les équipes disponibles\n"
    help_text += "• `/check` - Vérifier votre abonnement\n"
    help_text += "• `/referral` - Gérer vos parrainages\n\n"
    help_text += "*Note:* Les cotes sont obligatoires pour obtenir des prédictions précises.\n\n"
    help_text += "Pour plus de détails, contactez l'administrateur du bot."
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les erreurs."""
    logger.error(f"Une erreur est survenue: {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur."
            )
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du message d'erreur: {e}")

# Animation de vérification d'abonnement - version optimisée
async def animated_subscription_check(message, user_id, context=None, edit=False) -> bool:
    """Effectue une vérification d'abonnement avec animation et retourne le résultat."""
    # Vérifier d'abord le cache
    user_id_str = str(user_id)
    current_time = time.time()
    
    if user_id_str in _subscription_cache:
        timestamp, is_subscribed = _subscription_cache[user_id_str]
        if current_time - timestamp < _CACHE_DURATION:
            logger.info(f"Utilisation du cache pour la vérification d'abonnement de l'utilisateur {user_id}")
            
            if is_subscribed:
                # Afficher juste un message simple si en cache
                if edit:
                    msg = await message.edit_text("✅ *Abonnement vérifié!*", parse_mode='Markdown')
                else:
                    msg = await message.reply_text("✅ *Abonnement vérifié!*", parse_mode='Markdown')
                
                # Lancer la suite avec un court délai
                if context:
                    # Vérifier aussi si le parrainage est en cache
                    has_completed = False
                    if user_id_str in _referral_cache:
                        ref_timestamp, ref_count = _referral_cache[user_id_str]
                        if current_time - ref_timestamp < _CACHE_DURATION:
                            has_completed = ref_count >= MAX_REFERRALS
                    
                    if has_completed:
                        # Si tout est déjà vérifié en cache, aller directement aux prédictions
                        keyboard = [
                            [InlineKeyboardButton("🏆 Sélectionner les équipes", callback_data="start_prediction")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await asyncio.sleep(0.5)
                        await message.reply_text(
                            "🔮 *Prêt pour une prédiction*\n\n"
                            "Cliquez sur le bouton ci-dessous pour commencer.",
                            reply_markup=reply_markup,
                            parse_mode='Markdown'
                        )
                    else:
                        # Vérifier le parrainage de manière traditionnelle
                        await verify_referral(message, user_id, context.user_data.get("username", ""), context)
                
                return True
            else:
                # Afficher le message d'erreur sans animation
                keyboard = [
                    [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
                    [InlineKeyboardButton("🔍 Vérifier à nouveau", callback_data="verify_subscription")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if edit:
                    await message.edit_text(
                        "❌ *Abonnement non détecté*\n\n"
                        "Vous n'êtes pas encore abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).",
                        reply_markup=reply_markup,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                else:
                    await message.reply_text(
                        "❌ *Abonnement non détecté*\n\n"
                        "Vous n'êtes pas encore abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).",
                        reply_markup=reply_markup,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                
                return False
    
    # Si pas en cache, faire la vérification avec animation réduite
    # Message initial
    verify_text = "🔍 *Vérification de votre abonnement*"
    
    if edit:
        msg = await message.edit_text(verify_text, parse_mode='Markdown')
    else:
        msg = await message.reply_text(verify_text, parse_mode='Markdown')
    
    # Animation stylisée (cercle qui tourne) - version réduite
    emojis = ["🕐", "🕔", "🕘", "🕛"]  # Réduit de 12 à 4 émojis
    
    for i in range(len(emojis)):
        await msg.edit_text(
            f"{emojis[i]} *Vérification de votre abonnement en cours...*",
            parse_mode='Markdown'
        )
        await asyncio.sleep(0.2)  # Animation rapide mais visible
    
    # Animation finale
    await msg.edit_text(
        "🔄 *Connexion avec Telegram...*",
        parse_mode='Markdown'
    )
    await asyncio.sleep(0.3)
    
    # Effectuer la vérification
    is_subscribed = await check_user_subscription(user_id)
    
    # Mettre en cache le résultat
    _subscription_cache[user_id_str] = (time.time(), is_subscribed)
    
    if is_subscribed:
        # Animation de succès réduite
        success_frames = [
            "⬜⬜⬜",
            "⬛⬜⬜",
            "⬛⬛⬜",
            "⬛⬛⬛",
            "✅ *Abonnement vérifié!*"
        ]
        
        for frame in success_frames:
            await msg.edit_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.1)  # Plus rapide
        
        # Message final de succès
        await msg.edit_text(
            "✅ *Abonnement vérifié!*\n\n"
            "Vous êtes bien abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).\n"
            "Toutes les fonctionnalités sont désormais accessibles.",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Lancer la sélection d'équipes après un court délai, seulement si le contexte est fourni
        if context:
            # Vérifier si l'utilisateur a complété son quota de parrainages
            has_completed = await has_completed_referrals(user_id)
            
            if not has_completed:
                # Si le parrainage n'est pas complété, afficher un message
                keyboard = [
                    [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
                    [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await asyncio.sleep(0.5)  # Délai réduit
                await message.reply_text(
                    "⚠️ *Parrainage requis*\n\n"
                    f"Pour accéder aux prédictions, vous devez parrainer {MAX_REFERRALS} personne(s).\n\n"
                    "Partagez votre lien de parrainage avec vos amis.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                keyboard = [
                    [InlineKeyboardButton("🏆 Sélectionner les équipes", callback_data="start_prediction")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Envoyer un nouveau message avec le bouton de sélection
                await asyncio.sleep(0.5)  # Délai réduit
                await message.reply_text(
                    "🔮 *Prêt pour une prédiction*\n\n"
                    "Cliquez sur le bouton ci-dessous pour commencer.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
        return True
    else:
        # Animation d'échec réduite
        error_frames = [
            "⬜⬜⬜",
            "⬛⬜⬜",
            "⬛⬛⬜",
            "⬛⬛⬛",
            "❌ *Abonnement non détecté*"
        ]
        
        for frame in error_frames:
            await msg.edit_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.1)  # Plus rapide
        
        # Message d'erreur
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

# Animation de vérification de parrainage - version optimisée
async def verify_referral(message, user_id, username=None, context=None, edit=False) -> bool:
    """Effectue une vérification de parrainage avec animation et retourne le résultat."""
    # Vérifier d'abord le cache
    user_id_str = str(user_id)
    current_time = time.time()
    
    if user_id_str in _referral_cache:
        timestamp, referral_count = _referral_cache[user_id_str]
        if current_time - timestamp < _CACHE_DURATION:
            logger.info(f"Utilisation du cache pour la vérification de parrainage de l'utilisateur {user_id}")
            
            has_completed = referral_count >= MAX_REFERRALS
            
            if has_completed:
                # Afficher juste un message simple si en cache
                if edit:
                    msg = await message.edit_text("✅ *Parrainage complété!*", parse_mode='Markdown')
                else:
                    msg = await message.reply_text("✅ *Parrainage complété!*", parse_mode='Markdown')
                
                # Bouton pour commencer une prédiction
                keyboard = [
                    [InlineKeyboardButton("🏆 Faire une prédiction", callback_data="start_prediction")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await asyncio.sleep(0.3)
                await message.reply_text(
                    "🔮 *Prêt pour une prédiction*\n\n"
                    "Vous pouvez maintenant faire des prédictions!",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
                return True
            else:
                # Afficher le message d'erreur sans animation
                keyboard = [
                    [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
                    [InlineKeyboardButton("✅ Vérifier à nouveau", callback_data="verify_referral")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if edit:
                    await message.edit_text(
                        f"⏳ *Parrainage en cours - {referral_count}/{MAX_REFERRALS}*\n\n"
                        f"Vous avez actuellement {referral_count} parrainage(s) sur {MAX_REFERRALS} requis.\n\n"
                        f"Partagez votre lien de parrainage pour débloquer toutes les fonctionnalités.",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    await message.reply_text(
                        f"⏳ *Parrainage en cours - {referral_count}/{MAX_REFERRALS}*\n\n"
                        f"Vous avez actuellement {referral_count} parrainage(s) sur {MAX_REFERRALS} requis.\n\n"
                        f"Partagez votre lien de parrainage pour débloquer toutes les fonctionnalités.",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                
                return False
    
    # Vérifier si c'est un admin (bypass complet)
    try:
        from admin_access import is_admin
        if is_admin(user_id, username):
            keyboard = [
                [InlineKeyboardButton("🏆 Faire une prédiction", callback_data="start_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if edit:
                await message.edit_text(
                    "🔑 *Accès administrateur*\n\n"
                    "Toutes les fonctionnalités sont débloquées.",
                    parse_mode='Markdown'
                )
            else:
                await message.reply_text(
                    "🔑 *Accès administrateur*\n\n"
                    "Toutes les fonctionnalités sont débloquées.",
                    parse_mode='Markdown'
                )
            
            await asyncio.sleep(0.3)
            await message.reply_text(
                "🔮 *Prêt pour une prédiction*\n\n"
                "Vous pouvez maintenant faire des prédictions!",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            return True
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut admin: {e}")
    
    # Si pas en cache ni admin, faire la vérification avec animation réduite
    # Message initial
    verify_text = "🔍 *Vérification de votre parrainage*"
    
    if edit:
        msg = await message.edit_text(verify_text, parse_mode='Markdown')
    else:
        msg = await message.reply_text(verify_text, parse_mode='Markdown')
    
    # Animation stylisée (cercle qui tourne) - version réduite
    emojis = ["🕐", "🕔", "🕘", "🕛"]  # Réduit de 12 à 4 émojis
    
    for i in range(len(emojis)):
        await msg.edit_text(
            f"{emojis[i]} *Vérification de vos parrainages en cours...*",
            parse_mode='Markdown'
        )
        await asyncio.sleep(0.2)  # Animation rapide mais visible
    
    # Pause pour effet - mais plus courte
    await msg.edit_text(
        "🔄 *Analyse des données...*",
        parse_mode='Markdown'
    )
    await asyncio.sleep(0.3)
    
    # Animation plus longue - mais réduite
    check_frames = [
        "📊 *Recherche de vos filleuls...*",
        "👥 *Comptage des parrainages...*"
    ]
    
    for frame in check_frames:
        await msg.edit_text(frame, parse_mode='Markdown')
        await asyncio.sleep(0.3)  # Plus rapide
    
    # Effectuer la vérification
    # Effectuer la vérification
    referral_count = await count_referrals(user_id)
    has_completed = referral_count >= MAX_REFERRALS
    
    # Mettre en cache le résultat
    _referral_cache[user_id_str] = (time.time(), referral_count)
    
    if has_completed:
        # Animation de succès réduite
        success_frames = [
            "⬜⬜⬜",
            "⬛⬜⬜",
            "⬛⬛⬜",
            "⬛⬛⬛",
            "✅ *Parrainage complété!*"
        ]
        
        for frame in success_frames:
            await msg.edit_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.1)  # Plus rapide
        
        # Message final de succès
        await msg.edit_text(
            "✅ *Parrainage complété!*\n\n"
            f"Vous avez atteint votre objectif de {MAX_REFERRALS} parrainage(s).\n"
            "Toutes les fonctionnalités sont désormais débloquées.",
            parse_mode='Markdown'
        )
        
        # Ajouter bouton pour commencer une prédiction
        if context:
            keyboard = [
                [InlineKeyboardButton("🏆 Faire une prédiction", callback_data="start_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await asyncio.sleep(0.5)  # Délai réduit
            await message.reply_text(
                "🔮 *Prêt pour une prédiction*\n\n"
                "Vous pouvez maintenant faire des prédictions!",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        return True
    else:
        # Animation d'échec réduite
        error_frames = [
            "⬜⬜⬜",
            "⬛⬜⬜",
            "⬛⬛⬜",
            "⬛⬛⬛",
            "⏳ *Parrainage en cours*"
        ]
        
        for frame in error_frames:
            await msg.edit_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.1)  # Plus rapide
        
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

# Commande pour vérifier l'abonnement au canal
async def check_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie si l'utilisateur est abonné au canal @alvecapitalofficiel."""
    user_id = update.effective_user.id
    context.user_data["user_id"] = user_id
    
    # Utiliser l'animation de vérification
    await animated_subscription_check(update.message, user_id, context)

# Commande pour gérer les parrainages
async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les parrainages de l'utilisateur."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Vérifier l'abonnement d'abord
    is_subscribed = await check_user_subscription(user_id)
    if not is_subscribed:
        await send_subscription_required(update.message)
        return
    
    # S'assurer que l'utilisateur est enregistré
    await register_user(user_id, username)
    
    # Obtenir les statistiques de parrainage (en utilisant le cache si possible)
    referral_count = await count_referrals(user_id)
    has_completed = referral_count >= MAX_REFERRALS
    referred_users = await get_referred_users(user_id)
    
    # Générer un lien de parrainage
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    referral_link = await generate_referral_link(user_id, bot_username)
    
    # Créer le message
    message_text = "👥 *Système de Parrainage FIFA 4x4 Predictor*\n\n"
    
    if has_completed:
        message_text += "✅ *Statut: Parrainage complété*\n"
        message_text += f"Vous avez parrainé {referral_count}/{MAX_REFERRALS} personne(s) requise(s).\n"
        message_text += "Toutes les fonctionnalités sont débloquées!\n\n"
    else:
        message_text += "⏳ *Statut: Parrainage en cours*\n"
        message_text += f"Progression: {referral_count}/{MAX_REFERRALS} personne(s) parrainée(s).\n"
        message_text += f"Parrainez encore {MAX_REFERRALS - referral_count} personne(s) pour débloquer toutes les fonctionnalités.\n\n"
    
    message_text += "*Votre lien de parrainage:*\n"
    message_text += f"`{referral_link}`\n\n"
    
    # Utiliser une version simplifiée des instructions de parrainage pour les nouveaux utilisateurs
    # Plus courte, moins de requêtes API
    message_text += "__Conditions de parrainage:__\n" 
    message_text += "• L'invité doit cliquer sur votre lien\n"
    message_text += "• L'invité doit s'abonner au canal\n"
    message_text += "• L'invité doit démarrer le bot\n\n"
    
    # Ajouter la liste des utilisateurs parrainés
    if referred_users:
        message_text += "\n*Utilisateurs que vous avez parrainés:*\n"
        for user in referred_users:
            user_username = user.get('username', 'Inconnu')
            is_verified = "✅" if user.get('is_verified', False) else "⏳"
            message_text += f"• {is_verified} {user_username}\n"
    
    # Créer les boutons
    buttons = [
        [InlineKeyboardButton("🔗 Copier le lien", callback_data="copy_referral_link")]
    ]
    
    if not has_completed:
        buttons.append([InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        message_text,
        parse_mode='Markdown',
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

# Lancer une prédiction directement avec la commande predict
async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance le processus de prédiction quand la commande /predict est envoyée."""
    user_id = update.effective_user.id
    context.user_data["user_id"] = user_id
    
    # Vérifier l'abonnement via le cache si possible
    user_id_str = str(user_id)
    current_time = time.time()
    
    if user_id_str in _subscription_cache:
        timestamp, is_subscribed = _subscription_cache[user_id_str]
        if current_time - timestamp < _CACHE_DURATION:
            if not is_subscribed:
                await send_subscription_required(update.message)
                return
                
            # Vérifier aussi le parrainage via le cache si possible
            if user_id_str in _referral_cache:
                ref_timestamp, ref_count = _referral_cache[user_id_str]
                if current_time - ref_timestamp < _CACHE_DURATION:
                    has_completed = ref_count >= MAX_REFERRALS
                    
                    if not has_completed:
                        await send_referral_required(update.message)
                        return
                    
                    # Si tout est vérifié en cache, aller directement aux prédictions
                    keyboard = [
                        [InlineKeyboardButton("🏆 Sélectionner les équipes", callback_data="start_prediction")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await update.message.reply_text(
                        "🔮 *Prêt pour une prédiction*\n\n"
                        "Cliquez sur le bouton ci-dessous pour commencer.",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    return
    
    # Sinon, utiliser la méthode standard avec les vérifications 
    # Vérifier l'abonnement
    is_subscribed = await check_user_subscription(user_id)
    if not is_subscribed:
        await send_subscription_required(update.message)
        return
    
    # Vérifier aussi le parrainage
    has_completed = await has_completed_referrals(user_id)
    if not has_completed:
        await send_referral_required(update.message)
        return
    
    # Maintenant que les vérifications sont passées, utiliser l'animation de vérification avec le contexte
    await animated_subscription_check(update.message, user_id, context)

# Gestionnaire des boutons de callback optimisé
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les clics sur les boutons inline. Version optimisée avec file d'attente et cache."""
    query = update.callback_query
    await query.answer()  # Répondre immédiatement au callback pour éviter le "chargement" sur l'interface
    
    # Récupérer les données utilisateur
    user_id = query.from_user.id
    context.user_data["user_id"] = user_id
    context.user_data["username"] = query.from_user.username
    
    # Extraire le type de callback
    callback_data = query.data
    
    # Vérifier le niveau de charge actuel du système
    current_load = len(_api_queue)
    system_load = get_system_load_status(current_load)
    
    # Si la charge est critique, informer les utilisateurs non-admin de patienter
    if system_load == "critical" and not is_admin(user_id, query.from_user.username):
        estimated_wait = max(5, current_load / _MAX_API_REQUESTS_PER_SECOND)
        await query.message.reply_text(
            f"⚠️ *Système actuellement très sollicité*\n\n"
            f"Temps d'attente estimé: *{estimated_wait:.1f} secondes*\n"
            f"Merci de votre patience!",
            parse_mode='Markdown'
        )
    
    # Gestion optimisée de la file d'attente pour les requêtes API
    queue_position = current_load
    if queue_position > _MAX_API_REQUESTS_PER_SECOND * 2:  # Seuil doublé
        # Économiser une requête en ne notifiant que si l'attente est significative (>3s)
        estimated_wait = queue_position / _MAX_API_REQUESTS_PER_SECOND
        if estimated_wait > 3:
            await query.message.reply_text(
                f"⏳ *File d'attente active*\n\n"
                f"Position: *{queue_position}*\n"
                f"Temps d'attente estimé: *{estimated_wait:.1f} secondes*\n\n"
                f"Merci de votre patience!",
                parse_mode='Markdown'
            )
    
    # Utiliser le cache pour éviter les vérifications redondantes
    if callback_data in ["verify_subscription", "verify_referral", "start_prediction"]:
        # Vérifier l'horodatage de la dernière vérification
        last_verified = context.user_data.get("last_verified", 0)
        current_time = time.time()
        
        # Si la vérification a été faite récemment (moins de 5 minutes), utiliser le résultat en cache
        if current_time - last_verified < 300:  # 5 minutes
            subscription_status = context.user_data.get("subscription_status", False)
            referral_status = context.user_data.get("referral_status", False)
            
            # Traiter en fonction du type de callback et du statut en cache
            if callback_data == "verify_subscription":
                if subscription_status:
                    await handle_subscription_success(query.message, user_id, context, edit=True)
                    return
                else:
                    await handle_subscription_failure(query.message, edit=True)
                    return
            
            elif callback_data == "verify_referral" and subscription_status:
                if referral_status:
                    await handle_referral_success(query.message, user_id, context, edit=True)
                    return
                else:
                    await handle_referral_failure(query.message, user_id, context, edit=True)
                    return
            
            elif callback_data == "start_prediction":
                if subscription_status and referral_status:
                    await start_team_selection(query.message, context, edit=True)
                    return
                elif not subscription_status:
                    await send_subscription_required_lite(query.message, edit=True)
                    return
                else:
                    await send_referral_required_lite(query.message, edit=True)
                    return
    
    # Traiter les différents types de callbacks
    if callback_data == "verify_subscription":
        # Utiliser une version simplifiée pour économiser des requêtes
        await animated_subscription_check(query.message, user_id, context, edit=True)
    
    elif callback_data == "verify_referral":
        # Utiliser une version simplifiée
        await verify_referral(query.message, user_id, query.from_user.username, context, edit=True)
    
    elif callback_data == "get_referral_link":
        # Utiliser la fonction optimisée
        await process_referral_link_request(query, user_id, context)
    
    elif callback_data == "copy_referral_link":
        # Telegram gère automatiquement la copie
        await query.answer("Lien copié dans le presse-papier!")
    
    elif callback_data == "start_prediction":
        # Vérifier l'abonnement avant de lancer la prédiction (utilise le cache)
        is_subscribed = await check_user_subscription(user_id)
        
        if not is_subscribed:
            # Message d'erreur si l'abonnement n'est plus actif
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
                [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ *Abonnement requis*\n\n"
                "Votre abonnement à [AL VE CAPITAL](https://t.me/alvecapitalofficiel) n'est pas actif.\n"
                "Vous devez être abonné pour utiliser cette fonctionnalité.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
            
        # Vérifier aussi le parrainage (utilise le cache)
        has_completed = await has_completed_referrals(user_id, query.from_user.username)
        if not has_completed:
            # Message d'erreur si le parrainage n'est pas complété
            keyboard = [
                [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
                [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ *Parrainage requis*\n\n"
                f"Pour accéder aux prédictions, vous devez parrainer {MAX_REFERRALS} personne(s).\n\n"
                "Cliquez sur le bouton ci-dessous pour obtenir votre lien de parrainage.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Lancer la sélection des équipes
        await start_team_selection(query.message, context, edit=True)

# Fonction auxiliaire pour le traitement des liens de parrainage
async def process_referral_link_request(query, user_id, context):
    """Traite la demande de lien de parrainage de manière optimisée"""
    try:
        # Générer lien de parrainage
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
        referral_link = await generate_referral_link(user_id, bot_username)
        
        # Obtenir le nombre actuel de parrainages (utilise le cache)
        referral_count = await count_referrals(user_id)
        max_referrals = await get_max_referrals()
        
        # Créer les boutons
        keyboard = [
            [InlineKeyboardButton("🔗 Copier le lien", callback_data="copy_referral_link")],
            [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message avec les instructions de parrainage
        from referral_system import get_referral_instructions
        message_text = f"🔗 *Votre lien de parrainage:*\n\n`{referral_link}`\n\n"
        message_text += f"_Progression: {referral_count}/{max_referrals} parrainage(s)_\n\n"
        message_text += get_referral_instructions()
        
        await query.edit_message_text(
            message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Erreur lors du traitement du lien de parrainage: {e}")
        await query.edit_message_text(
            "Désolé, une erreur s'est produite lors de la génération de votre lien de parrainage. Veuillez réessayer.",
            parse_mode='Markdown'
        )

# Fonctions auxiliaires pour gérer les résultats des vérifications
async def handle_subscription_success(message, user_id, context, edit=True):
    """Gère le succès de la vérification d'abonnement sans animations"""
    # Mettre à jour le cache
    context.user_data["subscription_status"] = True
    context.user_data["last_verified"] = time.time()
    
    # Message de succès simple
    if edit:
        await message.edit_text(
            "✅ *Abonnement vérifié!*\n\n"
            "Vous êtes bien abonné à notre canal officiel.",
            parse_mode='Markdown'
        )
    else:
        await message.reply_text(
            "✅ *Abonnement vérifié!*\n\n"
            "Vous êtes bien abonné à notre canal officiel.",
            parse_mode='Markdown'
        )
    
    # Vérifier maintenant le parrainage si nécessaire
    await verify_referral(message, user_id, context.user_data.get("username", ""), context)

async def handle_subscription_failure(message, edit=True):
    """Gère l'échec de la vérification d'abonnement sans animations"""
    # Boutons standards
    keyboard = [
        [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
        [InlineKeyboardButton("🔍 Vérifier à nouveau", callback_data="verify_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Message d'erreur simple
    if edit:
        await message.edit_text(
            "❌ *Abonnement non détecté*\n\n"
            "Vous n'êtes pas encore abonné à notre canal officiel.\n"
            "Rejoignez le canal puis vérifiez à nouveau.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await message.reply_text(
            "❌ *Abonnement non détecté*\n\n"
            "Vous n'êtes pas encore abonné à notre canal officiel.\n"
            "Rejoignez le canal puis vérifiez à nouveau.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def handle_referral_success(message, user_id, context, edit=True):
    """Gère le succès de la vérification de parrainage sans animations"""
    # Mettre à jour le cache
    context.user_data["referral_status"] = True
    context.user_data["last_verified"] = time.time()
    
    # Message simplifié
    if edit:
        await message.edit_text(
            "✅ *Parrainage complété!*\n\n"
            "Vous pouvez maintenant accéder à toutes les fonctionnalités.",
            parse_mode='Markdown'
        )
    else:
        await message.reply_text(
            "✅ *Parrainage complété!*\n\n"
            "Vous pouvez maintenant accéder à toutes les fonctionnalités.",
            parse_mode='Markdown'
        )
    
    # Bouton pour commencer une prédiction
    keyboard = [
        [InlineKeyboardButton("🏆 Faire une prédiction", callback_data="start_prediction")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Envoyer un nouveau message avec le bouton
    await message.reply_text(
        "🔮 *Prêt pour une prédiction*\n\n"
        "Vous pouvez maintenant faire des prédictions!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_referral_failure(message, user_id, context, edit=True):
    """Gère l'échec de la vérification de parrainage sans animations"""
    # Obtenir le nombre actuel de parrainages
    from database_adapter import count_referrals_lite, get_max_referrals
    referral_count = await count_referrals_lite(user_id)
    max_referrals = await get_max_referrals()
    
    # Boutons standards
    keyboard = [
        [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
        [InlineKeyboardButton("✅ Vérifier à nouveau", callback_data="verify_referral")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Message d'erreur simplifié
    if edit:
        await message.edit_text(
            f"⏳ *Parrainage en cours - {referral_count}/{max_referrals}*\n\n"
            f"Partagez votre lien de parrainage pour débloquer toutes les fonctionnalités.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await message.reply_text(
            f"⏳ *Parrainage en cours - {referral_count}/{max_referrals}*\n\n"
            f"Partagez votre lien de parrainage pour débloquer toutes les fonctionnalités.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# Messages standards simplifiés pour économiser des requêtes
async def send_subscription_required_lite(message, edit=False):
    """Version légère du message d'abonnement requis"""
    keyboard = [
        [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
        [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "⚠️ *Abonnement requis* - Rejoignez notre canal officiel."
    
    if edit and hasattr(message, 'edit_text'):
        await message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def send_referral_required_lite(message, edit=False):
    """Version légère du message de parrainage requis"""
    keyboard = [
        [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
        [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"⚠️ *Parrainage requis* - Parrainez {MAX_REFERRALS} personne(s)."
    
    if edit and hasattr(message, 'edit_text'):
        await message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Fonction pour évaluer la charge du système
def get_system_load_status(queue_length):
    """Évalue la charge du système en fonction de la file d'attente"""
    if queue_length <= _MAX_API_REQUESTS_PER_SECOND:
        return "normal"
    elif queue_length <= _MAX_API_REQUESTS_PER_SECOND * 2:
        return "high"
    else:
        return "critical"

# Fonction pour démarrer la sélection des équipes (première équipe)
async def start_team_selection(message, context, edit=False, page=0) -> None:
    """Affiche la première page de sélection d'équipe."""
    try:
        context.user_data["selecting_team1"] = True
        await show_teams_page(message, context, page, edit, is_team1=True)
    except Exception as e:
        logger.error(f"Erreur lors du démarrage de la sélection d'équipes: {e}")
        if edit:
            await message.edit_text(
                "Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text(
                "Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur.",
                parse_mode='Markdown'
            )

# Fonction pour afficher une page d'équipes
async def show_teams_page(message, context, page=0, edit=False, is_team1=True) -> None:
    """Affiche une page de la liste des équipes."""
    teams = get_all_teams()
    
    # Calculer le nombre total de pages
    total_pages = (len(teams) + TEAMS_PER_PAGE - 1) // TEAMS_PER_PAGE
    
    # S'assurer que la page est valide
    page = max(0, min(page, total_pages - 1))
    
    # Obtenir les équipes pour cette page
    start_idx = page * TEAMS_PER_PAGE
    end_idx = min(start_idx + TEAMS_PER_PAGE, len(teams))
    page_teams = teams[start_idx:end_idx]
    
    # Créer les boutons pour les équipes
    team_buttons = []
    row = []
    
    callback_prefix = "select_team1_" if is_team1 else "select_team2_"
    
    for i, team in enumerate(page_teams):
        row.append(InlineKeyboardButton(team, callback_data=f"{callback_prefix}{team}"))
        if len(row) == 2 or i == len(page_teams) - 1:
            team_buttons.append(row)
            row = []
    
    # Ajouter les boutons de navigation
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Précédent", callback_data=f"teams_page_{page-1}"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Suivant ▶️", callback_data=f"teams_page_{page+1}"))
    
    if nav_buttons:
        team_buttons.append(nav_buttons)
    
    # Ajouter bouton pour revenir en arrière si nécessaire
    if not is_team1:
        team_buttons.append([InlineKeyboardButton("◀️ Retour", callback_data="start_prediction")])
    
    reply_markup = InlineKeyboardMarkup(team_buttons)
    
    # Texte du message
    team_type = "première" if is_team1 else "deuxième"
    text = (
        f"🏆 *Sélection des équipes* (Page {page+1}/{total_pages})\n\n"
        f"Veuillez sélectionner la *{team_type} équipe* pour votre prédiction:"
    )
    
    try:
        if edit:
            await message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Erreur lors de l'affichage des équipes: {e}")
        if edit:
            await message.edit_text(
                "Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text(
                "Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur.",
                parse_mode='Markdown'
            )

# Fonction pour démarrer la sélection de la deuxième équipe
async def start_team2_selection(message, context, edit=False, page=0) -> None:
    """Affiche les options de sélection pour la deuxième équipe."""
    team1 = context.user_data.get("team1", "")
    
    if not team1:
        if edit:
            await message.edit_text(
                "❌ *Erreur*\n\nVeuillez d'abord sélectionner la première équipe.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text(
                "❌ *Erreur*\n\nVeuillez d'abord sélectionner la première équipe.",
                parse_mode='Markdown'
            )
        return
    
    # Afficher la page de sélection de la deuxième équipe
    await show_teams_page(message, context, page, edit, is_team1=False)

# Gestionnaire pour la saisie de la cote de l'équipe 1
async def handle_odds_team1_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gère la saisie de la cote pour la première équipe."""
    if not context.user_data.get("awaiting_odds_team1", False):
        return ConversationHandler.END
    
    # Vérifier l'abonnement avant de traiter
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
        return ConversationHandler.END
    
    # Vérifier le parrainage avant de traiter
    has_completed = await has_completed_referrals(user_id)
    if not has_completed:
        await send_referral_required(update.message)
        return ConversationHandler.END
    
    user_input = update.message.text.strip()
    team1 = context.user_data.get("team1", "")
    team2 = context.user_data.get("team2", "")
    
    # Extraire la cote
    try:
        odds1 = float(user_input.replace(",", "."))
        
        # Vérifier que la cote est valide
        if odds1 < 1.01:
            await update.message.reply_text(
                "❌ *Valeur de cote invalide*\n\n"
                "La cote doit être supérieure à 1.01.",
                parse_mode='Markdown'
            )
            return ODDS_INPUT_TEAM1
        
        # Sauvegarder la cote
        context.user_data["odds1"] = odds1
        context.user_data["awaiting_odds_team1"] = False
        
        # Animation de validation de la cote - version simplifiée
        loading_message = await update.message.reply_text(
            f"✅ Cote de *{team1}* enregistrée: *{odds1}*",
            parse_mode='Markdown'
        )
        
        # Demander la cote de l'équipe 2
        await asyncio.sleep(0.3)  # Délai réduit
        await loading_message.edit_text(
            f"💰 *Saisie des cotes (obligatoire)*\n\n"
            f"Match: *{team1}* vs *{team2}*\n\n"
            f"Veuillez maintenant saisir la cote pour *{team2}*\n\n"
            f"_Exemple: 2.35_",
            parse_mode='Markdown'
        )
        
        # Passer à l'attente de la cote de l'équipe 2
        context.user_data["awaiting_odds_team2"] = True
        
        return ODDS_INPUT_TEAM2
    except ValueError:
        await update.message.reply_text(
            "❌ *Format incorrect*\n\n"
            f"Veuillez saisir uniquement la valeur numérique de la cote pour *{team1}*.\n\n"
            "Exemple: `1.85`",
            parse_mode='Markdown'
        )
        return ODDS_INPUT_TEAM1

# Gestionnaire pour la saisie de la cote de l'équipe 2
async def handle_odds_team2_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gère la saisie de la cote pour la deuxième équipe."""
    if not context.user_data.get("awaiting_odds_team2", False):
        return ConversationHandler.END
    
    # Vérifier l'abonnement avant de traiter
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
        return ConversationHandler.END
    
    # Vérifier le parrainage avant de traiter
    has_completed = await has_completed_referrals(user_id)
    if not has_completed:
        await send_referral_required(update.message)
        return ConversationHandler.END
    
    user_input = update.message.text.strip()
    team1 = context.user_data.get("team1", "")
    team2 = context.user_data.get("team2", "")
    odds1 = context.user_data.get("odds1", 0)
    
    # Extraire la cote
    try:
        odds2 = float(user_input.replace(",", "."))
        
        # Vérifier que la cote est valide
        if odds2 < 1.01:
            await update.message.reply_text(
                "❌ *Valeur de cote invalide*\n\n"
                "La cote doit être supérieure à 1.01.",
                parse_mode='Markdown'
            )
            return ODDS_INPUT_TEAM2
        
        # Sauvegarder la cote
        context.user_data["odds2"] = odds2
        context.user_data["awaiting_odds_team2"] = False
        
        # Animation de validation de la cote - version simplifiée
        loading_message = await update.message.reply_text(
            f"✅ Cote de *{team2}* enregistrée: *{odds2}*",
            parse_mode='Markdown'
        )
        
        # Animation de génération de prédiction - version optimisée
        await asyncio.sleep(0.3)  # Délai réduit
        await loading_message.edit_text(
            "🧠 *Analyse des données en cours...*",
            parse_mode='Markdown'
        )
        
        # Animation stylisée réduite 
        analysis_frames = [
            "📊 *Analyse des performances historiques...*",
            "⚽ *Calcul des probabilités de scores...*"
        ]
        
        for frame in analysis_frames:
            await asyncio.sleep(0.5)  # Animation plus rapide
            await loading_message.edit_text(frame, parse_mode='Markdown')
        
        # Génération de la prédiction
        try:
            # Ajouter à la file d'attente API
            _api_queue.append(time.time())
            
            prediction = predictor.predict_match(team1, team2, odds1, odds2)
            
            # Retirer de la file d'attente API
            if _api_queue:
                _api_queue.pop(0)
            
            if not prediction or "error" in prediction:
                error_msg = prediction.get("error", "Erreur inconnue") if prediction else "Impossible de générer une prédiction"
                
                # Proposer de réessayer
                keyboard = [
                    [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await loading_message.edit_text(
                    f"❌ *Erreur de prédiction*\n\n"
                    f"{error_msg}\n\n"
                    f"Veuillez essayer avec d'autres équipes.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
            
            # Formater et envoyer la prédiction
            prediction_text = format_prediction_message(prediction)
            
            # Animation finale avant d'afficher le résultat - version réduite
            await asyncio.sleep(0.3)  # Délai réduit
            await loading_message.edit_text("✨ *Affichage des résultats...*", parse_mode='Markdown')
            
            # Proposer une nouvelle prédiction
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await loading_message.edit_text(
                prediction_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            # Enregistrer la prédiction dans les logs (en arrière-plan pour ne pas bloquer)
            user_id = context.user_data.get("user_id", update.message.from_user.id)
            username = context.user_data.get("username", update.message.from_user.username)
            
            asyncio.create_task(save_prediction_log(
                user_id=user_id,
                username=username,
                team1=team1,
                team2=team2,
                odds1=odds1,
                odds2=odds2,
                prediction_result=prediction
            ))
            
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Erreur lors de la génération de la prédiction: {e}")
            
            # Proposer de réessayer en cas d'erreur
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await loading_message.edit_text(
                "❌ *Une erreur s'est produite lors de la génération de la prédiction*\n\n"
                "Veuillez réessayer avec d'autres équipes ou contacter l'administrateur.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ *Format incorrect*\n\n"
            f"Veuillez saisir uniquement la valeur numérique de la cote pour *{team2}*.\n\n"
            "Exemple: `2.35`",
            parse_mode='Markdown'
        )
        return ODDS_INPUT_TEAM2

# Fonction pour lister les équipes disponibles
async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des équipes disponibles dans la base de données."""
    # Vérifier l'abonnement avant de traiter
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
        return
    
    # Vérifier le parrainage avant de traiter
    has_completed = await has_completed_referrals(user_id)
    if not has_completed:
        await send_referral_required(update.message)
        return
    
    # Récupérer la liste des équipes
    teams = get_all_teams()
    
    if not teams:
        await update.message.reply_text("Aucune équipe n'a été trouvée dans la base de données.")
        return
    
    # Formater la liste des équipes de manière plus concise pour économiser des messages
    teams_text = "📋 *Équipes disponibles:*\n\n"
    
    # Grouper les équipes sans trop de formatage pour réduire la taille
    teams_by_letter = {}
    for team in teams:
        first_letter = team[0].upper()
        if first_letter not in teams_by_letter:
            teams_by_letter[first_letter] = []
        teams_by_letter[first_letter].append(team)
    
    # Ajouter chaque groupe d'équipes
    for letter in sorted(teams_by_letter.keys()):
        teams_text += f"*{letter}*: "
        teams_text += ", ".join(sorted(teams_by_letter[letter]))
        teams_text += "\n\n"
    
    # Si le message est trop long, diviser en plusieurs messages
    if len(teams_text) > 4000:
        chunks = [teams_text[i:i+4000] for i in range(0, len(teams_text), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode='Markdown')
    else:
        await update.message.reply_text(teams_text, parse_mode='Markdown')

# Gérer les messages directs
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Répond aux messages qui ne sont pas des commandes."""
    # Si l'utilisateur attend des cotes pour une équipe
    if context.user_data.get("awaiting_odds_team1", False):
        return await handle_odds_team1_input(update, context)
    
    if context.user_data.get("awaiting_odds_team2", False):
        return await handle_odds_team2_input(update, context)
    
    # Vérifier l'abonnement avant de traiter
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
        return
    
    message_text = update.message.text.strip()
    
    # Rechercher si le message ressemble à une demande de prédiction
    if " vs " in message_text or " contre " in message_text:
        # Vérifier le parrainage
        has_completed = await has_completed_referrals(user_id)
        if not has_completed:
            await send_referral_required(update.message)
            return
            
        # Informer l'utilisateur d'utiliser la méthode interactive
        keyboard = [
            [InlineKeyboardButton("🔮 Faire une prédiction", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "ℹ️ *Nouvelle méthode de prédiction*\n\n"
            "Pour une expérience améliorée, veuillez utiliser notre système interactif de prédiction.\n\n"
            "Cliquez sur le bouton ci-dessous pour commencer une prédiction guidée avec sélection d'équipes et cotes obligatoires.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Message par défaut si aucune action n'est déclenchée
    await update.message.reply_text(
        "Je ne comprends pas cette commande. Utilisez /help pour voir les commandes disponibles."
    )

# Fonction principale
def main() -> None:
    """Démarre le bot."""
    try:
        # Créer l'application
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Ajouter les gestionnaires de commandes
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("predict", predict_command))
        application.add_handler(CommandHandler("teams", teams_command))
        application.add_handler(CommandHandler("check", check_subscription_command))
        application.add_handler(CommandHandler("referral", referral_command))
        
        # Gestionnaire de conversation pour les cotes
        conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            states={
                ODDS_INPUT_TEAM1: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_odds_team1_input)],
                ODDS_INPUT_TEAM2: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_odds_team2_input)]
            },
            fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
        )
        application.add_handler(conv_handler)
        
        # Ajouter le gestionnaire pour les clics sur les boutons
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Ajouter le gestionnaire pour les messages normaux (après le ConversationHandler)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Ajouter le gestionnaire d'erreurs
        application.add_error_handler(error_handler)

        # Démarrer le bot
        logger.info(f"Bot démarré avec le token: {TELEGRAM_TOKEN[:5]}...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.critical(f"ERREUR CRITIQUE lors du démarrage du bot: {e}")
        import traceback
        logger.critical(traceback.format_exc())

if __name__ == '__main__':
    main()
