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

# Fonctions de base
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message quand la commande /start est envoyée."""
    # Vérifier l'abonnement au canal
    is_subscribed = await check_subscription(update, context)
    
    if is_subscribed:
        # Créer un message de bienvenue avec bouton pour commencer
        keyboard = [
            [InlineKeyboardButton("🔮 Faire une prédiction", callback_data="start_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"{WELCOME_MESSAGE}\n\n"
            f"👇 Cliquez sur le bouton ci-dessous pour commencer"
        )
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    else:
        # L'utilisateur n'est pas abonné, message déjà envoyé par check_subscription
        pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message d'aide quand la commande /help est envoyée."""
    await update.message.reply_text(HELP_MESSAGE, parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les erreurs."""
    logger.error(f"Une erreur est survenue: {context.error}")
    
    if update:
        # Envoi d'un message à l'utilisateur
        await update.message.reply_text(
            "Désolé, une erreur s'est produite. Veuillez réessayer ou contacter l'administrateur."
        )

# Fonction pour vérifier l'abonnement au canal
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Vérifie si l'utilisateur est abonné au canal @alvecapital1 et envoie un message si nécessaire."""
    user_id = update.effective_user.id
    
    try:
        # Vérifier si l'utilisateur est membre du canal
        chat_member = await context.bot.get_chat_member(chat_id="@alvecapital1", user_id=user_id)
        
        # Statuts indiquant que l'utilisateur est membre
        member_statuses = ['creator', 'administrator', 'member']
        
        if chat_member.status in member_statuses:
            # L'utilisateur est abonné
            return True
        else:
            # L'utilisateur n'est pas abonné
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ Vous n'êtes pas abonné à notre canal @alvecapital1.\n\n"
                "L'abonnement est requis pour accéder aux prédictions premium de FIFA 4x4.\n"
                "Rejoignez le canal puis retapez votre commande.",
                reply_markup=reply_markup
            )
            return False
    except Exception as e:
        logger.error(f"Erreur lors de la vérification d'abonnement: {e}")
        # En cas d'erreur, on laisse passer l'utilisateur
        return True

# Commande pour vérifier l'abonnement au canal
async def check_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie si l'utilisateur est abonné au canal @alvecapital1."""
    is_subscribed = await check_subscription(update, context)
    
    if is_subscribed:
        await update.message.reply_text(
            "✅ Félicitations! Vous êtes bien abonné au canal @alvecapital1.\n\n"
            "Vous pouvez maintenant utiliser toutes les fonctionnalités premium de FIFA 4x4 Predictor."
        )

