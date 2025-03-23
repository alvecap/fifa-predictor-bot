import logging
import re
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

# États de conversation pour la sélection des équipes
SELECTING_TEAM1, SELECTING_TEAM2, ENTERING_ODDS = range(3)

# Fonction pour vérifier l'abonnement
async def is_user_subscribed(bot, user_id, chat_id="@alvecapital1"):
    """
    Vérifie si un utilisateur est abonné au canal spécifié
    Retourne (True/False, message d'erreur si applicable)
    """
    try:
        # Vérifier si l'utilisateur est membre du canal
        chat_member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        
        # Statuts indiquant que l'utilisateur est membre
        member_statuses = ['creator', 'administrator', 'member']
        
        if chat_member.status in member_statuses:
            # L'utilisateur est abonné
            return True, None
        else:
            # L'utilisateur n'est pas abonné
            return False, f"Vous n'êtes pas abonné au canal {chat_id}."
    except Exception as e:
        logger.error(f"Erreur lors de la vérification d'abonnement: {e}")
        return False, "Une erreur est survenue lors de la vérification de votre abonnement."

# Fonctions de base
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message quand la commande /start est envoyée."""
    user = update.effective_user
    user_id = update.effective_user.id
    
    # Vérification silencieuse pour les nouveaux utilisateurs
    is_subscribed, _ = await is_user_subscribed(context.bot, user_id)
    
    # Créer les boutons interactifs pour la vérification d'abonnement
    keyboard = [
        [InlineKeyboardButton("📢 Rejoindre le Canal VIP", url="https://t.me/alvecapital1")],
        [InlineKeyboardButton("✅ Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 *Bienvenue {user.first_name} sur FIFA 4x4 Predictor!*\n\n"
        "Notre bot d'analyse vous aide à prédire les résultats des matchs "
        "FIFA 4x4 en utilisant l'intelligence artificielle.\n\n"
        "⚠️ *IMPORTANT*: Pour accéder à toutes les fonctionnalités, vous devez être abonné à notre canal principal.\n\n"
        "1️⃣ Rejoignez @alvecapital1\n"
        "2️⃣ Cliquez sur \"Vérifier mon abonnement\"\n"
        "3️⃣ Commencez à recevoir des prédictions gagnantes!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message d'aide quand la commande /help est envoyée."""
    help_text = """
🔮 *Commandes disponibles*:

• `/start` - Démarrer le bot
• `/help` - Afficher l'aide
• `/predict [Équipe1] vs [Équipe2]` - Obtenir une prédiction de match
• `/odds [Équipe1] vs [Équipe2] [cote1] [cote2]` - Prédiction avec les cotes
• `/teams` - Voir toutes les équipes disponibles
• `/check` - Vérifier l'abonnement au canal

*Exemples d'utilisation:*
`/predict Manchester United vs Chelsea`
`/odds Manchester United vs Chelsea 1.8 3.5`

⚠️ *Important*: Vous devez être abonné au canal @alvecapital1 pour utiliser les fonctionnalités du bot.
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les erreurs."""
    logger.error(f"Une erreur est survenue: {context.error}")
    
    if update:
        # Envoi d'un message à l'utilisateur
        await update.message.reply_text(
            "❌ *Désolé, une erreur s'est produite*. Veuillez réessayer ou contacter l'administrateur.",
            parse_mode='Markdown'
        )

