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
        
        # 2. Analyse des performances à domicile/extérieur
        # Team1 à domicile
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
                for score, count, pct in common_home[:MAX_PREDICTIONS_FULL_TIME]:
                    all_final_scores.append((score, pct))
            
            # 1ère mi-temps à domicile
            common_home_half = get_common_scores(self.team_stats[team1]['home_first_half'])
            if common_home_half:
                for score, count, pct in common_home_half[:MAX_PREDICTIONS_HALF_TIME]:
                    all_half_scores.append((score, pct))
        
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
                for score, count, pct in common_away[:MAX_PREDICTIONS_FULL_TIME]:
                    # Inverser le score car on a les stats du point de vue de l'équipe à l'extérieur
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        all_final_scores.append((inverted_score, pct))
                    except (ValueError, IndexError):
                        pass
            
            # 1ère mi-temps à l'extérieur
            common_away_half = get_common_scores(self.team_stats[team2]['away_first_half'])
            if common_away_half:
                for score, count, pct in common_away_half[:MAX_PREDICTIONS_HALF_TIME]:
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        all_half_scores.append((inverted_score, pct))
                    except (ValueError, IndexError):
                        pass
        
        # 3. Ajouter les tendances par numéro de match
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
        
        # Combiner et fusionner les scores identiques
        final_score_weights = defaultdict(float)
        for score, weight in all_final_scores:
            final_score_weights[score] += weight
        
        half_score_weights = defaultdict(float)
        for score, weight in all_half_scores:
            half_score_weights[score] += weight
        
        # Trier par poids décroissant
        sorted_final_scores = sorted(final_score_weights.items(), key=lambda x: x[1], reverse=True)
        sorted_half_scores = sorted(half_score_weights.items(), key=lambda x: x[1], reverse=True)
        
        # 4. Remplir les résultats de prédiction
        
        # Prédictions des scores mi-temps
        if sorted_half_scores:
            num_predictions = min(MAX_PREDICTIONS_HALF_TIME, len(sorted_half_scores))
            for i in range(num_predictions):
                score, weight = sorted_half_scores[i]
                confidence = min(99, max(50, round(weight)))
                
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
                            prediction_results["winner_half_time"] = {"team": team1, "probability": confidence}
                        elif team2_goals > team1_goals:
                            prediction_results["winner_half_time"] = {"team": team2, "probability": confidence}
                        else:
                            prediction_results["winner_half_time"] = {"team": "Nul", "probability": confidence}
                except (ValueError, IndexError):
                    continue
        
        # Prédictions des scores temps réglementaire
        if sorted_final_scores:
            num_predictions = min(MAX_PREDICTIONS_FULL_TIME, len(sorted_final_scores))
            for i in range(num_predictions):
                score, weight = sorted_final_scores[i]
                confidence = min(99, max(50, round(weight)))
                
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
                            prediction_results["winner_full_time"] = {"team": team1, "probability": confidence}
                        elif team2_goals > team1_goals:
                            prediction_results["winner_full_time"] = {"team": team2, "probability": confidence}
                        else:
                            prediction_results["winner_full_time"] = {"team": "Nul", "probability": confidence}
                except (ValueError, IndexError):
                    continue
        
        # Calcul du niveau de confiance global
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
        min_matches = min(home_matches, away_matches)
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

def get_over_under_recommendation(avg_goals, threshold=None):
    """Calcule une recommandation pour les paris Over/Under basée sur la moyenne des buts"""
    if threshold is None:
        # Déterminer le seuil approprié
        if avg_goals < 1.5:
            threshold = 1.5
        elif avg_goals < 2.5:
            threshold = 2.5
        elif avg_goals < 3.5:
            threshold = 3.5
        else:
            threshold = 4.5
    
    # Calculer la probabilité approximative
    probability = 50 + min(40, max(-40, (avg_goals - threshold) * 20))
    
    # Déterminer la recommandation
    if avg_goals > threshold:
        return {
            "line": threshold,
            "recommendation": "Over",
            "probability": round(probability)
        }
    else:
        return {
            "line": threshold,
            "recommendation": "Under",
            "probability": round(100 - probability)
        }

