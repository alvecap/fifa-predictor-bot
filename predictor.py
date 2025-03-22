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
            # Calculer les statistiques avancées
            self.calculate_advanced_stats()
        else:
            logger.warning("Aucune donnée de match disponible!")

    def calculate_advanced_stats(self):
        """Calcule des statistiques avancées pour les équipes"""
        self.team_power_ratings = {}
        self.team_forms = {}
        self.avg_goals_per_match = 0
        total_matches = 0
        total_goals = 0
        
        # Calculer la moyenne globale de buts par match
        for match in self.matches:
            score_final = match.get('score_final', '')
            if score_final:
                try:
                    parts = score_final.split(':')
                    home_goals = int(parts[0])
                    away_goals = int(parts[1])
                    total_goals += home_goals + away_goals
                    total_matches += 1
                except (ValueError, IndexError):
                    pass
        
        if total_matches > 0:
            self.avg_goals_per_match = total_goals / total_matches
        
        # Calculer les statistiques par équipe
        for team_name, stats in self.team_stats.items():
            # Calculer le ratio de victoires
            home_matches = stats.get('home_matches', 0)
            away_matches = stats.get('away_matches', 0)
            total_team_matches = home_matches + away_matches
            
            if total_team_matches > 0:
                home_wins = stats.get('home_wins', 0)
                away_wins = stats.get('away_wins', 0)
                total_wins = home_wins + away_wins
                win_ratio = total_wins / total_team_matches
            else:
                win_ratio = 0.0
            
            # Calculer la différence de buts moyenne
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
            
            # Calculer un score de puissance
            power_rating = (win_ratio * 70) + (goal_diff * 10)
            self.team_power_ratings[team_name] = max(0, min(100, power_rating))
            
            # Calculer la forme récente
            self.team_forms[team_name] = self.calculate_form(team_name)
    
    def calculate_form(self, team_name, last_n=5):
        """Calcule la forme récente d'une équipe (derniers matchs)"""
        team_results = []
        
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
                
                team_results.append(result)
            except (ValueError, IndexError):
                continue
        
        # Prendre les N derniers matchs
        recent_results = team_results[:last_n]
        
        # Calculer le score de forme
        form_score = 0
        max_score = 0
        
        for i, result in enumerate(recent_results):
            # Plus un match est récent, plus il pèse dans la forme
            weight = 1.0 - (i / (last_n * 2))
            max_score += weight * 3  # 3 points pour une victoire
            
            if result == 'W':
                form_score += 3 * weight
            elif result == 'D':
                form_score += 1 * weight
        
        # Normaliser entre 0 et 100
        if max_score > 0:
            form_score = (form_score / max_score) * 100
        else:
            form_score = 50  # Valeur par défaut
        
        return round(form_score)

    def predict_match(self, team1: str, team2: str, odds1: float = None, odds2: float = None) -> Optional[Dict[str, Any]]:
        """Prédit le résultat d'un match entre team1 et team2"""
        # Nettoyer les noms d'équipes (enlever les underscores, espaces en trop, etc.)
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
        
        # 1. Analyse des confrontations directes (avec FORTE pondération)
        direct_final_scores = []
        direct_first_half = []
        direct_results = {"team1_wins": 0, "team2_wins": 0, "draws": 0}
        
        for i, match in enumerate(direct_matches):
            home = match.get('team_home', '')
            away = match.get('team_away', '')
            score_final = match.get('score_final', '')
            score_1ere = match.get('score_1ere', '')
            
            # Donner plus de poids aux matchs récents
            recency_weight = 2.0 + ((len(direct_matches) - i) / len(direct_matches)) if direct_matches else 1.0
            
            if score_final:
                # Normaliser pour que team1 soit toujours à gauche
                if home == team1:
                    direct_final_scores.append((score_final, recency_weight))
                    
                    # Compter les résultats
                    parts = score_final.split(':')
                    if len(parts) == 2:
                        home_goals = int(parts[0])
                        away_goals = int(parts[1])
                        if home_goals > away_goals:
                            direct_results["team1_wins"] += 1
                        elif home_goals < away_goals:
                            direct_results["team2_wins"] += 1
                        else:
                            direct_results["draws"] += 1
                    
                    if score_1ere:
                        direct_first_half.append((score_1ere, recency_weight))
                else:
                    # Inverser le score si team1 est à l'extérieur
                    try:
                        parts = score_final.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        direct_final_scores.append((inverted_score, recency_weight))
                        
                        # Compter les résultats inversés
                        if len(parts) == 2:
                            home_goals = int(parts[0])
                            away_goals = int(parts[1])
                            if home_goals < away_goals:
                                direct_results["team1_wins"] += 1
                            elif home_goals > away_goals:
                                direct_results["team2_wins"] += 1
                            else:
                                direct_results["draws"] += 1
                        
                        if score_1ere:
                            half_parts = score_1ere.split(':')
                            inverted_half = f"{half_parts[1]}:{half_parts[0]}"
                            direct_first_half.append((inverted_half, recency_weight))
                    except (ValueError, IndexError):
                        pass
        
        # Calculer les probabilités basées sur les confrontations directes
        direct_win_prob_team1 = 0
        direct_win_prob_team2 = 0
        direct_draw_prob = 0
        
        direct_matches_count = direct_results["team1_wins"] + direct_results["team2_wins"] + direct_results["draws"]
        if direct_matches_count > 0:
            direct_win_prob_team1 = direct_results["team1_wins"] / direct_matches_count
            direct_win_prob_team2 = direct_results["team2_wins"] / direct_matches_count
            direct_draw_prob = direct_results["draws"] / direct_matches_count
        
        # Regrouper les scores avec leur poids
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
        
        # Ajouter les scores des confrontations directes avec un poids TRÈS important (x3)
        if common_direct_final:
            for score, weight in common_direct_final[:MAX_PREDICTIONS_FULL_TIME]:
                all_final_scores.append((score, weight * 3.0))
        
        if common_direct_half:
            for score, weight in common_direct_half[:MAX_PREDICTIONS_HALF_TIME]:
                all_half_scores.append((score, weight * 3.0))
        
        # 2. Intégration des cotes
        # Calculer les probabilités implicites à partir des cotes
        market_prob_team1 = 0
        market_prob_team2 = 0
        market_prob_draw = 0
        
        if odds1 and odds2:
            implied_prob1 = 1 / odds1
            implied_prob2 = 1 / odds2
            
            # Calculer la marge du bookmaker
            margin = (implied_prob1 + implied_prob2) - 1
            
            # Ajuster les probabilités en enlevant la marge
            if margin > 0:
                implied_prob1 = implied_prob1 / (1 + margin)
                implied_prob2 = implied_prob2 / (1 + margin)
            
            # Estimer la probabilité de match nul (généralement 20-30% des matchs)
            market_prob_team1 = implied_prob1 * 0.85  # Réduire pour laisser de la place au match nul
            market_prob_team2 = implied_prob2 * 0.85
            market_prob_draw = 1 - market_prob_team1 - market_prob_team2
        
        # 3. Analyse statistique des équipes
        # Récupérer les statistiques et forces des équipes
        team1_power = self.team_power_ratings.get(team1, 50)
        team2_power = self.team_power_ratings.get(team2, 50)
        team1_form = self.team_forms.get(team1, 50)
        team2_form = self.team_forms.get(team2, 50)
        
        # Analyse des performances à domicile/extérieur
        home_matches = self.team_stats[team1]['home_matches']
        away_matches = self.team_stats[team2]['away_matches']
        
        # Calculer l'avantage à domicile
        home_advantage = 7  # Points bonus pour l'équipe à domicile
        
        # Scores de puissance ajustés
        adjusted_team1_power = team1_power + home_advantage
        adjusted_team2_power = team2_power
        
        # Intégrer la forme récente (30% de l'évaluation)
        form_weight = 0.3
        final_team1_power = adjusted_team1_power * (1 - form_weight) + team1_form * form_weight
        final_team2_power = adjusted_team2_power * (1 - form_weight) + team2_form * form_weight
        
        # 4. COMBINAISON des analyses statistiques et des cotes
        # Déterminer les probabilités finales (50% cotes, 30% stats équipes, 20% confrontations directes)
        win_prob_team1 = 0
        win_prob_team2 = 0
        draw_prob = 0
        
        if odds1 and odds2:
            # Avec cotes: 50% cotes, 30% stats, 20% confrontations directes
            win_prob_team1 = (market_prob_team1 * 0.5) + 
                            ((final_team1_power / (final_team1_power + final_team2_power)) * 0.8 * 0.3) + 
                            (direct_win_prob_team1 * 0.2)
            
            win_prob_team2 = (market_prob_team2 * 0.5) + 
                            ((final_team2_power / (final_team1_power + final_team2_power)) * 0.8 * 0.3) + 
                            (direct_win_prob_team2 * 0.2)
            
            draw_prob = (market_prob_draw * 0.5) + 
                       (0.2 * 0.3) +  # 20% de chance de match nul basé sur les stats
                       (direct_draw_prob * 0.2)
        else:
            # Sans cotes: 60% stats, 40% confrontations directes
            win_prob_team1 = ((final_team1_power / (final_team1_power + final_team2_power)) * 0.8 * 0.6) + 
                            (direct_win_prob_team1 * 0.4)
            
            win_prob_team2 = ((final_team2_power / (final_team1_power + final_team2_power)) * 0.8 * 0.6) + 
                            (direct_win_prob_team2 * 0.4)
            
            draw_prob = (0.2 * 0.6) +  # 20% de chance de match nul basé sur les stats
                       (direct_draw_prob * 0.4)
        
        # Normaliser pour que la somme = 1
        total_prob = win_prob_team1 + win_prob_team2 + draw_prob
        if total_prob > 0:
            win_prob_team1 /= total_prob
            win_prob_team2 /= total_prob
            draw_prob /= total_prob
        
        # 5. Analyse des performances à domicile/extérieur pour les scores
        if home_matches > 0:
            # Scores les plus fréquents à domicile
            home_scores = [f"{g_for}:{g_against}" for g_for, g_against in zip(
                self.team_stats[team1]['home_goals_for'], self.team_stats[team1]['home_goals_against'])]
            common_home = get_common_scores(home_scores)
            
            if common_home:
                for score, count, pct in common_home[:MAX_PREDICTIONS_FULL_TIME]:
                    all_final_scores.append((score, pct * 1.5))  # x1.5 pour les tendances à domicile
            
            # 1ère mi-temps à domicile
            common_home_half = get_common_scores(self.team_stats[team1]['home_first_half'])
            if common_home_half:
                for score, count, pct in common_home_half[:MAX_PREDICTIONS_HALF_TIME]:
                    all_half_scores.append((score, pct * 1.5))
        
        if away_matches > 0:
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
                        all_final_scores.append((inverted_score, pct * 1.5))
                    except (ValueError, IndexError):
                        pass
            
            # 1ère mi-temps à l'extérieur
            common_away_half = get_common_scores(self.team_stats[team2]['away_first_half'])
            if common_away_half:
                for score, count, pct in common_away_half[:MAX_PREDICTIONS_HALF_TIME]:
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        all_half_scores.append((inverted_score, pct * 1.5))
                    except (ValueError, IndexError):
                        pass
        
        # 6. Ajouter les tendances par numéro de match
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
                        all_final_scores.append((score, pct * 0.8))
                
                if common_half:
                    for score, count, pct in common_half[:2]:
                        all_half_scores.append((score, pct * 0.8))
        
        # 7. Générer des scores en fonction des probabilités de victoire/match nul
        # Créer quelques scores typiques pour chaque résultat
        # Ces scores seront pondérés par les probabilités de résultat
        team1_win_scores = [("1:0", 30), ("2:0", 25), ("2:1", 20), ("3:1", 15), ("3:0", 10)]
        draw_scores = [("0:0", 35), ("1:1", 45), ("2:2", 20)]
        team2_win_scores = [("0:1", 30), ("0:2", 25), ("1:2", 20), ("1:3", 15), ("0:3", 10)]
        
        # Ajouter ces scores avec un poids proportionnel aux probabilités
        for score, base_weight in team1_win_scores:
            weight = base_weight * win_prob_team1 * 100
            all_final_scores.append((score, weight))
        
        for score, base_weight in draw_scores:
            weight = base_weight * draw_prob * 100
            all_final_scores.append((score, weight))
        
        for score, base_weight in team2_win_scores:
            weight = base_weight * win_prob_team2 * 100
            all_final_scores.append((score, weight))
        
        # Faire de même pour la mi-temps avec des scores adaptés
        team1_win_half = [("1:0", 50), ("2:0", 30), ("2:1", 20)]
        draw_half = [("0:0", 60), ("1:1", 40)]
        team2_win_half = [("0:1", 50), ("0:2", 30), ("1:2", 20)]
        
        for score, base_weight in team1_win_half:
            weight = base_weight * win_prob_team1 * 100 * 0.8  # Moins de corrélation pour la mi-temps
            all_half_scores.append((score, weight))
        
        for score, base_weight in draw_half:
            weight = base_weight * (draw_prob + 0.1) * 100  # Plus de nuls à la mi-temps
            all_half_scores.append((score, weight))
        
        for score, base_weight in team2_win_half:
            weight = base_weight * win_prob_team2 * 100 * 0.8
            all_half_scores.append((score, weight))
        
        # 8. Combiner et fusionner les scores identiques
        final_score_weights = defaultdict(float)
        for score, weight in all_final_scores:
            final_score_weights[score] += weight
        
        half_score_weights = defaultdict(float)
        for score, weight in all_half_scores:
            half_score_weights[score] += weight
        
        # Trier par poids décroissant
        sorted_final_scores = sorted(final_score_weights.items(), key=lambda x: x[1], reverse=True)
        sorted_half_scores = sorted(half_score_weights.items(), key=lambda x: x[1], reverse=True)
        
        # 9. Remplir les résultats de prédiction
        
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
                            ht_winner_prob = max(50, min(95, round(win_prob_team1 * 100)))
                            prediction_results["winner_half_time"] = {"team": team1, "probability": ht_winner_prob}
                        elif team2_goals > team1_goals:
                            ht_winner_prob = max(50, min(95, round(win_prob_team2 * 100)))
                            prediction_results["winner_half_time"] = {"team": team2, "probability": ht_winner_prob}
                        else:
                            ht_draw_prob = max(50, min(95, round(draw_prob * 100)))
                            prediction_results["winner_half_time"] = {"team": "Nul", "probability": ht_draw_prob}
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
                            ft_winner_prob = max(50, min(95, round(win_prob_team1 * 100)))
                            prediction_results["winner_full_time"] = {"team": team1, "probability": ft_winner_prob}
                        elif team2_goals > team1_goals:
                            ft_winner_prob = max(50, min(95, round(win_prob_team2 * 100)))
                            prediction_results["winner_full_time"] = {"team": team2, "probability": ft_winner_prob}
                        else:
                            ft_draw_prob = max(50, min(95, round(draw_prob * 100)))
                            prediction_results["winner_full_time"] = {"team": "Nul", "probability": ft_draw_prob}
                except (ValueError, IndexError):
                    continue
        
        # 10. Calcul du niveau de confiance global
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
            # Analyser si les cotes sont cohérentes avec notre analyse des confrontations directes
            if direct_matches_count > 0:
                # Favori selon les cotes
                bookmaker_favorite = team1 if market_prob_team1 > market_prob_team2 else team2
                
                # Favori selon les confrontations directes
                direct_favorite = team1 if direct_win_prob_team1 > direct_win_prob_team2 else team2
                
                if bookmaker_favorite == direct_favorite:
                    confidence_factors.append(85)  # Les cotes confirment l'historique
                else:
                    confidence_factors.append(65)  # Désaccord entre cotes et historique
            else:
                confidence_factors.append(75)  # Cotes disponibles mais pas d'historique direct
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
        
        # Calcul de la confiance globale (moyenne pondérée)
        if confidence_factors:
            prediction_results["confidence_level"] = round(sum(confidence_factors) / len(confidence_factors))
        
        # Arrondir les moyennes de buts
        prediction_results["avg_goals_half_time"] = round(prediction_results["avg_goals_half_time"], 1)
        prediction_results["avg_goals_full_time"] = round(prediction_results["avg_goals_full_time"], 1)
        
        # Ajouter des informations supplémentaires pour le débogage et l'analyse
        top_score = sorted_final_scores[0][0] if sorted_final_scores else "0:0"
        top_half = sorted_half_scores[0][0] if sorted_half_scores else "0:0"
        
        # Nombre total de buts selon le score le plus probable
        try:
            parts = top_score.split(':')
            total_goals = int(parts[0]) + int(parts[1])
        except:
            total_goals = prediction_results["avg_goals_full_time"]
        
        try:
            half_parts = top_half.split(':')
            half_goals = int(half_parts[0]) + int(half_parts[1])
        except:
            half_goals = prediction_results["avg_goals_half_time"]
        
        prediction_results["recommended_goals"] = {
            "half_time": half_goals,
            "full_time": total_goals
        }
        
        prediction_results["stats"] = {
            "team1_power": round(final_team1_power),
            "team2_power": round(final_team2_power),
            "team1_form": team1_form,
            "team2_form": team2_form,
            "win_prob_team1": round(win_prob_team1 * 100),
            "win_prob_team2": round(win_prob_team2 * 100),
            "draw_prob": round(draw_prob * 100),
            "direct_match_stats": direct_results
        }
        
        return prediction_results

