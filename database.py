import gspread
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict, Counter
import logging
from datetime import datetime
from config import CREDENTIALS_FILE, SPREADSHEET_ID
from telegram import Bot
from typing import Optional

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

async def check_user_subscription(user_id):
    """Vérifie si un utilisateur est abonné au canal @alvecapital1"""
    from config import TELEGRAM_TOKEN
    
    try:
        # Créer une instance du bot
        bot = Bot(token=TELEGRAM_TOKEN)
        
        # Vérifier si l'utilisateur est membre du canal
        chat_member = await bot.get_chat_member(chat_id="@alvecapital1", user_id=user_id)
        
        # Statuts indiquant que l'utilisateur est membre
        member_statuses = ['creator', 'administrator', 'member']
        
        # Vérifier le statut d'abonnement
        is_subscribed = chat_member.status in member_statuses
        
        logger.info(f"Vérification d'abonnement pour l'utilisateur {user_id}: {is_subscribed}")
        
        # Enregistrer la vérification
        save_subscription_log(user_id, None, is_subscribed)
        
        return is_subscribed
        
    except Exception as e:
        logger.error(f"Erreur lors de la vérification d'abonnement: {e}")
        # En cas d'erreur, considérer comme non abonné
        return False

def save_subscription_log(user_id, username, subscribed=False):
    """Enregistre les vérifications d'abonnement pour analyse future"""
    try:
        # Connexion à Google Sheets
        spreadsheet = connect_to_sheets()
        
        # Récupérer ou créer la feuille de logs d'abonnement
        try:
            sub_sheet = spreadsheet.worksheet("Logs des abonnements")
        except gspread.exceptions.WorksheetNotFound:
            sub_sheet = spreadsheet.add_worksheet(title="Logs des abonnements", rows=1000, cols=5)
            # Ajouter les en-têtes
            sub_sheet.update('A1:E1', [['Date', 'User ID', 'Username', 'Abonné', 'Action']])
        
        # Obtenir la date actuelle
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Ajouter l'entrée de log
        sub_sheet.append_row([
            current_date,
            str(user_id),
            username or "Inconnu",
            "Oui" if subscribed else "Non",
            "Vérification"
        ])
        
        logger.info(f"Log d'abonnement enregistré pour l'utilisateur {user_id}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement du log d'abonnement: {e}")
        return False
