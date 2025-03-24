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
    await update.message.reply_text(WELCOME_MESSAGE)

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

# Fonction pour vérifier si l'utilisateur est abonné au canal
async def is_user_subscribed(bot, user_id):
    """Vérifie si l'utilisateur est abonné au canal @alvecapital1."""
    try:
        # Vérifier si l'utilisateur est membre du canal
        chat_member = await bot.get_chat_member(chat_id="@alvecapital1", user_id=user_id)
        
        # Statuts indiquant que l'utilisateur est membre
        member_statuses = ['creator', 'administrator', 'member']
        
        return chat_member.status in member_statuses
    except Exception as e:
        logger.error(f"Erreur lors de la vérification d'abonnement: {e}")
        return False  # En cas d'erreur, on suppose que l'utilisateur n'est pas abonné

# Commande pour vérifier l'abonnement au canal
async def check_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie si l'utilisateur est abonné au canal @alvecapital1."""
    user_id = update.effective_user.id
    
    # Stocker l'ID du message de vérification pour le retrouver plus tard
    if 'subscription_message_id' not in context.user_data:
        context.user_data['subscription_message_id'] = update.message.message_id
    
    is_subscribed = await is_user_subscribed(context.bot, user_id)
    
    if is_subscribed:
        # L'utilisateur est abonné
        await update.message.reply_text(
            "✅ Félicitations! Vous êtes bien abonné au canal @alvecapital1.\n\n"
            "Vous pouvez maintenant utiliser toutes les fonctionnalités premium de FIFA 4x4 Predictor."
        )
    else:
        # L'utilisateur n'est pas abonné
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Vous n'êtes pas abonné à notre canal @alvecapital1.\n\n"
            "L'abonnement est requis pour accéder aux fonctionnalités premium de FIFA 4x4 Predictor.",
            reply_markup=reply_markup
        )

