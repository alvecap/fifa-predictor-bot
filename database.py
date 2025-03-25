import gspread
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict, Counter
import logging
from datetime import datetime
from config import CREDENTIALS_FILE, SPREADSHEET_ID

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

def get_all_matches_data():
    """Récupère les données des matchs depuis Google Sheets"""
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        
        # Récupérer la feuille principale
        main_sheet = spreadsheet.worksheet("Tous les matchs")
        
        # Récupérer toutes les valeurs brutes
        all_values = main_sheet.get_all_values()
        
        # Déterminer la ligne d'en-tête (ligne 3 normalement)
        header_row_index = 2  # 0-based index pour la ligne 3
        
        # S'assurer qu'il y a assez de lignes
        if len(all_values) <= header_row_index:
            logger.warning("Pas assez de données dans la feuille")
            return []
        
        # Récupérer les en-têtes
        headers = all_values[header_row_index]
        
        # Créer l'index des colonnes importantes
        column_indices = {
            'match_id': next((i for i, h in enumerate(headers) if 'Match ID' in h or 'match' in h.lower()), None),
            'team_home': next((i for i, h in enumerate(headers) if 'Domicile' in h), None),
            'team_away': next((i for i, h in enumerate(headers) if 'Extérieur' in h), None),
            'score_final': next((i for i, h in enumerate(headers) if 'Final' in h), None),
            'score_1ere': next((i for i, h in enumerate(headers) if '1ère' in h or '1ere' in h), None)
        }
        
        # Vérifier que les colonnes essentielles sont présentes
        missing_columns = [k for k, v in column_indices.items() if v is None]
        if missing_columns:
            logger.warning(f"Colonnes manquantes: {missing_columns}")
            logger.warning(f"En-têtes disponibles: {headers}")
            return []
        
        # Extraire les données
        matches = []
        for i in range(header_row_index + 1, len(all_values)):
            row = all_values[i]
            if len(row) <= max(column_indices.values()):
                continue  # Ignorer les lignes trop courtes
            
            match = {
                'match_id': row[column_indices['match_id']] if column_indices['match_id'] < len(row) else '',
                'team_home': row[column_indices['team_home']] if column_indices['team_home'] < len(row) else '',
                'team_away': row[column_indices['team_away']] if column_indices['team_away'] < len(row) else '',
                'score_final': row[column_indices['score_final']] if column_indices['score_final'] < len(row) else '',
                'score_1ere': row[column_indices['score_1ere']] if column_indices['score_1ere'] < len(row) else ''
            }
            
            if match['team_home'] and match['team_away']:
                matches.append(match)
        
        logger.info(f"Récupération de {len(matches)} matchs réussie")
        return matches
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des données de matchs: {e}")
        return []

def get_all_teams():
    """Récupère la liste de toutes les équipes"""
    matches = get_all_matches_data()
    teams = set()
    
    for match in matches:
        teams.add(match['team_home'])
        teams.add(match['team_away'])
    
    return sorted(list(teams))

