def normalize_team_name(team_name):
    """Normalise le nom d'une équipe en supprimant les accents et en standardisant le format"""
    import unicodedata
    import re
    
    if not team_name:
        return ""
    
    # Convertir en minuscule et supprimer les accents
    team_name = team_name.lower()
    team_name = unicodedata.normalize('NFKD', team_name).encode('ASCII', 'ignore').decode('utf-8')
    
    # Standardiser les noms communs
    replacements = {
        "forest": "nottingham forest",
        "foret de nottingham": "nottingham forest",
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