# WebApp command
async def webapp_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ouvre la WebApp pour les prédictions FIFA 4x4"""
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
    user_id = update.effective_user.id
    
    # Vérifier d'abord l'abonnement
    is_subscribed = await is_user_subscribed(context.bot, user_id)
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Enregistrer le message et la commande pour réexécution après vérification
        context.user_data['pending_command'] = 'predict'
        context.user_data['pending_text'] = update.message.text
        
        await update.message.reply_text(
            "❌ Vous n'êtes plus abonné au canal AL VE CAPITAL.\n"
            "🔄 Veuillez vous réabonner pour continuer à utiliser le bot.",
            reply_markup=reply_markup
        )
        return
    
    # Supprimer les anciens messages si nécessaire
    await clean_old_messages(context)
    
    # Extraire les équipes du message
    message_text = update.message.text[9:].strip()  # Enlever '/predict '
    
    # Essayer de trouver les noms d'équipes séparés par "vs" ou "contre"
    teams = re.split(r'\s+(?:vs|contre|VS|CONTRE)\s+', message_text)
    
    if len(teams) != 2 or not teams[0] or not teams[1]:
        # Si le format n'est pas correct, demander à l'utilisateur de réessayer
        sent_message = await update.message.reply_text(
            "Format incorrect. Veuillez utiliser: /predict Équipe1 vs Équipe2\n"
            "Exemple: /predict Manchester United vs Chelsea"
        )
        # Stocker l'ID du message pour le nettoyer plus tard
        if 'messages_to_delete' not in context.user_data:
            context.user_data['messages_to_delete'] = []
        context.user_data['messages_to_delete'].append(sent_message.message_id)
        return
    
    team1 = teams[0].strip()
    team2 = teams[1].strip()
    
    # Afficher un message de chargement
    loading_message = await update.message.reply_text("⏳ Analyse en cours, veuillez patienter...")
    
    # Stocker l'ID du message pour le nettoyer plus tard
    if 'messages_to_delete' not in context.user_data:
        context.user_data['messages_to_delete'] = []
    context.user_data['messages_to_delete'].append(loading_message.message_id)
    
    # Obtenir la prédiction
    prediction = predictor.predict_match(team1, team2)
    
    # Si la prédiction a échoué
    if not prediction or "error" in prediction:
        error_message = await loading_message.edit_text(
            f"❌ Impossible de générer une prédiction:\n"
            f"{prediction.get('error', 'Erreur inconnue')}"
        )
        context.user_data['messages_to_delete'].append(error_message.message_id)
        return
    
    # Formater et envoyer la prédiction avec la présentation améliorée
    prediction_text = format_improved_prediction_message(prediction)
    result_message = await loading_message.edit_text(prediction_text, parse_mode='Markdown')
    
    # Stocker l'ID du message de résultat
    context.user_data['current_result_message'] = result_message.message_id
    
    # Ajouter un bouton pour une nouvelle prédiction
    keyboard = [
        [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")],
        [InlineKeyboardButton("🏠 Retour au menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await result_message.edit_reply_markup(reply_markup=reply_markup)
    
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
    user_id = update.effective_user.id
    
    # Vérifier d'abord l'abonnement
    is_subscribed = await is_user_subscribed(context.bot, user_id)
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Enregistrer le message et la commande pour réexécution après vérification
        context.user_data['pending_command'] = 'odds'
        context.user_data['pending_text'] = update.message.text
        
        await update.message.reply_text(
            "❌ Vous n'êtes plus abonné au canal AL VE CAPITAL.\n"
            "🔄 Veuillez vous réabonner pour continuer à utiliser le bot.",
            reply_markup=reply_markup
        )
        return
    
    # Supprimer les anciens messages si nécessaire
    await clean_old_messages(context)
    
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
        sent_message = await update.message.reply_text(
            "Format incorrect. Veuillez utiliser: /odds Équipe1 vs Équipe2 cote1 cote2\n"
            "Exemple: /odds Manchester United vs Chelsea 1.8 3.5"
        )
        # Stocker l'ID du message pour le nettoyer plus tard
        if 'messages_to_delete' not in context.user_data:
            context.user_data['messages_to_delete'] = []
        context.user_data['messages_to_delete'].append(sent_message.message_id)
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
    loading_message = await update.message.reply_text("⏳ Analyse en cours, veuillez patienter...")
    
    # Stocker l'ID du message pour le nettoyer plus tard
    if 'messages_to_delete' not in context.user_data:
        context.user_data['messages_to_delete'] = []
    context.user_data['messages_to_delete'].append(loading_message.message_id)
    
    # Obtenir la prédiction avec les cotes
    prediction = predictor.predict_match(team1, team2, odds1, odds2)
    
    # Si la prédiction a échoué
    if not prediction or "error" in prediction:
        error_message = await loading_message.edit_text(
            f"❌ Impossible de générer une prédiction:\n"
            f"{prediction.get('error', 'Erreur inconnue')}"
        )
        context.user_data['messages_to_delete'].append(error_message.message_id)
        return
    
    # Formater et envoyer la prédiction avec la présentation améliorée
    prediction_text = format_improved_prediction_message(prediction)
    result_message = await loading_message.edit_text(prediction_text, parse_mode='Markdown')
    
    # Stocker l'ID du message de résultat
    context.user_data['current_result_message'] = result_message.message_id
    
    # Ajouter un bouton pour une nouvelle prédiction
    keyboard = [
        [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")],
        [InlineKeyboardButton("🏠 Retour au menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await result_message.edit_reply_markup(reply_markup=reply_markup)
    
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

# Fonction pour nettoyer les anciens messages
async def clean_old_messages(context):
    """Supprime les anciens messages pour garder l'historique propre."""
    if 'messages_to_delete' in context.user_data and context.user_data['messages_to_delete']:
        for message_id in context.user_data['messages_to_delete']:
            try:
                await context.bot.delete_message(
                    chat_id=context.user_data.get('chat_id'),
                    message_id=message_id
                )
            except Exception as e:
                logger.error(f"Erreur lors de la suppression du message {message_id}: {e}")
        
        # Vider la liste après suppression
        context.user_data['messages_to_delete'] = []
    
    # Nettoyer aussi le message de résultat actuel s'il existe
    if 'current_result_message' in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=context.user_data.get('chat_id'),
                message_id=context.user_data['current_result_message']
            )
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du message de résultat: {e}")