def get_team_statistics(matches):
    """Calcule les statistiques pour chaque équipe"""
    team_stats = {}
    
    for match in matches:
        team_home = match.get('team_home', '')
        team_away = match.get('team_away', '')
        score_final = match.get('score_final', '')
        score_1ere = match.get('score_1ere', '')
        
        if not team_home or not team_away or not score_final:
            continue
        
        # Initialiser les équipes si nécessaire
        if team_home not in team_stats:
            team_stats[team_home] = {
                'home_matches': 0, 'away_matches': 0,
                'home_goals_for': [], 'home_goals_against': [],
                'away_goals_for': [], 'away_goals_against': [],
                'home_first_half': [], 'away_first_half': [],
                'home_wins': 0, 'home_losses': 0, 'home_draws': 0,
                'away_wins': 0, 'away_losses': 0, 'away_draws': 0
            }
        
        if team_away not in team_stats:
            team_stats[team_away] = {
                'home_matches': 0, 'away_matches': 0,
                'home_goals_for': [], 'home_goals_against': [],
                'away_goals_for': [], 'away_goals_against': [],
                'home_first_half': [], 'away_first_half': [],
                'home_wins': 0, 'home_losses': 0, 'home_draws': 0,
                'away_wins': 0, 'away_losses': 0, 'away_draws': 0
            }
        
        # Extraire les scores finaux
        try:
            score_parts = score_final.split(':')
            home_goals = int(score_parts[0])
            away_goals = int(score_parts[1])
            
            # Mettre à jour les statistiques domicile/extérieur
            team_stats[team_home]['home_matches'] += 1
            team_stats[team_home]['home_goals_for'].append(home_goals)
            team_stats[team_home]['home_goals_against'].append(away_goals)
            
            team_stats[team_away]['away_matches'] += 1
            team_stats[team_away]['away_goals_for'].append(away_goals)
            team_stats[team_away]['away_goals_against'].append(home_goals)
            
            # Déterminer le résultat
            if home_goals > away_goals:
                team_stats[team_home]['home_wins'] += 1
                team_stats[team_away]['away_losses'] += 1
            elif away_goals > home_goals:
                team_stats[team_home]['home_losses'] += 1
                team_stats[team_away]['away_wins'] += 1
            else:
                team_stats[team_home]['home_draws'] += 1
                team_stats[team_away]['away_draws'] += 1
        except (ValueError, IndexError):
            pass
        
        # Extraire les scores de première période
        if score_1ere:
            try:
                half_parts = score_1ere.split(':')
                half_home = int(half_parts[0])
                half_away = int(half_parts[1])
                
                # Stocker les scores de première période
                team_stats[team_home]['home_first_half'].append(f"{half_home}:{half_away}")
                team_stats[team_away]['away_first_half'].append(f"{half_home}:{half_away}")
            except (ValueError, IndexError):
                pass
    
    return team_stats

def get_match_id_trends(matches):
    """Analyse les tendances par numéro de match"""
    match_id_trends = defaultdict(lambda: {'final_scores': [], 'first_half_scores': []})
    
    for match in matches:
        match_id = match.get('match_id', '')
        score_final = match.get('score_final', '')
        score_1ere = match.get('score_1ere', '')
        
        if match_id and score_final:
            match_id_trends[match_id]['final_scores'].append(score_final)
        
        if match_id and score_1ere:
            match_id_trends[match_id]['first_half_scores'].append(score_1ere)
    
    return match_id_trends

def get_common_scores(scores_list, top_n=5):
    """Retourne les scores les plus communs avec leur fréquence"""
    if not scores_list:
        return []
    
    counter = Counter(scores_list)
    total = len(scores_list)
    
    # Trier par fréquence et prendre les top_n plus fréquents
    most_common = counter.most_common(top_n)
    return [(score, count, round(count/total*100, 1)) for score, count in most_common]

def get_direct_confrontations(matches, team1, team2):
    """Récupère l'historique des confrontations directes entre deux équipes"""
    confrontations = []
    
    for match in matches:
        home = match.get('team_home', '')
        away = match.get('team_away', '')
        
        # Vérifier si c'est une confrontation entre ces deux équipes
        if (home == team1 and away == team2) or (home == team2 and away == team1):
            confrontations.append(match)
    
    return confrontations

def save_prediction_log(user_id, username, team1, team2, odds1=None, odds2=None, prediction_result=None):
    """Enregistre les prédictions demandées par les utilisateurs pour analyse future"""
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        
        # Récupérer ou créer la feuille de logs
        try:
            log_sheet = spreadsheet.worksheet("Logs des prédictions")
        except gspread.exceptions.WorksheetNotFound:
            log_sheet = spreadsheet.add_worksheet(title="Logs des prédictions", rows=1000, cols=10)
            # Ajouter les en-têtes
            log_sheet.update('A1:I1', [['Date', 'User ID', 'Username', 'Équipe 1', 'Équipe 2', 
                                        'Cote 1', 'Cote 2', 'Résultats prédits', 'Statut']])
        
        # Formater les résultats de prédiction
        prediction_str = "N/A"
        if prediction_result:
            try:
                prediction_str = str(prediction_result)
            except:
                prediction_str = "Format non supporté"
        
        # Obtenir la date actuelle
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Ajouter l'entrée de log
        log_sheet.append_row([
            current_date,
            str(user_id),
            username or "Inconnu",
            team1,
            team2,
            str(odds1) if odds1 else "N/A",
            str(odds2) if odds2 else "N/A",
            prediction_str,
            "Complété"
        ])
        
        logger.info(f"Log enregistré pour la prédiction {team1} vs {team2}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement du log: {e}")
        return False

