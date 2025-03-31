import logging
import asyncio
import sys
from typing import Optional, Dict, Any, List
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

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importation des configurations
from config import TELEGRAM_TOKEN, WELCOME_MESSAGE

# Imports pour la vérification admin
from admin_access import is_admin

# Imports pour les systèmes optimisés
from cache_system import start_cache_monitoring
from queue_manager import start_queue_manager, stop_queue_manager
from predictor import preload_prediction_data

# Imports pour les vérifications
from verification import (
    verify_subscription, verify_referral, send_subscription_required, 
    send_referral_required, verify_all_requirements, show_games_menu
)

# Imports pour le système de parrainage
from referral_system import (
    register_user, generate_referral_link,
    count_referrals, get_referred_users, get_max_referrals, get_referral_instructions
)

# Import depuis l'adaptateur de base de données
from database_adapter import get_all_teams, save_prediction_log

# Import des modules de jeux spécifiques
from games.apple_game import start_apple_game, handle_apple_callback
from games.baccarat_game import start_baccarat_game, handle_baccarat_callback, handle_baccarat_tour_input
from games.fifa_game import handle_fifa_callback

# États de conversation pour les jeux
BACCARAT_INPUT = 1
ODDS_INPUT = 2

# Variable pour suivre l'initialisation
_is_system_initialized = False

async def initialize_system():
    """
    Initialise tous les systèmes optimisés :
    1. Démarre le gestionnaire de file d'attente
    2. Précharge les données de prédiction
    3. Démarre la surveillance du cache
    """
    global _is_system_initialized
    
    if _is_system_initialized:
        logger.info("Système déjà initialisé")
        return
    
    logger.info("Initialisation du système optimisé...")
    
    # Démarrer le gestionnaire de file d'attente
    logger.info("Démarrage du gestionnaire de file d'attente...")
    await start_queue_manager()
    
    # Précharger les données de prédiction
    logger.info("Préchargement des données de prédiction...")
    preload_task = asyncio.create_task(preload_prediction_data())
    
    # Démarrer la surveillance du cache
    logger.info("Démarrage de la surveillance du cache...")
    cache_task = asyncio.create_task(start_cache_monitoring())
    
    # Attendre la fin du préchargement des données avec timeout
    try:
        await asyncio.wait_for(preload_task, timeout=30.0)
        logger.info("Préchargement des données de prédiction terminé avec succès")
    except asyncio.TimeoutError:
        logger.warning("Le préchargement des données de prédiction prend plus de temps que prévu, "
                      "l'application continuera à fonctionner mais avec des performances réduites initialement")
    
    _is_system_initialized = True
    logger.info("Système optimisé initialisé avec succès")

async def shutdown_system():
    """
    Arrête proprement tous les systèmes optimisés.
    """
    global _is_system_initialized
    
    if not _is_system_initialized:
        return
    
    logger.info("Arrêt du système optimisé...")
    
    # Arrêter le gestionnaire de file d'attente
    await stop_queue_manager()
    
    # Les autres tâches s'arrêteront automatiquement à la fermeture de l'application
    _is_system_initialized = False
    
    logger.info("Système optimisé arrêté avec succès")

# Fonction principale pour le jeu FIFA 4x4
async def start_fifa_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance le jeu FIFA 4x4 Predictor."""
    query = update.callback_query
    
    # Message introductif
    intro_text = (
        "🏆 *FIFA 4x4 PREDICTOR* 🏆\n\n"
        "Obtenez des prédictions précises basées sur des statistiques réelles de matchs FIFA 4x4.\n\n"
        "Pour commencer, sélectionnez les équipes qui s'affrontent et indiquez les cotes actuelles."
    )
    
    # Bouton pour lancer la sélection d'équipes
    keyboard = [
        [InlineKeyboardButton("👉 Sélectionner les équipes", callback_data="fifa_select_teams")],
        [InlineKeyboardButton("🎮 Retour au menu", callback_data="show_games")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Éditer le message pour afficher l'introduction du jeu
    await query.edit_message_text(
        intro_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Gestionnaire des callbacks spécifiques au bot
async def handle_game_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère la sélection d'un jeu depuis le menu principal."""
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username
    data = query.data
    
    # Log pour le debugging
    logger.info(f"Sélection de jeu: {data} par utilisateur {username} (ID: {user_id})")
    
    # Vérifier l'accès utilisateur (sauf pour les admin)
    admin_status = is_admin(user_id, username)
    if not admin_status:
        has_access = await verify_all_requirements(user_id, username, query.message, context)
        if not has_access:
            return
    
    await query.answer()  # Répondre au callback query
    
    if data == "game_fifa":
        # Lancer le jeu FIFA
        await start_fifa_game(update, context)
    elif data == "game_apple":
        # Lancer le jeu Apple of Fortune
        await start_apple_game(update, context)
    elif data == "game_baccarat":
        # Lancer le jeu Baccarat
        await start_baccarat_game(update, context)
    elif data == "show_games":
        # Afficher le menu des jeux
        await show_games_menu(query.message, context)
    else:
        # Commande inconnue, retour au menu
        await show_games_menu(query.message, context)

