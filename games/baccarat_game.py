import logging
import asyncio
import random
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Fonction principale pour le jeu Baccarat
async def start_baccarat_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Démarre le jeu Baccarat."""
    query = update.callback_query
    
    # Message introductif
    intro_text = (
        "🃏 *BACCARAT* 🃏\n\n"
        "Anticipez le gagnant entre le Joueur et le Banquier, ainsi que le nombre de points!\n\n"
        "Pour obtenir une prédiction, veuillez indiquer le numéro de la tour."
    )
    
    # Bouton pour entrer le numéro de tour
    keyboard = [
        [InlineKeyboardButton("🔢 Entrer le numéro de tour", callback_data="baccarat_enter_tour")],
        [InlineKeyboardButton("🎮 Retour au menu", callback_data="show_games")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Éditer le message pour afficher l'introduction du jeu
    await query.edit_message_text(
        intro_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Gestionnaire des callbacks spécifiques à Baccarat
async def handle_baccarat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les callbacks du jeu Baccarat."""
    query = update.callback_query
    callback_data = query.data
    
    if callback_data == "baccarat_enter_tour":
        # Demander à l'utilisateur d'entrer le numéro de tour
        await query.edit_message_text(
            "🔢 *Entrez le numéro de la tour:*\n\n"
            "_Envoyez simplement le numéro dans le chat._",
            parse_mode='Markdown'
        )
        
        # Mettre le flag pour indiquer qu'on attend un numéro de tour
        context.user_data["awaiting_baccarat_tour"] = True
    
    elif callback_data == "baccarat_new":
        # Relancer une nouvelle demande de numéro de tour
        await start_baccarat_game(update, context)
    
    elif callback_data == "show_games":
        # Retour au menu principal des jeux
        from verification import show_games_menu
        await show_games_menu(query.message, context)

# Gestionnaire pour la saisie du numéro de tour
async def handle_baccarat_tour_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère la saisie du numéro de tour pour le Baccarat."""
    if not context.user_data.get("awaiting_baccarat_tour", False):
        return
    
    # Récupérer le numéro de tour
    tour_input = update.message.text.strip()
    
    # Vérifier que l'entrée est valide
    if not tour_input.isdigit():
        await update.message.reply_text(
            "❌ *Format incorrect*\n\n"
            "Veuillez saisir uniquement un nombre pour le numéro de tour.\n"
            "Exemple: `42`",
            parse_mode='Markdown'
        )
        return
    
    # Convertir en nombre
    tour_number = int(tour_input)
    
    # Réinitialiser le flag
    context.user_data["awaiting_baccarat_tour"] = False
    
    # Générer la prédiction
    await generate_baccarat_prediction(update.message, tour_number, context)

# Fonction pour générer une prédiction de Baccarat
async def generate_baccarat_prediction(message, tour_number: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Génère une prédiction pour le jeu Baccarat."""
    # Options de prédiction
    gagnants = ["Joueur", "Banquier"]
    points = ["7.5", "8.5", "9.5", "10.5", "11.5", "12.5", "Moins de 13.5"]
    
    # Générer des prédictions aléatoires
    winner = random.choice(gagnants)
    point = random.choice(points)
    
    # Créer le message de prédiction
    baccarat_text = (
        f"🃏 *BACCARAT - Prédiction Tour #{tour_number}*\n\n"
        f"🏆 *Gagnant prédit:* {winner}\n"
        f"🔢 *Points prédits:* {point}\n\n"
    )
    
    # Ajouter une représentation visuelle
    if winner == "Joueur":
        baccarat_text += "👨‍💼 *Joueur* ✅ vs 🏦 Banquier\n\n"
    else:
        baccarat_text += "👨‍💼 Joueur vs 🏦 *Banquier* ✅\n\n"
    
    # Ajouter une petite explication
    baccarat_text += "_Cette prédiction a été générée aléatoirement._\n\n"
    
    # Buttons pour les actions suivantes
    keyboard = [
        [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="baccarat_new")],
        [InlineKeyboardButton("🎮 Accueil", callback_data="show_games")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Animation de la prédiction
    loading_message = await message.reply_text("🔮 *Génération de la prédiction...*", parse_mode='Markdown')
    
    loading_frames = [
        "🃏 *Analyse des cartes...*",
        "🎲 *Calcul des probabilités...*",
        "🧮 *Traitement des données...*"
    ]
    
    for frame in loading_frames:
        await asyncio.sleep(0.3)
        await loading_message.edit_text(frame, parse_mode='Markdown')
    
    # Animation finale avec suspense pour le gagnant
    suspense_frames = [
        "👨‍💼 Joueur vs 🏦 Banquier\n⏳ *Détermination du gagnant...*",
        "👨‍💼 Joueur... 🎭",
        "🏦 Banquier... 🎭",
        "🃏 *Et le gagnant est...*"
    ]
    
    for frame in suspense_frames:
        await asyncio.sleep(0.3)
        await loading_message.edit_text(frame, parse_mode='Markdown')
    
    # Afficher le résultat final
    await loading_message.edit_text(baccarat_text, reply_markup=reply_markup, parse_mode='Markdown')