# Fonctions pour le système de parrainage
async def register_user(user_id, username, referrer_id=None):
    """Enregistre un utilisateur dans la base de données et gère le parrainage"""
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        
        # Récupérer ou créer la feuille des utilisateurs
        try:
            users_sheet = spreadsheet.worksheet("Utilisateurs")
        except gspread.exceptions.WorksheetNotFound:
            users_sheet = spreadsheet.add_worksheet(title="Utilisateurs", rows=1000, cols=6)
            # Ajouter les en-têtes
            users_sheet.update('A1:F1', [['ID', 'Username', 'Date inscription', 'Parrain ID', 'Parrainages', 'Dernier accès']])
        
        # Vérifier si l'utilisateur existe déjà
        try:
            user_cell = users_sheet.find(str(user_id))
            user_row = user_cell.row
            
            # Mettre à jour l'entrée existante (date de dernier accès)
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            users_sheet.update_cell(user_row, 6, current_date)  # Colonne F
            
            logger.info(f"Utilisateur {user_id} mis à jour")
            
            # Si un parrain est fourni et que l'utilisateur n'a pas de parrain, ajouter le parrain
            if referrer_id:
                existing_referrer = users_sheet.cell(user_row, 4).value  # Colonne D
                if not existing_referrer or existing_referrer == "None":
                    users_sheet.update_cell(user_row, 4, str(referrer_id))
                    
                    # Incrémenter le compteur de parrainages du parrain
                    await increment_referral_count(spreadsheet, referrer_id)
                    
                    logger.info(f"Parrain {referrer_id} ajouté pour l'utilisateur {user_id}")
                
            return True
        except gspread.exceptions.CellNotFound:
            # L'utilisateur n'existe pas, l'ajouter
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            users_sheet.append_row([
                str(user_id),
                username or "Inconnu",
                current_date,
                str(referrer_id) if referrer_id else "None",
                "0",
                current_date
            ])
            
            # Si un parrain est fourni, incrémenter son compteur de parrainages
            if referrer_id:
                await increment_referral_count(spreadsheet, referrer_id)
                
            logger.info(f"Nouvel utilisateur enregistré: {user_id}")
            return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de l'utilisateur: {e}")
        return False

async def increment_referral_count(spreadsheet, referrer_id):
    """Incrémente le compteur de parrainages d'un utilisateur"""
    try:
        users_sheet = spreadsheet.worksheet("Utilisateurs")
        
        # Trouver la cellule du parrain
        referrer_cell = users_sheet.find(str(referrer_id))
        referrer_row = referrer_cell.row
        
        # Récupérer le nombre actuel de parrainages
        current_count_str = users_sheet.cell(referrer_row, 5).value  # Colonne E
        if current_count_str and current_count_str.isdigit():
            current_count = int(current_count_str)
        else:
            current_count = 0
        
        # Incrémenter et mettre à jour
        new_count = current_count + 1
        users_sheet.update_cell(referrer_row, 5, str(new_count))
        
        logger.info(f"Compteur de parrainages de {referrer_id} incrémenté à {new_count}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'incrémentation du compteur de parrainages: {e}")
        return False

async def count_referrals(user_id):
    """Retourne le nombre de parrainages d'un utilisateur"""
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        users_sheet = spreadsheet.worksheet("Utilisateurs")
        
        # Trouver la cellule de l'utilisateur
        user_cell = users_sheet.find(str(user_id))
        user_row = user_cell.row
        
        # Récupérer le nombre de parrainages
        referrals_count_str = users_sheet.cell(user_row, 5).value  # Colonne E
        
        if referrals_count_str and referrals_count_str.isdigit():
            return int(referrals_count_str)
        else:
            return 0
    except gspread.exceptions.CellNotFound:
        logger.warning(f"Utilisateur {user_id} non trouvé dans la base de données")
        return 0
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du nombre de parrainages: {e}")
        return 0

async def has_completed_referrals(user_id, required_count=1):
    """Vérifie si l'utilisateur a atteint le nombre requis de parrainages"""
    referrals_count = await count_referrals(user_id)
    return referrals_count >= required_count

