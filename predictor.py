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
        """Initialise le prédicteur de match avec une meilleure analyse statistique"""
        # Charger les données de matchs
        self.matches = get_all_matches_data()
        self.team_stats = None
        self.match_id_trends = None
        
        if self.matches:
            # Pré-calculer les statistiques pour améliorer les performances
            self.team_stats = get_team_statistics(self.matches)
            self.match_id_trends = get_match_id_trends(self.matches)
            # Calculer les statistiques avancées
            self.calculate_advanced_stats()
        else:
            logger.warning("Aucune donnée de match disponible!")
    
    def calculate_advanced_stats(self):
        """Calcule des statistiques avancées pour améliorer les prédictions"""
        self.team_power_ratings = {}
        self.team_forms = {}
        
        for team_name, stats in self.team_stats.items():
            # Calculer le ratio de victoires total
            total_matches = stats.get('home_matches', 0) + stats.get('away_matches', 0)
            if total_matches > 0:
                total_wins = stats.get('home_wins', 0) + stats.get('away_wins', 0)
                win_ratio = total_wins / total_matches
            else:
                win_ratio = 0.0
            
            # Calculer la différence moyenne de buts
            home_goals_for = stats.get('home_goals_for', [])
            home_goals_against = stats.get('home_goals_against', [])
            away_goals_for = stats.get('away_goals_for', [])
            away_goals_against = stats.get('away_goals_against', [])
            
            all_goals_for = home_goals_for + away_goals_for
            all_goals_against = home_goals_against + away_goals_against
            
            if all_goals_for and all_goals_against:
                avg_goals_for = sum(all_goals_for) / len(all_goals_for)
                avg_goals_against = sum(all_goals_against) / len(all_goals_against)
                goal_diff = avg_goals_for - avg_goals_against
            else:
                goal_diff = 0.0
            
            # Calculer un score de puissance basé sur le ratio de victoires et la différence de buts
            power_rating = (win_ratio * 70) + (goal_diff * 15)
            self.team_power_ratings[team_name] = max(0, min(100, power_rating))
            
            # Calculer la forme récente (basée sur les 5 derniers matchs si disponibles)
            self.team_forms[team_name] = self.calculate_team_form(team_name)

    def calculate_team_form(self, team_name, last_n=5):
        """Calcule la forme récente d'une équipe basée sur ses derniers résultats"""
        team_matches = []
        
        # Récupérer tous les matchs impliquant cette équipe
        for match in self.matches:
            team_home = match.get('team_home', '')
            team_away = match.get('team_away', '')
            score_final = match.get('score_final', '')
            
            if not score_final or not (team_home == team_name or team_away == team_name):
                continue
                
            try:
                parts = score_final.split(':')
                home_goals = int(parts[0])
                away_goals = int(parts[1])
                
                result = None
                if team_home == team_name:  # L'équipe joue à domicile
                    if home_goals > away_goals:
                        result = 'W'  # Victoire
                    elif home_goals < away_goals:
                        result = 'L'  # Défaite
                    else:
                        result = 'D'  # Match nul
                else:  # L'équipe joue à l'extérieur
                    if away_goals > home_goals:
                        result = 'W'  # Victoire
                    elif away_goals < home_goals:
                        result = 'L'  # Défaite
                    else:
                        result = 'D'  # Match nul
                
                team_matches.append(result)
            except (ValueError, IndexError):
                continue
        
        # Prendre seulement les N derniers matchs
        recent_matches = team_matches[:last_n]
        
        # Calculer le score de forme
        form_score = 0
        if recent_matches:
            for i, result in enumerate(recent_matches):
                # Pondération décroissante (les matchs plus récents ont plus d'importance)
                weight = 1 - (i / (2 * last_n))
                
                if result == 'W':
                    form_score += 3 * weight
                elif result == 'D':
                    form_score += 1 * weight
            
            # Normaliser sur 100
            max_possible_score = sum([(3 * (1 - (i / (2 * last_n)))) for i in range(len(recent_matches))])
            if max_possible_score > 0:
                form_score = (form_score / max_possible_score) * 100
            else:
                form_score = 50
        else:
            form_score = 50  # Valeur par défaut
        
        return round(form_score)

    def predict_match(self, team1: str, team2: str, odds1: float = None, odds2: float = None) -> Optional[Dict[str, Any]]:
        """Prédit le résultat d'un match entre team1 et team2 avec cotes améliorées"""
        # Nettoyer les noms d'équipes (enlever les underscores au début, les espaces en trop, etc.)
        team1 = team1.strip().lstrip('_')
        team2 = team2.strip().lstrip('_')
        
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
        
        # Analyser les confrontations directes récentes avec plus de poids
        for i, match in enumerate(direct_matches):
            home = match.get('team_home', '')
            away = match.get('team_away', '')
            score_final = match.get('score_final', '')
            score_1ere = match.get('score_1ere', '')
            
            # Donner plus de poids aux matchs récents (basé sur leur position dans la liste)
            recency_weight = 1.0 + (0.1 * (len(direct_matches) - i)) / len(direct_matches) if direct_matches else 1.0
            
            if score_final:
                # Si on veut normaliser pour que team1 soit toujours à gauche
                if home == team1:
                    direct_final_scores.append((score_final, recency_weight))
                    if score_1ere:
                        direct_first_half.append((score_1ere, recency_weight))
                else:
                    # Inverser le score si team1 est à l'extérieur
                    try:
                        parts = score_final.split(':')
                        direct_final_scores.append((f"{parts[1]}:{parts[0]}", recency_weight))
                        
                        if score_1ere:
                            half_parts = score_1ere.split(':')
                            direct_first_half.append((f"{half_parts[1]}:{half_parts[0]}", recency_weight))
                    except (ValueError, IndexError):
                        pass
        
        # Analyse des scores les plus fréquents dans les confrontations directes avec pondération
        direct_final_weights = defaultdict(float)
        for score, weight in direct_final_scores:
            direct_final_weights[score] += weight
        
        direct_half_weights = defaultdict(float)
        for score, weight in direct_first_half:
            direct_half_weights[score] += weight
        
        # Trier par poids
        common_direct_final = sorted(direct_final_weights.items(), key=lambda x: x[1], reverse=True)
        common_direct_half = sorted(direct_half_weights.items(), key=lambda x: x[1], reverse=True)
        
        # Préparation pour les prédictions multiples
        all_final_scores = []
        all_half_scores = []
        
        # Ajouter les scores des confrontations directes avec leur poids
        if common_direct_final:
            for score, weight in common_direct_final[:MAX_PREDICTIONS_FULL_TIME]:
                # Confrontations directes ont un poids très important (2x)
                all_final_scores.append((score, weight * 2))
        
        if common_direct_half:
            for score, weight in common_direct_half[:MAX_PREDICTIONS_HALF_TIME]:
                all_half_scores.append((score, weight * 2))
        
        # 2. Intégration des cotes et des scores de puissance
        # Calculer les forces relatives des équipes
        team1_power = self.team_power_ratings.get(team1, 50)
        team2_power = self.team_power_ratings.get(team2, 50)
        
        # Calculer les formes récentes
        team1_form = self.team_forms.get(team1, 50)
        team2_form = self.team_forms.get(team2, 50)
        
        # Intégrer les cotes si disponibles
        implied_prob1 = 0
        implied_prob2 = 0
        
        if odds1 and odds2:
            # Calculer les probabilités implicites à partir des cotes
            implied_prob1 = 1 / odds1
            implied_prob2 = 1 / odds2
            
            # Normaliser les probabilités (sum = 1)
            total_prob = implied_prob1 + implied_prob2
            implied_prob1 = implied_prob1 / total_prob
            implied_prob2 = implied_prob2 / total_prob
            
            # Ajuster les scores de puissance basés sur les cotes
            bookmaker_factor = 0.4  # Poids des cotes dans l'évaluation finale
            
            adjusted_team1_power = (team1_power / 100 * (1 - bookmaker_factor)) + (implied_prob1 * bookmaker_factor * 100)
            adjusted_team2_power = (team2_power / 100 * (1 - bookmaker_factor)) + (implied_prob2 * bookmaker_factor * 100)
        else:
            # Utiliser uniquement les statistiques historiques
            adjusted_team1_power = team1_power
            adjusted_team2_power = team2_power
        
        # Tenir compte de l'avantage à domicile
        home_advantage = 5  # 5% d'avantage pour l'équipe à domicile
        adjusted_team1_power += home_advantage
        
        # Tenir compte de la forme récente
        form_factor = 0.3  # Poids de la forme récente
        adjusted_team1_power = adjusted_team1_power * (1 - form_factor) + team1_form * form_factor
        adjusted_team2_power = adjusted_team2_power * (1 - form_factor) + team2_form * form_factor
        
        # Calcul des probabilités de victoire/match nul
        total_power = adjusted_team1_power + adjusted_team2_power
        win_prob_team1 = adjusted_team1_power / total_power * 0.8  # 80% de chance d'avoir un vainqueur
        win_prob_team2 = adjusted_team2_power / total_power * 0.8
        draw_prob = 1.0 - win_prob_team1 - win_prob_team2
        
        # 3. Analyse des performances à domicile/extérieur
        # Team1 à domicile
        home_matches = self.team_stats[team1]['home_matches']
        if home_matches > 0:
            # Scores les plus fréquents à domicile
            home_scores = [f"{g_for}:{g_against}" for g_for, g_against in zip(
                self.team_stats[team1]['home_goals_for'], self.team_stats[team1]['home_goals_against'])]
            common_home = get_common_scores(home_scores)
            
            if common_home:
                # Pondérer en fonction de la force relative
                power_weight = adjusted_team1_power / 100
                for score, count, pct in common_home[:MAX_PREDICTIONS_FULL_TIME]:
                    all_final_scores.append((score, pct * power_weight * 1.2))  # 1.2x pour favoriser les tendances à domicile
            
            # 1ère mi-temps à domicile
            common_home_half = get_common_scores(self.team_stats[team1]['home_first_half'])
            if common_home_half:
                for score, count, pct in common_home_half[:MAX_PREDICTIONS_HALF_TIME]:
                    all_half_scores.append((score, pct * power_weight * 1.2))
        
        # Team2 à l'extérieur
        away_matches = self.team_stats[team2]['away_matches']
        if away_matches > 0:
            # Scores les plus fréquents à l'extérieur
            away_scores = [f"{g_for}:{g_against}" for g_for, g_against in zip(
                self.team_stats[team2]['away_goals_for'], self.team_stats[team2]['away_goals_against'])]
            common_away = get_common_scores(away_scores)
            
            if common_away:
                # Pondérer en fonction de la force relative
                power_weight = adjusted_team2_power / 100
                for score, count, pct in common_away[:MAX_PREDICTIONS_FULL_TIME]:
                    # Inverser le score car on a les stats du point de vue de l'équipe à l'extérieur
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        all_final_scores.append((inverted_score, pct * power_weight * 1.2))
                    except (ValueError, IndexError):
                        pass
            
            # 1ère mi-temps à l'extérieur
            common_away_half = get_common_scores(self.team_stats[team2]['away_first_half'])
            if common_away_half:
                for score, count, pct in common_away_half[:MAX_PREDICTIONS_HALF_TIME]:
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        all_half_scores.append((inverted_score, pct * power_weight * 1.2))
                    except (ValueError, IndexError):
                        pass
        
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
        
        # 5. Analyse statistique avancée pour générer des scores probables
        # Calculer les moyennes de buts
        team1_home_goals = sum(self.team_stats[team1].get('home_goals_for', [])) / max(1, home_matches)
        team1_home_conceded = sum(self.team_stats[team1].get('home_goals_against', [])) / max(1, home_matches)
        
        team2_away_goals = sum(self.team_stats[team2].get('away_goals_for', [])) / max(1, away_matches)
        team2_away_conceded = sum(self.team_stats[team2].get('away_goals_against', [])) / max(1, away_matches)
        
        # Prédire les buts attendus
        expected_goals_team1 = (team1_home_goals + team2_away_conceded) / 2
        expected_goals_team2 = (team2_away_goals + team1_home_conceded) / 2
        
        # Ajuster en fonction des forces relatives
        expected_goals_team1 *= (adjusted_team1_power / adjusted_team2_power) ** 0.5
        expected_goals_team2 *= (adjusted_team2_power / adjusted_team1_power) ** 0.5
        
        # Générer des scores probables autour des valeurs attendues
        import itertools
        
        for team1_goals in range(max(0, int(expected_goals_team1 - 1)), int(expected_goals_team1 + 2)):
            for team2_goals in range(max(0, int(expected_goals_team2 - 1)), int(expected_goals_team2 + 2)):
                score = f"{team1_goals}:{team2_goals}"
                
                # Calculer la probabilité de ce score en fonction de la différence avec les valeurs attendues
                diff1 = abs(team1_goals - expected_goals_team1)
                diff2 = abs(team2_goals - expected_goals_team2)
                avg_diff = (diff1 + diff2) / 2
                
                # Plus la différence est faible, plus le poids est élevé
                weight = max(0, 70 - avg_diff * 30)
                
                # Ajuster en fonction des probabilités de victoire/nul
                if team1_goals > team2_goals:
                    weight *= win_prob_team1 * 1.5
                elif team2_goals > team1_goals:
                    weight *= win_prob_team2 * 1.5
                else:
                    weight *= draw_prob * 3  # Donner plus de poids au match nul si prédit
                
                all_final_scores.append((score, weight))
        
        # Faire de même pour la mi-temps (avec des valeurs ajustées)
        half_expected_goals_team1 = expected_goals_team1 * 0.45  # En moyenne, 45% des buts sont marqués en 1ère mi-temps
        half_expected_goals_team2 = expected_goals_team2 * 0.45
        
        for team1_goals in range(max(0, int(half_expected_goals_team1 - 0.5)), int(half_expected_goals_team1 + 1.5)):
            for team2_goals in range(max(0, int(half_expected_goals_team2 - 0.5)), int(half_expected_goals_team2 + 1.5)):
                score = f"{team1_goals}:{team2_goals}"
                
                diff1 = abs(team1_goals - half_expected_goals_team1)
                diff2 = abs(team2_goals - half_expected_goals_team2)
                avg_diff = (diff1 + diff2) / 2
                
                weight = max(0, 70 - avg_diff * 30)
                
                # Ajustement des probabilités comme pour le temps complet
                if team1_goals > team2_goals:
                    weight *= win_prob_team1 * 1.5
                elif team2_goals > team1_goals:
                    weight *= win_prob_team2 * 1.5
                else:
                    weight *= draw_prob * 2.5
                
                all_half_scores.append((score, weight))
        
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
                            # Utiliser la probabilité de victoire calculée précédemment
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
            # Analyser si les cotes sont cohérentes avec notre analyse statistique
            market_favorite = team1 if implied_prob1 > implied_prob2 else team2
            statistical_favorite = team1 if team1_power > team2_power else team2
            
            if market_favorite == statistical_favorite:
                confidence_factors.append(85)  # Cotes et statistiques en accord
            else:
                confidence_factors.append(65)  # Cotes et statistiques en désaccord
        else:
            confidence_factors.append(60)  # Pas de cotes disponibles
        
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
        
        # Facteur 5: Niveau de force des équipes
        avg_team_power = (team1_power + team2_power) / 2
        if avg_team_power > 75:
            confidence_factors.append(85)  # Équipes fortes = plus prévisibles
        elif avg_team_power > 50:
            confidence_factors.append(75)
        else:
            confidence_factors.append(65)  # Équipes plus faibles = moins prévisibles
        
        # Calcul de la confiance globale (moyenne pondérée)
        # Calcul de la confiance globale (moyenne pondérée)
        if confidence_factors:
            prediction_results["confidence_level"] = round(sum(confidence_factors) / len(confidence_factors))
        
        # Arrondir les moyennes de buts
        prediction_results["avg_goals_half_time"] = round(prediction_results["avg_goals_half_time"], 1)
        prediction_results["avg_goals_full_time"] = round(prediction_results["avg_goals_full_time"], 1)
        
        # Ajouter des informations supplémentaires pour le débogage
        prediction_results["stats"] = {
            "team1_power": round(team1_power),
            "team2_power": round(team2_power),
            "team1_form": team1_form,
            "team2_form": team2_form,
            "win_prob_team1": round(win_prob_team1 * 100),
            "win_prob_team2": round(win_prob_team2 * 100),
            "draw_prob": round(draw_prob * 100),
            "expected_goals_team1": round(expected_goals_team1, 2),
            "expected_goals_team2": round(expected_goals_team2, 2)
        }
        
        return prediction_results

