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

# Fonction principale pour le jeu Apple of Fortune
async def start_apple_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Démarre le jeu Apple of Fortune."""
    query = update.callback_query
    
    # Message introductif
    intro_text = (
        "🍎 *APPLE OF FORTUNE* 🍎\n\n"
        "Découvrez la position de la pomme gagnante parmi 5 positions possibles!\n\n"
        "Appuyez sur 'Obtenir une prédiction' pour commencer."
    )
    
    # Bouton pour lancer la prédiction
    keyboard = [
        [InlineKeyboardButton("🔮 Obtenir une prédiction", callback_data="apple_predict")],
        [InlineKeyboardButton("🎮 Retour au menu", callback_data="show_games")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Éditer le message pour afficher l'introduction du jeu
    await query.edit_message_text(
        intro_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Gestionnaire des callbacks spécifiques à Apple of Fortune
async def handle_apple_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les callbacks du jeu Apple of Fortune."""
    query = update.callback_query
    callback_data = query.data
    
    if callback_data == "apple_predict":
        # Générer une nouvelle prédiction
        await generate_apple_prediction(query, context, is_new=True)
    
    elif callback_data == "apple_next":
        # Générer la prédiction suivante dans la séquence
        await generate_apple_prediction(query, context, is_new=False)
    
    elif callback_data == "apple_new":
        # Recommencer avec une nouvelle séquence
        # Réinitialiser les compteurs
        context.user_data["apple_sequence"] = []
        await generate_apple_prediction(query, context, is_new=True)
    
    elif callback_data == "show_games":
        # Retour au menu principal des jeux
        from verification import show_games_menu
        await show_games_menu(query.message, context)

# Fonction pour générer une prédiction de pomme
async def generate_apple_prediction(query, context, is_new: bool = False) -> None:
    """Génère une prédiction de position de pomme."""
    # Initialiser la séquence si nécessaire
    if is_new or "apple_sequence" not in context.user_data:
        context.user_data["apple_sequence"] = []
    
    # Choisir une position aléatoire entre 1 et 5
    position = random.randint(1, 5)
    
    # Ajouter à la séquence
    context.user_data["apple_sequence"].append(position)
    sequence_num = len(context.user_data["apple_sequence"])
    
    # Créer le message de prédiction
    apple_text = (
        f"🍎 *APPLE OF FORTUNE - Prédiction #{sequence_num}*\n\n"
        f"Position: *{position}* sur 5\n\n"
    )
    
    # Représentation visuelle de la prédiction
    apple_display = ""
    for i in range(1, 6):
        if i == position:
            apple_display += "🍎 "
        else:
            apple_display += "⬜ "
    
    apple_text += f"{apple_display}\n\n"
    
    # Ajouter une petite explication
    apple_text += "_Cette position de pomme a été générée aléatoirement._\n\n"
    
    # Buttons pour les actions suivantes
    # Buttons pour les actions suivantes
    keyboard = [
        [InlineKeyboardButton("▶️ Suivant", callback_data="apple_next")],
        [InlineKeyboardButton("🔄 Nouvelle prédiction", callback_data="apple_new")],
        [InlineKeyboardButton("🎮 Accueil", callback_data="show_games")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Animation de la prédiction
    loading_frames = [
        "🔮 *Génération de la prédiction...*",
        "🔍 *Recherche de la pomme...*",
        "🧙‍♂️ *Analyse des positions...*"
    ]
    
    # Afficher l'animation
    await query.edit_message_text(loading_frames[0], parse_mode='Markdown')
    
    for frame in loading_frames[1:]:
        await asyncio.sleep(0.3)
        await query.edit_message_text(frame, parse_mode='Markdown')
    
    # Animation de sélection de la pomme
    pomme_frames = ["⬜ ⬜ ⬜ ⬜ ⬜"]
    
    # Construire l'animation de la pomme qui apparaît
    position_chars = ["⬜"] * 5
    position_chars[position-1] = "🍎"
    final_position = " ".join(position_chars)
    
    # Ajouter un effet de suspense avec des étoiles
    suspense_frames = []
    for i in range(1, 6):
        frame_chars = ["⬜"] * 5
        frame_chars[i-1] = "✨"
        suspense_frames.append(" ".join(frame_chars))
    
    # Ajouter la révélation finale
    suspense_frames.append(final_position)
    
    # Afficher l'animation de suspense
    for frame in suspense_frames:
        await asyncio.sleep(0.2)
        await query.edit_message_text(f"*Prédiction en cours...*\n\n{frame}", parse_mode='Markdown')
    
    # Afficher le message final
    await asyncio.sleep(0.3)
    await query.edit_message_text(apple_text, reply_markup=reply_markup, parse_mode='Markdown')
