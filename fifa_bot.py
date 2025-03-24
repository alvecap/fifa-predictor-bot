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
ODDS_INPUT = 3

# Fonctions de base
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message quand la commande /start est envoyée."""
    user = update.effective_user
    context.user_data["username"] = user.username
    
    # Message de bienvenue personnalisé avec un bouton unique
    welcome_text = f"👋 *AL VE*, Bienvenue sur *FIFA 4x4 Predictor*!\n\n"
    welcome_text += "Je vous aide à prédire les résultats de matchs de football FIFA 4x4 "
    welcome_text += "en me basant sur des données historiques.\n\n"
    welcome_text += "⚠️ Pour utiliser toutes les fonctionnalités, vous devez être abonné "
    welcome_text += f"à notre canal [@alvecapital1](https://t.me/alvecapital1)."
    
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
        "1️⃣ Rejoignez [@alvecapital1](https://t.me/alvecapital1)\n"
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
    
    # Message initial
    msg = await update.message.reply_text(
        "🔄 *Vérification de votre abonnement en cours...*",
        parse_mode='Markdown'
    )
    
    # Animation de vérification (3 points de suspension)
    for i in range(3):
        await msg.edit_text(
            f"🔄 *Vérification de votre abonnement en cours{'.' * (i+1)}*",
            parse_mode='Markdown'
        )
        await asyncio.sleep(0.7)
    
    # Effectuer la vérification
    is_subscribed = await check_user_subscription(user_id)
    
    if is_subscribed:
        # Afficher un message de succès
        await msg.edit_text(
            "✅ *Abonnement vérifié !*\n\n"
            "Vous êtes bien abonné à [@alvecapital1](https://t.me/alvecapital1).\n"
            "Toutes les fonctionnalités sont désormais accessibles.",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Message avec bouton pour commencer une prédiction
        keyboard = [
            [InlineKeyboardButton("🔮 Faire une prédiction", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🏆 *Que souhaitez-vous faire ?*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Afficher un message d'erreur
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔍 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            "❌ *Abonnement non détecté*\n\n"
            "Vous n'êtes pas encore abonné à [@alvecapital1](https://t.me/alvecapital1).\n\n"
            "*Instructions:*\n"
            "1️⃣ Cliquez sur le bouton 'Rejoindre le canal'\n"
            "2️⃣ Abonnez-vous au canal\n"
            "3️⃣ Revenez ici et cliquez sur 'Vérifier à nouveau'",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

# Lancer une prédiction directement avec la commande predict
async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance le processus de prédiction quand la commande /predict est envoyée."""
    user_id = update.effective_user.id
    context.user_data["user_id"] = user_id
    
    # Vérifier l'abonnement avant de procéder
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
        return
    
    # Lancer la sélection des équipes
    return await start_team_selection(update.message)

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
        # Message initial
        await query.edit_message_text(
            "🔄 *Vérification de votre abonnement en cours...*",
            parse_mode='Markdown'
        )
        
        # Animation de vérification (3 points de suspension)
        for i in range(3):
            await query.edit_message_text(
                f"🔄 *Vérification de votre abonnement en cours{'.' * (i+1)}*",
                parse_mode='Markdown'
            )
            await asyncio.sleep(0.7)
        
        # Effectuer la vérification
        is_subscribed = await check_user_subscription(user_id)
        
        if is_subscribed:
            # Afficher un message de succès
            await query.edit_message_text(
                "✅ *Abonnement vérifié !*\n\n"
                "Vous êtes bien abonné à [@alvecapital1](https://t.me/alvecapital1).\n"
                "Toutes les fonctionnalités sont désormais accessibles.",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            # Nouveau message avec bouton pour commencer une prédiction
            keyboard = [
                [InlineKeyboardButton("🔮 Faire une prédiction", callback_data="start_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "🏆 *Que souhaitez-vous faire ?*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            # Afficher un message d'erreur
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔍 Vérifier à nouveau", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ *Abonnement non détecté*\n\n"
                "Vous n'êtes pas encore abonné à [@alvecapital1](https://t.me/alvecapital1).\n\n"
                "*Instructions:*\n"
                "1️⃣ Cliquez sur le bouton 'Rejoindre le canal'\n"
                "2️⃣ Abonnez-vous au canal\n"
                "3️⃣ Revenez ici et cliquez sur 'Vérifier à nouveau'",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
    
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
                "Votre abonnement à [@alvecapital1](https://t.me/alvecapital1) n'est pas actif.\n"
                "Vous devez être abonné pour utiliser cette fonctionnalité.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Lancer la sélection des équipes
        await start_team_selection(query.message, edit=True)
    
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
                "Votre abonnement à [@alvecapital1](https://t.me/alvecapital1) n'est plus actif.\n"
                "Vous devez être abonné pour continuer cette action.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Extraire le nom de l'équipe 1
        team1 = query.data.replace("select_team1_", "")
        context.user_data["team1"] = team1
        
        # Obtenir la liste des équipes pour la sélection de l'équipe 2
        teams = get_all_teams()
        
        # Filtrer pour éviter que l'équipe 1 soit disponible
        teams = [t for t in teams if t != team1]
        
        # Créer des boutons pour les équipes populaires (max 8)
        popular_teams = teams[:8] if len(teams) > 8 else teams
        team_buttons = []
        row = []
        
        for i, team in enumerate(popular_teams):
            row.append(InlineKeyboardButton(team, callback_data=f"select_team2_{team}"))
            if len(row) == 2 or i == len(popular_teams) - 1:
                team_buttons.append(row)
                row = []
        
        # Ajouter bouton pour retour
        team_buttons.append([InlineKeyboardButton("◀️ Retour", callback_data="start_prediction")])
        
        reply_markup = InlineKeyboardMarkup(team_buttons)
        
        await query.edit_message_text(
            f"🏆 *Sélection des équipes*\n\n"
            f"Équipe 1: *{team1}*\n\n"
            f"Veuillez maintenant sélectionner la *deuxième équipe* pour votre prédiction:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
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
                "Votre abonnement à [@alvecapital1](https://t.me/alvecapital1) n'est plus actif.\n"
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
        
        # Demander directement les cotes (obligatoires)
        await query.edit_message_text(
            f"💰 *Saisie des cotes (obligatoire)*\n\n"
            f"Match: *{team1}* vs *{team2}*\n\n"
            f"Veuillez envoyer les cotes sous format:\n"
            f"{team1}: [cote1], {team2}: [cote2]\n\n"
            f"Exemple: `{team1}: 1.85, {team2}: 2.35`\n\n"
            f"_Saisissez les cotes directement dans votre message_",
            parse_mode='Markdown'
        )
        
        # Passer en mode conversation pour recevoir les cotes
        context.user_data["awaiting_odds"] = True
        context.user_data["odds_for_match"] = f"{team1} vs {team2}"
        
        return ODDS_INPUT
    
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
                "Votre abonnement à [@alvecapital1](https://t.me/alvecapital1) n'est pas actif.\n"
                "Vous devez être abonné pour utiliser cette fonctionnalité.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Lancer la sélection des équipes
        await start_team_selection(query.message, edit=True)

# Fonction pour démarrer la sélection des équipes
async def start_team_selection(message, edit=False) -> None:
    """Affiche les options de sélection d'équipe."""
    teams = get_all_teams()
    
    # Créer des boutons pour les équipes populaires (max 8)
    popular_teams = teams[:8] if len(teams) > 8 else teams
    team_buttons = []
    row = []
    
    for i, team in enumerate(popular_teams):
        row.append(InlineKeyboardButton(team, callback_data=f"select_team1_{team}"))
        if len(row) == 2 or i == len(popular_teams) - 1:
            team_buttons.append(row)
            row = []
    
    # Ajouter bouton pour suivant
    team_buttons.append([InlineKeyboardButton("▶️ Suivant", callback_data="next_teams")])
    
    reply_markup = InlineKeyboardMarkup(team_buttons)
    
    text = (
        "🏆 *Sélection des équipes*\n\n"
        "Veuillez sélectionner la *première équipe* pour votre prédiction:"
    )
    
    if edit:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Gestionnaire des entrées de cotes
async def handle_odds_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gère la saisie des cotes par l'utilisateur."""
    # Vérifier si l'utilisateur est en train de saisir des cotes
    if not context.user_data.get("awaiting_odds"):
        return ConversationHandler.END
    
    # Vérifier l'abonnement
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
        return ConversationHandler.END
    
    user_input = update.message.text
    team1 = context.user_data.get("team1", "")
    team2 = context.user_data.get("team2", "")
    
    # Extraire les cotes du message
    # Rechercher des patterns comme "team1: 1.85, team2: 2.35" ou simplement "1.85, 2.35"
    cotes_pattern = r'(\d+\.\d+)'
    cotes_matches = re.findall(cotes_pattern, user_input)
    
    if len(cotes_matches) < 2:
        # Pas assez de cotes trouvées
        await update.message.reply_text(
            "❌ *Format de cotes incorrect*\n\n"
            f"Veuillez envoyer les cotes sous format:\n"
            f"{team1}: [cote1], {team2}: [cote2]\n\n"
            f"Exemple: `{team1}: 1.85, {team2}: 2.35`\n\n"
            f"Les cotes sont *obligatoires* pour obtenir une prédiction précise.",
            parse_mode='Markdown'
        )
        return ODDS_INPUT
    
    # Récupérer les deux premières cotes trouvées
    odds1 = float(cotes_matches[0])
    odds2 = float(cotes_matches[1])
    
    # Vérifier les valeurs des cotes
    if odds1 < 1.01 or odds2 < 1.01:
        await update.message.reply_text(
            "❌ *Valeurs de cotes invalides*\n\n"
            "Les cotes doivent être supérieures à 1.01.",
            parse_mode='Markdown'
        )
        return ODDS_INPUT
    
    # Confirmer la réception des cotes
    context.user_data["odds1"] = odds1
    context.user_data["odds2"] = odds2
    context.user_data["awaiting_odds"] = False
    
    # Afficher un message de chargement
    loading_message = await update.message.reply_text(
        "⏳ *Analyse en cours...*\n\n"
        "Nous récupérons les données et calculons la prédiction pour votre match.\n"
        "Veuillez patienter un moment.",
        parse_mode='Markdown'
    )
    
    # Animation de chargement
    for i in range(3):
        await loading_message.edit_text(
            f"⏳ *Analyse en cours{'.' * (i+1)}*\n\n"
            f"Nous analysons les performances de *{team1}* et *{team2}*.\n"
            f"Veuillez patienter un moment.",
            parse_mode='Markdown'
        )
        await asyncio.sleep(0.8)
    
    # Générer la prédiction avec les cotes
    prediction = predictor.predict_match(team1, team2, odds1, odds2)
    
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

# Gérer les messages directs (pour éviter le /predict Équipe1 vs Équipe2)
# Gérer les messages directs (pour éviter le /predict Équipe1 vs Équipe2)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Répond aux messages qui ne sont pas des commandes."""
    # Vérifier l'abonnement avant de traiter
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        await send_subscription_required(update.message)
        return
    
    # Si l'utilisateur attend des cotes pour un match
    if context.user_data.get("awaiting_odds"):
        return await handle_odds_input(update, context)
    
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
            entry_points=[
                CallbackQueryHandler(button_callback, pattern="select_team2_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
            ],
            states={
                ODDS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_odds_input)]
            },
            fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
        )
        application.add_handler(conv_handler)
        
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