async def generate_referral_link(user_id, bot_username):
    """Génère un lien de parrainage pour l'utilisateur"""
    return f"https://t.me/{bot_username}?start=ref_{user_id}"

async def get_referred_users(user_id):
    """Récupère la liste des utilisateurs parrainés par l'utilisateur donné"""
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        users_sheet = spreadsheet.worksheet("Utilisateurs")
        
        # Récupérer toutes les données
        all_values = users_sheet.get_all_values()
        
        # Trouver l'index de la colonne de parrain
        header_row = all_values[0]
        referrer_col_idx = header_row.index("Parrain ID") if "Parrain ID" in header_row else 3  # Par défaut colonne D
        user_id_col_idx = header_row.index("ID") if "ID" in header_row else 0  # Par défaut colonne A
        username_col_idx = header_row.index("Username") if "Username" in header_row else 1  # Par défaut colonne B
        
        # Filtrer les utilisateurs qui ont l'ID de l'utilisateur comme parrain
        referred_users = []
        for row in all_values[1:]:  # Ignore header row
            if len(row) > referrer_col_idx and row[referrer_col_idx] == str(user_id):
                referred_users.append({
                    "id": row[user_id_col_idx] if len(row) > user_id_col_idx else "Unknown",
                    "username": row[username_col_idx] if len(row) > username_col_idx else "Unknown"
                })
        
        return referred_users
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des utilisateurs parrainés: {e}")
        return []

def save_referral(user_id, username, referral_link):
    """Enregistre un lien de parrainage dans la base de données"""
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        
        # Récupérer ou créer la feuille des liens de parrainage
        try:
            referrals_sheet = spreadsheet.worksheet("Liens de parrainage")
        except gspread.exceptions.WorksheetNotFound:
            referrals_sheet = spreadsheet.add_worksheet(title="Liens de parrainage", rows=1000, cols=4)
            # Ajouter les en-têtes
            referrals_sheet.update('A1:D1', [['User ID', 'Username', 'Lien', 'Date création']])
        
        # Vérifier si l'utilisateur a déjà un lien
        try:
            user_cell = referrals_sheet.find(str(user_id))
            user_row = user_cell.row
            
            # Mettre à jour le lien existant
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            referrals_sheet.update_cell(user_row, 3, referral_link)  # Colonne C
            referrals_sheet.update_cell(user_row, 4, current_date)  # Colonne D
            
            logger.info(f"Lien de parrainage mis à jour pour l'utilisateur {user_id}")
        except gspread.exceptions.CellNotFound:
            # L'utilisateur n'a pas de lien, en créer un nouveau
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            referrals_sheet.append_row([
                str(user_id),
                username or "Inconnu",
                referral_link,
                current_date
            ])
            
            logger.info(f"Nouveau lien de parrainage créé pour l'utilisateur {user_id}")
        
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement du lien de parrainage: {e}")
        return False

def check_referral_status(user_id):
    """Vérifie le statut de parrainage d'un utilisateur"""
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        users_sheet = spreadsheet.worksheet("Utilisateurs")
        
        # Trouver la cellule de l'utilisateur
        user_cell = users_sheet.find(str(user_id))
        user_row = user_cell.row
        user_data = users_sheet.row_values(user_row)
        
        # Récupérer les données pertinentes
        if len(user_data) >= 5:
            username = user_data[1]
            registration_date = user_data[2]
            referrer_id = user_data[3] if user_data[3] != "None" else None
            referrals_count = int(user_data[4]) if user_data[4].isdigit() else 0
            
            return {
                "user_id": user_id,
                "username": username,
                "registration_date": registration_date,
                "referrer_id": referrer_id,
                "referrals_count": referrals_count
            }
        else:
            logger.warning(f"Données incomplètes pour l'utilisateur {user_id}")
            return None
    except gspread.exceptions.CellNotFound:
        logger.warning(f"Utilisateur {user_id} non trouvé dans la base de données")
        return None
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut de parrainage: {e}")
        return None

async def check_user_subscription(user_id):
    """Vérifie si un utilisateur est abonné au canal"""
    # Cette fonction serait normalement implémentée avec l'API Telegram
    # Pour l'instant, nous retournons simplement True pour simuler un abonnement
    return True
