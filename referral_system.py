import logging
import asyncio
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import TELEGRAM_TOKEN, CREDENTIALS_FILE, SPREADSHEET_ID

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Nombre maximum de parrainages requis
MAX_REFERRALS = 1

# Connexion à Google Sheets
def connect_to_sheets():
    """Établit la connexion avec Google Sheets"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(credentials)
        return client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        logger.error(f"Erreur de connexion à Google Sheets: {e}")
        raise

async def register_user(user_id, username, referrer_id=None):
    """
    Enregistre ou met à jour un utilisateur dans la base de données.
    Si referrer_id est fourni, crée une relation de parrainage.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str): Nom d'utilisateur Telegram
        referrer_id (int, optional): ID Telegram du parrain
    
    Returns:
        bool: True si l'opération a réussi, False sinon
    """
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        
        # Récupérer ou créer la feuille des utilisateurs
        try:
            users_sheet = spreadsheet.worksheet("Utilisateurs")
        except gspread.exceptions.WorksheetNotFound:
            # Si la feuille n'existe pas, on la crée
            users_sheet = spreadsheet.add_worksheet(title="Utilisateurs", rows=1000, cols=5)
            # Ajouter les en-têtes
            users_sheet.update('A1:E1', [['ID Telegram', 'Username', 'Date d\'inscription', 'Dernière activité', 'Parrainé par']])
        
        # Vérifier si l'utilisateur existe déjà
        try:
            user_cell = users_sheet.find(str(user_id))
            # Utilisateur trouvé, mise à jour
            row_index = user_cell.row
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Mettre à jour le nom d'utilisateur et la date d'activité
            users_sheet.update_cell(row_index, 2, username or "Inconnu")
            users_sheet.update_cell(row_index, 4, current_time)
            
            # Si un parrain est spécifié et que ce n'est pas déjà enregistré, le mettre à jour
            if referrer_id and referrer_id != user_id:
                current_referrer = users_sheet.cell(row_index, 5).value
                if not current_referrer:
                    users_sheet.update_cell(row_index, 5, str(referrer_id))
                    
                    # Créer la relation de parrainage
                    await create_referral_relationship(user_id, referrer_id)
            
        except gspread.exceptions.CellNotFound:
            # Utilisateur non trouvé, ajout
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = [str(user_id), username or "Inconnu", current_time, current_time, str(referrer_id) if referrer_id and referrer_id != user_id else ""]
            users_sheet.append_row(new_row)
            
            # Si un parrain est spécifié, créer la relation de parrainage
            if referrer_id and referrer_id != user_id:
                await create_referral_relationship(user_id, referrer_id)
        
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de l'utilisateur: {e}")
        return False

async def create_referral_relationship(user_id, referrer_id):
    """
    Crée une relation de parrainage dans la feuille de calcul.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur parrainé
        referrer_id (int): ID Telegram du parrain
    """
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        
        # Récupérer ou créer la feuille des parrainages
        try:
            referrals_sheet = spreadsheet.worksheet("Parrainages")
        except gspread.exceptions.WorksheetNotFound:
            # Si la feuille n'existe pas, on la crée
            referrals_sheet = spreadsheet.add_worksheet(title="Parrainages", rows=1000, cols=5)
            # Ajouter les en-têtes
            referrals_sheet.update('A1:E1', [['Parrain ID', 'Filleul ID', 'Date', 'Vérifié', 'Date de vérification']])
        
        # Vérifier si la relation de parrainage existe déjà
        try:
            # Chercher à la fois le parrain et le filleul pour être sûr
            referrals = referrals_sheet.get_all_values()
            relationship_exists = False
            
            for row in referrals[1:]:  # Ignorer l'en-tête
                if len(row) >= 2 and row[0] == str(referrer_id) and row[1] == str(user_id):
                    relationship_exists = True
                    break
            
            if not relationship_exists:
                # Créer la relation
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_row = [str(referrer_id), str(user_id), current_time, "Non", ""]
                referrals_sheet.append_row(new_row)
                
                # Lancer la vérification d'abonnement en arrière-plan
                asyncio.create_task(verify_and_update_referral(user_id, referrer_id))
        
        except Exception as e:
            logger.error(f"Erreur lors de la recherche ou création de la relation de parrainage: {e}")
    
    except Exception as e:
        logger.error(f"Erreur lors de la création de la relation de parrainage: {e}")

async def verify_and_update_referral(user_id, referrer_id):
    """
    Vérifie si l'utilisateur est abonné au canal et met à jour le statut de parrainage.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        referrer_id (int): ID Telegram du parrain
    """
    try:
        # Attendre un peu avant de vérifier (laisser le temps à l'utilisateur de s'abonner)
        await asyncio.sleep(5)
        
        # Vérifier l'abonnement
        is_subscribed = await check_channel_subscription(user_id)
        
        if is_subscribed:
            try:
                # Connexion à Google Sheets
                spreadsheet = connect_to_sheets()
                referrals_sheet = spreadsheet.worksheet("Parrainages")
                
                # Trouver la relation de parrainage
                referrals = referrals_sheet.get_all_values()
                for i, row in enumerate(referrals[1:], start=2):  # Start=2 pour tenir compte de l'en-tête
                    if len(row) >= 2 and row[0] == str(referrer_id) and row[1] == str(user_id):
                        # Mettre à jour le statut de vérification
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        referrals_sheet.update_cell(i, 4, "Oui")
                        referrals_sheet.update_cell(i, 5, current_time)
                        logger.info(f"Parrainage vérifié: {referrer_id} -> {user_id}")
                        break
            
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour du statut de parrainage: {e}")
        else:
            logger.info(f"Utilisateur {user_id} non abonné, parrainage non vérifié")
    
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du parrainage: {e}")

async def check_channel_subscription(user_id, channel_id="@alvecapitalofficiel"):
    """
    Vérifie si un utilisateur est abonné à un canal Telegram spécifique.
    
    Args:
        user_id (int): ID de l'utilisateur Telegram
        channel_id (str): ID du canal à vérifier (par défaut "@alvecapitalofficiel")
        
    Returns:
        bool: True si l'utilisateur est abonné, False sinon
    """
    try:
        # Vérification préalable si l'utilisateur est admin
        try:
            from verification import is_admin, ADMIN_IDS, ADMIN_USERNAMES
            # Vérification directe par ID (le plus fiable)
            if user_id in ADMIN_IDS:
                logger.info(f"Vérification d'abonnement contournée pour l'admin (ID: {user_id})")
                return True
        except ImportError:
            # Si verification n'est pas importable, on continue normalement
            pass
            
        bot = Bot(token=TELEGRAM_TOKEN)
        
        # Vérifier si l'utilisateur est membre du canal
        chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        
        # Les statuts qui indiquent une adhésion active au canal
        valid_statuses = ['creator', 'administrator', 'member']
        
        return chat_member.status in valid_statuses
    
    except TelegramError as e:
        logger.error(f"Erreur lors de la vérification de l'abonnement: {e}")
        return False

async def has_completed_referrals(user_id, username=None):
    """
    Vérifie si l'utilisateur a atteint le nombre requis de parrainages.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str, optional): Nom d'utilisateur Telegram pour vérification admin
        
    Returns:
        bool: True si l'utilisateur a complété ses parrainages ou est admin, False sinon
    """
    try:
        # Vérifier d'abord si c'est un admin (importation tardive pour éviter les imports circulaires)
        try:
            from verification import is_admin, ADMIN_IDS, ADMIN_USERNAMES
            
            # Vérification directe par ID (le plus fiable)
            if user_id in ADMIN_IDS:
                logger.info(f"Vérification de parrainage contournée pour l'admin (ID: {user_id})")
                return True
                
            # Vérification par nom d'utilisateur (backup)
            if username and username.lower() in [admin.lower() for admin in ADMIN_USERNAMES]:
                logger.info(f"Vérification de parrainage contournée pour l'admin {username}")
                return True
                
        except ImportError:
            # Si verification n'est pas importable, continue normalement
            pass
        
        referral_count = await count_referrals(user_id)
        return referral_count >= MAX_REFERRALS
    except Exception as e:
        logger.error(f"Erreur lors de la vérification des parrainages: {e}")
        return False

async def count_referrals(user_id):
    """
    Compte le nombre de parrainages vérifiés pour un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        int: Le nombre de parrainages vérifiés
    """
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        
        try:
            referrals_sheet = spreadsheet.worksheet("Parrainages")
            
            # Récupérer tous les parrainages
            referrals = referrals_sheet.get_all_values()
            
            # Compter les parrainages vérifiés où l'utilisateur est le parrain
            count = 0
            for row in referrals[1:]:  # Ignorer l'en-tête
                if len(row) >= 4 and row[0] == str(user_id) and row[3] == "Oui":
                    count += 1
            
            return count
        
        except gspread.exceptions.WorksheetNotFound:
            # La feuille n'existe pas, donc aucun parrainage
            return 0
    
    except Exception as e:
        logger.error(f"Erreur lors du comptage des parrainages: {e}")
        return 0

async def get_referred_users(user_id):
    """
    Récupère la liste des utilisateurs parrainés par un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        list: Liste des utilisateurs parrainés avec leurs informations
    """
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        
        try:
            referrals_sheet = spreadsheet.worksheet("Parrainages")
            users_sheet = spreadsheet.worksheet("Utilisateurs")
            
            # Récupérer tous les parrainages
            referrals = referrals_sheet.get_all_values()
            
            # Filtrer les parrainages où l'utilisateur est le parrain
            referred_user_ids = []
            referred_status = {}
            
            for row in referrals[1:]:  # Ignorer l'en-tête
                if len(row) >= 4 and row[0] == str(user_id):
                    filleul_id = row[1]
                    referred_user_ids.append(filleul_id)
                    referred_status[filleul_id] = row[3] == "Oui"  # Vérification du statut "Oui"
            
            # Récupérer les informations des utilisateurs parrainés
            referred_users = []
            
            for filleul_id in referred_user_ids:
                try:
                    user_cell = users_sheet.find(filleul_id)
                    row_values = users_sheet.row_values(user_cell.row)
                    
                    # S'assurer qu'il y a suffisamment de valeurs
                    if len(row_values) >= 2:
                        username = row_values[1]
                        referred_users.append({
                            'id': filleul_id,
                            'username': username,
                            'is_verified': referred_status.get(filleul_id, False)
                        })
                except gspread.exceptions.CellNotFound:
                    # Utilisateur non trouvé
                    referred_users.append({
                        'id': filleul_id,
                        'username': 'Inconnu',
                        'is_verified': referred_status.get(filleul_id, False)
                    })
            
            return referred_users
        
        except gspread.exceptions.WorksheetNotFound:
            # Une ou les deux feuilles n'existent pas
            return []
    
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des utilisateurs parrainés: {e}")
        return []

async def generate_referral_link(user_id, bot_username):
    """
    Génère un lien de parrainage pour un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        bot_username (str): Nom d'utilisateur du bot
        
    Returns:
        str: Lien de parrainage
    """
    return f"https://t.me/{bot_username}?start=ref{user_id}"

# Fonction pour obtenir les instructions de parrainage
def get_referral_instructions():
    """
    Retourne les instructions pour qu'un parrainage soit validé.
    
    Returns:
        str: Message formaté avec les instructions
    """
    return (
        "*📋 Conditions pour qu'un parrainage soit validé:*\n\n"
        "1️⃣ *L'invité doit cliquer sur votre lien de parrainage*\n"
        "2️⃣ *L'invité doit démarrer le bot* avec la commande /start\n"
        "3️⃣ *L'invité doit s'abonner* au canal [AL VE CAPITAL](https://t.me/alvecapitalofficiel)\n\n"
        "_Note: Le parrainage sera automatiquement vérifié et validé une fois ces conditions remplies_"
    )