# Format de prédiction amélioré avec séparateurs visuels
def format_improved_prediction_message(prediction: Dict[str, Any]) -> str:
    """Formate le résultat de prédiction avec une présentation améliorée et séparateurs visuels."""
    if "error" in prediction:
        return f"❌ Erreur: {prediction['error']}"
    
    teams = prediction["teams"]
    team1 = teams["team1"]
    team2 = teams["team2"]
    
    message = [
        f"🔮 *PRÉDICTION: {team1} vs {team2}*",
        f"📊 Niveau de confiance: *{prediction['confidence_level']}%*",
        f"🤝 Confrontations directes: {prediction['direct_matches']}",
        "\n─────────────────────────"
    ]
    
    # Section 1: Scores exacts à la première mi-temps
    message.append("\n*⏱️ SCORES PRÉVUS (1ÈRE MI-TEMPS):*")
    if prediction["half_time_scores"]:
        for i, score_data in enumerate(prediction["half_time_scores"], 1):
            message.append(f"  *{i}.* {score_data['score']} ({score_data['confidence']}%)")
    else:
        message.append("  _Pas assez de données pour prédire le score à la mi-temps_")
    
    # Gagnant à la mi-temps
    winner_ht = prediction["winner_half_time"]
    if winner_ht["team"]:
        if winner_ht["team"] == "Nul":
            message.append(f"\n👉 *Mi-temps: Match nul probable* ({winner_ht['probability']}%)")
        else:
            message.append(f"\n👉 *Mi-temps: {winner_ht['team']} gagnant probable* ({winner_ht['probability']}%)")
    
    message.append("─────────────────────────")
    
    # Section 2: Scores exacts au temps réglementaire
    message.append("\n*⚽ SCORES PRÉVUS (TEMPS RÉGLEMENTAIRE):*")
    if prediction["full_time_scores"]:
        for i, score_data in enumerate(prediction["full_time_scores"], 1):
            message.append(f"  *{i}.* {score_data['score']} ({score_data['confidence']}%)")
    else:
        message.append("  _Pas assez de données pour prédire le score final_")
    
    # Gagnant du match
    winner_ft = prediction["winner_full_time"]
    if winner_ft["team"]:
        if winner_ft["team"] == "Nul":
            message.append(f"\n👉 *Résultat final: Match nul probable* ({winner_ft['probability']}%)")
        else:
            message.append(f"\n👉 *Résultat final: {winner_ft['team']} gagnant probable* ({winner_ft['probability']}%)")
    
    message.append("─────────────────────────")
    
    # Section 3: Statistiques moyennes
    message.append("\n*📈 STATISTIQUES MOYENNES:*")
    message.append(f"  • Buts 1ère mi-temps: *{prediction['avg_goals_half_time']}*")
    message.append(f"  • Buts temps réglementaire: *{prediction['avg_goals_full_time']}*")
    
    # Section 4: Information sur les cotes si disponibles
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        message.append("\n─────────────────────────")
        message.append("\n*💰 COTES:*")
        message.append(f"  • {team1}: *{odds['team1']}*")
        message.append(f"  • {team2}: *{odds['team2']}*")
    
    message.append("\n─────────────────────────")
    message.append("\n_Cliquez sur 'Nouvelle prédiction' ci-dessous pour analyser un autre match._")
    
    return "\n".join(message)

