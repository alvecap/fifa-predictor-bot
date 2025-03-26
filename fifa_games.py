import logging
import re
import asyncio
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

from config import TELEGRAM_TOKEN
from verification import (
    animated_subscription_check, animated_referral_check,
    send_subscription_required, send_referral_required,
    verify_all_requirements, verify_before_game, show_games_menu,
    verify_callback, is_admin
)
from referral_system import (
    register_user, generate_referral_link,
    count_referrals, get_referred_users, MAX_REFERRALS, get_referral_instructions
)

# Import des modules de jeux
from games.fifa_game import start_fifa_game, handle_fifa_callback
from games.apple_game import start_apple_game, handle_apple_callback
from games.baccarat_game import start_baccarat_game, handle_baccarat_callback

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# États de conversation
VERIFY_SUBSCRIPTION = 1
GAME_SELECTION = 2
BACCARAT_INPUT = 3

# Fonctions de base
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message quand la commande /start est envoyée."""
    user = update.effective_user
    user_id = user.id
    username = user.username
    context.user_data["username"] = username
    
    # Vérifier si l'utilisateur vient d'un lien de parrainage
    referrer_id = None
    if context.args and len(context.args) > 0 and context.args[0].startswith('ref'):
        try:
            referrer_id = int(context.args[0][3:])  # Extraire l'ID du parrain
            logger.info(f"User {user_id} came from referral link of user {referrer_id}")
        except (ValueError, IndexError):
            referrer_id = None
    
    # Enregistrer l'utilisateur dans la base de données avec le parrain si applicable
    await register_user(user_id, username, referrer_id)
    
    # Message de bienvenue personnalisé
    welcome_text = (
        "🎮 *Bienvenue sur FIFA GAMES* 🎮\n\n"
        "Préparez-vous à vivre l'expérience ultime de prédiction de jeux FIFA et casino virtuel !\n\n"
        "*Nos jeux disponibles :*\n"
        "🏆 *FIFA 4x4 Predictor* - Prédictions précises basées sur des données historiques\n"
        "🍎 *Apple of Fortune* - Trouvez la bonne pomme et multipliez vos chances\n"
        "🃏 *Baccarat* - Anticipez le gagnant entre le Joueur et le Banquier\n\n"
        "⚡ *Nouveaux jeux bientôt disponibles !* ⚡\n\n"
        "⚠️ Pour accéder à toutes ces fonctionnalités, vous devez :\n"
        "1️⃣ Être abonné à notre canal [AL VE CAPITAL](https://t.me/alvecapitalofficiel)\n"
        "2️⃣ Parrainer 1 personne pour débloquer l'accès complet\n\n"
        "Commencez l'aventure en vérifiant votre abonnement ci-dessous 👇"
    )
    
    # Vérifier si l'utilisateur est un administrateur
    is_admin_user = await is_admin(user_id, username)
    
    # Créer les boutons
    buttons = [
        [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")],
        [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
    ]
    
    # Ajouter le bouton de parrainage si nécessaire
    if not is_admin_user:  # Les admins n'ont pas besoin de parrainer
        buttons.append([InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

    # Pour les administrateurs, afficher directement le menu des jeux
    if is_admin_user:
        await update.message.reply_text(
            "🔑 *Accès administrateur détecté*\n\n"
            "Vous avez un accès complet à toutes les fonctionnalités.",
            parse_mode='Markdown'
        )
        await show_games_menu(update.message, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message d'aide quand la commande /help est envoyée."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Vérifier les conditions d'accès
    if not await verify_all_requirements(user_id, username, update.effective_message, context):
        return
    
    help_text = (
        "*🎮 FIFA GAMES - Aide*\n\n"
        "*Commandes disponibles:*\n"
        "• `/start` - Démarrer le bot\n"
        "• `/help` - Afficher ce message d'aide\n"
        "• `/games` - Afficher le menu des jeux\n"
        "• `/referral` - Gérer vos parrainages\n\n"
        "*Jeux disponibles:*\n"
        "• 🏆 *FIFA 4x4 Predictor* - Prédictions basées sur des statistiques réelles\n"
        "• 🍎 *Apple of Fortune* - Jeu de prédiction de pomme chanceux\n"
        "• 🃏 *Baccarat* - Prédictions de résultats de jeu de cartes\n\n"
        "Pour plus d'informations sur chaque jeu, sélectionnez-le dans le menu principal."
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu des jeux disponibles."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Vérifier les conditions d'accès
    if await verify_all_requirements(user_id, username, update.effective_message, context):
        # Afficher le menu des jeux
        await show_games_menu(update.effective_message, context)

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

# Commande pour vérifier l'abonnement au canal
async def check_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie si l'utilisateur est abonné au canal @alvecapitalofficiel."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    
    # Utiliser l'animation de vérification
    await animated_subscription_check(update.message, user_id, username, context)

# Commande pour gérer les parrainages
async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les parrainages de l'utilisateur."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Vérifier si c'est un admin
    if await is_admin(user_id, username):
        await update.message.reply_text(
            "🔑 *Mode Administrateur*\n\n"
            "Vous n'avez pas besoin de gérer les parrainages en tant qu'administrateur.",
            parse_mode='Markdown'
        )
        return
    
    # Vérifier l'abonnement d'abord
    is_subscribed = await verify_all_requirements(user_id, username, update.effective_message, context=None)
    if not is_subscribed:
        return
    
    # S'assurer que l'utilisateur est enregistré
    await register_user(user_id, username)
    
    # Obtenir les statistiques de parrainage
    referral_count = await count_referrals(user_id)
    has_completed = referral_count >= MAX_REFERRALS
    referred_users = await get_referred_users(user_id)
    
    # Générer un lien de parrainage
    # Générer un lien de parrainage
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    referral_link = await generate_referral_link(user_id, bot_username)
    
    # Créer le message
    message_text = "👥 *Système de Parrainage FIFA GAMES*\n\n"
    
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
    
    # Ajouter les instructions de parrainage
    message_text += "Pour parrainer un ami:\n"
    message_text += "1️⃣ Envoyez votre lien à votre ami\n"
    message_text += "2️⃣ Votre ami doit cliquer sur le lien\n"
    message_text += "3️⃣ L'ami doit redémarrer le bot pour activer le parrainage\n\n"
    
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
    
    buttons.append([InlineKeyboardButton("🎮 Menu des jeux", callback_data="show_games")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        message_text,
        parse_mode='Markdown',
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

# Gestionnaire des boutons de callback
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Gère les clics sur les boutons inline."""
    query = update.callback_query
    await query.answer()
    
    # Récupérer les données utilisateur
    user_id = query.from_user.id
    username = query.from_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Traiter les différents types de callback
    if query.data == "verify_subscription":
        # Utiliser l'animation de vérification avec le contexte
        await animated_subscription_check(query.message, user_id, username, context, edit=True)
    
    elif query.data == "verify_referral":
        # Vérifier d'abord l'abonnement
        is_subscribed = await verify_all_requirements(user_id, username, query.message, context=None)
        if not is_subscribed:
            return
        
        # Vérifier le parrainage avec animation
        await animated_referral_check(query.message, user_id, username, context, edit=True)
    
    elif query.data == "get_referral_link":
        # Vérifier l'abonnement avant de donner le lien
        is_subscribed = await verify_all_requirements(user_id, username, query.message, context=None)
        if not is_subscribed:
            return
        
        # Générer et afficher un lien de parrainage
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
        referral_link = await generate_referral_link(user_id, bot_username)
        
        # Obtenir le nombre actuel de parrainages
        referral_count = await count_referrals(user_id)
        
        # Créer les boutons
        keyboard = [
            [InlineKeyboardButton("🔗 Copier le lien", callback_data="copy_referral_link")],
            [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message avec les instructions de parrainage
        message_text = f"🔗 *Votre lien de parrainage:*\n\n`{referral_link}`\n\n"
        message_text += f"_Progression: {referral_count}/{MAX_REFERRALS} parrainage(s)_\n\n"
        message_text += "Pour parrainer un ami:\n"
        message_text += "1️⃣ Envoyez votre lien à votre ami\n"
        message_text += "2️⃣ Votre ami doit cliquer sur le lien\n"
        message_text += "3️⃣ L'ami doit redémarrer le bot pour activer le parrainage"
        
        await query.edit_message_text(
            message_text,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    
    elif query.data == "copy_referral_link":
        # Telegram gère automatiquement la copie
        await query.answer("Lien copié dans le presse-papier!")
    
    elif query.data == "show_games":
        # Vérifier les conditions d'accès
        if await verify_all_requirements(user_id, username, query.message, context):
            # Afficher le menu des jeux
            await show_games_menu(query.message, context)
    
    # Gestion des redirections vers les différents jeux
    elif query.data == "game_fifa":
        # Redirection vers le jeu FIFA 4x4
        await verify_callback(update, context, start_fifa_game)
    
    elif query.data == "game_apple":
        # Redirection vers le jeu Apple of Fortune
        await verify_callback(update, context, start_apple_game)
    
    elif query.data == "game_baccarat":
        # Redirection vers le jeu Baccarat
        await verify_callback(update, context, start_baccarat_game)
    
    # Gestion des callbacks spécifiques à chaque jeu
    elif query.data.startswith("fifa_"):
        # Callback spécifique au jeu FIFA 4x4
        await verify_callback(update, context, handle_fifa_callback)
    
    elif query.data.startswith("apple_"):
        # Callback spécifique au jeu Apple of Fortune
        await verify_callback(update, context, handle_apple_callback)
    
    elif query.data.startswith("baccarat_"):
        # Callback spécifique au jeu Baccarat
        await verify_callback(update, context, handle_baccarat_callback)
    
    return None

# Gérer les messages directs
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Répond aux messages qui ne sont pas des commandes."""
    # Vérifier si c'est un message pour Baccarat (tour #)
    if context.user_data.get("awaiting_baccarat_tour", False):
        from games.baccarat_game import handle_baccarat_tour_input
        return await handle_baccarat_tour_input(update, context)
    
    # Vérifier l'abonnement avant de traiter
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Message par défaut informant l'utilisateur des commandes disponibles
    await update.message.reply_text(
        "👋 *Bienvenue sur FIFA GAMES!*\n\n"
        "Utilisez les commandes suivantes pour naviguer:\n"
        "• `/start` - Commencer ou redémarrer le bot\n"
        "• `/games` - Afficher le menu des jeux\n"
        "• `/help` - Voir toutes les commandes disponibles",
        parse_mode='Markdown'
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
        application.add_handler(CommandHandler("games", games_command))
        application.add_handler(CommandHandler("check", check_subscription_command))
        application.add_handler(CommandHandler("referral", referral_command))
        
        # Ajouter le gestionnaire pour les clics sur les boutons
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Ajouter le gestionnaire pour les messages normaux
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
