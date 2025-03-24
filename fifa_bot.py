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

# Commande pour vérifier l'abonnement au canal
async def check_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vérifie si l'utilisateur est abonné au canal @alvecapital1."""
    user_id = update.effective_user.id
    
    try:
        # Vérifier si l'utilisateur est membre du canal
        chat_member = await context.bot.get_chat_member(chat_id="@alvecapital1", user_id=user_id)
        
        # Statuts indiquant que l'utilisateur est membre
        member_statuses = ['creator', 'administrator', 'member']
        
        if chat_member.status in member_statuses:
            # L'utilisateur est abonné
            await update.message.reply_text(
                "✅ Félicitations! Vous êtes bien abonné au canal @alvecapital1.\n\n"
                "Vous pouvez maintenant utiliser toutes les fonctionnalités premium de FIFA 4x4 Predictor."
            )
        else:
            # L'utilisateur n'est pas abonné
            keyboard = [
                [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapital1")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ Vous n'êtes pas abonné à notre canal @alvecapital1.\n\n"
                "L'abonnement est requis pour accéder aux fonctionnalités premium de FIFA 4x4 Predictor.",
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Erreur lors de la vérification d'abonnement: {e}")
        await update.message.reply_text(
            "⚠️ Une erreur est survenue lors de la vérification de votre abonnement. "
            "Veuillez réessayer plus tard ou contacter le support."
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
    loading_message = await update.message.reply_text("⏳ Analyse en cours, veuillez patienter...")
    
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
    await loading_message.edit_text(prediction_text, parse_mode='Markdown')
    
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
    loading_message = await update.message.reply_text("⏳ Analyse en cours, veuillez patienter...")
    
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
    await loading_message.edit_text(prediction_text, parse_mode='Markdown')
    
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
    await update.message.reply_text(
        "Je ne comprends pas cette commande. Utilisez /help pour voir les commandes disponibles."
    )

# Gestion des clics sur les boutons
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les clics sur les boutons inline."""
    query = update.callback_query
    await query.answer()
    
    # Annulation
    if query.data == "cancel":
        await query.edit_message_text("Opération annulée.")
        return
    
    # Prédiction à partir d'un bouton
    if query.data.startswith("predict_"):
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
            prediction_text = format_prediction_message(prediction)
            await query.edit_message_text(prediction_text, parse_mode='Markdown')
            
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
