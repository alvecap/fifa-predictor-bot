def format_prediction_message(prediction: Dict[str, Any]) -> str:
    """Formate le résultat de prédiction en message lisible avec émojis"""
    if "error" in prediction:
        return f"❌ Erreur: {prediction['error']}"
    
    teams = prediction["teams"]
    team1 = teams["team1"]
    team2 = teams["team2"]
    
    message = [
        f"🔮 *PRÉDICTION: {team1} vs {team2}*",
        f"📊 Niveau de confiance: {prediction['confidence_level']}%",
        f"🤝 Confrontations directes: {prediction['direct_matches']}",
        "\n"
    ]
    
    # Section 1: Scores exacts à la première mi-temps
    message.append("⏱️ *SCORES PRÉVUS (1ÈRE MI-TEMPS):*")
    if prediction["half_time_scores"]:
        for i, score_data in enumerate(prediction["half_time_scores"], 1):
            message.append(f"  {i}. {score_data['score']} ({score_data['confidence']}%)")
    else:
        message.append("  Pas assez de données pour prédire le score à la mi-temps")
    
    # Gagnant à la mi-temps
    winner_ht = prediction["winner_half_time"]
    if winner_ht["team"]:
        if winner_ht["team"] == "Nul":
            message.append(f"  👉 Mi-temps: Match nul probable ({winner_ht['probability']}%)")
        else:
            message.append(f"  👉 Mi-temps: {winner_ht['team']} gagnant probable ({winner_ht['probability']}%)")
    message.append("")
    
    # Section 2: Scores exacts au temps réglementaire
    message.append("⚽ *SCORES PRÉVUS (TEMPS RÉGLEMENTAIRE):*")
    if prediction["full_time_scores"]:
        for i, score_data in enumerate(prediction["full_time_scores"], 1):
            message.append(f"  {i}. {score_data['score']} ({score_data['confidence']}%)")
    else:
        message.append("  Pas assez de données pour prédire le score final")
    
    # Gagnant du match
    winner_ft = prediction["winner_full_time"]
    if winner_ft["team"]:
        if winner_ft["team"] == "Nul":
            message.append(f"  👉 Résultat final: Match nul probable ({winner_ft['probability']}%)")
        else:
            message.append(f"  👉 Résultat final: {winner_ft['team']} gagnant probable ({winner_ft['probability']}%)")
    message.append("")
    
    # Section 3: Statistiques moyennes
    message.append("📈 *STATISTIQUES MOYENNES:*")
    message.append(f"  • Buts 1ère mi-temps: {prediction['avg_goals_half_time']}")
    message.append(f"  • Buts temps réglementaire: {prediction['avg_goals_full_time']}")
    
    # Section 4: Information sur les cotes si disponibles
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        message.append("")
        message.append("💰 *COTES:*")
        message.append(f"  • {team1}: {odds['team1']}")
        message.append(f"  • {team2}: {odds['team2']}")
    
    return "\n".join(message)
