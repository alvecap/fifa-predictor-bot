import logging
import asyncio
import random
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import get_all_teams, save_prediction_log
from predictor import MatchPredictor, format_prediction_message

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialisation du prédicteur
predictor = MatchPredictor()

# États de conversation pour le jeu FIFA
TEAM_SELECTION = 1
ODDS_INPUT_TEAM1 = 2
ODDS_INPUT_TEAM2 = 3

# Constantes pour la pagination des équipes
TEAMS_PER_PAGE = 8

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

# Gestionnaire des callbacks spécifiques à FIFA 4x4
async def handle_fifa_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Gère les callbacks du jeu FIFA 4x4."""
    query = update.callback_query
    callback_data = query.data
    
    # Vérifier si c'est un admin (importation tardive pour éviter les imports circulaires)
    try:
        from verification import is_admin
        user_id = query.from_user.id
        username = query.from_user.username
        admin_status = await is_admin(user_id, username)
    except ImportError:
        admin_status = False
    
    if callback_data == "fifa_select_teams":
        # Lancer la sélection des équipes
        context.user_data["selecting_team1"] = True
        await start_team_selection(query.message, context, edit=True)
    
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
        
        return ODDS_INPUT_TEAM1
    
    elif callback_data == "fifa_new_prediction":
        # Relancer une nouvelle prédiction
        await start_fifa_game(update, context)
    
    return None

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
    
    # Vérifier si c'est un admin
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Importation tardive de is_admin pour éviter les imports circulaires
    try:
        from verification import is_admin
        admin_status = await is_admin(user_id, username)
        if admin_status:
            # Si c'est un admin, pas besoin de vérifier d'autres conditions
            logger.info(f"Bypass des vérifications pour l'admin {username} (ID: {user_id})")
        else:
            # Sinon, vérifier l'abonnement et le parrainage comme d'habitude
            from database import check_user_subscription
            from referral_system import has_completed_referrals
            from verification import send_subscription_required, send_referral_required
            
            is_subscribed = await check_user_subscription(user_id)
            if not is_subscribed:
                await send_subscription_required(update.message)
                return ConversationHandler.END
            
            has_completed_status = await has_completed_referrals(user_id, username)
            if not has_completed_status:
                await send_referral_required(update.message)
                return ConversationHandler.END
    except ImportError:
        # Si on ne peut pas importer is_admin, continuer comme d'habitude
        pass
    
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
    
    # Vérifier si c'est un admin
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Importation tardive de is_admin pour éviter les imports circulaires
    try:
        from verification import is_admin
        admin_status = await is_admin(user_id, username)
        if admin_status:
            # Si c'est un admin, pas besoin de vérifier d'autres conditions
            logger.info(f"Bypass des vérifications pour l'admin {username} (ID: {user_id})")
        else:
            # Sinon, vérifier l'abonnement et le parrainage comme d'habitude
            from database import check_user_subscription
            from referral_system import has_completed_referrals
            from verification import send_subscription_required, send_referral_required
            
            is_subscribed = await check_user_subscription(user_id)
            if not is_subscribed:
                await send_subscription_required(update.message)
                return ConversationHandler.END
            
            has_completed_status = await has_completed_referrals(user_id, username)
            if not has_completed_status:
                await send_referral_required(update.message)
                return ConversationHandler.END
    except ImportError:
        # Si on ne peut pas importer is_admin, continuer comme d'habitude
        pass
    
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
        return ODDS_INPUT_TEAM2

# Cette fonction est appelée depuis fifa_games.py pour traiter les messages entrants
# concernant les cotes pour FIFA
async def handle_fifa_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Traite les messages liés au jeu FIFA."""
    # Vérifier si c'est un admin (importation tardive pour éviter les imports circulaires)
    try:
        from verification import is_admin
        user_id = update.effective_user.id
        username = update.effective_user.username
        admin_status = await is_admin(user_id, username)
        if admin_status:
            logger.info(f"Traitement du message avec droits d'admin pour {username} (ID: {user_id})")
    except ImportError:
        pass
        
    # Vérifier si nous attendons une cote
    if context.user_data.get("awaiting_odds_team1", False):
        return await handle_odds_team1_input(update, context)
    
    if context.user_data.get("awaiting_odds_team2", False):
        return await handle_odds_team2_input(update, context)
    
    return None
