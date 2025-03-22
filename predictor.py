from collections import defaultdict, Counter
import logging
from typing import Dict, List, Tuple, Optional, Any
import math
from config import MAX_PREDICTIONS_HALF_TIME, MAX_PREDICTIONS_FULL_TIME
from database import (
    get_all_matches_data, get_team_statistics, 
    get_match_id_trends, get_common_scores, get_direct_confrontations
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MatchPredictor:
    def __init__(self):
        """Initialise le prédicteur de match"""
        # Charger les données de matchs
        self.matches = get_all_matches_data()
        self.team_stats = None
        self.match_id_trends = None
        
        if self.matches:
            # Pré-calculer les statistiques pour améliorer les performances
            self.team_stats = get_team_statistics(self.matches)
            self.match_id_trends = get_match_id_trends(self.matches)
        else:
            logger.warning("Aucune donnée de match disponible!")

    def predict_match(self, team1: str, team2: str, odds1: float = None, odds2: float = None) -> Optional[Dict[str, Any]]:
        """Prédit le résultat d'un match entre team1 et team2"""
        logger.info(f"Analyse du match: {team1} vs {team2}")
        
        # Vérifier si les équipes existent dans nos données
        if not self.team_stats:
            logger.error("Statistiques d'équipes non disponibles")
            return None
            
        if team1 not in self.team_stats:
            logger.warning(f"Équipe '{team1}' non trouvée dans les données historiques")
            return {"error": f"Équipe '{team1}' non trouvée dans notre base de données"}
        
        if team2 not in self.team_stats:
            logger.warning(f"Équipe '{team2}' non trouvée dans les données historiques")
            return {"error": f"Équipe '{team2}' non trouvée dans notre base de données"}
        
        # Récupérer les confrontations directes
        direct_matches = get_direct_confrontations(self.matches, team1, team2)
        
        # Initialiser les résultats de prédiction
        prediction_results = {
            "teams": {
                "team1": team1,
                "team2": team2,
            },
            "odds": {
                "team1": odds1,
                "team2": odds2
            },
            "direct_matches": len(direct_matches),
            "half_time_scores": [],
            "full_time_scores": [],
            "winner_half_time": {"team": "", "probability": 0},
            "winner_full_time": {"team": "", "probability": 0},
            "avg_goals_half_time": 0,
            "avg_goals_full_time": 0,
            "confidence_level": 0
        }
        
        # 1. Analyse des confrontations directes
        direct_final_scores = []
        direct_first_half = []
        
        for match in direct_matches:
            home = match.get('team_home', '')
            away = match.get('team_away', '')
            score_final = match.get('score_final', '')
            score_1ere = match.get('score_1ere', '')
            
            if score_final:
                # Si on veut normaliser pour que team1 soit toujours à gauche
                if home == team1:
                    direct_final_scores.append(score_final)
                    if score_1ere:
                        direct_first_half.append(score_1ere)
                else:
                    # Inverser le score si team1 est à l'extérieur
                    try:
                        parts = score_final.split(':')
                        direct_final_scores.append(f"{parts[1]}:{parts[0]}")
                        
                        if score_1ere:
                            half_parts = score_1ere.split(':')
                            direct_first_half.append(f"{half_parts[1]}:{half_parts[0]}")
                    except (ValueError, IndexError):
                        pass
        
        # Analyse des scores les plus fréquents dans les confrontations directes
        common_direct_final = get_common_scores(direct_final_scores)
        common_direct_half = get_common_scores(direct_first_half)
        
        # Préparation pour les prédictions multiples
        all_final_scores = []
        all_half_scores = []
        
        # Ajouter les scores des confrontations directes avec leur poids
        if common_direct_final:
            for score, count, pct in common_direct_final[:MAX_PREDICTIONS_FULL_TIME]:
                all_final_scores.append((score, pct * 1.5))  # Poids plus élevé pour les confrontations directes
        
        if common_direct_half:
            for score, count, pct in common_direct_half[:MAX_PREDICTIONS_HALF_TIME]:
                all_half_scores.append((score, pct * 1.5))
        
        # 2. Analyse des performances à domicile/extérieur avec pondération améliorée
        # Team1 à domicile - considéré comme l'équipe recevant
        home_matches = self.team_stats[team1]['home_matches']
        if home_matches > 0:
            home_win_pct = round(self.team_stats[team1]['home_wins'] / home_matches * 100, 1)
            home_draw_pct = round(self.team_stats[team1]['home_draws'] / home_matches * 100, 1)
            home_loss_pct = round(self.team_stats[team1]['home_losses'] / home_matches * 100, 1)
            
            # Scores les plus fréquents à domicile
            home_scores = [f"{g_for}:{g_against}" for g_for, g_against in zip(
                self.team_stats[team1]['home_goals_for'], self.team_stats[team1]['home_goals_against'])]
            common_home = get_common_scores(home_scores)
            
            if common_home:
                # Plus de poids aux équipes avec plus de matchs à domicile (meilleur échantillon)
                home_weight_factor = min(1.0 + (home_matches / 20), 1.5)
                for score, count, pct in common_home[:MAX_PREDICTIONS_FULL_TIME]:
                    all_final_scores.append((score, pct * home_weight_factor))
            
            # 1ère mi-temps à domicile
            common_home_half = get_common_scores(self.team_stats[team1]['home_first_half'])
            if common_home_half:
                for score, count, pct in common_home_half[:MAX_PREDICTIONS_HALF_TIME]:
                    all_half_scores.append((score, pct * home_weight_factor))
        
        # Team2 à l'extérieur
        away_matches = self.team_stats[team2]['away_matches']
        if away_matches > 0:
            away_win_pct = round(self.team_stats[team2]['away_wins'] / away_matches * 100, 1)
            away_draw_pct = round(self.team_stats[team2]['away_draws'] / away_matches * 100, 1)
            away_loss_pct = round(self.team_stats[team2]['away_losses'] / away_matches * 100, 1)
            
            # Scores les plus fréquents à l'extérieur
            away_scores = [f"{g_for}:{g_against}" for g_for, g_against in zip(
                self.team_stats[team2]['away_goals_for'], self.team_stats[team2]['away_goals_against'])]
            common_away = get_common_scores(away_scores)
            
            if common_away:
                # Plus de poids aux équipes avec plus de matchs à l'extérieur
                away_weight_factor = min(1.0 + (away_matches / 20), 1.5)
                for score, count, pct in common_away[:MAX_PREDICTIONS_FULL_TIME]:
                    # Inverser le score car on a les stats du point de vue de l'équipe à l'extérieur
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        all_final_scores.append((inverted_score, pct * away_weight_factor))
                    except (ValueError, IndexError):
                        pass
            
            # 1ère mi-temps à l'extérieur
            common_away_half = get_common_scores(self.team_stats[team2]['away_first_half'])
            if common_away_half:
                for score, count, pct in common_away_half[:MAX_PREDICTIONS_HALF_TIME]:
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        all_half_scores.append((inverted_score, pct * away_weight_factor))
                    except (ValueError, IndexError):
                        pass
        
        # 3. Calculer les forces relatives des équipes
        team1_power = 0
        team2_power = 0
        
        # Points basés sur le ratio de victoires à domicile/extérieur
        if home_matches > 0:
            team1_power += (self.team_stats[team1]['home_wins'] / home_matches) * 50
        
        if away_matches > 0:
            team2_power += (self.team_stats[team2]['away_wins'] / away_matches) * 50
        
        # Points basés sur la différence de buts
        if home_matches > 0:
            home_goals_for = sum(self.team_stats[team1]['home_goals_for'])
            home_goals_against = sum(self.team_stats[team1]['home_goals_against'])
            avg_goal_diff = (home_goals_for - home_goals_against) / home_matches
            team1_power += max(0, avg_goal_diff * 10)  # 10 points par but de différence positive
        
        if away_matches > 0:
            away_goals_for = sum(self.team_stats[team2]['away_goals_for'])
            away_goals_against = sum(self.team_stats[team2]['away_goals_against'])
            avg_goal_diff = (away_goals_for - away_goals_against) / away_matches
            team2_power += max(0, avg_goal_diff * 10)
        
        # Ajuster en fonction des cotes si disponibles
        if odds1 and odds2:
            # Cotes plus faibles = équipe plus forte
            cotes_factor1 = 100 / (odds1 * 2)  # Max 50 points pour des cotes de 1.0
            cotes_factor2 = 100 / (odds2 * 2)
            
            team1_power = team1_power * 0.7 + cotes_factor1 * 0.3
            team2_power = team2_power * 0.7 + cotes_factor2 * 0.3
        
        # Calculer les probabilités de victoire
        total_power = team1_power + team2_power
        if total_power > 0:
            win_prob_team1 = team1_power / total_power * 0.8  # 80% des matchs ont un gagnant
            win_prob_team2 = team2_power / total_power * 0.8
        else:
            win_prob_team1 = 0.4
            win_prob_team2 = 0.4
        
        draw_prob = 1 - win_prob_team1 - win_prob_team2
        
        # 4. Ajouter les tendances par numéro de match
        all_match_ids = [match.get('match_id', '') for match in self.matches if match.get('match_id', '')]
        match_id_counter = Counter(all_match_ids)
        most_common_ids = match_id_counter.most_common(3)
        
        for match_id, _ in most_common_ids:
            if match_id in self.match_id_trends:
                final_scores = self.match_id_trends[match_id]['final_scores']
                first_half_scores = self.match_id_trends[match_id]['first_half_scores']
                
                common_final = get_common_scores(final_scores)
                common_half = get_common_scores(first_half_scores)
                
                if common_final:
                    for score, count, pct in common_final[:2]:
                        all_final_scores.append((score, pct * 0.8))  # Poids légèrement plus faible
                
                if common_half:
                    for score, count, pct in common_half[:2]:
                        all_half_scores.append((score, pct * 0.8))
        
        # 5. Ajouter une analyse statistique basée sur le nombre moyen de buts
        # Calculer moyennes de buts marqués et encaissés
        team1_avg_scored = 0
        team1_avg_conceded = 0
        if home_matches > 0:
            team1_avg_scored = sum(self.team_stats[team1]['home_goals_for']) / home_matches
            team1_avg_conceded = sum(self.team_stats[team1]['home_goals_against']) / home_matches
        
        team2_avg_scored = 0
        team2_avg_conceded = 0
        if away_matches > 0:
            team2_avg_scored = sum(self.team_stats[team2]['away_goals_for']) / away_matches
            team2_avg_conceded = sum(self.team_stats[team2]['away_goals_against']) / away_matches
        
        # Prédiction basée sur les moyennes croisées
        expected_team1_goals = (team1_avg_scored + team2_avg_conceded) / 2
        expected_team2_goals = (team2_avg_scored + team1_avg_conceded) / 2
        
        # Générer quelques scores possibles selon ces moyennes
        import itertools
        
        # Définir les plages de scores possibles
        team1_range = range(max(0, int(expected_team1_goals - 1)), int(expected_team1_goals + 2))
        team2_range = range(max(0, int(expected_team2_goals - 1)), int(expected_team2_goals + 2))
        
        # Générer toutes les combinaisons dans ces plages
        for t1, t2 in itertools.product(team1_range, team2_range):
            # Calcul de probabilité simple
            distance_from_expected = ((t1 - expected_team1_goals) ** 2 + (t2 - expected_team2_goals) ** 2) ** 0.5
            probability = max(10, 100 - distance_from_expected * 25)  # Entre 10 et 100
            
            score = f"{t1}:{t2}"
            all_final_scores.append((score, probability))
            
            # Pour la mi-temps, diviser les valeurs par 2
            if t1 // 2 == t1 / 2 and t2 // 2 == t2 / 2:  # N'ajouter que des scores plausibles
                half_score = f"{t1//2}:{t2//2}"
                all_half_scores.append((half_score, probability * 0.8))
        
        # 6. Combiner et fusionner les scores identiques
        final_score_weights = defaultdict(float)
        for score, weight in all_final_scores:
            final_score_weights[score] += weight
        
        half_score_weights = defaultdict(float)
        for score, weight in all_half_scores:
            half_score_weights[score] += weight
        
        # Trier par poids décroissant
        sorted_final_scores = sorted(final_score_weights.items(), key=lambda x: x[1], reverse=True)
        sorted_half_scores = sorted(half_score_weights.items(), key=lambda x: x[1], reverse=True)
        
        # 7. Remplir les résultats de prédiction
        
        # Prédictions des scores mi-temps
        if sorted_half_scores:
            num_predictions = min(MAX_PREDICTIONS_HALF_TIME, len(sorted_half_scores))
            total_weight = sum(weight for _, weight in sorted_half_scores[:num_predictions])
            
            for i in range(num_predictions):
                score, weight = sorted_half_scores[i]
                # Normaliser la confiance entre 50 et 95%
                normalized_weight = weight / total_weight if total_weight > 0 else 0
                confidence = min(95, max(50, round(50 + normalized_weight * 45)))
                
                try:
                    parts = score.split(':')
                    team1_goals = int(parts[0])
                    team2_goals = int(parts[1])
                    
                    prediction_results["half_time_scores"].append({
                        "score": score,
                        "confidence": confidence
                    })
                    
                    # Calculer la moyenne des buts pour la 1ère mi-temps
                    prediction_results["avg_goals_half_time"] += (team1_goals + team2_goals) / num_predictions
                    
                    # Déterminer le gagnant de la 1ère mi-temps pour le premier score
                    if i == 0:
                        if team1_goals > team2_goals:
                            half_time_confidence = min(90, round(confidence * 1.1))
                            prediction_results["winner_half_time"] = {"team": team1, "probability": half_time_confidence}
                        elif team2_goals > team1_goals:
                            half_time_confidence = min(90, round(confidence * 1.1))
                            prediction_results["winner_half_time"] = {"team": team2, "probability": half_time_confidence}
                        else:
                            prediction_results["winner_half_time"] = {"team": "Nul", "probability": confidence}
                except (ValueError, IndexError):
                    continue
        
        # Prédictions des scores temps réglementaire
        if sorted_final_scores:
            num_predictions = min(MAX_PREDICTIONS_FULL_TIME, len(sorted_final_scores))
            total_weight = sum(weight for _, weight in sorted_final_scores[:num_predictions])
            
            for i in range(num_predictions):
                score, weight = sorted_final_scores[i]
                # Normaliser la confiance entre 50 et 95%
                normalized_weight = weight / total_weight if total_weight > 0 else 0
                confidence = min(95, max(50, round(50 + normalized_weight * 45)))
                
                try:
                    parts = score.split(':')
                    team1_goals = int(parts[0])
                    team2_goals = int(parts[1])
                    
                    prediction_results["full_time_scores"].append({
                        "score": score,
                        "confidence": confidence
                    })
                    
                    # Calculer la moyenne des buts pour le temps réglementaire
                    prediction_results["avg_goals_full_time"] += (team1_goals + team2_goals) / num_predictions
                    
                    # Déterminer le gagnant du match pour le premier score
                    if i == 0:
                        if team1_goals > team2_goals:
                            win_confidence = round(win_prob_team1 * 100)
                            prediction_results["winner_full_time"] = {"team": team1, "probability": win_confidence}
                        elif team2_goals > team1_goals:
                            win_confidence = round(win_prob_team2 * 100)
                            prediction_results["winner_full_time"] = {"team": team2, "probability": win_confidence}
                        else:
                            draw_confidence = round(draw_prob * 100)
                            prediction_results["winner_full_time"] = {"team": "Nul", "probability": draw_confidence}
                except (ValueError, IndexError):
                    continue
        
        # 8. Calcul du niveau de confiance global
        confidence_factors = []
        
        # Facteur 1: Nombre de confrontations directes
        if len(direct_matches) >= 5:
            confidence_factors.append(90)
        elif len(direct_matches) >= 3:
            confidence_factors.append(80)
        elif len(direct_matches) >= 1:
            confidence_factors.append(70)
        else:
            confidence_factors.append(50)
        
        # Facteur 2: Nombre de matchs à domicile/extérieur
        min_matches = min(home_matches if home_matches > 0 else float('inf'), 
                          away_matches if away_matches > 0 else float('inf'))
        
        if min_matches == float('inf'):
            min_matches = 0
            
        if min_matches >= 10:
            confidence_factors.append(90)
        elif min_matches >= 5:
            confidence_factors.append(80)
        elif min_matches >= 2:
            confidence_factors.append(70)
        else:
            confidence_factors.append(50)
        
        # Facteur 3: Présence de cotes (indique une analyse supplémentaire)
        if odds1 and odds2:
            confidence_factors.append(75)
        
        # Facteur 4: Cohérence des prédictions
        if sorted_final_scores and sorted_half_scores:
            top_full_score = sorted_final_scores[0][0] if sorted_final_scores else ""
            top_half_score = sorted_half_scores[0][0] if sorted_half_scores else ""
            
            if top_full_score and top_half_score:
                try:
                    full_parts = top_full_score.split(':')
                    half_parts = top_half_score.split(':')
                    
                    # Si les tendances sont cohérentes entre mi-temps et temps complet
                    if (int(full_parts[0]) > int(full_parts[1]) and int(half_parts[0]) > int(half_parts[1])) or \
                       (int(full_parts[0]) < int(full_parts[1]) and int(half_parts[0]) < int(half_parts[1])) or \
                       (int(full_parts[0]) == int(full_parts[1]) and int(half_parts[0]) == int(half_parts[1])):
                        confidence_factors.append(85)
                    else:
                        confidence_factors.append(70)
                except (ValueError, IndexError):
                    confidence_factors.append(65)
        
        # Calcul de la confiance globale (moyenne pondérée)
        if confidence_factors:
            prediction_results["confidence_level"] = round(sum(confidence_factors) / len(confidence_factors))
        
        # Arrondir les moyennes de buts
        prediction_results["avg_goals_half_time"] = round(prediction_results["avg_goals_half_time"], 1)
        prediction_results["avg_goals_full_time"] = round(prediction_results["avg_goals_full_time"], 1)
        
        return prediction_results


def format_prediction_message(prediction: Dict[str, Any]) -> str:
    """Formate le résultat de prédiction en message lisible"""
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
    message.append("*⏱️ SCORES PRÉVUS (1ÈRE MI-TEMPS):*")
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
    message.append("*⚽ SCORES PRÉVUS (TEMPS RÉGLEMENTAIRE):*")
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
    
    # Nouvelle section: Recommandations de paris
    message.append("*💡 RECOMMANDATIONS:*")
    
    # Analyser le nombre de buts pour over/under
    avg_goals_ht = prediction["avg_goals_half_time"]
    ht_line = 0.5 if avg_goals_ht < 0.8 else (1.5 if avg_goals_ht < 2.3 else 2.5)
    ht_bet = "Plus" if avg_goals_ht > ht_line else "Moins"
    ht_pct = min(90, max(65, int(abs(avg_goals_ht - ht_line) * 20 + 65)))
    message.append(f"  • Mi-temps: {ht_bet} de {ht_line} buts ({ht_pct}%)")
    
    avg_goals_ft = prediction["avg_goals_full_time"]
    ft_line = 1.5 if avg_goals_ft < 2.5 else (2.5 if avg_goals_ft < 3.5 else 3.5)
    ft_bet = "Plus" if avg_goals_ft > ft_line else "Moins"
    ft_pct = min(90, max(65, int(abs(avg_goals_ft - ft_line) * 15 + 65)))
    message.append(f"  • Match: {ft_bet} de {ft_line} buts ({ft_pct}%)")
    
    # Recommandation sur le vainqueur si la probabilité est élevée
    if winner_ft["team"] != "Nul" and winner_ft["probability"] > 65:
        message.append(f"  • Vainqueur: {winner_ft['team']} ({winner_ft['probability']}%)")
    message.append("")
    
    # Section 3: Statistiques moyennes
    message.append("*📈 STATISTIQUES MOYENNES:*")
    message.append(f"  • Buts 1ère mi-temps: {prediction['avg_goals_half_time']}")
    message.append(f"  • Buts temps réglementaire: {prediction['avg_goals_full_time']}")
    
    # Section 4: Information sur les cotes si disponibles
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        message.append("")
        message.append("*💰 COTES:*")
        message.append(f"  • {team1}: {odds['team1']}")
        message.append(f"  • {team2}: {odds['team2']}")
    
    return "\n".join(message)