# Fonction pour réagir aux messages non reconnus comme commandes
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Répond aux messages qui ne sont pas des commandes."""
    message_text = update.message.text.strip()
    
    # Stocker l'ID du chat pour la suppression de messages
    context.user_data['chat_id'] = update.effective_chat.id
    
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
            
            sent_message = await update.message.reply_text(
                f"Souhaitez-vous obtenir une prédiction pour le match:\n\n"
                f"*{teams[0]} vs {teams[1]}*?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            # Stocker l'ID du message pour le nettoyer plus tard
            if 'messages_to_delete' not in context.user_data:
                context.user_data['messages_to_delete'] = []
            context.user_data['messages_to_delete'].append(sent_message.message_id)
            return
    
    # Message par défaut si aucune action n'est déclenchée
    sent_message = await update.message.reply_text(
        "Je ne comprends pas cette commande. Utilisez /help pour voir les commandes disponibles."
    )
    
    # Stocker l'ID du message pour le nettoyer plus tard
    if 'messages_to_delete' not in context.user_data:
        context.user_data['messages_to_delete'] = []
    context.user_data['messages_to_delete'].append(sent_message.message_id)

# Gestion des clics sur les boutons
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les clics sur les boutons inline."""
    query = update.callback_query
    await query.answer()
    
    # Stocker l'ID du chat pour la suppression de messages
    context.user_data['chat_id'] = update.effective_chat.id
    
    # Gestion du bouton "Nouvelle prédiction"
    if query.data == "new_prediction":
        # Vérifier l'abonnement de l'utilisateur
        is_subscribed = await is_user_subscribed(context.bot, update.effective_user.id)
        
        if not is_subscribed:
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Mettre à jour le message existant avec l'erreur d'abonnement
            await query.edit_message_text(
                "❌ Vous n'êtes plus abonné au canal AL VE CAPITAL.\n"
                "🔄 Veuillez vous réabonner pour continuer à utiliser le bot.",
                reply_markup=reply_markup
            )
            return
        
        # Nettoyer les anciens messages
        await clean_old_messages(context)
        
        # Afficher les équipes disponibles
        teams_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Pour obtenir une prédiction, utilisez:\n\n"
                 "/predict Équipe1 vs Équipe2\n"
                 "ou\n"
                 "/odds Équipe1 vs Équipe2 cote1 cote2\n\n"
                 "Exemple: /predict Manchester United vs Chelsea"
        )
        
        # Stocker l'ID du message pour le nettoyer plus tard
        if 'messages_to_delete' not in context.user_data:
            context.user_data['messages_to_delete'] = []
        context.user_data['messages_to_delete'].append(teams_message.message_id)
        return
    
    # Vérification d'abonnement
    if query.data == "verify_subscription":
        is_subscribed = await is_user_subscribed(context.bot, update.effective_user.id)
        
        if is_subscribed:
            # Si l'utilisateur est maintenant abonné
            await query.edit_message_text(
                "✅ Félicitations! Vous êtes bien abonné au canal @alvecapital1.\n\n"
                "Vous pouvez maintenant utiliser toutes les fonctionnalités premium de FIFA 4x4 Predictor."
            )
            
            # S'il y a une commande en attente, l'exécuter
            if 'pending_command' in context.user_data and 'pending_text' in context.user_data:
                command = context.user_data['pending_command']
                text = context.user_data['pending_text']
                
                # Simuler l'envoi de la commande
                if command == 'predict':
                    # Créer un message avec le texte de la commande en attente
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=text
                    )
                    
                    # Extraire les équipes du message
                    message_text = text[9:].strip()
                    teams = re.split(r'\s+(?:vs|contre|VS|CONTRE)\s+', message_text)
                    
                    if len(teams) == 2 and teams[0] and teams[1]:
                        team1 = teams[0].strip()
                        team2 = teams[1].strip()
                        
                        # Afficher un message de chargement
                        loading_message = await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text="⏳ Analyse en cours, veuillez patienter..."
                        )
                        
                        # Obtenir la prédiction
                        prediction = predictor.predict_match(team1, team2)
                        
                        # Formater et envoyer la prédiction
                        prediction_text = format_improved_prediction_message(prediction)
                        
                        # Ajouter un bouton pour une nouvelle prédiction
                        keyboard = [
                            [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")],
                            [InlineKeyboardButton("🏠 Retour au menu", callback_data="back_to_menu")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await loading_message.edit_text(prediction_text, parse_mode='Markdown', reply_markup=reply_markup)
                
                # Nettoyer les données de commande en attente
                # Nettoyer les données de commande en attente
                del context.user_data['pending_command']
                del context.user_data['pending_text']
        else:
            # L'utilisateur n'est toujours pas abonné
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ Vous n'êtes toujours pas abonné au canal @alvecapital1.\n\n"
                "L'abonnement est requis pour accéder aux fonctionnalités premium de FIFA 4x4 Predictor.",
                reply_markup=reply_markup
            )
        return
    
    # Retour au menu principal
    if query.data == "back_to_menu":
        await clean_old_messages(context)
        
        menu_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Bienvenue sur FIFA 4x4 Predictor! Que souhaitez-vous faire?\n\n"
                 "/predict - Obtenir une prédiction de match\n"
                 "/odds - Prédiction avec cotes\n"
                 "/teams - Voir les équipes disponibles\n"
                 "/help - Aide détaillée"
        )
        return
    
    # Annulation
    if query.data == "cancel":
        await query.edit_message_text("Opération annulée.")
        return
    
    # Prédiction à partir d'un bouton
    if query.data.startswith("predict_"):
        # Vérifier l'abonnement de l'utilisateur
        is_subscribed = await is_user_subscribed(context.bot, update.effective_user.id)
        
        if not is_subscribed:
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
                [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ Vous n'êtes plus abonné au canal AL VE CAPITAL.\n"
                "🔄 Veuillez vous réabonner pour continuer à utiliser le bot.",
                reply_markup=reply_markup
            )
            return
        
        # Extraire les équipes du callback_data
        data_parts = query.data.split("_")
        if len(data_parts) >= 3:
            team1 = data_parts[1]
            team2 = "_".join(data_parts[2:])  # Gérer les noms d'équipe avec des underscores
            
            # Afficher un message de chargement
            await query.edit_message_text("⏳ Analyse en cours, veuillez patienter...")
            
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
            prediction_text = format_improved_prediction_message(prediction)
            
            # Ajouter un bouton pour une nouvelle prédiction
            keyboard = [
                [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="new_prediction")],
                [InlineKeyboardButton("🏠 Retour au menu", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(prediction_text, parse_mode='Markdown', reply_markup=reply_markup)
            
            # Enregistrer la prédiction dans les logs
            user = update.effective_user
            save_prediction_log(
                user_id=user.id,
                username=user.username,
                team1=team1,
                team2=team2,
                prediction_result=prediction
            )

# Fonction pour lister les équipes disponibles
async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la liste des équipes disponibles dans la base de données."""
    # Vérifier l'abonnement de l'utilisateur
    is_subscribed = await is_user_subscribed(context.bot, update.effective_user.id)
    
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")],
            [InlineKeyboardButton("🔄 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Vous n'êtes plus abonné au canal AL VE CAPITAL.\n"
            "🔄 Veuillez vous réabonner pour continuer à utiliser le bot.",
            reply_markup=reply_markup
        )
        return
    
    # Supprimer les anciens messages si nécessaire
    await clean_old_messages(context)
    
    # Récupérer la liste des équipes
    teams = get_all_teams()
    
    if not teams:
        sent_message = await update.message.reply_text("Aucune équipe n'a été trouvée dans la base de données.")
        
        # Stocker l'ID du message pour le nettoyer plus tard
        if 'messages_to_delete' not in context.user_data:
            context.user_data['messages_to_delete'] = []
        context.user_data['messages_to_delete'].append(sent_message.message_id)
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
    
    # Ajouter un bouton pour effectuer une prédiction
    keyboard = [
        [InlineKeyboardButton("🔮 Faire une prédiction", callback_data="new_prediction")],
        [InlineKeyboardButton("🏠 Retour au menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Si le message est trop long, diviser en plusieurs messages
    if len(teams_text) > 4000:
        chunks = [teams_text[i:i+4000] for i in range(0, len(teams_text), 4000)]
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1:  # Dernier message
                sent_message = await update.message.reply_text(chunk, parse_mode='Markdown', reply_markup=reply_markup)
            else:
                sent_message = await update.message.reply_text(chunk, parse_mode='Markdown')
            
            # Stocker l'ID du message pour le nettoyer plus tard
            if 'messages_to_delete' not in context.user_data:
                context.user_data['messages_to_delete'] = []
            context.user_data['messages_to_delete'].append(sent_message.message_id)
    else:
        sent_message = await update.message.reply_text(teams_text, parse_mode='Markdown', reply_markup=reply_markup)
        
        # Stocker l'ID du message pour le nettoyer plus tard
        if 'messages_to_delete' not in context.user_data:
            context.user_data['messages_to_delete'] = []
        context.user_data['messages_to_delete'].append(sent_message.message_id)

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
