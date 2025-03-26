import logging
import asyncio
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

from config import TELEGRAM_TOKEN, WELCOME_MESSAGE
from admin_access import is_admin
from verification import (
    verify_subscription, verify_referral, send_subscription_required, 
    send_referral_required, verify_all_requirements, show_games_menu
)
from referral_system import (
    register_user, generate_referral_link,
    count_referrals, get_referred_users, MAX_REFERRALS, get_referral_instructions
)

# Import des modules de jeux spécifiques
from fifa_bot import start as bot_start, help_command, referral_command, handle_message, error_handler
from games.apple_game import start_apple_game, handle_apple_callback
from games.baccarat_game import start_baccarat_game, handle_baccarat_callback, handle_baccarat_tour_input

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# États de conversation pour les jeux
BACCARAT_INPUT = 1
ODDS_INPUT = 2

# Fonction pour le jeu FIFA 4x4
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

# Gestionnaire des callbacks spécifiques à FIFA 4x4
async def handle_fifa_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Gère les callbacks du jeu FIFA 4x4."""
    query = update.callback_query
    callback_data = query.data
    user_id = query.from_user.id
    username = query.from_user.username
    
    # Vérifier l'accès utilisateur (sauf pour les admin)
    admin_status = is_admin(user_id, username)
    if not admin_status:
        has_access = await verify_all_requirements(user_id, username, query.message, context)
        if not has_access:
            return None
    
    await query.answer()  # Répondre au callback
    
    if callback_data == "show_games":
        # Retour au menu principal des jeux
        await show_games_menu(query.message, context)
        return None
    
    if callback_data == "fifa_select_teams":
        # Lancer la sélection des équipes
        context.user_data["selecting_team1"] = True
        await start_team_selection(query.message, context, edit=True)
    
    elif callback_data.startswith("teams_page_"):
        # Gestion de la pagination pour les équipes
        page = int(callback_data.split("_")[-1])
        is_team1 = context.user_data.get("selecting_team1", True)
        await show_teams_page(query.message, context, page, edit=True, is_team1=is_team1)
    
    elif callback_data.startswith("select_team1_"):
        # Extraire le nom de l'équipe 1
        team1 = callback_data.replace("select_team1_", "")
        context.user_data["team1"] = team1
        context.user_data["selecting_team1"] = False
        
        # Animation de sélection
        anim_frames = [
            f"✅ *{team1}* sélectionné!",
            f"✅ *{team1}* ✅",
            f"🎯 *{team1}* sélectionné!"
        ]
        
        for frame in anim_frames:
            await query.edit_message_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.3)
        
        # Puis passer à la sélection de l'équipe 2
        await start_team2_selection(query.message, context, edit=True)
    
    elif callback_data.startswith("select_team2_"):
        # Extraire le nom de l'équipe 2
        team2 = callback_data.replace("select_team2_", "")
        team1 = context.user_data.get("team1", "")
        
        if not team1:
            await query.edit_message_text(
                "❌ *Erreur de sélection*\n\n"
                "Veuillez recommencer la procédure de sélection des équipes.",
                parse_mode='Markdown'
            )
            return
        
        # Sauvegarder l'équipe 2
        context.user_data["team2"] = team2
        
        # Animation de sélection
        anim_frames = [
            f"✅ *{team2}* sélectionné!",
            f"✅ *{team2}* ✅",
            f"🎯 *{team2}* sélectionné!"
        ]
        
        for frame in anim_frames:
            await query.edit_message_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.3)
        
        # Demander la première cote
        await query.edit_message_text(
            f"💰 *Saisie des cotes (obligatoire)*\n\n"
            f"Match: *{team1}* vs *{team2}*\n\n"
            f"Veuillez saisir la cote pour *{team1}*\n\n"
            f"_Exemple: 1.85_",
            parse_mode='Markdown'
        )
        
        # Passer en mode conversation pour recevoir les cotes
        context.user_data["awaiting_odds_team1"] = True
        context.user_data["odds_for_match"] = f"{team1} vs {team2}"
        
        return ConversationHandler.END
    
    elif callback_data == "fifa_new_prediction":
        # Relancer une nouvelle prédiction
        await start_fifa_game(update, context)
    
    return None

# Gestionnaire de sélection du jeu depuis le menu principal
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

# Fonction pour démarrer la sélection des équipes (première équipe)
async def start_team_selection(message, context, edit=False, page=0) -> None:
    """Affiche la première page de sélection d'équipe."""
    try:
        from database import get_all_teams
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
    from database import get_all_teams
    
    # Constantes pour la pagination des équipes
    TEAMS_PER_PAGE = 8
    
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
        team_buttons.append([InlineKeyboardButton("◀️ Retour", callback_data="fifa_select_teams")])
    else:
        team_buttons.append([InlineKeyboardButton("🎮 Menu principal", callback_data="show_games")])
    
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
    
    # Vérifier si c'est un admin d'abord
    user_id = update.effective_user.id
    username = update.effective_user.username
    admin_status = is_admin(user_id, username)
    
    # Si c'est un admin, pas besoin de vérifications supplémentaires
    if not admin_status:
        # Vérification des conditions d'accès pour les non-admin
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
            await update.message.reply_text(
                "❌ *Valeur de cote invalide*\n\n"
                "La cote doit être supérieure à 1.01.",
                parse_mode='Markdown'
            )
            return ODDS_INPUT
        
        # Sauvegarder la cote
        context.user_data["odds1"] = odds1
        context.user_data["awaiting_odds_team1"] = False
        
        # Animation de validation de la cote
        loading_message = await update.message.reply_text(
            f"✅ Cote de *{team1}* enregistrée: *{odds1}*",
            parse_mode='Markdown'
        )
        
        # Demander la cote de l'équipe 2
        await asyncio.sleep(0.5)
        await loading_message.edit_text(
            f"💰 *Saisie des cotes (obligatoire)*\n\n"
            f"Match: *{team1}* vs *{team2}*\n\n"
            f"Veuillez maintenant saisir la cote pour *{team2}*\n\n"
            f"_Exemple: 2.35_",
            parse_mode='Markdown'
        )
        
        # Passer à l'attente de la cote de l'équipe 2
        context.user_data["awaiting_odds_team2"] = True
        
        return ODDS_INPUT
    except ValueError:
        await update.message.reply_text(
            "❌ *Format incorrect*\n\n"
            f"Veuillez saisir uniquement la valeur numérique de la cote pour *{team1}*.\n\n"
            "Exemple: `1.85`",
            parse_mode='Markdown'
        )
        return ODDS_INPUT