# Commande pour vérifier l'abonnement au canal
async def check_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie si l'utilisateur est abonné au canal @alvecapital1."""
    user_id = update.effective_user.id
    
    is_subscribed, error_message = await is_user_subscribed(context.bot, user_id)
    
    if is_subscribed:
        # L'utilisateur est abonné
        keyboard = [
            [InlineKeyboardButton("🔮 Commencer une prédiction", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ *Félicitations!* Vous êtes bien abonné au canal @alvecapital1.\n\n"
            "Vous pouvez maintenant utiliser toutes les fonctionnalités premium de FIFA 4x4 Predictor.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # L'utilisateur n'est pas abonné
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"❌ {error_message}\n\n"
            "*L'abonnement est obligatoire* pour accéder aux fonctionnalités de FIFA 4x4 Predictor.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# Gestionnaire des clics sur les boutons
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les clics sur les boutons inline."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer()
    
    # Vérification d'abonnement
    if query.data == "verify_subscription":
        is_subscribed, error_message = await is_user_subscribed(context.bot, user_id)
        
        if is_subscribed:
            # L'utilisateur est abonné - Montrer le menu principal
            keyboard = [
                [InlineKeyboardButton("🔮 Nouvelle Prédiction", callback_data="start_prediction")],
                [InlineKeyboardButton("📋 Liste des Équipes", callback_data="show_teams")],
                [InlineKeyboardButton("ℹ️ Comment ça marche", callback_data="how_it_works")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "✅ *Félicitations!* Votre abonnement est vérifié.\n\n"
                "🏆 *FIFA 4x4 PREDICTOR - MENU PRINCIPAL*\n\n"
                "Choisissez une option pour commencer:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            # L'utilisateur n'est pas abonné
            keyboard = [
                [InlineKeyboardButton("📢 Rejoindre le Canal VIP", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ *Abonnement obligatoire*\n\n"
                f"{error_message}\n\n"
                "Pour accéder aux prédictions FIFA 4x4, veuillez d'abord rejoindre notre canal puis cliquer sur 'Vérifier à nouveau'.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    # Démarrer le processus de prédiction
    elif query.data == "start_prediction":
        # Vérifier à nouveau l'abonnement
        is_subscribed, error_message = await is_user_subscribed(context.bot, user_id)
        
        if not is_subscribed:
            keyboard = [
                [InlineKeyboardButton("📢 Rejoindre le Canal VIP", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ *Accès refusé*\n\n"
                "Vous n'êtes plus abonné à notre canal @alvecapital1.\n"
                "Veuillez vous réabonner pour continuer à utiliser ce service.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Afficher le sélecteur d'équipes
        await show_team_selector(update, context)
    
    # Afficher les équipes disponibles
    elif query.data == "show_teams":
        # Vérifier à nouveau l'abonnement
        is_subscribed, error_message = await is_user_subscribed(context.bot, user_id)
        
        if not is_subscribed:
            keyboard = [
                [InlineKeyboardButton("📢 Rejoindre le Canal VIP", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ *Accès refusé*\n\n"
                "Vous n'êtes plus abonné à notre canal @alvecapital1.\n"
                "Veuillez vous réabonner pour continuer à utiliser ce service.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        teams = get_all_teams()
        
        if not teams:
            await query.edit_message_text(
                "⚠️ *Aucune équipe trouvée*\n\n"
                "Aucune équipe n'a été trouvée dans la base de données.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="back_to_menu")]]),
                parse_mode='Markdown'
            )
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
        
        # Si le message est trop long, le diviser
        max_length = 4000
        if len(teams_text) > max_length:
            chunks = [teams_text[i:i+max_length] for i in range(0, len(teams_text), max_length)]
            
            # Envoyer le premier morceau en éditant le message existant
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="back_to_menu")]]
            await query.edit_message_text(
                chunks[0],
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
            # Envoyer les morceaux restants en nouveaux messages
            for chunk in chunks[1:]:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=chunk,
                    parse_mode='Markdown'
                )
        else:
            keyboard = [[InlineKeyboardButton("🔙 Retour", callback_data="back_to_menu")]]
            await query.edit_message_text(
                teams_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    
    # Afficher comment ça marche
    elif query.data == "how_it_works":
        await query.edit_message_text(
            "ℹ️ *Comment utiliser FIFA 4x4 Predictor*\n\n"
            "Notre bot utilise l'intelligence artificielle pour analyser les données historiques des matchs FIFA 4x4 et générer des prédictions précises.\n\n"
            "*📱 Via l'interface de boutons:*\n"
            "1. Cliquez sur 'Nouvelle Prédiction'\n"
            "2. Sélectionnez les équipes qui s'affrontent\n"
            "3. Entrez les cotes (obligatoire)\n"
            "4. Recevez votre prédiction détaillée\n\n"
            "*⌨️ Via les commandes textuelles:*\n"
            "• `/predict Équipe1 vs Équipe2` - Obtenir une prédiction simple (les cotes vous seront demandées)\n"
            "• `/odds Équipe1 vs Équipe2 cote1 cote2` - Prédiction directe avec cotes\n\n"
            "Exemple: `/predict Manchester United vs Chelsea`\n"
            "Exemple: `/odds Arsenal vs Liverpool 1.8 3.5`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="back_to_menu")]]),
            parse_mode='Markdown'
        )
    
    # Retour au menu principal
    elif query.data == "back_to_menu":
        keyboard = [
            [InlineKeyboardButton("🔮 Nouvelle Prédiction", callback_data="start_prediction")],
            [InlineKeyboardButton("📋 Liste des Équipes", callback_data="show_teams")],
            [InlineKeyboardButton("ℹ️ Comment ça marche", callback_data="how_it_works")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🏆 *FIFA 4x4 PREDICTOR - MENU PRINCIPAL*\n\n"
            "Choisissez une option pour commencer:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Gestion de la navigation dans le sélecteur d'équipes
    elif query.data.startswith("team_page_"):
        page = int(query.data.split("_")[-1])
        context.user_data["current_page"] = page
        await show_team_page(update, context)
    
    # Gestion de la sélection d'équipe 1
    elif query.data.startswith("select_team1_"):
        team_name = query.data[12:]  # Enlever "select_team1_"
        context.user_data["team1"] = team_name
        context.user_data["selecting"] = "team2"
        await show_team_selector(update, context, "team2")
    
    # Gestion de la sélection d'équipe 2
    elif query.data.startswith("select_team2_"):
        team_name = query.data[12:]  # Enlever "select_team2_"
        team1 = context.user_data.get("team1", "")
        
        # Vérifier que les équipes sont différentes
        if team_name == team1:
            await query.edit_message_text(
                "⚠️ *Équipes identiques*\n\n"
                "Vous devez sélectionner deux équipes différentes.\n\n"
                f"Vous avez déjà sélectionné *{team1}* comme première équipe.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Choisir une autre équipe", callback_data="back_to_team2")]]),
                parse_mode='Markdown'
            )
            return
        
        context.user_data["team2"] = team_name
        
        # Passer à l'étape des cotes (obligatoire)
        await show_odds_entry(update, context)
    
    # Gestion du retour à la sélection de l'équipe 2
    elif query.data == "back_to_team2":
        context.user_data["selecting"] = "team2"
        await show_team_selector(update, context, "team2")
    
    # Gestion de l'entrée des cotes
    elif query.data == "enter_odds":
        context.user_data["entering_odds"] = True
        
        await query.edit_message_text(
            "💰 *Entrez les cotes*\n\n"
            "Veuillez envoyer les cotes au format suivant:\n"
            "`cote1 cote2`\n\n"
            "Exemple: `1.85 3.4`\n\n"
            "Ces cotes correspondent respectivement à:\n"
            f"• *{context.user_data.get('team1', 'Équipe 1')}*: cote1\n"
            f"• *{context.user_data.get('team2', 'Équipe 2')}*: cote2",
            parse_mode='Markdown'
        )
        
        return ENTERING_ODDS
    
    # Prédiction via bouton (depuis un message avec vs)
    elif query.data.startswith("predict_"):
        # Extraire les équipes du callback_data
        data_parts = query.data.split("_")
        if len(data_parts) >= 3:
            team1 = data_parts[1]
            team2 = "_".join(data_parts[2:])  # Gérer les noms d'équipe avec des underscores
            
            # Vérifier l'abonnement
            is_subscribed, error_message = await is_user_subscribed(context.bot, user_id)
            
            if not is_subscribed:
                keyboard = [
                    [InlineKeyboardButton("📢 Rejoindre le Canal VIP", url="https://t.me/alvecapital1")],
                    [InlineKeyboardButton("🔄 Vérifier mon abonnement", callback_data="verify_subscription")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "❌ *Accès refusé*\n\n"
                    "Vous devez être abonné à notre canal @alvecapital1 pour accéder aux prédictions.\n\n"
                    "Rejoignez le canal puis vérifiez votre abonnement pour continuer.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            
            # Stocker les équipes et demander les cotes (obligatoire)
            context.user_data["team1"] = team1
            context.user_data["team2"] = team2
            
            # Passer à l'étape des cotes
            context.user_data["entering_odds"] = True
            
            await query.edit_message_text(
                f"⚽ *Match sélectionné: {team1} vs {team2}*\n\n"
                "💰 *Entrez les cotes*\n\n"
                "Veuillez envoyer les cotes au format suivant:\n"
                "`cote1 cote2`\n\n"
                "Exemple: `1.85 3.4`\n\n"
                "Ces cotes correspondent respectivement à:\n"
                f"• *{team1}*: cote1\n"
                f"• *{team2}*: cote2",
                parse_mode='Markdown'
            )
            
            return ENTERING_ODDS
    
    # Annuler une opération
    elif query.data == "cancel":
        await query.edit_message_text("❌ *Opération annulée*.", parse_mode='Markdown')

# Fonction pour afficher le sélecteur d'équipes
async def show_team_selector(update: Update, context: ContextTypes.DEFAULT_TYPE, selecting_team="team1"):
    """Affiche le sélecteur d'équipes avec pagination."""
    context.user_data["selecting"] = selecting_team
    context.user_data["current_page"] = 0
    
    # Récupérer toutes les équipes
    teams = get_all_teams()
    context.user_data["all_teams"] = teams
    
    await show_team_page(update, context)

# Fonction pour afficher une page d'équipes
async def show_team_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche une page du sélecteur d'équipes."""
    query = update.callback_query
    
    teams = context.user_data.get("all_teams", [])
    current_page = context.user_data.get("current_page", 0)
    selecting = context.user_data.get("selecting", "team1")
    
    # Configurer la pagination
    teams_per_page = 8
    total_pages = (len(teams) + teams_per_page - 1) // teams_per_page
    
    start_idx = current_page * teams_per_page
    end_idx = min(start_idx + teams_per_page, len(teams))
    current_teams = teams[start_idx:end_idx]
    
    # Créer les boutons pour les équipes
    keyboard = []
    
    # Ajouter une rangée pour chaque équipe
    for team in current_teams:
        callback_data = f"select_{selecting}_{team}"
        keyboard.append([InlineKeyboardButton(team, callback_data=callback_data)])
    
    # Ajouter les boutons de navigation
    nav_row = []
    
    if current_page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Précédent", callback_data=f"team_page_{current_page-1}"))
    
    if current_page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Suivant ➡️", callback_data=f"team_page_{current_page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
    
    # Ajouter un bouton de retour
    keyboard.append([InlineKeyboardButton("🔙 Retour au menu", callback_data="back_to_menu")])
    
    # Titre du message
    title = f"🔍 *Sélectionnez l'équipe {1 if selecting == 'team1' else 2}*\n\n"
    
    if selecting == "team2" and "team1" in context.user_data:
        title += f"Équipe 1: *{context.user_data['team1']}*\n\n"
    
    title += f"Page {current_page + 1}/{total_pages if total_pages > 0 else 1}"
    
    await query.edit_message_text(
        title,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# Fonction pour afficher l'entrée des cotes
async def show_odds_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche l'écran pour entrer les cotes (obligatoire)."""
    query = update.callback_query
    team1 = context.user_data.get("team1", "")
    team2 = context.user_data.get("team2", "")
    
    keyboard = [
        [InlineKeyboardButton("💰 Entrer les cotes", callback_data="enter_odds")],
        [InlineKeyboardButton("🔙 Revenir à la sélection", callback_data="back_to_team2")]
    ]
    
    await query.edit_message_text(
        f"⚽ *Match sélectionné: {team1} vs {team2}*\n\n"
        "💰 *Entrez les cotes des bookmakers pour une prédiction précise*\n\n"
        "_Conseil_: Les cotes *améliorent significativement* la qualité des prédictions en tenant compte des probabilités du marché.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# Fonction pour gérer l'entrée des cotes
async def handle_odds_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère l'entrée des cotes par l'utilisateur."""
    # Vérifier si l'utilisateur est en train d'entrer des cotes
    if not context.user_data.get("entering_odds", False):
        return ConversationHandler.END
    
    # Récupérer le texte et les équipes
    text = update.message.text
    team1 = context.user_data.get("team1", "")
    team2 = context.user_data.get("team2", "")
    
    # Essayer de parser les cotes
    odds_pattern = r'(\d+\.?\d*)\s+(\d+\.?\d*)'
    match = re.match(odds_pattern, text)
    
    if not match:
        await update.message.reply_text(
            "⚠️ *Format de cotes invalide*\n\n"
            "Veuillez entrer deux nombres séparés par un espace.\n\n"
            "Exemple: `1.85 3.4`",
            parse_mode='Markdown'
        )
        return ENTERING_ODDS
    
    odds1 = float(match.group(1))
    odds2 = float(match.group(2))
    
    # Vérifier que les cotes sont valides
    if odds1 < 1.01 or odds2 < 1.01:
        await update.message.reply_text(
            "⚠️ *Cotes invalides*\n\n"
            "Les cotes doivent être supérieures à 1.01.\n\n"
            "Veuillez réessayer:",
            parse_mode='Markdown'
        )
        return ENTERING_ODDS
    
    # Réinitialiser l'état d'entrée des cotes
    context.user_data["entering_odds"] = False
    
    # Générer la prédiction avec les cotes
    await generate_prediction(update, context, team1, team2, odds1, odds2)
    
    return ConversationHandler.END

# Fonction pour générer et afficher une prédiction
async def generate_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE, team1, team2, odds1=None, odds2=None):
    """Génère et affiche une prédiction pour deux équipes données."""
    # Déterminer s'il s'agit d'un message ou d'un callback query
    if update.callback_query:
        message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏳ *Analyse en cours*, veuillez patienter...",
            parse_mode='Markdown'
        )
    else:
        message = await update.message.reply_text(
            "⏳ *Analyse en cours*, veuillez patienter...",
            parse_mode='Markdown'
        )
    
    # Obtenir la prédiction
    prediction = predictor.predict_match(team1, team2, odds1, odds2)
    
    # Si la prédiction a échoué
    if not prediction or "error" in prediction:
        await message.edit_text(
            f"❌ *Impossible de générer une prédiction*:\n"
            f"{prediction.get('error', 'Erreur inconnue')}",
            parse_mode='Markdown'
        )
        return
    
    # Formater et envoyer la prédiction
    prediction_text = format_prediction_message(prediction)
    
    keyboard = [
        [InlineKeyboardButton("🔮 Nouvelle Prédiction", callback_data="start_prediction")],
        [InlineKeyboardButton("🔙 Retour au menu", callback_data="back_to_menu")]
    ]
    
    await message.edit_text(
        prediction_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # Enregistrer la prédiction dans les logs
    # Enregistrer la prédiction dans les logs
    user = update.effective_user
    save_prediction_log(
        user_id=user.id,
        username=user.username,
        team1=team1,
        team2=team2,
        odds1=odds1,
        odds2=odds2,
        prediction_result=prediction
    )

# Traitement des prédictions simples
async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Traite la commande /predict pour les prédictions de match."""
    user_id = update.effective_user.id
    
    # Vérifier l'abonnement
    is_subscribed, error_message = await is_user_subscribed(context.bot, user_id)
    
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("📢 Rejoindre le Canal VIP", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("✅ Vérifier mon abonnement", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ *Accès refusé*\n\n"
            "Vous devez être abonné à notre canal @alvecapital1 pour accéder aux prédictions.\n\n"
            "Rejoignez le canal puis vérifiez votre abonnement pour continuer.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Extraire les équipes du message
    message_text = update.message.text[9:].strip()  # Enlever '/predict '
    
    # Essayer de trouver les noms d'équipes séparés par "vs" ou "contre"
    teams = re.split(r'\s+(?:vs|contre|VS|CONTRE)\s+', message_text)
    
    if len(teams) != 2 or not teams[0] or not teams[1]:
        # Si le format n'est pas correct, demander à l'utilisateur de réessayer
        await update.message.reply_text(
            "❌ *Format incorrect*\n\n"
            "Veuillez utiliser: `/predict Équipe1 vs Équipe2`\n"
            "Exemple: `/predict Manchester United vs Chelsea`",
            parse_mode='Markdown'
        )
        return
    
    team1 = teams[0].strip()
    team2 = teams[1].strip()
    
    # Stocker les équipes pour demander les cotes (obligatoire)
    context.user_data["team1"] = team1
    context.user_data["team2"] = team2
    context.user_data["entering_odds"] = True
    
    # Demander les cotes à l'utilisateur
    await update.message.reply_text(
        f"⚽ *Match sélectionné: {team1} vs {team2}*\n\n"
        "💰 *Entrez les cotes*\n\n"
        "Veuillez envoyer les cotes au format suivant:\n"
        "`cote1 cote2`\n\n"
        "Exemple: `1.85 3.4`\n\n"
        "Ces cotes correspondent respectivement à:\n"
        f"• *{team1}*: cote1\n"
        f"• *{team2}*: cote2",
        parse_mode='Markdown'
    )
    
    return ENTERING_ODDS

# Traitement des prédictions avec cotes
async def odds_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Traite la commande /odds pour les prédictions de match avec cotes."""
    user_id = update.effective_user.id
    
    # Vérifier l'abonnement
    is_subscribed, error_message = await is_user_subscribed(context.bot, user_id)
    
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("📢 Rejoindre le Canal VIP", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("✅ Vérifier mon abonnement", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ *Accès refusé*\n\n"
            "Vous devez être abonné à notre canal @alvecapital1 pour accéder aux prédictions.\n\n"
            "Rejoignez le canal puis vérifiez votre abonnement pour continuer.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Extraire les équipes et les cotes du message
    message_parts = update.message.text[6:].strip().split()  # Enlever '/odds '
    
    # Trouver l'index de "vs" ou "contre"
    separator_index = -1
    for i, part in enumerate(message_parts):
        if part.lower() in ["vs", "contre"]:
            separator_index = i
            break
    
    if separator_index == -1 or separator_index == 0 or separator_index == len(message_parts) - 1:
        # Si le format n'est pas correct, demander à l'utilisateur de réessayer
        await update.message.reply_text(
            "❌ *Format incorrect*\n\n"
            "Veuillez utiliser: `/odds Équipe1 vs Équipe2 cote1 cote2`\n"
            "Exemple: `/odds Manchester United vs Chelsea 1.8 3.5`",
            parse_mode='Markdown'
        )
        return
    
    # Extraire les noms d'équipes
    team1 = " ".join(message_parts[:separator_index]).strip()
    
    # Chercher les cotes à la fin
    odds_pattern = r'(\d+\.\d+)'
    odds_matches = re.findall(odds_pattern, " ".join(message_parts[separator_index+1:]))
    
    if len(odds_matches) < 2:
        # Si les cotes ne sont pas correctement formatées
        context.user_data["team1"] = team1
        team2 = " ".join(message_parts[separator_index+1:]).strip()
        context.user_data["team2"] = team2
        context.user_data["entering_odds"] = True
        
        # Demander les cotes à l'utilisateur
        await update.message.reply_text(
            f"⚽ *Match sélectionné: {team1} vs {team2}*\n\n"
            "💰 *Entrez les cotes*\n\n"
            "Veuillez envoyer les cotes au format suivant:\n"
            "`cote1 cote2`\n\n"
            "Exemple: `1.85 3.4`\n\n"
            "Ces cotes correspondent respectivement à:\n"
            f"• *{team1}*: cote1\n"
            f"• *{team2}*: cote2",
            parse_mode='Markdown'
        )
        
        return ENTERING_ODDS
    else:
        # Extraire les deux dernières cotes trouvées
        odds1 = float(odds_matches[-2])
        odds2 = float(odds_matches[-1])
        
        # Extraire le nom de l'équipe 2 en enlevant les cotes
        team2_parts = message_parts[separator_index+1:]
        team2_text = " ".join(team2_parts)
        for odd in odds_matches[-2:]:
            team2_text = team2_text.replace(odd, "").strip()
        team2 = team2_text.rstrip("- ,").strip()
    
    # Afficher un message de chargement
    loading_message = await update.message.reply_text(
        "⏳ *Analyse en cours*, veuillez patienter...",
        parse_mode='Markdown'
    )
    
    # Obtenir la prédiction avec les cotes
    prediction = predictor.predict_match(team1, team2, odds1, odds2)
    
    # Si la prédiction a échoué
    if not prediction or "error" in prediction:
        await loading_message.edit_text(
            f"❌ *Impossible de générer une prédiction*:\n"
            f"{prediction.get('error', 'Erreur inconnue')}",
            parse_mode='Markdown'
        )
        return
    
    # Formater et envoyer la prédiction
    prediction_text = format_prediction_message(prediction)
    
    keyboard = [
        [InlineKeyboardButton("🔮 Nouvelle Prédiction", callback_data="start_prediction")],
        [InlineKeyboardButton("🔙 Menu Principal", callback_data="back_to_menu")]
    ]
    
    await loading_message.edit_text(
        prediction_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # Enregistrer la prédiction dans les logs
    user = update.message.from_user
    save_prediction_log(
        user_id=user.id,
        username=user.username,
        team1=team1,
        team2=team2,
        odds1=odds1,
        odds2=odds2,
        prediction_result=prediction
    )

# Fonction pour réagir aux messages non reconnus comme commandes
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Répond aux messages qui ne sont pas des commandes."""
    message_text = update.message.text.strip()
    
    # Rechercher si le message ressemble à une demande de prédiction
    if " vs " in message_text or " contre " in message_text:
        # Extraire les équipes
        teams = re.split(r'\s+(?:vs|contre|VS|CONTRE)\s+', message_text)
        
        if len(teams) == 2 and teams[0] and teams[1]:
            # Créer des boutons pour confirmer la prédiction
            keyboard = [
                [InlineKeyboardButton("✅ Prédire ce match", callback_data=f"predict_{teams[0]}_{teams[1]}")],
                [InlineKeyboardButton("❌ Annuler", callback_data="cancel")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Souhaitez-vous obtenir une prédiction pour le match:\n\n"
                f"*{teams[0]} vs {teams[1]}*?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
    
    # Message par défaut si aucune action n'est déclenchée
    keyboard = [
        [InlineKeyboardButton("🔮 Faire une prédiction", callback_data="start_prediction")],
        [InlineKeyboardButton("❓ Aide", callback_data="how_it_works")],
        [InlineKeyboardButton("✅ Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Je ne comprends pas cette commande. Utilisez l'un des boutons ci-dessous ou envoyez /help pour voir les commandes disponibles.",
        reply_markup=reply_markup
    )

# Fonction pour lister les équipes disponibles
async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des équipes disponibles dans la base de données."""
    user_id = update.effective_user.id
    
    # Vérifier l'abonnement
    is_subscribed, error_message = await is_user_subscribed(context.bot, user_id)
    
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("📢 Rejoindre le Canal VIP", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("✅ Vérifier mon abonnement", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ *Accès refusé*\n\n"
            "Vous devez être abonné à notre canal @alvecapital1 pour accéder à cette fonctionnalité.\n\n"
            "Rejoignez le canal puis vérifiez votre abonnement pour continuer.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Récupérer la liste des équipes
    teams = get_all_teams()
    
    if not teams:
        await update.message.reply_text(
            "⚠️ Aucune équipe n'a été trouvée dans la base de données.",
            parse_mode='Markdown'
        )
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

# Fonction principale
def main() -> None:
    """Démarre le bot."""
    try:
        # Créer l'application
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Ajouter le gestionnaire de conversation pour les cotes
        conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(button_click, pattern="^enter_odds$"),
                CommandHandler("predict", predict_command),
                CallbackQueryHandler(button_click, pattern="^predict_")
            ],
            states={
                ENTERING_ODDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_odds_input)],
            },
            fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        )
        
        application.add_handler(conv_handler)

        # Ajouter les gestionnaires de commandes
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("odds", odds_command))
        application.add_handler(CommandHandler("teams", teams_command))
        application.add_handler(CommandHandler("check", check_subscription_command))
        
        # Ajouter le gestionnaire pour les clics sur les boutons
        application.add_handler(CallbackQueryHandler(button_click))
        
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
