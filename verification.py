import logging
import asyncio
from typing import Optional, Callable, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes

from database import check_user_subscription
from referral_system import has_completed_referrals, MAX_REFERRALS

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Liste des administrateurs (accès complet sans vérifications)
ADMIN_USERNAMES = ["alve08"]  # Ajoutez d'autres admins si nécessaire

async def is_admin(user_id: int, username: str) -> bool:
    """Vérifie si l'utilisateur est un administrateur."""
    if username and username.lower() in [admin.lower() for admin in ADMIN_USERNAMES]:
        logger.info(f"Accès administrateur accordé à l'utilisateur {username} (ID: {user_id})")
        return True
    return False

# Animation de vérification d'abonnement
async def animated_subscription_check(message, user_id, username, context=None, edit=False) -> bool:
    """Effectue une vérification d'abonnement avec animation et retourne le résultat."""
    # Vérifier d'abord si c'est un admin
    if await is_admin(user_id, username):
        if edit:
            await message.edit_text(
                "🔑 *Accès administrateur*\n\n"
                "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text(
                "🔑 *Accès administrateur*\n\n"
                "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown'
            )
        return True
    
    # Message initial
    verify_text = "🔍 *Vérification de votre abonnement*"
    
    if edit:
        msg = await message.edit_text(verify_text, parse_mode='Markdown')
    else:
        msg = await message.reply_text(verify_text, parse_mode='Markdown')
    
    # Animation stylisée (cercle qui tourne) - version accélérée
    emojis = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]
    
    for i in range(len(emojis)):
        await msg.edit_text(
            f"{emojis[i]} *Vérification de votre abonnement en cours...*",
            parse_mode='Markdown'
        )
        await asyncio.sleep(0.1)  # Réduit pour une animation plus rapide
    
    # Animation finale
    await msg.edit_text(
        "🔄 *Connexion avec Telegram...*",
        parse_mode='Markdown'
    )
    await asyncio.sleep(0.3)
    
    # Effectuer la vérification
    is_subscribed = await check_user_subscription(user_id)
    
    if is_subscribed:
        # Animation de succès - version accélérée
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
            await asyncio.sleep(0.1)
        
        # Message final de succès
        await msg.edit_text(
            "✅ *Abonnement vérifié!*\n\n"
            "Vous êtes bien abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Lancer la vérification du parrainage si le contexte est fourni
        if context:
            await animated_referral_check(message, user_id, username, context)
            
        return True
    else:
        # Animation d'échec - version accélérée
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
            await asyncio.sleep(0.1)
        
        # Message d'erreur
        keyboard = [
            [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
            [InlineKeyboardButton("🔍 Vérifier à nouveau", callback_data="verify_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            "❌ *Abonnement non détecté*\n\n"
            "Vous n'êtes pas encore abonné à [AL VE CAPITAL](https://t.me/alvecapitalofficiel).\n\n"
            "*Instructions:*\n"
            "1️⃣ Cliquez sur le bouton 'Rejoindre le canal'\n"
            "2️⃣ Abonnez-vous au canal\n"
            "3️⃣ Revenez ici et cliquez sur 'Vérifier à nouveau'",
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        return False

# Animation de vérification de parrainage
async def animated_referral_check(message, user_id, username, context=None, edit=False) -> bool:
    """Effectue une vérification de parrainage avec animation et retourne le résultat."""
    # Vérifier d'abord si c'est un admin
    if await is_admin(user_id, username):
        if edit:
            await message.edit_text(
                "🔑 *Accès administrateur*\n\n"
                "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text(
                "🔑 *Accès administrateur*\n\n"
                "Toutes les fonctionnalités sont débloquées en mode administrateur.",
                parse_mode='Markdown'
            )
            
        # Si on est en mode admin, on passe directement au menu des jeux
        if context:
            await show_games_menu(message, context)
            
        return True
    
    # Message initial
    verify_text = "🔍 *Vérification de votre parrainage*"
    
    if edit:
        msg = await message.edit_text(verify_text, parse_mode='Markdown')
    else:
        msg = await message.reply_text(verify_text, parse_mode='Markdown')
    
    # Animation stylisée (cercle qui tourne) - version accélérée
    emojis = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]
    
    for i in range(len(emojis)):
        await msg.edit_text(
            f"{emojis[i]} *Vérification de vos parrainages en cours...*",
            parse_mode='Markdown'
        )
        await asyncio.sleep(0.1)
    
    # Pause pour effet
    await msg.edit_text(
        "🔄 *Analyse des données...*",
        parse_mode='Markdown'
    )
    await asyncio.sleep(0.3)
    
    # Animation plus courte
    check_frames = [
        "📊 *Recherche de vos filleuls...*",
        "👥 *Comptage des parrainages...*",
        "📈 *Vérification des conditions...*"
    ]
    
    for frame in check_frames:
        await msg.edit_text(frame, parse_mode='Markdown')
        await asyncio.sleep(0.3)
    
    # Effectuer la vérification
    has_completed = await has_completed_referrals(user_id)
    
    if has_completed:
        # Animation de succès - version accélérée
        success_frames = [
            "⬜⬜⬜⬜⬜",
            "⬛⬜⬜⬜⬜",
            "⬛⬛⬜⬜⬜",
            "⬛⬛⬛⬜⬜",
            "⬛⬛⬛⬛⬜",
            "⬛⬛⬛⬛⬛",
            "✅ *Parrainage complété!*"
        ]
        
        for frame in success_frames:
            await msg.edit_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.1)
        
        # Message final de succès
        await msg.edit_text(
            "✅ *Parrainage complété!*\n\n"
            f"Vous avez atteint votre objectif de {MAX_REFERRALS} parrainage(s).\n"
            "Toutes les fonctionnalités sont désormais débloquées.",
            parse_mode='Markdown'
        )
        
        # Afficher le menu des jeux après validation complète
        if context:
            await show_games_menu(message, context)
        
        return True
    else:
        # Animation d'échec - version accélérée
        error_frames = [
            "⬜⬜⬜⬜⬜",
            "⬛⬜⬜⬜⬜",
            "⬛⬛⬜⬜⬜",
            "⬛⬛⬛⬜⬜",
            "⬛⬛⬛⬛⬜",
            "⬛⬛⬛⬛⬛",
            "⏳ *Parrainage en cours*"
        ]
        
        for frame in error_frames:
            await msg.edit_text(frame, parse_mode='Markdown')
            await asyncio.sleep(0.1)
        
        # Obtenir le nombre actuel de parrainages
        from referral_system import count_referrals
        referral_count = await count_referrals(user_id)
        
        # Message indiquant le nombre actuel de parrainages
        keyboard = [
            [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
            [InlineKeyboardButton("✅ Vérifier à nouveau", callback_data="verify_referral")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"⏳ *Parrainage en cours - {referral_count}/{MAX_REFERRALS}*\n\n"
            f"Vous avez actuellement {referral_count} parrainage(s) sur {MAX_REFERRALS} requis.\n\n"
            f"Partagez votre lien de parrainage pour débloquer toutes les fonctionnalités.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return False

# Message standard quand l'abonnement est requis
async def send_subscription_required(message) -> None:
    """Envoie un message indiquant que l'abonnement est nécessaire."""
    keyboard = [
        [InlineKeyboardButton("📣 Rejoindre le canal", url="https://t.me/alvecapitalofficiel")],
        [InlineKeyboardButton("🔍 Vérifier mon abonnement", callback_data="verify_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "⚠️ *Abonnement requis*\n\n"
        "Pour utiliser cette fonctionnalité, vous devez être abonné à notre canal.\n\n"
        "*Instructions:*\n"
        "1️⃣ Rejoignez [AL VE CAPITAL](https://t.me/alvecapitalofficiel)\n"
        "2️⃣ Cliquez sur '🔍 Vérifier mon abonnement'",
        reply_markup=reply_markup,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

# Message standard quand le parrainage est requis
async def send_referral_required(message) -> None:
    """Envoie un message indiquant que le parrainage est nécessaire."""
    keyboard = [
        [InlineKeyboardButton("🔗 Obtenir mon lien de parrainage", callback_data="get_referral_link")],
        [InlineKeyboardButton("✅ Vérifier mon parrainage", callback_data="verify_referral")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "⚠️ *Parrainage requis*\n\n"
        f"Pour utiliser cette fonctionnalité, vous devez parrainer {MAX_REFERRALS} personne(s).\n\n"
        "Partagez votre lien de parrainage avec vos amis pour débloquer toutes les fonctionnalités.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Vérification complète avant d'accéder à une fonctionnalité
async def verify_all_requirements(user_id, username, message, context=None, edit=False) -> bool:
    """Vérifie toutes les conditions d'accès (abonnement + parrainage)."""
    # Vérifier d'abord si c'est un admin
    # Vérifier d'abord si c'est un admin
    if await is_admin(user_id, username):
        return True
    
    # Vérifier l'abonnement
    is_subscribed = await check_user_subscription(user_id)
    if not is_subscribed:
        await send_subscription_required(message)
        return False
    
    # Vérifier le parrainage
    has_completed = await has_completed_referrals(user_id)
    if not has_completed:
        await send_referral_required(message)
        return False
    
    return True

# Fonction pour vérifier avant de lancer un jeu
async def verify_before_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_function: Callable) -> None:
    """Vérifie toutes les conditions avant de lancer un jeu."""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Vérifier les conditions d'accès
    if await verify_all_requirements(user_id, username, update.effective_message, context):
        # Si tout est validé, lance le jeu demandé
        await game_function(update, context)

# Affichage du menu principal des jeux
async def show_games_menu(message: Message, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu principal avec tous les jeux disponibles."""
    # Texte du menu
    menu_text = (
        "🎮 *FIFA GAMES - Menu Principal* 🎮\n\n"
        "Choisissez un jeu pour obtenir des prédictions :\n\n"
        "🏆 *FIFA 4x4 Predictor*\n"
        "_Prédictions précises basées sur des statistiques réelles de matchs FIFA 4x4_\n\n"
        "🍎 *Apple of Fortune*\n"
        "_Trouvez la bonne pomme et multipliez vos chances de gagner_\n\n"
        "🃏 *Baccarat*\n"
        "_Anticipez le gagnant entre le Joueur et le Banquier_\n\n"
        "⚡ *Plus de jeux bientôt disponibles!* ⚡"
    )
    
    # Boutons pour accéder aux différents jeux
    keyboard = [
        [InlineKeyboardButton("🏆 FIFA 4x4 Predictor", callback_data="game_fifa")],
        [InlineKeyboardButton("🍎 Apple of Fortune", callback_data="game_apple")],
        [InlineKeyboardButton("🃏 Baccarat", callback_data="game_baccarat")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Envoi du message avec animation
    try:
        # Animation de transition vers le menu des jeux
        transition_frames = [
            "🎲 *Chargement des jeux...*",
            "🎮 *Préparation du menu...*",
            "🎯 *Tout est prêt!*"
        ]
        
        msg = await message.reply_text(transition_frames[0], parse_mode='Markdown')
        
        for frame in transition_frames[1:]:
            await asyncio.sleep(0.3)
            await msg.edit_text(frame, parse_mode='Markdown')
        
        # Message final avec le menu
        await msg.edit_text(
            menu_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erreur lors de l'affichage du menu des jeux: {e}")
        await message.reply_text(
            "Désolé, une erreur s'est produite lors du chargement du menu des jeux. Veuillez réessayer.",
            parse_mode='Markdown'
        )

# Callback de vérification pour les actions qui nécessitent des permissions
async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_function: Callable) -> None:
    """Vérifie les conditions avant d'exécuter un callback spécifique."""
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username
    
    # Vérification rapide des conditions
    if await verify_all_requirements(user_id, username, query.message, context, edit=True):
        # Si tout est validé, exécute la fonction callback
        await callback_function(update, context)
