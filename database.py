def get_all_teams():
    """Récupère la liste de toutes les équipes"""
    matches = get_all_matches_data()
    teams = set()
    
    for match in matches:
        teams.add(match['team_home'])
        teams.add(match['team_away'])
    
    return sorted(list(teams))