def format_prediction_message(prediction: Dict[str, Any]) -> str:
    """Formate le résultat de prédiction en message lisible et concis"""
    if "error" in prediction:
        return f"❌ *Erreur*: {prediction['error']}"
    
    teams = prediction["teams"]
    team1 = teams["team1"]
    team2 = teams["team2"]
    
    # Informations de base
    header = [
        f"🔮 *FIFA 4x4 PRÉDICTION*",
        f"",
        f"⚽ *{team1}* vs *{team2}*",
        f"📊 Fiabilité: {prediction['confidence_level']}% | 🤝 Confrontations: {prediction['direct_matches']}",
        f""
    ]
    
    # Section 1: Résultat final
    winner_ft = prediction["winner_full_time"]
    result_section = ["*📝 RÉSULTAT FINAL*"]
    
    if winner_ft["team"]:
        if winner_ft["team"] == "Nul":
            result_section.append(f"🔹 *Prédiction*: Match nul ({winner_ft['probability']}%)")
        else:
            result_section.append(f"🔹 *Prédiction*: Victoire *{winner_ft['team']}* ({winner_ft['probability']}%)")
    
    # Ajouter les scores probables (max 2)
    if prediction["full_time_scores"]:
        scores = []
        for i, score_data in enumerate(prediction["full_time_scores"][:2]):
            scores.append(f"*{score_data['score']}* ({score_data['confidence']}%)")
        result_section.append(f"🔹 *Scores probables*: {' ou '.join(scores)}")
    
    # Ajouter les buts (Over/Under)
    avg_goals_ft = prediction["avg_goals_full_time"]
    ou_recommendation = get_over_under_recommendation(avg_goals_ft)
    result_section.append(f"🔹 *Buts*: {ou_recommendation['recommendation']} {ou_recommendation['line']} ({ou_recommendation['probability']}%)")
    
    # Section 2: Mi-temps
    halftime_section = ["\n*⏱️ PRÉDICTION MI-TEMPS*"]
    
    # Vainqueur à la mi-temps
    winner_ht = prediction["winner_half_time"]
    if winner_ht["team"]:
        if winner_ht["team"] == "Nul":
            halftime_section.append(f"🔹 *Prédiction*: Match nul ({winner_ht['probability']}%)")
        else:
            halftime_section.append(f"🔹 *Prédiction*: Avantage *{winner_ht['team']}* ({winner_ht['probability']}%)")
    
    # Ajouter le score le plus probable de mi-temps
    if prediction["half_time_scores"]:
        score_data = prediction["half_time_scores"][0]
        halftime_section.append(f"🔹 *Score probable*: *{score_data['score']}* ({score_data['confidence']}%)")
    
    # Ajouter les buts de mi-temps (Over/Under)
    avg_goals_ht = prediction["avg_goals_half_time"]
    ou_recommendation_ht = get_over_under_recommendation(avg_goals_ht, threshold=1.5 if avg_goals_ht < 2 else 2.5)
    halftime_section.append(f"🔹 *Buts*: {ou_recommendation_ht['recommendation']} {ou_recommendation_ht['line']} ({ou_recommendation_ht['probability']}%)")
    
    # Section cotes (si disponibles)
    odds_section = []
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        odds_section = [
            "",
            "*💰 COTES*",
            f"🔹 *{team1}*: {odds['team1']}",
            f"🔹 *{team2}*: {odds['team2']}"
        ]
    
    # Section des conseils
    tips_section = [
        "",
        "*💡 CONSEILS DE PARIS*"
    ]
    
    # Conseil 1: Résultat match
    if winner_ft["team"] and winner_ft["probability"] > 65:
        if winner_ft["team"] == "Nul":
            tips_section.append(f"🔸 *Match nul* ({winner_ft['probability']}%)")
        else:
            tips_section.append(f"🔸 *Victoire {winner_ft['team']}* ({winner_ft['probability']}%)")
    elif winner_ft["team"] and winner_ft["probability"] > 55:
        if winner_ft["team"] == "Nul":
            tips_section.append(f"🔸 *Double chance*: {team1} ou Match nul")
        else:
            other_team = team2 if winner_ft["team"] == team1 else team1
            tips_section.append(f"🔸 *Double chance*: {winner_ft['team']} ou Match nul")
    
    # Conseil 2: Nombre de buts
    if ou_recommendation["probability"] > 65:
        tips_section.append(f"🔸 *Buts*: {ou_recommendation['recommendation']} {ou_recommendation['line']} ({ou_recommendation['probability']}%)")
    
    # Conseil 3: Les deux équipes marquent?
    both_teams_score = False
    for score_data in prediction["full_time_scores"][:3]:
        parts = score_data["score"].split(":")
        if int(parts[0]) > 0 and int(parts[1]) > 0:
            both_teams_score = True
            break
    
    if both_teams_score:
        tips_section.append("🔸 *Les deux équipes marquent*: Oui")
    else:
        tips_section.append("🔸 *Les deux équipes marquent*: Non")
    
    # Avertissement
    disclaimer = [
        "",
        "*⚠️ Avertissement*: Ces prédictions sont basées sur des données historiques et ne garantissent pas le résultat. Pariez de manière responsable."
    ]
    
    # Assembler le message complet
    all_sections = [
        "\n".join(header),
        "\n".join(result_section),
        "\n".join(halftime_section)
    ]
    
    if odds_section:
        all_sections.append("\n".join(odds_section))
    
    all_sections.append("\n".join(tips_section))
    all_sections.append("\n".join(disclaimer))
    
    return "\n".join(all_sections)
