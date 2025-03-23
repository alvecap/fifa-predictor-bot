import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
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

# États de conversation supplémentaires
VERIFY_SUBSCRIPTION = 3
SUBSCRIPTION_VERIFIED = 4

# Fonctions de base
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message quand la commande /start est envoyée."""
    user = update.effective_user
    context.user_data["username"] = user.username
    
    # Afficher un message de bienvenue personnalisé
    welcome_message = WELCOME_MESSAGE.replace("👋", f"👋 *{user.first_name}*,")
    await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    # Vérifier immédiatement l'abonnement
    await check_subscription_status(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message d'aide quand la commande /help est envoyée."""
    await update.message.reply_text(HELP_MESSAGE, parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les erreurs."""
    logger.error(f"Une erreur est survenue: {context.error}")
    
    if update:
        # Envoi d'un message à l'utilisateur
        try:
            await update.effective_message.reply_text(
                "Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur."
            )
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du message d'erreur: {e}")

# Vérification d'abonnement
async def check_subscription_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie le statut d'abonnement et envoie un message approprié."""
    if not update or not update.effective_user:
        logger.error("Mise à jour ou utilisateur manquant lors de la vérification d'abonnement")
        return
        
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Enregistrer l'ID utilisateur dans le contexte
    context.user_data["user_id"] = user_id
    
    # Vérifier l'abonnement
    is_subscribed = await check_user_subscription(user_id)
    
    if is_subscribed:
        # Utilisateur déjà abonné
        keyboard = [
            [InlineKeyboardButton("📊 Faire une prédiction", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.reply_text(
            "✅ *Votre abonnement est actif!*\n\n"
            "Vous avez accès à toutes les fonctionnalités premium de *FIFA 4x4 Predictor*.\n"
            "Utilisez les boutons ci-dessous pour commencer.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Utilisateur non abonné, proposer de s'abonner
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier mon abonnement", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.reply_text(
            "⚠️ *Vérification d'abonnement nécessaire*\n\n"
            "Pour utiliser le *FIFA 4x4 Predictor*, vous devez être abonné à notre canal.\n\n"
            "1️⃣ Rejoignez [@alvecapital1](https://t.me/alvecapital1)\n"
            "2️⃣ Cliquez sur '🔄 Vérifier mon abonnement'\n\n"
            "*Avantages de l'abonnement:*\n"
            "• 🎯 Prédictions précises en temps réel\n"
            "• 📊 Analyses statistiques détaillées\n"
            "• 💰 Optimisation des paris sportifs",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

# Commande pour vérifier l'abonnement au canal
async def check_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie si l'utilisateur est abonné au canal @alvecapital1."""
    await check_subscription_status(update, context)

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
        # Vérifier l'abonnement
        is_subscribed = await check_user_subscription(user_id)
        
        if is_subscribed:
            # Abonnement vérifié avec succès
            keyboard = [
                [InlineKeyboardButton("📊 Faire une prédiction", callback_data="start_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "✅ *Félicitations!* Votre abonnement est vérifié.\n\n"
                "Vous avez maintenant accès à toutes les fonctionnalités premium de *FIFA 4x4 Predictor*.\n"
                "Utilisez le bouton ci-dessous pour commencer vos prédictions.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            # Utilisateur toujours non abonné
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ *Abonnement non détecté*\n\n"
                "Vous n'êtes pas encore abonné à [@alvecapital1](https://t.me/alvecapital1).\n\n"
                "Pour accéder aux prédictions, veuillez:\n"
                "1️⃣ Cliquer sur le bouton 'Rejoindre le canal'\n"
                "2️⃣ S'abonner au canal\n"
                "3️⃣ Revenir ici et cliquer sur 'Vérifier à nouveau'",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
    
    elif query.data == "start_prediction":
        # Vérifier que l'abonnement est toujours actif
        is_subscribed = await check_user_subscription(user_id)
        
        if not is_subscribed:
            # L'abonnement n'est plus actif
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier mon abonnement", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ *Abonnement expiré ou non détecté*\n\n"
                "Votre abonnement à [@alvecapital1](https://t.me/alvecapital1) n'est plus actif.\n"
                "Veuillez vous réabonner pour continuer à utiliser le service.",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
        # Démarrer la sélection d'équipes
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
        
        # Ajouter bouton pour recherche personnalisée
        team_buttons.append([InlineKeyboardButton("🔍 Recherche manuelle", callback_data="manual_search")])
        
        reply_markup = InlineKeyboardMarkup(team_buttons)
        
        await query.edit_message_text(
            "🏆 *Sélection des équipes*\n\n"
            "Veuillez sélectionner la *première équipe* pour votre prédiction:\n\n"
            "Vous pouvez choisir parmi les équipes populaires ci-dessous ou utiliser la recherche manuelle.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("select_team1_"):
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
        
        # Ajouter bouton pour recherche personnalisée et retour
        team_buttons.append([InlineKeyboardButton("🔍 Recherche manuelle", callback_data="manual_search_team2")])
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
        
        # Proposer d'ajouter les cotes
        keyboard = [
            [
                InlineKeyboardButton("✅ Ajouter des cotes", callback_data="add_odds"),
                InlineKeyboardButton("❌ Sans cotes", callback_data="no_odds")
            ],
            [InlineKeyboardButton("◀️ Retour", callback_data=f"select_team1_{team1}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🏆 *Match sélectionné*: *{team1}* vs *{team2}*\n\n"
            f"Souhaitez-vous ajouter les cotes pour améliorer la précision de la prédiction?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data == "add_odds":
        # Demander les cotes
        team1 = context.user_data.get("team1", "")
        team2 = context.user_data.get("team2", "")
        
        if not team1 or not team2:
            await query.edit_message_text(
                "❌ *Erreur de sélection*\n\n"
                "Veuillez recommencer la procédure de sélection des équipes.",
                parse_mode='Markdown'
            )
            return
        
        # Passer en mode conversation pour recevoir les cotes
        context.user_data["awaiting_odds"] = True
        
        await query.edit_message_text(
            f"💰 *Saisie des cotes*\n\n"
            f"Match: *{team1}* vs *{team2}*\n\n"
            f"Veuillez envoyer les cotes sous format:\n"
            f"{team1}: [cote1], {team2}: [cote2]\n\n"
            f"Exemple: `{team1}: 1.85, {team2}: 2.35`",
            parse_mode='Markdown'
        )
        
        return ODDS_INPUT
    
    elif query.data == "no_odds":
        # Générer une prédiction sans cotes
        team1 = context.user_data.get("team1", "")
        team2 = context.user_data.get("team2", "")
        
        if not team1 or not team2:
            await query.edit_message_text(
                "❌ *Erreur de sélection*\n\n"
                "Veuillez recommencer la procédure de sélection des équipes.",
                parse_mode='Markdown'
            )
            return
        
        # Afficher un message de chargement
        await query.edit_message_text(
            "⏳ *Analyse en cours...*\n\n"
            "Nous récupérons les données et calculons la prédiction pour votre match.\n"
            "Veuillez patienter un moment.",
            parse_mode='Markdown'
        )
        
        # Générer la prédiction
        prediction = predictor.predict_match(team1, team2)
        
        if not prediction or "error" in prediction:
            error_msg = prediction.get("error", "Erreur inconnue") if prediction else "Impossible de générer une prédiction"
            
            # Proposer de réessayer
            keyboard = [
                [InlineKeyboardButton("🔄 Essayer un autre match", callback_data="start_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❌ *Erreur de prédiction*\n\n"
                f"{error_msg}\n\n"
                f"Veuillez essayer avec d'autres équipes.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Formater et envoyer la prédiction
        prediction_text = format_prediction_message(prediction)
        
        # Proposer une nouvelle prédiction
        keyboard = [
            [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            prediction_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Enregistrer la prédiction dans les logs
        user_id = context.user_data.get("user_id", query.from_user.id)
        username = context.user_data.get("username", query.from_user.username)
        
        save_prediction_log(
            user_id=user_id,
            username=username,
            team1=team1,
            team2=team2,
            prediction_result=prediction
        )
    
    elif query.data.startswith("predict_"):
        # Vérifier l'abonnement avant de générer une prédiction
        is_subscribed = await check_user_subscription(user_id)
        
        if not is_subscribed:
            # L'utilisateur n'est pas abonné, rediriger vers la vérification
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier mon abonnement", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ *Abonnement requis*\n\n"
                "Pour accéder aux prédictions, vous devez être abonné à notre canal.\n\n"
                "1️⃣ Rejoignez [@alvecapital1](https://t.me/alvecapital1)\n"
                "2️⃣ Cliquez sur '🔄 Vérifier mon abonnement'",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
            
        # Extraire les équipes du callback_data
        data_parts = query.data.split("_")
        if len(data_parts) >= 3:
            team1 = data_parts[1]
            team2 = "_".join(data_parts[2:])  # Gérer les noms d'équipe avec des underscores
            
            # Afficher un message de chargement
            await query.edit_message_text(
                "⏳ *Analyse en cours...*\n\n"
                "Nous récupérons les données et calculons la prédiction pour votre match.\n"
                "Veuillez patienter un moment.",
                parse_mode='Markdown'
            )
            
            # Obtenir la prédiction
            prediction = predictor.predict_match(team1, team2)
            
            # Si la prédiction a échoué
            if not prediction or "error" in prediction:
                error_msg = prediction.get("error", "Erreur inconnue") if prediction else "Impossible de générer une prédiction"
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Essayer un autre match", callback_data="start_prediction")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"❌ *Erreur de prédiction*\n\n{error_msg}",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            
            # Formater et envoyer la prédiction
            prediction_text = format_prediction_message(prediction)
            
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="start_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                prediction_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            # Enregistrer la prédiction dans les logs
            save_prediction_log(
                user_id=user_id,
                username=context.user_data.get("username", query.from_user.username),
                team1=team1,
                team2=team2,
                prediction_result=prediction
            )
    
    elif query.data == "cancel":
        # Annulation d'une action
        await query.edit_message_text("❌ Opération annulée.")

# Gestionnaire des entrées de cotes
async def handle_odds_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gère la saisie des cotes par l'utilisateur."""
    # Vérifier si l'utilisateur est en train de saisir des cotes
    if not context.user_data.get("awaiting_odds"):
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
            f"Exemple: `{team1}: 1.85, {team2}: 2.35`",
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
    
    # Générer la prédiction avec les cotes
    prediction = predictor.predict_match(team1, team2, odds1, odds2)
    
    if not prediction or "error" in prediction:
        error_msg = prediction.get("error", "Erreur inconnue") if prediction else "Impossible de générer une prédiction"
        
        # Proposer de réessayer
        keyboard = [
            [InlineKeyboardButton("🔄 Essayer un autre match", callback_data="start_prediction")]
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
        [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="start_prediction")]
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

# WebApp command
async def webapp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ouvre la WebApp pour les prédictions FIFA 4x4"""
    # Vérifier l'abonnement de l'utilisateur
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        # L'utilisateur n'est pas abonné
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier mon abonnement", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ *Abonnement requis*\n\n"
            "Pour accéder à l'application web de prédiction, vous devez être abonné à notre canal.\n\n"
            "1️⃣ Rejoignez [@alvecapital1](https://t.me/alvecapital1)\n"
            "2️⃣ Cliquez sur '🔄 Vérifier mon abonnement'",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        return
    
    # URL de votre WebApp - remplacez par l'URL réelle après déploiement
    webapp_url = "https://votre-username.github.io/fifa-predictor-bot/"
    
    webapp_button = InlineKeyboardButton(
        text="📊 Ouvrir l'application de prédiction",
        web_app=WebAppInfo(url=webapp_url)
    )
    
    keyboard = InlineKeyboardMarkup([[webapp_button]])
    
    await update.message.reply_text(
        "🔮 *FIFA 4x4 PREDICTOR - APPLICATION WEB*\n\n"
        "Accédez à notre interface de prédiction avancée avec:\n"
        "• Prédictions de scores précises\n"
        "• Analyses statistiques détaillées\n"
        "• Interface utilisateur intuitive\n\n"
        "Cliquez sur le bouton ci-dessous pour commencer ⬇️",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

# Traitement des prédictions simples
async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Traite la commande /predict pour les prédictions de match."""
    # Vérifier l'abonnement avant de traiter la commande
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        # L'utilisateur n'est pas abonné, rediriger vers la vérification
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier mon abonnement", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ *Abonnement requis*\n\n"
            "Pour accéder aux prédictions, vous devez être abonné à notre canal principal.\n\n"
            "1️⃣ Rejoignez [@alvecapital1](https://t.me/alvecapital1)\n"
            "2️⃣ Vérifiez votre abonnement en cliquant sur le bouton ci-dessous",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        return
        
    # Extraire les équipes du message
    message_text = update.message.text[9:].strip()  # Enlever '/predict '
    
    # Essayer de trouver les noms d'équipes séparés par "vs" ou "contre"
    teams = re.split(r'\s+(?:vs|contre|VS|CONTRE)\s+', message_text)
    
    if len(teams) != 2 or not teams[0] or not teams[1]:
        # Si le format n'est pas correct, demander à l'utilisateur de réessayer
        await update.message.reply_text(
            "Format incorrect. Veuillez utiliser: /predict Équipe1 vs Équipe2\n"
            "Exemple: /predict Manchester United vs Chelsea"
        )
        return
    
    team1 = teams[0].strip()
    team2 = teams[1].strip()
    
    # Afficher un message de chargement
    loading_message = await update.message.reply_text(
        "⏳ *Analyse en cours...*\n\n"
        "Nous récupérons les données et calculons la prédiction pour votre match.\n"
        "Veuillez patienter un moment.",
        parse_mode='Markdown'
    )
    
    # Obtenir la prédiction
    prediction = predictor.predict_match(team1, team2)
    
    # Si la prédiction a échoué
    if not prediction or "error" in prediction:
        error_msg = prediction.get("error", "Erreur inconnue") if prediction else "Impossible de générer une prédiction"
        
        # Proposer de réessayer
        keyboard = [
            [InlineKeyboardButton("🔄 Essayer un autre match", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await loading_message.edit_text(
            f"❌ *Erreur de prédiction*\n\n"
            f"{error_msg}\n\n"
            f"Veuillez essayer avec d'autres équipes.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Formater et envoyer la prédiction
    prediction_text = format_prediction_message(prediction)
    
    # Proposer une nouvelle prédiction
    keyboard = [
        [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="start_prediction")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await loading_message.edit_text(
        prediction_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # Enregistrer la prédiction dans les logs
    user = update.message.from_user
    save_prediction_log(
        user_id=user.id,
        username=user.username,
        team1=team1,
        team2=team2,
        prediction_result=prediction
    )

# Traitement des prédictions avec cotes
async def odds_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Traite la commande /odds pour les prédictions de match avec cotes."""
    # Vérifier l'abonnement avant de traiter la commande
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        # L'utilisateur n'est pas abonné, rediriger vers la vérification
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier mon abonnement", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ *Abonnement requis*\n\n"
            "Pour accéder aux prédictions avec cotes, vous devez être abonné à notre canal principal.\n\n"
            "1️⃣ Rejoignez [@alvecapital1](https://t.me/alvecapital1)\n"
            "2️⃣ Vérifiez votre abonnement en cliquant sur le bouton ci-dessous",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
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
            "Format incorrect. Veuillez utiliser: /odds Équipe1 vs Équipe2 cote1 cote2\n"
            "Exemple: /odds Manchester United vs Chelsea 1.8 3.5"
        )
        return
    
    # Extraire les noms d'équipes
    team1 = " ".join(message_parts[:separator_index]).strip()
    
    # Chercher les cotes à la fin
    odds_pattern = r'(\d+\.\d+)'
    odds_matches = re.findall(odds_pattern, " ".join(message_parts[separator_index+1:]))
    
    if len(odds_matches) < 2:
        # Si les cotes ne sont pas correctement formatées
        team2 = " ".join(message_parts[separator_index+1:]).strip()
        odds1 = None
        odds2 = None
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
        "⏳ *Analyse en cours...*\n\n"
        "Nous récupérons les données et calculons la prédiction pour votre match.\n"
        "Veuillez patienter un moment.",
        parse_mode='Markdown'
    )
    
    # Obtenir la prédiction avec les cotes
    prediction = predictor.predict_match(team1, team2, odds1, odds2)
    
    # Si la prédiction a échoué
    if not prediction or "error" in prediction:
        error_msg = prediction.get("error", "Erreur inconnue") if prediction else "Impossible de générer une prédiction"
        
        # Proposer de réessayer
        keyboard = [
            [InlineKeyboardButton("🔄 Essayer un autre match", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await loading_message.edit_text(
            f"❌ *Erreur de prédiction*\n\n"
            f"{error_msg}\n\n"
            f"Veuillez essayer avec d'autres équipes.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Formater et envoyer la prédiction
    prediction_text = format_prediction_message(prediction)
    
    # Proposer une nouvelle prédiction
    keyboard = [
        [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="start_prediction")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await loading_message.edit_text(
        prediction_text,
        reply_markup=reply_markup,
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
        # Vérifier l'abonnement avant de traiter
        user_id = update.effective_user.id
        is_subscribed = await check_user_subscription(user_id)
        
        if not is_subscribed:
            # L'utilisateur n'est pas abonné, rediriger vers la vérification
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier mon abonnement", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚠️ *Abonnement requis*\n\n"
                "Pour accéder aux prédictions, vous devez être abonné à notre canal principal.\n\n"
                "1️⃣ Rejoignez [@alvecapital1](https://t.me/alvecapital1)\n"
                "2️⃣ Vérifiez votre abonnement en cliquant sur le bouton ci-dessous",
                reply_markup=reply_markup,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return
        
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
    await update.message.reply_text(
        "Je ne comprends pas cette commande. Utilisez /help pour voir les commandes disponibles."
    )

# Fonction pour lister les équipes disponibles
async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des équipes disponibles dans la base de données."""
    # Vérifier l'abonnement avant de traiter
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id)
    
    if not is_subscribed:
        # L'utilisateur n'est pas abonné, rediriger vers la vérification
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier mon abonnement", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ *Abonnement requis*\n\n"
            "Pour accéder à la liste des équipes, vous devez être abonné à notre canal principal.\n\n"
            "1️⃣ Rejoignez [@alvecapital1](https://t.me/alvecapital1)\n"
            "2️⃣ Vérifiez votre abonnement en cliquant sur le bouton ci-dessous",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
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

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les informations pour mettre en place le bot."""
    setup_text = """
🔧 *Configuration du bot FIFA 4x4 Predictor*

Ce bot utilise une base de données de matchs FIFA 4x4 pour générer des prédictions précises.

*Fichiers nécessaires:*
- `google_credentials.json` - Pour accéder à votre Google Sheets
- `config.py` - Configuration du bot avec les tokens et paramètres

*Installation:*
1. Assurez-vous que Python 3.7+ est installé
2. Installez les dépendances: `pip install -r requirements.txt`
3. Lancez le bot: `python fifa_bot.py`

*Hébergement:*
Pour un fonctionnement continu, hébergez sur un serveur comme:
- Heroku
- PythonAnywhere
- VPS personnel

*Pour plus d'informations, contactez l'administrateur du bot.*
"""
    await update.message.reply_text(setup_text, parse_mode='Markdown')

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
        application.add_handler(CommandHandler("odds", odds_command))
        application.add_handler(CommandHandler("teams", teams_command))
        application.add_handler(CommandHandler("setup", setup_command))
        application.add_handler(CommandHandler("webapp", webapp_command))
        application.add_handler(CommandHandler("check", check_subscription_command))
        
        # Gestionnaire de conversation pour les cotes
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_callback, pattern="^add_odds$")],
            states={
                ODDS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_odds_input)],
            },
            fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
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