# WebApp command
async def webapp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ouvre la WebApp pour les prédictions FIFA 4x4"""
    # Vérifier d'abord l'abonnement
    is_subscribed = await check_subscription(update, context)
    if not is_subscribed:
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
    # Vérifier d'abord l'abonnement au canal
    is_subscribed = await check_subscription(update, context)
    if not is_subscribed:
        return
    
    # Extraire les équipes du message
    message_text = update.message.text[9:].strip()  # Enlever '/predict '
    
    # Essayer de trouver les noms d'équipes séparés par "vs" ou "contre"
    teams = re.split(r'\s+(?:vs|contre|VS|CONTRE)\s+', message_text)
    
    if len(teams) != 2 or not teams[0] or not teams[1]:
        # Si le format n'est pas correct, demander à l'utilisateur de réessayer
        await update.message.reply_text(
            "🔍 Format incorrect.\n\n"
            "Veuillez utiliser: `/predict Équipe1 vs Équipe2`\n"
            "Exemple: `/predict Manchester United vs Chelsea`",
            parse_mode='Markdown'
        )
        return
    
    team1 = teams[0].strip()
    team2 = teams[1].strip()
    
    # Afficher un message de chargement
    loading_message = await update.message.reply_text(
        "⏳ *Analyse en cours*\n\n"
        "• Chargement des données historiques...\n"
        "• Analyse des confrontations directes...\n"
        "• Calcul des probabilités...",
        parse_mode='Markdown'
    )
    
    # Obtenir la prédiction
    prediction = predictor.predict_match(team1, team2)
    
    # Si la prédiction a échoué
    if not prediction or "error" in prediction:
        await loading_message.edit_text(
            f"❌ Impossible de générer une prédiction:\n"
            f"{prediction.get('error', 'Erreur inconnue')}"
        )
        return
    
    # Formater et envoyer la prédiction
    prediction_text = format_prediction_message(prediction)
    
    # Ajouter un bouton "Nouvelle prédiction"
    keyboard = [
        [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await loading_message.edit_text(
        prediction_text, 
        parse_mode='Markdown',
        reply_markup=reply_markup
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
    # Vérifier d'abord l'abonnement au canal
    is_subscribed = await check_subscription(update, context)
    if not is_subscribed:
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
            "🔍 Format incorrect.\n\n"
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
        "⏳ *Analyse en cours*\n\n"
        "• Chargement des données historiques...\n"
        "• Analyse des confrontations directes...\n"
        "• Intégration des cotes bookmakers...\n"
        "• Calcul des probabilités...",
        parse_mode='Markdown'
    )
    
    # Obtenir la prédiction avec les cotes
    prediction = predictor.predict_match(team1, team2, odds1, odds2)
    
    # Si la prédiction a échoué
    if not prediction or "error" in prediction:
        await loading_message.edit_text(
            f"❌ Impossible de générer une prédiction:\n"
            f"{prediction.get('error', 'Erreur inconnue')}"
        )
        return
    
    # Formater et envoyer la prédiction
    prediction_text = format_prediction_message(prediction)
    
    # Ajouter un bouton "Nouvelle prédiction"
    keyboard = [
        [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await loading_message.edit_text(
        prediction_text, 
        parse_mode='Markdown',
        reply_markup=reply_markup
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
        # Vérifier d'abord l'abonnement au canal
        is_subscribed = await check_subscription(update, context)
        if not is_subscribed:
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
                f"🔮 Souhaitez-vous obtenir une prédiction pour le match:\n\n"
                f"*{teams[0]} vs {teams[1]}*?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
    
    # Message par défaut si aucune action n'est déclenchée
    await update.message.reply_text(
        "👋 Bonjour! Je suis FIFA 4x4 Predictor Bot.\n\n"
        "Pour obtenir une prédiction, utilisez la commande /predict ou /odds.\n"
        "Pour voir toutes les commandes disponibles, tapez /help."
    )

# Gestion des clics sur les boutons
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les clics sur les boutons inline."""
    query = update.callback_query
    await query.answer()
    
    # Annulation
    if query.data == "cancel":
        await query.edit_message_text("❌ Opération annulée.")
        return
    
    # Nouvelle prédiction
    if query.data == "new_prediction":
        # Vérifier d'abord l'abonnement au canal
        user_id = update.effective_user.id
        
        try:
            # Vérifier si l'utilisateur est membre du canal
            chat_member = await context.bot.get_chat_member(chat_id="@alvecapital1", user_id=user_id)
            
            # Statuts indiquant que l'utilisateur est membre
            member_statuses = ['creator', 'administrator', 'member']
            
            if chat_member.status not in member_statuses:
                # L'utilisateur n'est pas abonné
                keyboard = [
                    [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "❌ Vous n'êtes plus abonné à notre canal @alvecapital1.\n\n"
                    "L'abonnement est requis pour accéder aux prédictions FIFA 4x4.\n"
                    "Rejoignez le canal puis réessayez.",
                    reply_markup=reply_markup
                )
                return
        except Exception as e:
            logger.error(f"Erreur lors de la vérification d'abonnement: {e}")
            # Continuer en cas d'erreur
        
        # Afficher le formulaire de nouvelle prédiction
        keyboard = [
            [InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", callback_data="league_england")],
            [InlineKeyboardButton("🇪🇸 La Liga", callback_data="league_spain")],
            [InlineKeyboardButton("🇮🇹 Serie A", callback_data="league_italy")],
            [InlineKeyboardButton("🇫🇷 Ligue 1", callback_data="league_france")],
            [InlineKeyboardButton("🇩🇪 Bundesliga", callback_data="league_germany")],
            [InlineKeyboardButton("🌍 Autre équipe", callback_data="league_other")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔮 *NOUVELLE PRÉDICTION*\n\n"
            "Sélectionnez une ligue pour voir les équipes disponibles, ou utilisez directement les commandes:\n\n"
            "• `/predict Équipe1 vs Équipe2`\n"
            "• `/odds Équipe1 vs Équipe2 cote1 cote2`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Démarrer une prédiction
    if query.data == "start_prediction":
        # Vérifier d'abord l'abonnement au canal
        user_id = update.effective_user.id
        
        try:
            # Vérifier si l'utilisateur est membre du canal
            chat_member = await context.bot.get_chat_member(chat_id="@alvecapital1", user_id=user_id)
            
            # Statuts indiquant que l'utilisateur est membre
            member_statuses = ['creator', 'administrator', 'member']
            
            if chat_member.status not in member_statuses:
                # L'utilisateur n'est pas abonné
                keyboard = [
                    [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "❌ Vous n'êtes pas abonné à notre canal @alvecapital1.\n\n"
                    "L'abonnement est requis pour accéder aux prédictions FIFA 4x4.\n"
                    "Rejoignez le canal puis réessayez.",
                    reply_markup=reply_markup
                )
                return
        except Exception as e:
            logger.error(f"Erreur lors de la vérification d'abonnement: {e}")
            # Continuer en cas d'erreur
        
        # Afficher les instructions
        await query.edit_message_text(
            "🔮 *PRÉDICTION FIFA 4x4*\n\n"
            "Pour obtenir une prédiction, utilisez l'une de ces commandes:\n\n"
            "• `/predict Équipe1 vs Équipe2`\n"
            "  Exemple: `/predict Manchester United vs Chelsea`\n\n"
            "• `/odds Équipe1 vs Équipe2 cote1 cote2`\n"
            "  Exemple: `/odds Liverpool vs Arsenal 1.85 4.2`\n\n"
            "Vous pouvez aussi simplement écrire le nom des équipes séparées par 'vs'.",
            parse_mode='Markdown'
        )
        return
    
    # Sélection de ligue
    if query.data.startswith("league_"):
        league = query.data.replace("league_", "")
        
        # Obtenir quelques équipes populaires de cette ligue
        teams = get_teams_by_league(league)
        
        keyboard = []
        for team in teams:
            keyboard.append([InlineKeyboardButton(team, callback_data=f"team1_{team}")])
        
        keyboard.append([InlineKeyboardButton("◀️ Retour", callback_data="new_prediction")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🔮 *NOUVELLE PRÉDICTION* - Sélection de l'équipe 1\n\n"
            f"Choisissez la première équipe:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Sélection de l'équipe 1
    if query.data.startswith("team1_"):
        team1 = query.data.replace("team1_", "")
        
        # Obtenir les équipes qui ont joué contre team1
        opposing_teams = get_opposing_teams(team1)
        
        keyboard = []
        for team in opposing_teams:
            keyboard.append([InlineKeyboardButton(team, callback_data=f"team2_{team1}_{team}")])
        
        keyboard.append([InlineKeyboardButton("◀️ Retour", callback_data="new_prediction")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🔮 *NOUVELLE PRÉDICTION* - Sélection de l'équipe 2\n\n"
            f"Équipe 1: *{team1}*\n\n"
            f"Choisissez l'équipe adverse:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Sélection de l'équipe 2
    if query.data.startswith("team2_"):
        parts = query.data.replace("team2_", "").split("_", 1)
        if len(parts) == 2:
            team1 = parts[0]
            team2 = parts[1]
            
            keyboard = [
                [InlineKeyboardButton("✅ Prédire sans cotes", callback_data=f"predict_{team1}_{team2}")],
                [InlineKeyboardButton("💰 Ajouter des cotes", callback_data=f"odds_{team1}_{team2}")],
                [InlineKeyboardButton("◀️ Retour", callback_data=f"team1_{team1}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🔮 *NOUVELLE PRÉDICTION*\n\n"
                f"Match sélectionné: *{team1}* vs *{team2}*\n\n"
                f"Comment souhaitez-vous procéder?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        return
    
    # Prédiction à partir d'un bouton
    if query.data.startswith("predict_"):
        # Vérifier d'abord l'abonnement au canal
        user_id = update.effective_user.id
        
        try:
            # Vérifier si l'utilisateur est membre du canal
            chat_member = await context.bot.get_chat_member(chat_id="@alvecapital1", user_id=user_id)
            
            # Statuts indiquant que l'utilisateur est membre
            member_statuses = ['creator', 'administrator', 'member']
            
            if chat_member.status not in member_statuses:
                # L'utilisateur n'est pas abonné
                keyboard = [
                    [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "❌ Vous n'êtes pas abonné à notre canal @alvecapital1.\n\n"
                    "L'abonnement est requis pour accéder aux prédictions FIFA 4x4.\n"
                    "Rejoignez le canal puis réessayez.",
                    reply_markup=reply_markup
                )
                return
        except Exception as e:
            logger.error(f"Erreur lors de la vérification d'abonnement: {e}")
            # Continuer en cas d'erreur
            
        # Extraire les équipes du callback_data
        data_parts = query.data.split("_")
        if len(data_parts) >= 3:
            team1 = data_parts[1]
            team2 = "_".join(data_parts[2:])  # Gérer les noms d'équipe avec des underscores
            
            # Afficher un message de chargement
            await query.edit_message_text(
                "⏳ *Analyse en cours*\n\n"
                "• Chargement des données historiques...\n"
                "• Analyse des confrontations directes...\n"
                "• Calcul des probabilités...",
                parse_mode='Markdown'
            )
            
            # Obtenir la prédiction
            prediction = predictor.predict_match(team1, team2)
            
            # Si la prédiction a échoué
            if not prediction or "error" in prediction:
                await query.edit_message_text(
                    f"❌ Impossible de générer une prédiction:\n"
                    f"{prediction.get('error', 'Erreur inconnue')}"
                )
                return
            
            # Formater et envoyer la prédiction
            prediction_text = format_prediction_message(prediction)
            
            # Ajouter un bouton "Nouvelle prédiction"
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                prediction_text, 
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            # Enregistrer la prédiction dans les logs
            user = update.effective_user
            save_prediction_log(
                user_id=user.id,
                username=user.username,
                team1=team1,
                team2=team2,
                prediction_result=prediction
            )

    # Ajouter des cotes à une prédiction
    if query.data.startswith("odds_"):
        parts = query.data.replace("odds_", "").split("_", 1)
        if len(parts) == 2:
            team1 = parts[0]
            team2 = parts[1]
            
            context.user_data['odds_teams'] = (team1, team2)
            
            await query.edit_message_text(
                f"💰 *AJOUT DES COTES*\n\n"
                f"Match: *{team1}* vs *{team2}*\n\n"
                f"Veuillez envoyer les cotes au format suivant:\n"
                f"`cote1 cote2`\n\n"
                f"Exemple: `1.85 3.5`",
                parse_mode='Markdown'
            )
            
            return ODDS_INPUT
        return

# Fonction pour obtenir les équipes par ligue
def get_teams_by_league(league: str) -> List[str]:
    """Retourne une liste d'équipes populaires de la ligue spécifiée."""
    teams_by_league = {
        "england": ["Arsenal", "Manchester United", "Liverpool", "Chelsea", "Manchester City", "Tottenham"],
        "spain": ["Barcelona", "Real Madrid", "Atletico Madrid", "Sevilla", "Valencia", "Villarreal"],
        "italy": ["Juventus", "Inter Milan", "AC Milan", "Napoli", "AS Roma", "Lazio"],
        "france": ["PSG", "Marseille", "Lyon", "Monaco", "Lille", "Nice"],
        "germany": ["Bayern Munich", "Borussia Dortmund", "RB Leipzig", "Bayer Leverkusen", "Schalke 04", "Wolfsburg"],
        "other": ["Ajax", "Porto", "Benfica", "Sporting CP", "Galatasaray", "Celtic", "Rangers"]
    }
    
    return teams_by_league.get(league, ["Équipe non trouvée"])

# Fonction pour obtenir les équipes adverses
def get_opposing_teams(team: str) -> List[str]:
    """Retourne une liste d'équipes qui ont joué contre l'équipe spécifiée."""
    # Dans une implémentation réelle, vous récupéreriez ces données de votre base de données
    # Pour cette démo, on utilise une liste générée
    all_teams = get_all_teams()
    
    # Filtrer pour ne pas inclure l'équipe elle-même
    return [t for t in all_teams if t != team][:10]  # Limiter à 10 équipes pour l'interface

# Fonction pour lister les équipes disponibles
async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des équipes disponibles dans la base de données."""
    # Vérifier d'abord l'abonnement au canal
    is_subscribed = await check_subscription(update, context)
    if not is_subscribed:
        return
        
    # Récupérer la liste des équipes
    # Récupérer la liste des équipes
    teams = get_all_teams()
    
    if not teams:
        await update.message.reply_text("Aucune équipe n'a été trouvée dans la base de données.")
        return
    
    # Formater la liste des équipes
    teams_text = "📋 *ÉQUIPES DISPONIBLES:*\n\n"
    
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

# Gestionnaire pour les entrées de cotes
async def odds_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Traite les entrées de cotes après avoir sélectionné les équipes."""
    try:
        # Récupérer les équipes stockées dans user_data
        team1, team2 = context.user_data.get('odds_teams', (None, None))
        
        if not team1 or not team2:
            await update.message.reply_text(
                "❌ Erreur: équipes non spécifiées. Veuillez recommencer."
            )
            return ConversationHandler.END
        
        # Récupérer les cotes du message
        odds_text = update.message.text.strip()
        odds_parts = re.findall(r'(\d+\.?\d*)', odds_text)
        
        if len(odds_parts) < 2:
            await update.message.reply_text(
                "❌ Format incorrect. Veuillez envoyer deux nombres séparés par un espace.\n"
                "Exemple: `1.85 3.5`",
                parse_mode='Markdown'
            )
            return ODDS_INPUT
        
        odds1 = float(odds_parts[0])
        odds2 = float(odds_parts[1])
        
        # Vérifier que les cotes sont valides
        if odds1 < 1.01 or odds2 < 1.01:
            await update.message.reply_text(
                "❌ Les cotes doivent être supérieures à 1.01. Veuillez réessayer."
            )
            return ODDS_INPUT
        
        # Afficher un message de chargement
        loading_message = await update.message.reply_text(
            "⏳ *Analyse en cours*\n\n"
            "• Chargement des données historiques...\n"
            "• Analyse des confrontations directes...\n"
            "• Intégration des cotes bookmakers...\n"
            "• Calcul des probabilités...",
            parse_mode='Markdown'
        )
        
        # Obtenir la prédiction
        prediction = predictor.predict_match(team1, team2, odds1, odds2)
        
        # Si la prédiction a échoué
        if not prediction or "error" in prediction:
            await loading_message.edit_text(
                f"❌ Impossible de générer une prédiction:\n"
                f"{prediction.get('error', 'Erreur inconnue')}"
            )
            return ConversationHandler.END
        
        # Formater et envoyer la prédiction
        prediction_text = format_prediction_message(prediction)
        
        # Ajouter un bouton "Nouvelle prédiction"
        keyboard = [
            [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await loading_message.edit_text(
            prediction_text, 
            parse_mode='Markdown',
            reply_markup=reply_markup
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
        
        # Effacer les données temporaires
        if 'odds_teams' in context.user_data:
            del context.user_data['odds_teams']
        
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Erreur lors du traitement des cotes: {e}")
        await update.message.reply_text(
            "❌ Une erreur s'est produite. Veuillez réessayer avec le format: `1.85 3.5`",
            parse_mode='Markdown'
        )
        return ODDS_INPUT

# Fonction pour annuler la conversation
async def cancel_odds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Annule la conversation et efface les données temporaires."""
    # Effacer les données temporaires
    if 'odds_teams' in context.user_data:
        del context.user_data['odds_teams']
    
    await update.message.reply_text(
        "❌ Opération annulée. Vous pouvez commencer une nouvelle prédiction."
    )
    
    return ConversationHandler.END

# Réinitialiser le webhook Telegram au démarrage
def reset_telegram_session():
    """Réinitialise la session Telegram du bot"""
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            logger.info("Webhook Telegram réinitialisé avec succès")
            return True
        else:
            logger.warning(f"Échec de réinitialisation du webhook: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Erreur lors de la réinitialisation du webhook: {e}")
        return False

# Fonction principale
def main() -> None:
    """Démarre le bot."""
    try:
        # Réinitialiser d'abord la session Telegram
        reset_telegram_session()
        
        # Créer l'application
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Création du conversation handler pour les cotes
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_click, pattern=r'^odds_')],
            states={
                ODDS_INPUT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, odds_input_handler)
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_odds)],
            per_message=False
        )

        # Ajouter les gestionnaires de commandes
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("predict", predict_command))
        application.add_handler(CommandHandler("odds", odds_command))
        application.add_handler(CommandHandler("teams", teams_command))
        application.add_handler(CommandHandler("setup", setup_command))
        application.add_handler(CommandHandler("webapp", webapp_command))
        application.add_handler(CommandHandler("check", check_subscription_command))
        
        # Ajouter le gestionnaire de conversation pour les cotes
        application.add_handler(conv_handler)
        
        # Ajouter le gestionnaire pour les clics sur les boutons (qui ne sont pas gérés par le conv_handler)
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
