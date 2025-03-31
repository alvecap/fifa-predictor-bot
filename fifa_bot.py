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

# Configuration
from config import TELEGRAM_TOKEN, WELCOME_MESSAGE, HELP_MESSAGE, TEAM_INPUT, ODDS_INPUT

# Gestionnaires optimisés
from queue_manager import (
    send_message_queued, edit_message_queued, 
    get_system_load_status, start_queue_manager
)
from gif_animations import (
    send_verification_animation, send_prediction_animation,
    send_game_animation
)
from cache_system import (
    get_cached_subscription_status, cache_subscription_status,
    get_cached_referral_count, cache_referral_count,
    get_cached_teams, cache_teams,
    get_cached_prediction, cache_prediction
)

# Modules existants
from database_adapter import get_all_teams, save_prediction_log, check_user_subscription
from predictor import MatchPredictor, format_prediction_message
from referral_system import (
    register_user, has_completed_referrals, generate_referral_link,
    count_referrals, get_referred_users, MAX_REFERRALS, get_referral_instructions
)
from verification import (
    verify_subscription, verify_referral, 
    send_subscription_required, send_referral_required,
    verify_all_requirements, show_games_menu
)
from admin_access import is_admin

# Initialisation du système
from games import ensure_initialization

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

# Fonctions de base
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message quand la commande /start est envoyée. Version optimisée."""
    user = update.effective_user
    user_id = user.id
    username = user.username
    context.user_data["username"] = username
    context.user_data["user_id"] = user_id
    
    # Répondre IMMÉDIATEMENT avec un message simple pour confirmer que le bot fonctionne
    welcome_message = await send_message_queued(
        chat_id=update.message.chat_id,
        text=f"👋 *Bienvenue {username} sur FIFA 4x4 Predictor!*\n\n"
             "Je suis en train d'activer votre compte...",
        parse_mode='Markdown',
        user_id=user_id,
        high_priority=True
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
    
    # Vérifier si l'utilisateur a déjà complété son quota de parrainages (via le cache)
    has_completed = False
    try:
        # Vérifier si c'est un admin
        if is_admin(user_id, username):
            has_completed = True
        else:
            # Utiliser le cache si disponible
            cached_count = await get_cached_referral_count(user_id)
            if cached_count is not None:
                has_completed = cached_count >= MAX_REFERRALS
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
    await edit_message_queued(
        message=welcome_message,
        text=welcome_text,
        parse_mode='Markdown',
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        user_id=user_id,
        high_priority=True
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message d'aide quand la commande /help est envoyée."""
    # Récupérer les infos utilisateur
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérifier si c'est un admin
    if is_admin(user_id, username):
        help_text = "*🔮 FIFA 4x4 Predictor - Aide (Admin)*\n\n"
        help_text += "*Commandes disponibles:*\n"
        help_text += "• `/start` - Démarrer le bot\n"
        help_text += "• `/help` - Afficher ce message d'aide\n"
        help_text += "• `/predict` - Commencer une prédiction\n"
        help_text += "• `/teams` - Voir toutes les équipes disponibles\n"
        help_text += "• `/check` - Vérifier l'état du système\n"
        help_text += "• `/games` - Menu des jeux disponibles\n"
        help_text += "• `/admin` - Commandes administrateur\n"
        
        await send_message_queued(
            chat_id=update.message.chat_id,
            text=help_text,
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        return
    
    # Vérifier l'abonnement via le cache
    cached_status = await get_cached_subscription_status(user_id)
    if cached_status is not None:
        is_subscribed = cached_status
    else:
        # Si pas en cache, vérifier et mettre en cache
        is_subscribed = await check_user_subscription(user_id)
        await cache_subscription_status(user_id, is_subscribed)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
        return
    
    # Vérifier aussi le parrainage via le cache
    cached_count = await get_cached_referral_count(user_id)
    if cached_count is not None:
        has_completed = cached_count >= MAX_REFERRALS
    else:
        # Si pas en cache, vérifier et mettre en cache
        has_completed = await has_completed_referrals(user_id)
        referral_count = await count_referrals(user_id)
        await cache_referral_count(user_id, referral_count)
    
    if not has_completed:
        await send_referral_required(update.message)
        return
    
    help_text = "*🔮 FIFA 4x4 Predictor - Aide*\n\n"
    help_text += "*Commandes disponibles:*\n"
    help_text += "• `/start` - Démarrer le bot\n"
    help_text += "• `/help` - Afficher ce message d'aide\n"
    help_text += "• `/predict` - Commencer une prédiction\n"
    help_text += "• `/teams` - Voir toutes les équipes disponibles\n"
    help_text += "• `/check` - Vérifier votre abonnement\n"
    help_text += "• `/referral` - Gérer vos parrainages\n"
    help_text += "• `/games` - Menu des jeux disponibles\n\n"
    help_text += "*Note:* Les cotes sont obligatoires pour obtenir des prédictions précises.\n\n"
    help_text += "Pour plus de détails, contactez l'administrateur du bot."
    
    await send_message_queued(
        chat_id=update.message.chat_id,
        text=help_text,
        parse_mode='Markdown',
        user_id=user_id,
        high_priority=True
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les erreurs."""
    logger.error(f"Une erreur est survenue: {context.error}")
    
    if update and update.effective_message:
        try:
            await send_message_queued(
                chat_id=update.effective_message.chat_id,
                text="Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur.",
                user_id=None,
                high_priority=True
            )
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du message d'erreur: {e}")

# Commande pour vérifier l'abonnement au canal
async def check_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie si l'utilisateur est abonné au canal @alvecapitalofficiel."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Si c'est un admin, afficher les infos système au lieu de la vérification d'abonnement
    if is_admin(user_id, username):
        # Obtenir le statut du système
        from queue_manager import queue_manager
        status = queue_manager.get_queue_status()
        
        # Formater le message
        status_text = "*🔧 Statut du système*\n\n"
        status_text += f"File d'attente: {status['total_waiting']} utilisateurs\n"
        status_text += f"• Haute priorité: {status['high_priority']}\n"
        status_text += f"• Moyenne priorité: {status['medium_priority']}\n"
        status_text += f"• Basse priorité: {status['low_priority']}\n\n"
        status_text += f"Requêtes par seconde: {status['processed_per_second']}/{queue_manager.max_requests_per_second}\n"
        status_text += f"Temps d'attente moyen: {status['avg_wait_time']:.2f}s\n"
        status_text += f"Charge système: {status['system_load']}\n"
        
        # Obtenir les statistiques du cache
        from cache_system import cache
        cache_stats = cache.get_stats()
        
        status_text += "\n*📊 Statistiques du cache*\n\n"
        status_text += f"Taux de succès: {cache_stats.get('hit_rate', 0):.1f}%\n"
        status_text += f"Succès: {cache_stats.get('hits', 0)}\n"
        status_text += f"Échecs: {cache_stats.get('misses', 0)}\n"
        status_text += f"Entrées expirées: {cache_stats.get('expired', 0)}\n"
        
        await send_message_queued(
            chat_id=update.message.chat_id,
            text=status_text,
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        return
    
    # Utiliser la vérification animée optimisée
    await verify_subscription(update.message, user_id, username, context)

# Commande pour gérer les parrainages
async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les parrainages de l'utilisateur."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérifier l'abonnement via le cache
    cached_status = await get_cached_subscription_status(user_id)
    if cached_status is not None:
        is_subscribed = cached_status
    else:
        # Si pas en cache, vérifier et mettre en cache
        is_subscribed = await check_user_subscription(user_id)
        await cache_subscription_status(user_id, is_subscribed)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
        return
    
    # S'assurer que l'utilisateur est enregistré
    await register_user(user_id, username)
    
    # Obtenir les statistiques de parrainage (en utilisant le cache si possible)
    cached_count = await get_cached_referral_count(user_id)
    if cached_count is not None:
        referral_count = cached_count
    else:
        referral_count = await count_referrals(user_id)
        await cache_referral_count(user_id, referral_count)
    
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
    
    await send_message_queued(
        chat_id=update.message.chat_id,
        text=message_text,
        parse_mode='Markdown',
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        user_id=user_id,
        high_priority=True
    )

# Lancer une prédiction directement avec la commande predict
async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance le processus de prédiction quand la commande /predict est envoyée."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérification optimisée
    has_access = await verify_all_requirements(user_id, username, update.message, context)
    if not has_access:
        return
    
    # Lancer le processus de prédiction avec file d'attente si nécessaire
    # Vérifier le niveau de charge actuel du système
    system_load = get_system_load_status()
    
    if system_load == "critical" and not is_admin(user_id, username):
        # Notifier l'utilisateur de la charge élevée
        from queue_manager import queue_manager
        status = queue_manager.get_queue_status()
        estimated_wait = max(5, status["total_waiting"] / queue_manager.max_requests_per_second)
        
        # Message d'attente
        await send_message_queued(
            chat_id=update.message.chat_id,
            text=f"⚠️ *Système actuellement très sollicité*\n\n"
                 f"Il y a actuellement {status['total_waiting']} utilisateurs en attente.\n"
                 f"Temps d'attente estimé: *{estimated_wait:.1f} secondes*\n\n"
                 f"Vous serez notifié dès que votre tour arrivera. Merci de votre patience!",
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=False
        )
    
    # Lancer la sélection des équipes
    keyboard = [
        [InlineKeyboardButton("🏆 Sélectionner les équipes", callback_data="start_prediction")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_message_queued(
        chat_id=update.message.chat_id,
        text="🔮 *Prêt pour une prédiction*\n\n"
             "Cliquez sur le bouton ci-dessous pour commencer.",
        reply_markup=reply_markup,
        parse_mode='Markdown',
        user_id=user_id,
        high_priority=True
    )

# Afficher le menu des jeux
async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu des jeux disponibles."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérification optimisée des exigences
    if not is_admin(user_id, username):
        has_access = await verify_all_requirements(user_id, username, update.message, context)
        if not has_access:
            return
    
    # Afficher le menu des jeux
    await show_games_menu(update.message, context)

# Gestionnaire des boutons de callback optimisé
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les clics sur les boutons inline. Version optimisée avec file d'attente et cache."""
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    data = query.data
    
    await query.answer()  # Répondre immédiatement au callback pour éviter le "chargement" sur l'interface
    
    # Log pour debugging
    logger.info(f"Callback reçu: {data} de l'utilisateur {username} (ID: {user_id})")
    
    # Vérifier le niveau de charge du système
    system_load = get_system_load_status()
    
    # Si la charge est critique, informer les utilisateurs non-admin
    if system_load == "critical" and not is_admin(user_id, username):
        # Récupérer les stats de file d'attente
        from queue_manager import queue_manager
        status = queue_manager.get_queue_status()
        estimated_wait = max(5, status["total_waiting"] / queue_manager.max_requests_per_second)
        
        # Notifier l'utilisateur seulement si l'attente est significative
        if estimated_wait > 10:
            await send_message_queued(
                chat_id=query.message.chat_id,
                text=f"⚠️ *Système actuellement très sollicité*\n\n"
                     f"Temps d'attente estimé: *{estimated_wait:.1f} secondes*\n"
                     f"Merci de votre patience!",
                parse_mode='Markdown',
                user_id=user_id,
                high_priority=False
            )
    
    # Traiter les différents types de callbacks
    if data == "verify_subscription":
        # Vérifie l'abonnement
        await verify_subscription(query.message, user_id, username, context, edit=True)
    
    elif data == "verify_referral":
        # Vérifie le parrainage
        await verify_referral(query.message, user_id, username, context, edit=True)
    
    elif data == "get_referral_link":
        # Génère un lien de parrainage
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
        referral_link = await generate_referral_link(user_id, bot_username)
        
        # Obtenir le nombre actuel de parrainages
        cached_count = await get_cached_referral_count(user_id)
        if cached_count is not None:
            referral_count = cached_count
        else:
            referral_count = await count_referrals(user_id)
            await cache_referral_count(user_id, referral_count)
        
        # Créer les boutons
        keyboard = [
            [InlineKeyboardButton("🔗 Copier le lien", callback_data="copy_referral_link")],
            [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message avec les instructions de parrainage
        from referral_system import get_referral_instructions
        message_text = f"🔗 *Votre lien de parrainage:*\n\n`{referral_link}`\n\n"
        message_text += f"_Progression: {referral_count}/{MAX_REFERRALS} parrainage(s)_\n\n"
        message_text += get_referral_instructions()
        
        await edit_message_queued(
            message=query.message,
            text=message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            user_id=user_id,
            high_priority=True
        )
    
    elif data == "copy_referral_link":
        # Telegram gère automatiquement la copie
        pass  # Déjà répondu avec query.answer()
    
    elif data == "start_prediction":
        # Vérification optimisée des exigences
        if not is_admin(user_id, username):
            has_access = await verify_all_requirements(user_id, username, query.message, context)
            if not has_access:
                return
        
        # Lancer la sélection des équipes
        context.user_data["selecting_team1"] = True
        await start_team_selection(query.message, context, edit=True)
    
    elif data.startswith("teams_page_"):
        # Navigation dans les pages d'équipes
        try:
            page = int(data.split("_")[2])
            is_team1 = context.user_data.get("selecting_team1", True)
            
            # Vérifier si c'est un admin
            if not is_admin(user_id, username):
                has_access = await verify_all_requirements(user_id, username, query.message, context)
                if not has_access:
                    return
            
            # Afficher la page d'équipes
            await show_teams_page(query.message, context, page, edit=True, is_team1=is_team1)
        except (ValueError, IndexError):
            logger.error(f"Erreur lors du traitement de la page d'équipes: {data}")
    
    elif data.startswith("select_team1_"):
        # Sélection de la première équipe
        team1 = data[len("select_team1_"):]
        context.user_data["team1"] = team1
        context.user_data["selecting_team1"] = False
        
        # Animation simplifiée
        await edit_message_queued(
            message=query.message,
            text=f"✅ *{team1}* sélectionné!\n\nChargement des options pour l'équipe adverse...",
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        
        # Passer à la sélection de la deuxième équipe
        await start_team2_selection(query.message, context, edit=True)
    
    elif data.startswith("select_team2_"):
        # Sélection de la deuxième équipe
        team2 = data[len("select_team2_"):]
        team1 = context.user_data.get("team1", "")
        
        if not team1:
            await edit_message_queued(
                message=query.message,
                text="❌ *Erreur de sélection*\n\n"
                    "Veuillez recommencer la procédure de sélection des équipes.",
                parse_mode='Markdown',
                user_id=user_id,
                high_priority=True
            )
            return
        
        # Sauvegarder l'équipe 2
        context.user_data["team2"] = team2
        
        # Animation simplifiée
        await edit_message_queued(
            message=query.message,
            text=f"✅ *{team2}* sélectionné!\n\nPréparation de la saisie des cotes...",
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        
        # Demander la première cote
        await edit_message_queued(
            message=query.message,
            text=f"💰 *Saisie des cotes (obligatoire)*\n\n"
                f"Match: *{team1}* vs *{team2}*\n\n"
                f"Veuillez saisir la cote pour *{team1}*\n\n"
                f"_Exemple: 1.85_",
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        
        # Passer en mode conversation pour recevoir les cotes
        context.user_data["awaiting_odds_team1"] = True
        context.user_data["odds_for_match"] = f"{team1} vs {team2}"
    
    elif data == "new_prediction":
        # Nouvelle prédiction
        keyboard = [
            [InlineKeyboardButton("🏆 Sélectionner les équipes", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await edit_message_queued(
            message=query.message,
            text="🔮 *Nouvelle prédiction*\n\n"
                 "Cliquez sur le bouton ci-dessous pour commencer.",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
    
    elif data == "show_games":
        # Afficher le menu des jeux
        await show_games_menu(query.message, context)
    
    elif data.startswith("game_"):
        # Traitement des jeux spécifiques
        # Traitement des jeux spécifiques
        game_type = data[len("game_"):]
        
        if game_type == "fifa":
            # Vérifier l'accès
            if not is_admin(user_id, username):
                has_access = await verify_all_requirements(user_id, username, query.message, context)
                if not has_access:
                    return
            
            # Afficher l'animation du jeu FIFA
            await send_game_animation(
                message=query.message,
                game_type="fifa",
                final_text="🏆 *FIFA 4x4 PREDICTOR*\n\n"
                        "Pour obtenir une prédiction, sélectionnez les équipes qui s'affrontent.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👉 Sélectionner les équipes", callback_data="start_prediction")],
                    [InlineKeyboardButton("🎮 Retour au menu", callback_data="show_games")]
                ]),
                edit=True,
                user_id=user_id,
                animation_duration=1.0
            )
        
        elif game_type == "apple":
            # Afficher animation pour Apple of Fortune
            await send_game_animation(
                message=query.message,
                game_type="apple",
                final_text="🍎 *APPLE OF FORTUNE*\n\n"
                        "Découvrez la position de la pomme gagnante parmi 5 positions possibles!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔮 Obtenir une prédiction", callback_data="apple_predict")],
                    [InlineKeyboardButton("🎮 Retour au menu", callback_data="show_games")]
                ]),
                edit=True,
                user_id=user_id,
                animation_duration=1.0
            )
        
        elif game_type == "baccarat":
            # Afficher animation pour Baccarat
            await send_game_animation(
                message=query.message,
                game_type="baccarat",
                final_text="🃏 *BACCARAT*\n\n"
                        "Anticipez le gagnant entre le Joueur et le Banquier, ainsi que le nombre de points!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔢 Entrer le numéro de tour", callback_data="baccarat_enter_tour")],
                    [InlineKeyboardButton("🎮 Retour au menu", callback_data="show_games")]
                ]),
                edit=True,
                user_id=user_id,
                animation_duration=1.0
            )
    
    elif data.startswith("apple_") or data.startswith("baccarat_"):
        # Traiter les jeux aléatoires (ces jeux seront implémentés dans leurs fichiers respectifs)
        # Pour Apple of Fortune
        if data == "apple_predict":
            from games.apple_game import handle_apple_callback
            await handle_apple_callback(update, context)
        
        # Pour Baccarat
        elif data.startswith("baccarat_"):
            from games.baccarat_game import handle_baccarat_callback
            await handle_baccarat_callback(update, context)
    
    else:
        # Callback non reconnu
        logger.warning(f"Callback non reconnu: {data}")
        await edit_message_queued(
            message=query.message,
            text="Action non reconnue. Veuillez réessayer ou utiliser le menu principal.",
            user_id=user_id,
            high_priority=True
        )

