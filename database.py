import gspread
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict, Counter
import logging
from datetime import datetime
import unicodedata
import re
from config import CREDENTIALS_FILE, SPREADSHEET_ID

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def normalize_team_name(team_name):
    """Normalise le nom d'une équipe en supprimant les accents et en standardisant le format"""
    if not team_name:
        return ""
    
    # Convertir en minuscule et supprimer les accents
    team_name = team_name.lower()
    team_name = unicodedata.normalize('NFKD', team_name).encode('ASCII', 'ignore').decode('utf-8')
    
    # Standardiser les noms communs
    replacements = {
        "forest": "nottingham forest",
        "foret de nottingham": "nottingham forest",
        "foret": "nottingham forest",
        "nottinghamforest": "nottingham forest",
        "man utd": "manchester united",
        "man united": "manchester united",
        "man city": "manchester city",
        "newcastle": "newcastle united",
        "west ham": "west ham united",
        "brighton": "brighton & hove albion",
        "tottenham": "tottenham hotspur",
        "spurs": "tottenham hotspur",
        "wolves": "wolverhampton",
        "sheffield": "sheffield united"
    }
    
    # Appliquer les remplacements
    for key, value in replacements.items():
        if key == team_name or key in team_name:
            return value
    
    return team_name

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

def get_direct_confrontations(matches, team1, team2):
    """Récupère l'historique des confrontations directes entre deux équipes"""
    confrontations = []
    
    # Normaliser les noms des équipes
    norm_team1 = normalize_team_name(team1)
    norm_team2 = normalize_team_name(team2)
    
    for match in matches:
        home = match.get('team_home', '')
        away = match.get('team_away', '')
        
        # Normaliser les noms des équipes dans le match
        norm_home = normalize_team_name(home)
        norm_away = normalize_team_name(away)
        
        # Vérifier si c'est une confrontation entre ces deux équipes
        if (norm_home == norm_team1 and norm_away == norm_team2) or \
           (norm_home == norm_team2 and norm_away == norm_team1):
            confrontations.append(match)
    
    return confrontations

def get_all_teams():
    """Récupère la liste de toutes les équipes"""
    matches = get_all_matches_data()
    teams = set()
    
    for match in matches:
        teams.add(match['team_home'])
        teams.add(match['team_away'])
    
    return sorted(list(teams))

def get_team_statistics(matches):
    """Calcule les statistiques pour chaque équipe avec une meilleure analyse des tendances à buts élevés"""
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
                'away_wins': 0, 'away_losses': 0, 'away_draws': 0,
                'high_scoring_matches': 0, 'avg_total_goals': 0
            }
        
        if team_away not in team_stats:
            team_stats[team_away] = {
                'home_matches': 0, 'away_matches': 0,
                'home_goals_for': [], 'home_goals_against': [],
                'away_goals_for': [], 'away_goals_against': [],
                'home_first_half': [], 'away_first_half': [],
                'home_wins': 0, 'home_losses': 0, 'home_draws': 0,
                'away_wins': 0, 'away_losses': 0, 'away_draws': 0,
                'high_scoring_matches': 0, 'avg_total_goals': 0
            }
        
        # Extraire les scores finaux
        try:
            score_parts = score_final.split(':')
            home_goals = int(score_parts[0])
            away_goals = int(score_parts[1])
            total_goals = home_goals + away_goals
            
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
            
            # Analyser les matchs à buts élevés
            if total_goals >= 10:  # Seuil pour matchs à buts très élevés
                team_stats[team_home]['high_scoring_matches'] += 1
                team_stats[team_away]['high_scoring_matches'] += 1
            
            # Mise à jour de la moyenne de buts
            team_stats[team_home]['avg_total_goals'] = (team_stats[team_home]['avg_total_goals'] * 
                                                        (team_stats[team_home]['home_matches'] - 1) + 
                                                        total_goals) / team_stats[team_home]['home_matches']
            
            team_stats[team_away]['avg_total_goals'] = (team_stats[team_away]['avg_total_goals'] * 
                                                        (team_stats[team_away]['away_matches'] - 1) + 
                                                        total_goals) / team_stats[team_away]['away_matches']
            
        except (ValueError, IndexError, ZeroDivisionError):
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
    """Analyse les tendances par numéro de match avec une meilleure gestion des buts élevés"""
    match_id_trends = defaultdict(lambda: {'final_scores': [], 'first_half_scores': [], 'avg_goals': 0, 'high_scoring': False})
    
    for match in matches:
        match_id = match.get('match_id', '')
        score_final = match.get('score_final', '')
        score_1ere = match.get('score_1ere', '')
        
        if match_id and score_final:
            match_id_trends[match_id]['final_scores'].append(score_final)
            
            # Analyser le nombre total de buts
            try:
                parts = score_final.split(':')
                total_goals = int(parts[0]) + int(parts[1])
                
                # Mettre à jour la moyenne de buts
                current_scores = match_id_trends[match_id]['final_scores']
                match_id_trends[match_id]['avg_goals'] = (match_id_trends[match_id]['avg_goals'] * (len(current_scores) - 1) + total_goals) / len(current_scores)
                
                # Marquer les matchs à buts élevés
                if total_goals >= 10:
                    match_id_trends[match_id]['high_scoring'] = True
            except (ValueError, IndexError, ZeroDivisionError):
                pass
        
        if match_id and score_1ere:
            match_id_trends[match_id]['first_half_scores'].append(score_1ere)
    
    return match_id_trends

def get_common_scores(scores_list, top_n=5):
    """Retourne les scores les plus communs avec leur fréquence et un bonus pour les scores à buts élevés"""
    if not scores_list:
        return []
    
    counter = Counter(scores_list)
    total = len(scores_list)
    
    # Calculer les statistiques de base
    raw_scores = [(score, count, round(count/total*100, 1)) for score, count in counter.items()]
    
    # Appliquer un bonus pour les scores à buts élevés
    enhanced_scores = []
    for score, count, percentage in raw_scores:
        try:
            parts = score.split(':')
            total_goals = int(parts[0]) + int(parts[1])
            
            # Appliquer un léger bonus pour les scores avec beaucoup de buts
            # pour refléter la tendance des matchs FIFA 4x4 à avoir des scores élevés
            if total_goals >= 10:
                # Bonus de 10% pour les scores très élevés
                enhanced_scores.append((score, count, percentage * 1.1))
            elif total_goals >= 7:
                # Bonus de 5% pour les scores élevés
                enhanced_scores.append((score, count, percentage * 1.05))
            else:
                enhanced_scores.append((score, count, percentage))
        except (ValueError, IndexError):
            enhanced_scores.append((score, count, percentage))
    
    # Trier par fréquence ajustée et prendre les top_n plus fréquents
    most_common = sorted(enhanced_scores, key=lambda x: x[2], reverse=True)[:top_n]
    return most_common

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
