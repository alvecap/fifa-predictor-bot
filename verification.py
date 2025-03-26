import logging
import asyncio
from typing import Optional, Callable, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes

from database import check_user_subscription
from referral_system import has_completed_referrals, MAX_REFERRALS, count_referrals

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Liste des administrateurs (accès complet sans vérifications)
ADMIN_USERNAMES = ["alve08"]  # Noms d'utilisateur des admins
ADMIN_IDS = [6054768666]  # ID des administrateurs

async def is_admin(user_id: int, username: str = None) -> bool:
    """
    Vérifie si l'utilisateur est un administrateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str, optional): Nom d'utilisateur Telegram
        
    Returns:
        bool: True si l'utilisateur est admin, False sinon
    """
    # Vérification par ID (plus fiable)
    if user_id in ADMIN_IDS:
        logger.info(f"Accès administrateur accordé à l'utilisateur ID: {user_id}")
        return True
    
    # Vérification par nom d'utilisateur (backup)
    if username and username.lower() in [admin.lower() for admin in ADMIN_USERNAMES]:
        logger.info(f"Accès administrateur accordé à l'utilisateur {username} (ID: {user_id})")
        return True
    
    return False

# Vérification d'abonnement
async def verify_subscription(message, user_id, username, context=None, edit=False) -> bool:
    """
    Vérifie si l'utilisateur est abonné au canal.
    
    Args:
        message: Message Telegram (pour répondre)
        user_id (int): ID de l'utilisateur
        username (str): Nom d'utilisateur
        context: Contexte de conversation Telegram (optionnel)
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        
    Returns:
        bool: True si l'utilisateur est abonné ou admin, False sinon
    """
    # Vérifier si c'est un admin
    if await is_admin(user_id, username):
        if edit and hasattr(message, 'edit_text'):
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
    
    if edit and hasattr(message, 'edit_text'):
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
        await asyncio.sleep(0.1)  # Animation rapide
    
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
            await verify_referral(message, user_id, username, context)
            
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

# Vérification de parrainage
async def verify_referral(message, user_id, username, context=None, edit=False) -> bool:
    """
    Vérifie si l'utilisateur a complété ses parrainages.
    
    Args:
        message: Message Telegram (pour répondre)
        user_id (int): ID de l'utilisateur
        username (str): Nom d'utilisateur
        context: Contexte de conversation Telegram (optionnel)
        edit (bool): Si True, édite le message au lieu d'en envoyer un nouveau
        
    Returns:
        bool: True si l'utilisateur a complété ses parrainages ou est admin, False sinon
    """
    # Vérifier si c'est un admin
    if await is_admin(user_id, username):
        if edit and hasattr(message, 'edit_text'):
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
    
    if edit and hasattr(message, 'edit_text'):
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
    has_completed = await has_completed_referrals(user_id, username)
    
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
async def verify_all_requirements(user_id, username, message, context=None) -> bool:
    """
    Vérifie toutes les conditions d'accès (abonnement + parrainage).
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str): Nom d'utilisateur Telegram
        message: Message Telegram pour répondre
        context: Contexte de conversation Telegram (optionnel)
        
    Returns:
        bool: True si l'utilisateur a accès (admin ou abonné+parrainé), False sinon
    """
    # Vérifier d'abord si c'est un admin
    if await is_admin(user_id, username):
        logger.info(f"Vérification contournée pour l'administrateur {username} (ID: {user_id})")
        return True
    
    # Vérifier l'abonnement
    is_subscribed = await check_user_subscription(user_id)
    if not is_subscribed:
        await send_subscription_required(message)
        return False
    
    # Vérifier le parrainage
    has_completed = await has_completed_referrals(user_id, username)
    if not has_completed:
        await send_referral_required(message)
        return False
    
    return True

# Affichage du menu principal des jeux
async def show_games_menu(message, context) -> None:
    """
    Affiche le menu principal avec tous les jeux disponibles.
    
    Args:
        message: Message Telegram pour répondre
        context: Contexte de conversation Telegram
    """
    # Extraire l'ID utilisateur et le nom d'utilisateur
    user_id = None
    username = None
    
    if hasattr(message, 'from_user'):
        user_id = message.from_user.id
        username = message.from_user.username
    elif context and context.user_data:
        user_id = context.user_data.get("user_id")
        username = context.user_data.get("username")
    
    # Vérifier si c'est un admin
    admin_status = False
    if user_id:
        admin_status = await is_admin(user_id, username)
    
    # Texte du menu
    menu_text = (
        "🎮 *FIFA GAMES - Menu Principal* 🎮\n\n"
        "Choisissez un jeu pour obtenir des prédictions :\n\n"
        "🏆 *FIFA 4x4 Predictor*\n"
        "_Prédictions précises basées sur des statistiques réelles et analyses de matchs_\n\n"
        "🍎 *Apple of Fortune*\n"
        "_Trouvez la bonne pomme grâce à notre système prédictif avancé_\n\n"
        "🃏 *Baccarat*\n"
        "_Anticipez le gagnant avec notre technologie d'analyse de tendances_\n\n"
        "⚡ *Plus de jeux en préparation* ⚡"
    )
    
    # Boutons pour accéder aux différents jeux
    keyboard = [
        [InlineKeyboardButton("🏆 FIFA 4x4 Predictor", callback_data="game_fifa")],
        [InlineKeyboardButton("🍎 Apple of Fortune", callback_data="game_apple")],
        [InlineKeyboardButton("🃏 Baccarat", callback_data="game_baccarat")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if admin_status:
            # Affichage direct sans animation pour les admins
            logger.info(f"Affichage direct du menu pour l'admin {username} (ID: {user_id})")
            if hasattr(message, 'edit_text'):
                await message.edit_text(
                    menu_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await message.reply_text(
                    menu_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            return
        
        # Animation pour les non-admins
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
        
# Vérification complète pour les callbacks
async def verify_callback_requirements(user_id, username, message, callback_function, context, *args, **kwargs) -> None:
    """
    Vérifie les conditions d'accès avant d'exécuter un callback.
    
    Args:
        user_id (int): ID de l'utilisateur
        username (str): Nom d'utilisateur
        message: Message Telegram
        callback_function: Fonction de callback à exécuter si les vérifications sont passées
        context: Contexte de conversation Telegram
        *args, **kwargs: Arguments additionnels pour la fonction de callback
    """
    # Vérifier d'abord si c'est un admin
    if await is_admin(user_id, username):
        # Exécuter directement le callback pour les admins
        logger.info(f"Exécution directe pour l'admin {username} (ID: {user_id})")
        await callback_function(context, *args, **kwargs)
        return
    
    # Pour les non-admins, vérifier les conditions d'accès
    has_access = await verify_all_requirements(user_id, username, message, context)
    if has_access:
        # Si toutes les vérifications sont passées, exécuter le callback
        await callback_function(context, *args, **kwargs)