# Fonction pour démarrer la sélection des équipes (première équipe)
async def start_team_selection(message, context, edit=False, page=0) -> None:
    """Affiche la première page de sélection d'équipe."""
    try:
        context.user_data["selecting_team1"] = True
        await show_teams_page(message, context, page, edit, is_team1=True)
    except Exception as e:
        logger.error(f"Erreur lors du démarrage de la sélection d'équipes: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        text = "Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur."
        
        if edit and hasattr(message, 'edit_text'):
            await edit_message_queued(
                message=message,
                text=text,
                parse_mode='Markdown',
                user_id=context.user_data.get("user_id"),
                high_priority=True
            )
        else:
            await send_message_queued(
                chat_id=message.chat_id,
                text=text,
                parse_mode='Markdown',
                user_id=context.user_data.get("user_id"),
                high_priority=True
            )

# Fonction pour afficher une page d'équipes
async def show_teams_page(message, context, page=0, edit=False, is_team1=True) -> None:
    """Affiche une page de la liste des équipes."""
    try:
        # Essayer d'obtenir les équipes depuis le cache
        teams = await get_cached_teams()
        
        if not teams:
            # Si pas en cache, charger depuis la base de données
            teams = get_all_teams()
            
            if teams:
                # Mettre en cache pour la prochaine fois
                await cache_teams(teams)
        
        # Vérifier si des équipes ont été trouvées
        if not teams:
            logger.error("Aucune équipe trouvée dans la base de données")
            error_message = "Aucune équipe disponible. Veuillez contacter l'administrateur."
            
            if edit and hasattr(message, 'edit_text'):
                await edit_message_queued(
                    message=message,
                    text=error_message,
                    parse_mode='Markdown',
                    user_id=context.user_data.get("user_id"),
                    high_priority=True
                )
            else:
                await send_message_queued(
                    chat_id=message.chat_id,
                    text=error_message,
                    parse_mode='Markdown',
                    user_id=context.user_data.get("user_id"),
                    high_priority=True
                )
            return
        
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
        else:
            team_buttons.append([InlineKeyboardButton("🎮 Menu principal", callback_data="show_games")])
        
        reply_markup = InlineKeyboardMarkup(team_buttons)
        
        # Texte du message
        team_type = "première" if is_team1 else "deuxième"
        text = (
            f"🏆 *Sélection des équipes* (Page {page+1}/{total_pages})\n\n"
            f"Veuillez sélectionner la *{team_type} équipe* pour votre prédiction:"
        )
        
        if edit and hasattr(message, 'edit_text'):
            await edit_message_queued(
                message=message,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown',
                user_id=context.user_data.get("user_id"),
                high_priority=True
            )
        else:
            await send_message_queued(
                chat_id=message.chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown',
                user_id=context.user_data.get("user_id"),
                high_priority=True
            )
        
    except Exception as e:
        logger.error(f"Erreur lors de l'affichage des équipes: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        text = "Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur."
        
        if edit and hasattr(message, 'edit_text'):
            await edit_message_queued(
                message=message,
                text=text,
                parse_mode='Markdown',
                user_id=context.user_data.get("user_id"),
                high_priority=True
            )
        else:
            await send_message_queued(
                chat_id=message.chat_id,
                text=text,
                parse_mode='Markdown',
                user_id=context.user_data.get("user_id"),
                high_priority=True
            )

# Fonction pour démarrer la sélection de la deuxième équipe
async def start_team2_selection(message, context, edit=False, page=0) -> None:
    """Affiche les options de sélection pour la deuxième équipe."""
    team1 = context.user_data.get("team1", "")
    
    if not team1:
        text = "❌ *Erreur*\n\nVeuillez d'abord sélectionner la première équipe."
        
        if edit and hasattr(message, 'edit_text'):
            await edit_message_queued(
                message=message,
                text=text,
                parse_mode='Markdown',
                user_id=context.user_data.get("user_id"),
                high_priority=True
            )
        else:
            await send_message_queued(
                chat_id=message.chat_id,
                text=text,
                parse_mode='Markdown',
                user_id=context.user_data.get("user_id"),
                high_priority=True
            )
        return
    
    # Afficher la page de sélection de la deuxième équipe
    await show_teams_page(message, context, page, edit, is_team1=False)

# Gestionnaire pour la saisie de la cote de l'équipe 1
async def handle_odds_team1_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gère la saisie de la cote pour la première équipe."""
    if not context.user_data.get("awaiting_odds_team1", False):
        return ConversationHandler.END
    
    # Vérification optimisée des exigences
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if not is_admin(user_id, username):
        has_access = await verify_all_requirements(user_id, username, update.message, context)
        if not has_access:
            return ConversationHandler.END
    
    user_input = update.message.text.strip()
    team1 = context.user_data.get("team1", "")
    team2 = context.user_data.get("team2", "")
    
    # Extraire la cote
    try:
        odds1 = float(user_input.replace(",", "."))
        
        # Vérifier que la cote est valide
        if odds1 < 1.01:
            await send_message_queued(
                chat_id=update.message.chat_id,
                text="❌ *Valeur de cote invalide*\n\n"
                    "La cote doit être supérieure à 1.01.",
                parse_mode='Markdown',
                user_id=user_id,
                high_priority=True
            )
            return ODDS_INPUT_TEAM1
        
        # Sauvegarder la cote
        context.user_data["odds1"] = odds1
        context.user_data["awaiting_odds_team1"] = False
        
        # Animation de validation de la cote
        loading_message = await send_message_queued(
            chat_id=update.message.chat_id,
            text=f"✅ Cote de *{team1}* enregistrée: *{odds1}*",
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        
        # Demander la cote de l'équipe 2
        await asyncio.sleep(0.3)  # Délai réduit
        
        await edit_message_queued(
            message=loading_message,
            text=f"💰 *Saisie des cotes (obligatoire)*\n\n"
                f"Match: *{team1}* vs *{team2}*\n\n"
                f"Veuillez maintenant saisir la cote pour *{team2}*\n\n"
                f"_Exemple: 2.35_",
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        
        # Passer à l'attente de la cote de l'équipe 2
        context.user_data["awaiting_odds_team2"] = True
        
        return ODDS_INPUT_TEAM2
    except ValueError:
        await send_message_queued(
            chat_id=update.message.chat_id,
            text="❌ *Format incorrect*\n\n"
                f"Veuillez saisir uniquement la valeur numérique de la cote pour *{team1}*.\n\n"
                "Exemple: `1.85`",
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        return ODDS_INPUT_TEAM1

# Gestionnaire pour la saisie de la cote de l'équipe 2
async def handle_odds_team2_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gère la saisie de la cote pour la deuxième équipe."""
    if not context.user_data.get("awaiting_odds_team2", False):
        return ConversationHandler.END
    
    # Vérification optimisée des exigences
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if not is_admin(user_id, username):
        has_access = await verify_all_requirements(user_id, username, update.message, context)
        if not has_access:
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
            await send_message_queued(
                chat_id=update.message.chat_id,
                text="❌ *Valeur de cote invalide*\n\n"
                    "La cote doit être supérieure à 1.01.",
                parse_mode='Markdown',
                user_id=user_id,
                high_priority=True
            )
            return ODDS_INPUT_TEAM2
        
        # Sauvegarder la cote
        context.user_data["odds2"] = odds2
        context.user_data["awaiting_odds_team2"] = False
        
        # Vérifier d'abord le cache pour la prédiction
        cached_prediction = await get_cached_prediction(team1, team2, odds1, odds2)
        if cached_prediction:
            logger.info(f"Prédiction trouvée en cache pour {team1} vs {team2}")
            
            # Formater la prédiction pour l'affichage
            prediction_text = format_prediction_message(cached_prediction)
            
            # Afficher le résultat
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Afficher une animation avant le résultat
            await send_prediction_animation(
                message=update.message,
                final_text=prediction_text,
                reply_markup=reply_markup,
                user_id=user_id,
                game_type="fifa",
                loading_duration=1.0
            )
            
            # Enregistrer la prédiction dans les logs (en arrière-plan)
            asyncio.create_task(save_prediction_log(
                user_id=user_id,
                username=username,
                team1=team1,
                team2=team2,
                odds1=odds1,
                odds2=odds2,
                prediction_result=cached_prediction
            ))
            
            return ConversationHandler.END
        
        # Si pas en cache, générer la prédiction avec animation
        loading_message = await send_message_queued(
            chat_id=update.message.chat_id,
            text=f"🧠 *Analyse des données en cours...*",
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        
        # Générer la prédiction
        try:
            # Génération de la prédiction
            prediction = await predictor.predict_match(team1, team2, odds1, odds2)
            
            if not prediction or "error" in prediction:
                error_msg = prediction.get("error", "Erreur inconnue") if prediction else "Impossible de générer une prédiction"
                
                # Proposer de réessayer
                keyboard = [
                    [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await edit_message_queued(
                    message=loading_message,
                    text=f"❌ *Erreur de prédiction*\n\n"
                        f"{error_msg}\n\n"
                        f"Veuillez essayer avec d'autres équipes.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                    user_id=user_id,
                    high_priority=True
                )
                return ConversationHandler.END
            
            # Formater et envoyer la prédiction
            prediction_text = format_prediction_message(prediction)
            
            # Proposer une nouvelle prédiction
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await edit_message_queued(
                message=loading_message,
                text=prediction_text,
                reply_markup=reply_markup,
                parse_mode='Markdown',
                user_id=user_id,
                high_priority=True
            )
            
            # Mettre en cache la prédiction pour les prochaines demandes
            await cache_prediction(team1, team2, odds1, odds2, prediction)
            
            # Enregistrer la prédiction dans les logs (en arrière-plan)
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
            import traceback
            logger.error(traceback.format_exc())
            
            # Proposer de réessayer en cas d'erreur
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await edit_message_queued(
                message=loading_message,
                text="❌ *Une erreur s'est produite lors de la génération de la prédiction*\n\n"
                    "Veuillez réessayer avec d'autres équipes ou contacter l'administrateur.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                user_id=user_id,
                high_priority=True
            )
            return ConversationHandler.END
    except ValueError:
        await send_message_queued(
            chat_id=update.message.chat_id,
            text="❌ *Format incorrect*\n\n"
                f"Veuillez saisir uniquement la valeur numérique de la cote pour *{team2}*.\n\n"
                "Exemple: `2.35`",
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        return ODDS_INPUT_TEAM2
        # Fonction pour lister les équipes disponibles
async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des équipes disponibles dans la base de données."""
    # Récupérer les infos utilisateur
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérification optimisée des exigences
    if not is_admin(user_id, username):
        has_access = await verify_all_requirements(user_id, username, update.message, context)
        if not has_access:
            return
    
    # Récupérer la liste des équipes (depuis le cache si possible)
    teams = await get_cached_teams()
    if not teams:
        teams = get_all_teams()
        if teams:
            await cache_teams(teams)
    
    if not teams:
        await send_message_queued(
            chat_id=update.message.chat_id,
            text="Aucune équipe n'a été trouvée dans la base de données.",
            user_id=user_id,
            high_priority=True
        )
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
            await send_message_queued(
                chat_id=update.message.chat_id,
                text=chunk,
                parse_mode='Markdown',
                user_id=user_id,
                high_priority=True
            )
    else:
        await send_message_queued(
            chat_id=update.message.chat_id,
            text=teams_text,
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )

# Gérer les messages directs
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Répond aux messages qui ne sont pas des commandes."""
    # Récupérer les infos utilisateur
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Si l'utilisateur attend des cotes pour une équipe
    if context.user_data.get("awaiting_odds_team1", False):
        return await handle_odds_team1_input(update, context)
    
    if context.user_data.get("awaiting_odds_team2", False):
        return await handle_odds_team2_input(update, context)
    
    # Vérifier l'abonnement via le cache
    if not is_admin(user_id, username):
        cached_status = await get_cached_subscription_status(user_id)
        if cached_status is not None:
            is_subscribed = cached_status
        else:
            # Si pas en cache, vérifier et mettre en cache
            is_subscribed = await check_user_subscription(user_id)
            await cache_subscription_status(user_id, is_subscribed)
        
        if not is_subscribed:
            await send_subscription_required(update.message)
            return
    
    message_text = update.message.text.strip()
    
    # Rechercher si le message ressemble à une demande de prédiction
    if " vs " in message_text or " contre " in message_text:
        # Vérifier le parrainage via le cache
        if not is_admin(user_id, username):
            cached_count = await get_cached_referral_count(user_id)
            if cached_count is not None:
                has_completed = cached_count >= MAX_REFERRALS
            else:
                # Si pas en cache, vérifier et mettre en cache
                has_completed = await has_completed_referrals(user_id)
                referral_count = await count_referrals(user_id)
                await cache_referral_count(user_id, referral_count)
            
            if not has_completed:
                await send_referral_required(update.message)
                return
        
        # Informer l'utilisateur d'utiliser la méthode interactive
        keyboard = [
            [InlineKeyboardButton("🔮 Faire une prédiction", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await send_message_queued(
            chat_id=update.message.chat_id,
            text="ℹ️ *Nouvelle méthode de prédiction*\n\n"
                "Pour une expérience améliorée, veuillez utiliser notre système interactif de prédiction.\n\n"
                "Cliquez sur le bouton ci-dessous pour commencer une prédiction guidée avec sélection d'équipes et cotes obligatoires.",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            user_id=user_id,
            high_priority=True
        )
        return
    
    # Message par défaut si aucune action n'est déclenchée
    await send_message_queued(
        chat_id=update.message.chat_id,
        text="Je ne comprends pas cette commande. Utilisez /help pour voir les commandes disponibles.",
        user_id=user_id,
        high_priority=True
    )

# Fonction principale
def main() -> None:
    """Démarre le bot."""
    try:
        # Initialiser le système amélioré
        ensure_initialization()
        
        # Créer l'application
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Ajouter les gestionnaires de commandes
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("predict", predict_command))
        application.add_handler(CommandHandler("teams", teams_command))
        application.add_handler(CommandHandler("check", check_subscription_command))
        application.add_handler(CommandHandler("referral", referral_command))
        application.add_handler(CommandHandler("games", games_command))
        
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
