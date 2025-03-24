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

from config import TELEGRAM_TOKEN, WELCOME_MESSAGE, HELP_MESSAGE, TEAM_INPUT, ODDS_INPUT
from database import get_all_teams, save_prediction_log, check_user_subscription
from predictor import MatchPredictor, format_prediction_message

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
    """Envoie un message quand la commande /start est envoyée."""
    user = update.effective_user
    context.user_data["username"] = user.username
    
    # Message de bienvenue personnalisé avec un bouton unique
    welcome_text = f"👋 *AL VE*, Bienvenue sur *FIFA 4x4 Predictor*!\n\n"
    welcome_text += "🏆 Je vous aide à *prédire les résultats* de matchs de football FIFA 4x4 "
    welcome_text += "en me basant sur des *données historiques* précises.\n\n"
    welcome_text += "⚠️ Pour utiliser toutes les fonctionnalités, vous devez être abonné "
    welcome_text += f"à notre canal [AL VE CAPITAL](https://t.me/alvecapital1)."
    
    # Créer un bouton unique pour la vérification
    keyboard = [
        [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
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
    
    help_text = "*🔮 FIFA 4x4 Predictor - Aide*\n\n"
    help_text += "*Commandes disponibles:*\n"
    help_text += "• `/start` - Démarrer le bot\n"
    help_text += "• `/help` - Afficher ce message d'aide\n"
    help_text += "• `/predict` - Commencer une prédiction\n"
    help_text += "• `/teams` - Voir toutes les équipes disponibles\n"
    help_text += "• `/check` - Vérifier votre abonnement\n\n"
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

# Animation de vérification d'abonnement
async def animated_subscription_check(message, user_id, edit=False) -> bool:
    """Effectue une vérification d'abonnement avec animation et retourne le résultat."""
    # Message initial
    verify_text = "🔍 *Vérification de votre abonnement*"
    
    if edit:
        msg = await message.edit_text(verify_text, parse_mode='Markdown')
    else:
        msg = await message.reply_text(verify_text, parse_mode='Markdown')
    
    # Animation stylée (cercle qui tourne)
    emojis = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]
    
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
    await asyncio.sleep(0.5)
    
    # Effectuer la vérification
    is_subscribed = await check_user_subscription(user_id)
    
    if is_subscribed:
        # Animation de succès
        success_frames = [
            "⬜⬜⬜⬜⬜",
            "⬛⬜⬜⬜⬜",
            "⬛⬛⬜⬜⬜",
            "⬛⬛⬛⬜⬜",
            "⬛⬛⬛⬛⬜",
            "⬛⬛⬛⬛⬛",
            "✅ *Abonnement vérifié!*"
        ]
        
        for frame in success_frames:
            await msg.edit_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.2)
        
        # Message final de succès
        await msg.edit_text(
            "✅ *Abonnement vérifié!*\n\n"
            "Vous êtes bien abonné à [AL VE CAPITAL](https://t.me/alvecapital1).\n"
            "Toutes les fonctionnalités sont désormais accessibles.",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Nouveau message avec bouton pour commencer une prédiction
        keyboard = [
            [InlineKeyboardButton("🔮 Faire une prédiction", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(
            "🏆 *Que souhaitez-vous faire ?*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return True
    else:
        # Animation d'échec
        error_frames = [
            "⬜⬜⬜⬜⬜",
            "⬛⬜⬜⬜⬜",
            "⬛⬛⬜⬜⬜",
            "⬛⬛⬛⬜⬜",
            "⬛⬛⬛⬛⬜",
            "⬛⬛⬛⬛⬛",
            "❌ *Abonnement non détecté*"
        ]
        
        for frame in error_frames:
            await msg.edit_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.2)
        
        # Message d'erreur
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔍 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            "❌ *Abonnement non détecté*\n\n"
            "Vous n'êtes pas encore abonné à [AL VE CAPITAL](https://t.me/alvecapital1).\n\n"
            "*Instructions:*\n"
            "1️⃣ Cliquez sur le bouton 'Rejoindre le canal'\n"
            "2️⃣ Abonnez-vous au canal\n"
            "3️⃣ Revenez ici et cliquez sur 'Vérifier à nouveau'",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        return False

# Message standard quand l'abonnement est requis
async def send_subscription_required(message) -> None:
    """Envoie un message indiquant que l'abonnement est nécessaire."""
    keyboard = [
        [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
        [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "⚠️ *Abonnement requis*\n\n"
        "Pour utiliser cette fonctionnalité, vous devez être abonné à notre canal.\n\n"
        "*Instructions:*\n"
        "1️⃣ Rejoignez [AL VE CAPITAL](https://t.me/alvecapital1)\n"
        "2️⃣ Cliquez sur '🔍 Vérifier mon abonnement'",
        reply_markup=reply_markup,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

# Commande pour vérifier l'abonnement au canal
async def check_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie si l'utilisateur est abonné au canal @alvecapital1."""
    user_id = update.effective_user.id
    context.user_data["user_id"] = user_id
    
    # Utiliser l'animation de vérification
    await animated_subscription_check(update.message, user_id)

# Lancer une prédiction directement avec la commande predict
async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance le processus de prédiction quand la commande /predict est envoyée."""
    user_id = update.effective_user.id
    context.user_data["user_id"] = user_id
    
    # Utiliser l'animation de vérification
    is_subscribed = await animated_subscription_check(update.message, user_id)
    
    if is_subscribed:
        # Lancer la sélection des équipes après une courte pause
        await asyncio.sleep(0.5)
        await start_team_selection(update.message, context)

# Gestionnaire des boutons de callback
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les clics sur les boutons inline."""
    query = update.callback_query
    await query.answer()
    
    # Récupérer les données utilisateur
    user_id = query.from_user.id
    context.user_data["user_id"] = user_id
    context.user_data["username"] = query.from_user.username
    
    if query.data == "verify_subscription":
        # Utiliser l'animation de vérification
        await animated_subscription_check(query.message, user_id, edit=True)
    
    elif query.data == "start_prediction":
        # Vérifier l'abonnement avant de lancer la prédiction
        is_subscribed = await check_user_subscription(user_id)
        
        if not is_subscribed:
            # Message d'erreur si l'abonnement n'est plus actif
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ *Abonnement requis*\n\n"
                "Votre abonnement à [AL VE CAPITAL](https://t.me/alvecapital1) n'est pas actif.\n"
                "Vous devez être abonné pour utiliser cette fonctionnalité.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Lancer la sélection des équipes
        await start_team_selection(query.message, context, edit=True)
    
    elif query.data.startswith("teams_page_"):
        # Gestion de la pagination pour les équipes
        page = int(query.data.split("_")[-1])
        await show_teams_page(query.message, context, page, edit=True)
    
    elif query.data.startswith("select_team1_"):
        # Vérifier l'abonnement
        is_subscribed = await check_user_subscription(user_id)
        if not is_subscribed:
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ *Abonnement requis*\n\n"
                "Votre abonnement à [AL VE CAPITAL](https://t.me/alvecapital1) n'est plus actif.\n"
                "Vous devez être abonné pour continuer cette action.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Extraire le nom de l'équipe 1
        team1 = query.data.replace("select_team1_", "")
        context.user_data["team1"] = team1
        
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
    
    elif query.data.startswith("select_team2_"):
        # Vérifier l'abonnement
        is_subscribed = await check_user_subscription(user_id)
        if not is_subscribed:
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ *Abonnement requis*\n\n"
                "Votre abonnement à [AL VE CAPITAL](https://t.me/alvecapital1) n'est plus actif.\n"
                "Vous devez être abonné pour continuer cette action.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Extraire le nom de l'équipe 2
        team2 = query.data.replace("select_team2_", "")
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
    
    elif query.data == "cancel":
        # Annulation d'une action
        await query.edit_message_text("❌ Opération annulée.")
    
    elif query.data == "new_prediction":
        # Vérifier l'abonnement avant de lancer une nouvelle prédiction
        is_subscribed = await check_user_subscription(user_id)
        
        if not is_subscribed:
            # Message d'erreur si l'abonnement n'est plus actif
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ *Abonnement requis*\n\n"
                "Votre abonnement à [AL VE CAPITAL](https://t.me/alvecapital1) n'est pas actif.\n"
                "Vous devez être abonné pour utiliser cette fonctionnalité.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Animation de vérification
        await animated_subscription_check(query.message, user_id, edit=True)
        
        # Si on arrive ici, l'abonnement est valide car la fonction animated_subscription_check a retourné True
        # Lancer la sélection des équipes
        await start_team_selection(query.message, context, edit=True)

# Fonction pour démarrer la sélection des équipes (première équipe)
async def start_team_selection(message, context, edit=False, page=0) -> None:
    """Affiche la première page de sélection d'équipe."""
    await show_teams_page(message, context, page, edit, is_team1=True)

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
    
    if edit:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

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
    
    # Vérifier l'abonnement
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
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
        
        # Animation de validation de la cote
        loading_message = await update.message.reply_text(
            f"✅ Cote de *{team1}* enregistrée: *{odds1}*",
            parse_mode='Markdown'
        )
        
        # Demander la cote de l'équipe 2
        await asyncio.sleep(1)
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
    
    # Vérifier l'abonnement
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
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
        
        # Animation de validation de la cote
        loading_message = await update.message.reply_text(
            f"✅ Cote de *{team2}* enregistrée: *{odds2}*",
            parse_mode='Markdown'
        )
        
        # Animation de génération de prédiction
        await asyncio.sleep(0.5)
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
            await asyncio.sleep(0.7)
            await loading_message.edit_text(frame, parse_mode='Markdown')
        
        # Génération de la prédiction
        prediction = predictor.predict_match(team1, team2, odds1, odds2)
        
        if not prediction or "error" in prediction:
            error_msg = prediction.get("error", "Erreur inconnue") if prediction else "Impossible de générer une prédiction"
            
            # Proposer de réessayer
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
        
        # Animation finale avant d'afficher le résultat
        final_frames = [
            "🎯 *Prédiction prête!*",
            "✨ *Affichage des résultats...*"
        ]
        
        for frame in final_frames:
            await asyncio.sleep(0.5)
            await loading_message.edit_text(frame, parse_mode='Markdown')
        
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
    
    # Récupérer la liste des équipes
    teams = get_all_teams()
    
    if not teams:
        await update.message.reply_text("Aucune équipe n'a été trouvée dans la base de données.")
        return
    
    # Formater la liste des équipes
    teams_text = "📋 *Équipes disponibles dans la base de données:*\n\n"
    
    # Grouper les équipes par lettre alphabétique
    teams_by_letter = {}
    for team in teams:
        first_letter = team[0].upper()
        if first_letter not in teams_by_letter:
            teams_by_letter[first_letter] = []
        teams_by_letter[first_letter].append(team)
    
    # Ajouter chaque groupe d'équipes
    for letter in sorted(teams_by_letter.keys()):
        teams_text += f"*{letter}*\n"
        for team in sorted(teams_by_letter[letter]):
            teams_text += f"• {team}\n"
        teams_text += "\n"
    
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