def format_prediction_message(prediction: Dict[str, Any]) -> str:
    """Formate le résultat de prédiction en message lisible avec design embelli"""
    if "error" in prediction:
        return f"❌ Erreur: {prediction['error']}"
    
    teams = prediction["teams"]
    team1 = teams["team1"]
    team2 = teams["team2"]
    
    message = [
        f"🏆 *PREDICTION FIFA 4x4* 🏆",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"⚽ *{team1}* 🆚 *{team2}*",
        f"📊 Fiabilité: {prediction['confidence_level']}% | 🤝 Matchs: {prediction['direct_matches']}",
        f"━━━━━━━━━━━━━━━━━━━━━",
        "\n"
    ]
    
    # Section 0: Probabilités de résultat
    stats = prediction.get("stats", {})
    if stats:
        message.append("📋 *PRONOSTIC RÉSULTAT:*")
        message.append(f"  🔹 Victoire {team1}: {stats.get('win_prob_team1', 0)}%")
        message.append(f"  🔸 Match nul: {stats.get('draw_prob', 0)}%")
        message.append(f"  🔹 Victoire {team2}: {stats.get('win_prob_team2', 0)}%")
        message.append("")
    
    # Section 1: Scores mi-temps
    message.append("⏱️ *SCORES MI-TEMPS:*")
    if prediction["half_time_scores"]:
        for i, score_data in enumerate(prediction["half_time_scores"][:2], 1):
            stars = "⭐⭐⭐" if i == 1 else "⭐⭐"
            message.append(f"  {stars} *{score_data['score']}* ({score_data['confidence']}%)")
    else:
        message.append("  ℹ️ Données insuffisantes")
    
    # Gagnant à la mi-temps
    winner_ht = prediction["winner_half_time"]
    if winner_ht["team"]:
        if winner_ht["team"] == "Nul":
            message.append(f"  👉 Pronostic: *Match nul* ({winner_ht['probability']}%)")
        else:
            message.append(f"  👉 Pronostic: *{winner_ht['team']}* ({winner_ht['probability']}%)")
    
    # Recommandation buts mi-temps
    half_goals = prediction.get("recommended_goals", {}).get("half_time", prediction["avg_goals_half_time"])
    
    if half_goals == 0:
        message.append(f"  🎯 *Moins de 0.5* buts (75%)")
    elif half_goals == 1:
        message.append(f"  🎯 *Moins de 1.5* buts (70%)")
    else:
        message.append(f"  🎯 *Plus de {half_goals - 0.5}* buts (70%)")
    
    message.append("")
    
    # Section 2: Scores temps réglementaire
    message.append("⚽ *SCORES TEMPS RÉGLEMENTAIRE:*")
    if prediction["full_time_scores"]:
        for i, score_data in enumerate(prediction["full_time_scores"][:3], 1):
            stars = "⭐⭐⭐" if i == 1 else ("⭐⭐" if i == 2 else "⭐")
            message.append(f"  {stars} *{score_data['score']}* ({score_data['confidence']}%)")
    else:
        message.append("  ℹ️ Données insuffisantes")
    
    # Gagnant du match
    winner_ft = prediction["winner_full_time"]
    if winner_ft["team"]:
        if winner_ft["team"] == "Nul":
            message.append(f"  👉 Pronostic: *Match nul* ({winner_ft['probability']}%)")
        else:
            message.append(f"  👉 Pronostic: *{winner_ft['team']}* ({winner_ft['probability']}%)")
    
    # Recommandation buts temps complet
    full_goals = prediction.get("recommended_goals", {}).get("full_time", prediction["avg_goals_full_time"])
    
    if full_goals <= 1:
        message.append(f"  🎯 *Moins de 1.5* buts (70%)")
    elif full_goals == 2:
        message.append(f"  🎯 *Plus de 1.5* buts (75%)")
    elif full_goals == 3:
        message.append(f"  🎯 *Plus de 2.5* buts (70%)")
    elif full_goals == 4:
        message.append(f"  🎯 *Plus de 3.5* buts (65%)")
    else:
        message.append(f"  🎯 *Plus de 4.5* buts (65%)")
    
    message.append("")
    
    # Section 3: Statistiques et forme des équipes
    message.append("📈 *ANALYSE DES ÉQUIPES:*")
    
    direct_stats = stats.get("direct_match_stats", {})
    if direct_stats and prediction['direct_matches'] > 0:
        message.append(f"  🔍 Confrontations directes:")
        message.append(f"      • {team1}: {direct_stats.get('team1_wins', 0)} victoires")
        message.append(f"      • Nuls: {direct_stats.get('draws', 0)}")
        message.append(f"      • {team2}: {direct_stats.get('team2_wins', 0)} victoires")
    
    message.append(f"  💪 Forme récente: ")
    message.append(f"      • {team1}: {stats.get('team1_form', 0)}/100")
    message.append(f"      • {team2}: {stats.get('team2_form', 0)}/100")
    
    # Section 4: Information sur les cotes si disponibles
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        message.append("")
        message.append("💰 *COTES:*")
        message.append(f"  • {team1}: {odds['team1']}")
        message.append(f"  • {team2}: {odds['team2']}")
    
    # Ajouter le footer avec canal
    message.append("")
    message.append("━━━━━━━━━━━━━━━━━━━━━")
    message.append("📱 Rejoignez @alvecapital1 pour plus de prédictions!")
    
    return "\n".join(message)