# Gestionnaire principal des callbacks
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère tous les callbacks de boutons"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    username = query.from_user.username
    
    # Stocker les informations utilisateur dans le contexte
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Log pour debugging avec plus de détails
    logger.info(f"Callback principal reçu: '{data}' de l'utilisateur {username} (ID: {user_id})")
    
    # Traiter explicitement les callbacks de sélection d'équipe
    if data.startswith("select_team1_") or data.startswith("select_team2_"):
        await handle_fifa_callback(update, context)
        return
    
    # Gérer explicitement les callbacks de pagination
    if data.startswith("fifa_page_") or data.startswith("teams_page_"):
        # Extraire le numéro de page
        try:
            if data.startswith("fifa_page_"):
                page = int(data.split("_")[2])
            else:
                page = int(data.split("_")[2])
                
            is_team1 = context.user_data.get("selecting_team1", True)
            
            # S'assurer que les non-admins ont accès
            admin_status = is_admin(user_id, username)
            if not admin_status:
                has_access = await verify_all_requirements(user_id, username, query.message, context)
                if not has_access:
                    return
                    
            await query.answer()  # Répondre au callback
            
            # Importer les fonctions nécessaires dynamiquement pour éviter les importations circulaires
            from games.fifa_game import show_teams_page
            
            # Afficher rapidement la page suivante sans délai
            await show_teams_page(query.message, context, page, edit=True, is_team1=is_team1)
            return
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la pagination: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.answer("Erreur lors du changement de page")
            return
    
    # Traiter les différents types de callbacks
    if data == "show_games":
        # Afficher le menu des jeux
        await show_games_menu(query.message, context)
    elif data.startswith("game_"):
        # Callbacks pour sélection de jeu
        await handle_game_selection(update, context)
    elif data.startswith("fifa_"):
        # Callbacks spécifiques au jeu FIFA
        await handle_fifa_callback(update, context)
    elif data.startswith("apple_"):
        # Callbacks spécifiques au jeu Apple of Fortune
        await handle_apple_callback(update, context)
    elif data.startswith("baccarat_"):
        # Callbacks spécifiques au jeu Baccarat
        await handle_baccarat_callback(update, context)
    elif data == "verify_subscription":
        # Vérification d'abonnement
        await verify_subscription(query.message, user_id, username, context, edit=True)
    elif data == "verify_referral":
        # Vérification de parrainage
        await verify_referral(query.message, user_id, username, context, edit=True)
    elif data == "get_referral_link":
        # Générer et afficher un lien de parrainage
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
        referral_link = await generate_referral_link(user_id, bot_username)
        
        # Obtenir le nombre actuel de parrainages
        referral_count = await count_referrals(user_id)
        max_referrals = await get_max_referrals()
        
        # Créer les boutons
        keyboard = [
            [InlineKeyboardButton("🔗 Copier le lien", callback_data="copy_referral_link")],
            [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message avec les instructions de parrainage
        message_text = f"🔗 *Votre lien de parrainage:*\n\n`{referral_link}`\n\n"
        message_text += f"_Progression: {referral_count}/{max_referrals} parrainage(s)_\n\n"
        message_text += get_referral_instructions()
        
        await query.edit_message_text(
            message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    elif data == "copy_referral_link":
        # Telegram gère automatiquement la copie
        await query.answer("Lien copié dans le presse-papier!")
    else:
        # Commande inconnue
        logger.warning(f"Callback non reconnu: {data}")
        await query.answer("Action non reconnue")

# Gestionnaire des messages pour les différents jeux
async def handle_game_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Traite les messages spécifiques aux jeux."""
    # Stocker les informations utilisateur dans le contexte
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérifier le statut admin
    admin_status = is_admin(user_id, username)
    if admin_status:
        logger.info(f"Message reçu de l'administrateur {username} (ID: {user_id})")
    
    # Vérifier si c'est un message pour Baccarat (tour #)
    if context.user_data.get("awaiting_baccarat_tour", False):
        return await handle_baccarat_tour_input(update, context)
    
    # Vérifier si c'est un message pour FIFA (cotes équipe 1)
    if context.user_data.get("awaiting_odds_team1", False):
        from games.fifa_game import handle_odds_team1_input
        return await handle_odds_team1_input(update, context)
    
    # Vérifier si c'est un message pour FIFA (cotes équipe 2)
    if context.user_data.get("awaiting_odds_team2", False):
        from games.fifa_game import handle_odds_team2_input
        return await handle_odds_team2_input(update, context)
    
    # Sinon, traiter comme un message normal
    message_text = update.message.text.strip()
    
    # Rechercher si le message ressemble à une demande de prédiction
    if " vs " in message_text or " contre " in message_text:
        # Vérifier si l'utilisateur a accès (admin ou abonnement+parrainage)
        if not admin_status:
            has_access = await verify_all_requirements(user_id, username, update.message, context)
            if not has_access:
                return
        
        # Informer l'utilisateur d'utiliser la méthode interactive
        keyboard = [
            [InlineKeyboardButton("🔮 Faire une prédiction", callback_data="fifa_select_teams")]
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

# Commande pour afficher le menu des jeux
async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu des jeux."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Pour tout le monde, afficher directement le menu des jeux
    await show_games_menu(update.message, context)

# Commande d'aide
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche l'aide lorsque l'utilisateur utilise la commande /help."""
    # Récupérer les infos utilisateur
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérifier si c'est un admin
    if is_admin(user_id, username):
        help_text = "*🔮 FIFA 4x4 PREDICTOR - Aide (Admin)*\n\n"
        help_text += "*Commandes disponibles:*\n"
        help_text += "• `/start` - Démarrer le bot\n"
        help_text += "• `/help` - Afficher ce message d'aide\n"
        help_text += "• `/games` - Menu des jeux disponibles\n"
        help_text += "• `/check` - Vérifier l'état du système\n"
        
        await update.message.reply_text(
            help_text,
            parse_mode='Markdown'
        )
        return
    
    # Vérifier si l'utilisateur a accès
    has_access = await verify_all_requirements(user_id, username, update.message, context)
    if not has_access:
        return
    
    # Afficher le message d'aide standard
    help_text = "*🔮 FIFA 4x4 PREDICTOR - Aide*\n\n"
    help_text += "*Commandes disponibles:*\n"
    help_text += "• `/start` - Démarrer le bot\n"
    help_text += "• `/help` - Afficher ce message d'aide\n"
    help_text += "• `/games` - Menu des jeux disponibles\n"
    help_text += "• `/check` - Vérifier votre abonnement\n"
    help_text += "• `/referral` - Gérer vos parrainages\n\n"
    help_text += "*Note:* Les cotes sont obligatoires pour obtenir des prédictions précises."
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown'
    )

# Commande pour la gestion des parrainages
async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les informations et statistiques de parrainage."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérifier l'abonnement
    is_subscribed = await verify_subscription(update.message, user_id, username, context=None, edit=False)
    if not is_subscribed and not is_admin(user_id, username):
        return
    
    # S'assurer que l'utilisateur est enregistré
    await register_user(user_id, username)
    
    # Obtenir les statistiques de parrainage
    referral_count = await count_referrals(user_id)
    max_referrals = await get_max_referrals()
    has_completed = referral_count >= max_referrals
    referred_users = await get_referred_users(user_id)
    
    # Générer un lien de parrainage
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    referral_link = await generate_referral_link(user_id, bot_username)
    
    # Créer le message
    message_text = "👥 *Système de Parrainage FIFA 4x4 Predictor*\n\n"
    
    if has_completed:
        message_text += "✅ *Statut: Parrainage complété*\n"
        message_text += f"Vous avez parrainé {referral_count}/{max_referrals} personne(s) requise(s).\n"
        message_text += "Toutes les fonctionnalités sont débloquées!\n\n"
    else:
        message_text += "⏳ *Statut: Parrainage en cours*\n"
        message_text += f"Progression: {referral_count}/{max_referrals} personne(s) parrainée(s).\n"
        message_text += f"Parrainez encore {max_referrals - referral_count} personne(s) pour débloquer toutes les fonctionnalités.\n\n"
    
    message_text += "*Votre lien de parrainage:*\n"
    message_text += f"`{referral_link}`\n\n"
    
    # Utiliser une version simplifiée des instructions de parrainage
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

# Commande pour vérifier l'abonnement
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie l'abonnement au canal."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    await verify_subscription(update.message, user_id, username, context)

# Gestionnaire d'erreurs
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

# Point d'entrée pour la commande /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère la commande /start."""
    # Sauvegarder l'ID utilisateur dans le contexte
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérifier si c'est un admin
    if is_admin(user_id, username):
        logger.info(f"Commande /start par l'administrateur {username} (ID: {user_id})")
        
        # Crée un bouton direct pour chaque jeu
        keyboard = [
            [InlineKeyboardButton("🏆 FIFA 4x4 Predictor", callback_data="game_fifa")],
            [InlineKeyboardButton("🍎 Apple of Fortune", callback_data="game_apple")],
            [InlineKeyboardButton("🃏 Baccarat", callback_data="game_baccarat")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔑 *Accès administrateur*\n\n"
            "Sélectionnez directement un jeu:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
        
    # Envoyer un message rapide pour confirmer la réception
    message = await update.message.reply_text(
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
    
    # Enregistrer l'utilisateur sans attendre le résultat
    asyncio.create_task(register_user(user_id, username, referrer_id))
    
    # Message de bienvenue complet avec boutons
    welcome_text = f"✅ *Compte activé!*\n\n"
    welcome_text += "🏆 Bienvenue sur *FIFA 4x4 Predictor*!\n\n"
    welcome_text += "⚠️ Pour utiliser toutes les fonctionnalités, vous devez être abonné "
    welcome_text += f"à notre canal [AL VE CAPITAL](https://t.me/alvecapitalofficiel)."
    
    # Vérifier si l'utilisateur a déjà complété son quota de parrainages
    has_completed = False
    try:
        referral_count = await count_referrals(user_id)
        max_referrals = await get_max_referrals()
        has_completed = referral_count >= max_referrals
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du parrainage: {e}")
    
    # Créer les boutons
    buttons = [
        [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    
    # Ajouter un bouton pour obtenir le lien de parrainage si nécessaire
    if not has_completed and not is_admin(user_id, username):
        buttons.append([InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    # Mettre à jour le message précédent avec les informations complètes
    try:
        await message.edit_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour du message de bienvenue: {e}")
        # En cas d'erreur, envoyer un nouveau message
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )

# Fonction principale pour démarrer le bot
async def run_bot():
    """Démarre le bot Telegram."""
    try:
        # Initialiser les systèmes optimisés
        await initialize_system()
        
        # Créer l'application
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Ajouter les gestionnaires de commandes
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("games", games_command))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("referral", referral_command))
        
        # Gestionnaire de conversation pour les entrées spécifiques aux jeux
        conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_game_messages)],
            states={
                ODDS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_game_messages)],
                BACCARAT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_game_messages)]
            },
            fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
        )
        application.add_handler(conv_handler)
        
        # Gestionnaire pour tous les callbacks
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Ajouter le gestionnaire pour les messages normaux non gérés par la conversation
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_game_messages))
        
        # Ajouter le gestionnaire d'erreurs
        application.add_error_handler(error_handler)

        # Démarrer le bot
        logger.info(f"Bot démarré avec le token: {TELEGRAM_TOKEN[:5]}...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # Signaler le succès de démarrage
        logger.info("Bot FIFA 4x4 Predictor entièrement démarré et prêt à recevoir des commandes.")
        
        # Maintenir le bot en exécution
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Arrêt du bot par l'utilisateur...")
    except Exception as e:
        logger.critical(f"ERREUR CRITIQUE lors du démarrage du bot: {e}")
        import traceback
        logger.critical(traceback.format_exc())
        # Continuation du code de fifa_games.py

    finally:
        # Arrêter le bot proprement
        logger.info("Arrêt du bot...")
        
        # Arrêter les systèmes optimisés
        try:
            await shutdown_system()
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt du système: {e}")
            
        # Arrêter l'application
        try:
            if 'application' in locals():
                await application.stop()
                await application.shutdown()
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt de l'application: {e}")

# Fonction principale
def main() -> None:
    """Démarre le bot."""
    try:
        # Configurer asyncio pour mieux gérer les erreurs
        import asyncio
        
        # Pour Python 3.10 et plus, on peut ajouter un meilleur débogage
        try:
            asyncio.get_event_loop().set_debug(True)
        except:
            pass
        
        # Réinitialiser les webhooks Telegram avant le démarrage
        try:
            import requests
            from config import TELEGRAM_TOKEN
            
            # URL pour supprimer le webhook et les mises à jour en attente
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true"
            
            # Faire la requête
            response = requests.get(url)
            if response.status_code == 200:
                logger.info("✅ Réinitialisation des webhooks Telegram réussie!")
            else:
                logger.warning(f"⚠️ Erreur lors de la réinitialisation des webhooks: {response.text}")
        except Exception as e:
            logger.warning(f"⚠️ Erreur lors de la réinitialisation des webhooks: {e}")
        
        # Lancer le bot dans une boucle asyncio
        asyncio.run(run_bot())
        
    except KeyboardInterrupt:
        logger.info("Bot arrêté par l'utilisateur.")
    except Exception as e:
        logger.critical(f"ERREUR CRITIQUE lors du démarrage du bot: {e}")
        import traceback
        logger.critical(traceback.format_exc())
        # Assurer un code de sortie non-zéro en cas d'erreur
        import sys
        sys.exit(1)

if __name__ == '__main__':
    main()
