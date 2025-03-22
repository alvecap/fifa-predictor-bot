# Ajouter cette fonction au fichier database.py si elle n'existe pas déjà

def get_all_teams_alphabetical():
    """Récupère la liste de toutes les équipes, triée et organisée par lettre."""
    teams = get_all_teams()
    
    # Organiser les équipes par première lettre
    teams_by_letter = {}
    for team in teams:
        first_letter = team[0].upper()
        if first_letter not in teams_by_letter:
            teams_by_letter[first_letter] = []
        teams_by_letter[first_letter].append(team)
    
    # Trier les équipes dans chaque groupe
    for letter in teams_by_letter:
        teams_by_letter[letter].sort()
    
    return teams_by_letter