# Gestionnaire pour la saisie de la cote de l'équipe 2
async def handle_odds_team2_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gère la saisie de la cote pour la deuxième équipe."""
    if not context.user_data.get("awaiting_odds_team2", False):
        return ConversationHandler.END
    
    # Vérifier si c'est un admin d'abord
    user_id = update.effective_user.id
    username = update.effective_user.username
    admin_status = is_admin(user_id, username)
    
    # Si c'est un admin, pas besoin de vérifications supplémentaires
    if not admin_status:
        # Vérification des conditions d'accès pour les non-admin
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
            await update.message.reply_text(
                "❌ *Valeur de cote invalide*\n\n"
                "La cote doit être supérieure à 1.01.",
                parse_mode='Markdown'
            )
            return ODDS_INPUT
        
        # Sauvegarder la cote
        context.user_data["odds2"] = odds2
        context.user_data["awaiting_odds_team2"] = False
        
        # Animation de validation de la cote
        loading_message = await update.message.reply_text(
            f"✅ Cote de *{team2}* enregistrée: *{odds2}*",
            parse_mode='Markdown'
        )
        
        # Animation de génération de prédiction
        await asyncio.sleep(0.3)
        await loading_message.edit_text(
            "🧠 *Analyse des données en cours...*",
            parse_mode='Markdown'
        )
        
        # Animation stylisée pour l'analyse
        analysis_frames = [
            "📊 *Analyse des performances historiques...*",
            "🏆 *Analyse des confrontations directes...*",
            "⚽ *Calcul des probabilités de scores...*",
            "📈 *Finalisation des prédictions...*"
        ]
        
        for frame in analysis_frames:
            await asyncio.sleep(0.3)
            await loading_message.edit_text(frame, parse_mode='Markdown')
        
        # Génération de la prédiction
        try:
            from predictor import MatchPredictor, format_prediction_message
            
            predictor = MatchPredictor()
            prediction = predictor.predict_match(team1, team2, odds1, odds2)
            
            if not prediction or "error" in prediction:
                error_msg = prediction.get("error", "Erreur inconnue") if prediction else "Impossible de générer une prédiction"
                
                # Proposer de réessayer
                keyboard = [
                    [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="fifa_new_prediction")],
                    [InlineKeyboardButton("🎮 Accueil", callback_data="show_games")]
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
            
            # Animation finale avant d'afficher le résultat
            final_frames = [
                "🎯 *Prédiction prête!*",
                "✨ *Affichage des résultats...*"
            ]
            
            for frame in final_frames:
                await asyncio.sleep(0.3)
                await loading_message.edit_text(frame, parse_mode='Markdown')
            
            # Proposer une nouvelle prédiction
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="fifa_new_prediction")],
                [InlineKeyboardButton("🎮 Accueil", callback_data="show_games")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await loading_message.edit_text(
                prediction_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            # Enregistrer la prédiction dans les logs
            from database import save_prediction_log
            
            user_id = context.user_data.get("user_id", update.message.from_user.id)
            username = context.user_data.get("username", update.message.from_user.username)
            
            save_prediction_log(
                user_id=user_id,
                username=username,
                team1=team1,
                team2=team2,
                odds1=odds1,
                odds2=odds2,
                prediction_result=prediction
            )
            
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Erreur lors de la génération de la prédiction: {e}")
            
            # Proposer de réessayer en cas d'erreur
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="fifa_new_prediction")],
                [InlineKeyboardButton("🎮 Accueil", callback_data="show_games")]
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
        return ODDS_INPUT

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
    
    # Log pour debugging
    logger.info(f"Callback reçu: {data} de l'utilisateur {username} (ID: {user_id})")
    
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
        
        # Créer les boutons
        keyboard = [
            [InlineKeyboardButton("🔗 Copier le lien", callback_data="copy_referral_link")],
            [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Message avec les instructions de parrainage
        message_text = f"🔗 *Votre lien de parrainage:*\n\n`{referral_link}`\n\n"
        message_text += f"_Progression: {referral_count}/{MAX_REFERRALS} parrainage(s)_\n\n"
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
        return await handle_odds_team1_input(update, context)
    
    # Vérifier si c'est un message pour FIFA (cotes équipe 2)
    if context.user_data.get("awaiting_odds_team2", False):
        return await handle_odds_team2_input(update, context)
    
    # Sinon, traiter comme un message normal
    return await handle_message(update, context)

# Commande pour afficher le menu des jeux
async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu des jeux."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Vérifier si c'est un admin
    admin_status = is_admin(user_id, username)
    if admin_status:
        logger.info(f"Commande /games par l'administrateur {username} (ID: {user_id})")
        # Pour les admins, afficher directement le menu des jeux
        await show_games_menu(update.message, context)
        return
    
    # Pour les non-admins, vérifier les conditions d'accès
    has_access = await verify_all_requirements(user_id, username, update.message, context)
    if has_access:
        await show_games_menu(update.message, context)

# Commande pour vérifier l'abonnement au canal
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie l'abonnement au canal."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    await verify_subscription(update.message, user_id, username, context)

# Fonction principale pour démarrer le bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Point d'entrée personnalisé depuis fifa_games.py"""
    # Sauvegarder l'ID utilisateur dans le contexte
    user_id = update.effective_user.id
    username = update.effective_user.username
    context.user_data["user_id"] = user_id
    context.user_data["username"] = username
    
    # Vérifier si c'est un admin
    admin_status = is_admin(user_id, username)
    if admin_status:
        logger.info(f"Commande /start par l'administrateur {username} (ID: {user_id})")
        
    # Traiter de la même manière que le bot standard
    await bot_start(update, context)

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
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("referral", referral_command))
        
        # Gestionnaire de conversation pour les entrées de cotes
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
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.critical(f"ERREUR CRITIQUE lors du démarrage du bot: {e}")
        import traceback
        logger.critical(traceback.format_exc())

if __name__ == '__main__':
    main()