def format_prediction_message(prediction: Dict[str, Any]) -> str:
    """Formate le résultat de prédiction en message lisible avec plus d'informations"""
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
    
    # Section 0: Probabilités de résultat (si disponibles)
    stats = prediction.get("stats", {})
    if stats:
        message.append("*📊 PROBABILITÉS:*")
        message.append(f"  • Victoire {team1}: {stats.get('win_prob_team1', 0)}%")
        message.append(f"  • Match nul: {stats.get('draw_prob', 0)}%")
        message.append(f"  • Victoire {team2}: {stats.get('win_prob_team2', 0)}%")
        message.append("")
    
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
    
    # Ajouter une recommandation pour le nombre de buts à la mi-temps
    avg_goals_ht = prediction["avg_goals_half_time"]
    if avg_goals_ht > 0:
        # Déterminer la ligne de buts la plus proche
        if avg_goals_ht < 0.85:
            line = 0.5
            rec = "Plus" if avg_goals_ht > 0.5 else "Moins"
        elif avg_goals_ht < 1.85:
            line = 1.5
            rec = "Plus" if avg_goals_ht > 1.5 else "Moins"
        else:
            line = 2.5
            rec = "Plus" if avg_goals_ht > 2.5 else "Moins"
        
        conf = min(95, max(60, 75 + round(10 * abs(avg_goals_ht - line))))
        message.append(f"  💬 Recommandation: *{rec} de {line}* buts en 1ère mi-temps ({conf}%)")
    
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
    
    # Ajouter une recommandation pour le nombre de buts au temps réglementaire
    avg_goals_ft = prediction["avg_goals_full_time"]
    if avg_goals_ft > 0:
        # Déterminer la ligne de buts la plus proche
        if avg_goals_ft < 1.85:
            line = 1.5
            rec = "Plus" if avg_goals_ft > 1.5 else "Moins"
        elif avg_goals_ft < 2.85:
            line = 2.5
            rec = "Plus" if avg_goals_ft > 2.5 else "Moins"
        elif avg_goals_ft < 3.85:
            line = 3.5
            rec = "Plus" if avg_goals_ft > 3.5 else "Moins"
        else:
            line = 4.5
            rec = "Plus" if avg_goals_ft > 4.5 else "Moins"
        
        conf = min(95, max(60, 75 + round(10 * abs(avg_goals_ft - line))))
        message.append(f"  💬 Recommandation: *{rec} de {line}* buts au total ({conf}%)")
    
    message.append("")
    
    # Section 3: Statistiques des équipes (si disponibles)
    if stats:
        message.append("*📈 ANALYSE DES ÉQUIPES:*")
        message.append(f"  • Force: {team1} ({stats.get('team1_power', 0)}) vs {team2} ({stats.get('team2_power', 0)})")
        message.append(f"  • Forme récente: {team1} ({stats.get('team1_form', 0)}) vs {team2} ({stats.get('team2_form', 0)})")
        
        # Ajouter moyenne des buts
        message.append(f"  • Buts attendus: {stats.get('expected_goals_team1', 0)} - {stats.get('expected_goals_team2', 0)}")
        message.append(f"  • Total buts prévus: {prediction['avg_goals_full_time']}")
        message.append("")
    else:
        # Section statistiques moyennes (version antérieure)
        message.append("*📈 STATISTIQUES MOYENNES:*")
        message.append(f"  • Buts 1ère mi-temps: {prediction['avg_goals_half_time']}")
        message.append(f"  • Buts temps réglementaire: {prediction['avg_goals_full_time']}")
        message.append("")
    
    # Section 4: Information sur les cotes si disponibles
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        message.append("*💰 COTES:*")
        message.append(f"  • {team1}: {odds['team1']}")
        message.append(f"  • {team2}: {odds['team2']}")
    
    return "\n".join(message)
