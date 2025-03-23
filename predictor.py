from collections import defaultdict, Counter
import logging
from typing import Dict, List, Tuple, Optional, Any
import math
import unicodedata
import re
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

class MatchPredictor:
    def __init__(self):
        """Initialise le prédicteur de match"""
        # Charger les données de matchs
        self.matches = get_all_matches_data()
        self.team_stats = None
        self.match_id_trends = None
        self.teams_map = {}  # Mapping des noms normalisés vers les noms originaux
        
        if self.matches:
            # Pré-calculer les statistiques pour améliorer les performances
            self.team_stats = get_team_statistics(self.matches)
            self.match_id_trends = get_match_id_trends(self.matches)
            
            # Créer un mapping des noms d'équipes normalisés vers les noms originaux
            for team_name in self.team_stats.keys():
                norm_name = normalize_team_name(team_name)
                self.teams_map[norm_name] = team_name
        else:
            logger.warning("Aucune donnée de match disponible!")

    def predict_match(self, team1: str, team2: str, odds1: float = None, odds2: float = None) -> Optional[Dict[str, Any]]:
        """Prédit le résultat d'un match entre team1 et team2"""
        logger.info(f"Analyse du match: {team1} vs {team2}")
        
        # Normaliser les noms des équipes
        norm_team1 = normalize_team_name(team1)
        norm_team2 = normalize_team_name(team2)
        
        # Rechercher les équipes dans le mapping
        team1_key = None
        team2_key = None
        
        if norm_team1 in self.teams_map:
            team1_key = self.teams_map[norm_team1]
        else:
            # Recherche alternative si le mapping exact n'est pas trouvé
            for norm_key, orig_key in self.teams_map.items():
                if norm_team1 in norm_key or norm_key in norm_team1:
                    team1_key = orig_key
                    break
        
        if norm_team2 in self.teams_map:
            team2_key = self.teams_map[norm_team2]
        else:
            # Recherche alternative si le mapping exact n'est pas trouvé
            for norm_key, orig_key in self.teams_map.items():
                if norm_team2 in norm_key or norm_key in norm_team2:
                    team2_key = orig_key
                    break
        
        # Vérifier si les équipes existent dans nos données
        if not self.team_stats:
            logger.error("Statistiques d'équipes non disponibles")
            return None
        
        if not team1_key:
            logger.warning(f"Équipe '{team1}' non trouvée dans les données historiques")
            return {"error": f"Équipe '{team1}' non trouvée dans notre base de données"}
        
        if not team2_key:
            logger.warning(f"Équipe '{team2}' non trouvée dans les données historiques")
            return {"error": f"Équipe '{team2}' non trouvée dans notre base de données"}
        
        # Récupérer les confrontations directes
        direct_matches = get_direct_confrontations(self.matches, team1_key, team2_key)
        
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
        
        # Calculer l'avantage basé sur les cotes si disponibles
        team1_advantage = 0.5  # Valeur neutre par défaut
        if odds1 is not None and odds2 is not None:
            # Convertir les cotes en probabilités implicites
            try:
                odds1_val = float(odds1)
                odds2_val = float(odds2)
                if odds1_val > 0 and odds2_val > 0:
                    prob1 = 1 / odds1_val
                    prob2 = 1 / odds2_val
                    sum_prob = prob1 + prob2
                    
                    # Normaliser les probabilités (pour éliminer la marge du bookmaker)
                    norm_prob1 = prob1 / sum_prob
                    
                    # L'avantage est la probabilité normalisée de team1
                    team1_advantage = norm_prob1
                    logger.info(f"Avantage calculé basé sur les cotes: {team1_advantage:.2f}")
            except (ValueError, ZeroDivisionError) as e:
                logger.warning(f"Erreur dans le calcul de l'avantage des cotes: {e}")
        
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
                if home == team1_key:
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
                # Poids plus élevé pour les confrontations directes (x2)
                all_final_scores.append((score, pct * 2.0))
        
        if common_direct_half:
            for score, count, pct in common_direct_half[:MAX_PREDICTIONS_HALF_TIME]:
                # Poids plus élevé pour les confrontations directes (x2)
                all_half_scores.append((score, pct * 2.0))
        
        # 2. Analyse des performances à domicile/extérieur
        # Team1 à domicile (utiliser team1_key pour accéder aux statistiques)
        home_matches = self.team_stats[team1_key]['home_matches']
        if home_matches > 0:
            home_win_pct = round(self.team_stats[team1_key]['home_wins'] / home_matches * 100, 1)
            home_draw_pct = round(self.team_stats[team1_key]['home_draws'] / home_matches * 100, 1)
            home_loss_pct = round(self.team_stats[team1_key]['home_losses'] / home_matches * 100, 1)
            
            # Scores les plus fréquents à domicile
            home_scores = [f"{g_for}:{g_against}" for g_for, g_against in zip(
                self.team_stats[team1_key]['home_goals_for'], self.team_stats[team1_key]['home_goals_against'])]
            common_home = get_common_scores(home_scores)
            
            if common_home:
                for score, count, pct in common_home[:MAX_PREDICTIONS_FULL_TIME]:
                    # Ajuster le poids selon l'avantage des cotes
                    adj_weight = pct * (0.8 + team1_advantage * 0.4)
                    all_final_scores.append((score, adj_weight))
            
            # 1ère mi-temps à domicile
            common_home_half = get_common_scores(self.team_stats[team1_key]['home_first_half'])
            if common_home_half:
                for score, count, pct in common_home_half[:MAX_PREDICTIONS_HALF_TIME]:
                    # Ajuster le poids selon l'avantage des cotes
                    adj_weight = pct * (0.8 + team1_advantage * 0.4)
                    all_half_scores.append((score, adj_weight))
        
        # Team2 à l'extérieur (utiliser team2_key pour accéder aux statistiques)
        away_matches = self.team_stats[team2_key]['away_matches']
        if away_matches > 0:
            away_win_pct = round(self.team_stats[team2_key]['away_wins'] / away_matches * 100, 1)
            away_draw_pct = round(self.team_stats[team2_key]['away_draws'] / away_matches * 100, 1)
            away_loss_pct = round(self.team_stats[team2_key]['away_losses'] / away_matches * 100, 1)
            
            # Scores les plus fréquents à l'extérieur
            away_scores = [f"{g_for}:{g_against}" for g_for, g_against in zip(
                self.team_stats[team2_key]['away_goals_for'], self.team_stats[team2_key]['away_goals_against'])]
            common_away = get_common_scores(away_scores)
            
            if common_away:
                for score, count, pct in common_away[:MAX_PREDICTIONS_FULL_TIME]:
                    # Inverser le score car on a les stats du point de vue de l'équipe à l'extérieur
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        # Ajuster le poids selon l'avantage des cotes (inversé pour team2)
                        adj_weight = pct * (0.8 + (1 - team1_advantage) * 0.4)
                        all_final_scores.append((inverted_score, adj_weight))
                    except (ValueError, IndexError):
                        pass
            
            # 1ère mi-temps à l'extérieur
            common_away_half = get_common_scores(self.team_stats[team2_key]['away_first_half'])
            if common_away_half:
                for score, count, pct in common_away_half[:MAX_PREDICTIONS_HALF_TIME]:
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        # Ajuster le poids selon l'avantage des cotes (inversé pour team2)
                        adj_weight = pct * (0.8 + (1 - team1_advantage) * 0.4)
                        all_half_scores.append((inverted_score, adj_weight))
                    except (ValueError, IndexError):
                        pass
        
        # 3. Ajouter les tendances par numéro de match
        all_match_ids = [match.get('match_id', '') for match in self.matches if match.get('match_id', '')]
        match_id_counter = Counter(all_match_ids)
        most_common_ids = match_id_counter.most_common(5)  # Augmenté à 5 pour FIFA 4x4
        
        for match_id, _ in most_common_ids:
            if match_id in self.match_id_trends:
                final_scores = self.match_id_trends[match_id]['final_scores']
                first_half_scores = self.match_id_trends[match_id]['first_half_scores']
                
                common_final = get_common_scores(final_scores)
                common_half = get_common_scores(first_half_scores)
                
                if common_final:
                    for score, count, pct in common_final[:MAX_PREDICTIONS_FULL_TIME]:
                        # Poids légèrement plus faible pour les tendances générales
                        all_final_scores.append((score, pct * 0.9))
                
                if common_half:
                    for score, count, pct in common_half[:MAX_PREDICTIONS_HALF_TIME]:
                        # Poids légèrement plus faible pour les tendances générales
                        all_half_scores.append((score, pct * 0.9))
        
        # 4. Favoriser les scores avec beaucoup de buts (FIFA 4x4 a tendance à avoir beaucoup de buts)
        for i, (score, weight) in enumerate(all_final_scores[:]):
            try:
                parts = score.split(':')
                team1_goals = int(parts[0])
                team2_goals = int(parts[1])
                total_goals = team1_goals + team2_goals
                
                # Augmenter le poids des scores avec beaucoup de buts
                if total_goals >= 13:
                    all_final_scores.append((score, weight * 1.5))  # Bonus très élevé
                elif total_goals >= 10:
                    all_final_scores.append((score, weight * 1.3))  # Bonus élevé
                elif total_goals >= 7:
                    all_final_scores.append((score, weight * 1.15))  # Bonus modéré
            except (ValueError, IndexError):
                pass
        
        for i, (score, weight) in enumerate(all_half_scores[:]):
            try:
                parts = score.split(':')
                team1_goals = int(parts[0])
                team2_goals = int(parts[1])
                total_goals = team1_goals + team2_goals
                
                # Augmenter le poids des scores avec beaucoup de buts
                if total_goals >= 8:
                    all_half_scores.append((score, weight * 1.5))  # Bonus très élevé
                elif total_goals >= 6:
                    all_half_scores.append((score, weight * 1.3))  # Bonus élevé
                elif total_goals >= 4:
                    all_half_scores.append((score, weight * 1.15))  # Bonus modéré
            except (ValueError, IndexError):
                pass
        
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
        
        # 5. Remplir les résultats de prédiction
        
        # Prédictions des scores mi-temps
        if sorted_half_scores:
            num_predictions = min(MAX_PREDICTIONS_HALF_TIME, len(sorted_half_scores))
            
            # Normaliser les poids pour obtenir des pourcentages
            total_weight = sum(weight for _, weight in sorted_half_scores[:num_predictions])
            if total_weight > 0:  # Éviter division par zéro
                for i in range(num_predictions):
                    score, weight = sorted_half_scores[i]
                    # Calculer le pourcentage de confiance (limité entre 50 et 90)
                    confidence = min(90, max(50, round((weight / total_weight) * 100)))
                    
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
            
            # Normaliser les poids pour obtenir des pourcentages
            total_weight = sum(weight for _, weight in sorted_final_scores[:num_predictions])
            if total_weight > 0:  # Éviter division par zéro
                for i in range(num_predictions):
                    score, weight = sorted_final_scores[i]
                    # Calculer le pourcentage de confiance (limité entre 50 et 90)
                    confidence = min(90, max(50, round((weight / total_weight) * 100)))
                    
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
        
        # 6. Calcul du niveau de confiance global
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
        min_matches = min(home_matches if home_matches else 0, away_matches if away_matches else 0)
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
            confidence_factors.append(80)
        
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
        
        # Facteur 5: Différence de niveau entre les équipes (basée sur les cotes)
        if odds1 and odds2:
            try:
                odds1_val = float(odds1)
                odds2_val = float(odds2)
                odds_ratio = odds1_val / odds2_val
                if 0.8 <= odds_ratio <= 1.2:  # Équipes proches
                    confidence_factors.append(85)  # Équipes équilibrées = prédiction plus fiable
                elif 0.5 <= odds_ratio <= 1.5:  # Différence modérée
                    confidence_factors.append(75)
                else:  # Grande différence
                    confidence_factors.append(65)  # Plus difficile de prédire des matchs déséquilibrés
            except (ValueError, ZeroDivisionError):
                pass
        
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
    
    # Nombre de buts mi-temps
    avg_ht_goals = prediction["avg_goals_half_time"]
    if avg_ht_goals > 0:
        message.append(f"  📈 Moyenne de buts: {avg_ht_goals} (FIFA 4x4 a tendance aux mi-temps à buts élevés)")
        
        # Conseils sur les buts à la mi-temps
        if avg_ht_goals >= 5:
            message.append(f"  💡 Conseil: Plus de 4.5 buts à la mi-temps pourrait être intéressant")
        elif avg_ht_goals >= 3:
            message.append(f"  💡 Conseil: Plus de 2.5 buts à la mi-temps est probable")
        
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
    
    # Nombre de buts temps réglementaire
    avg_ft_goals = prediction["avg_goals_full_time"]
    if avg_ft_goals > 0:
        message.append(f"  📈 Moyenne de buts: {avg_ft_goals} (FIFA 4x4 a tendance aux matchs à buts élevés)")
        
        # Conseils sur les buts temps réglementaire
        if avg_ft_goals >= 9:
            message.append(f"  💡 Conseil: Plus de 8.5 buts au total est probable")
        elif avg_ft_goals >= 7:
            message.append(f"  💡 Conseil: Plus de 6.5 buts au total est probable")
    
    message.append("")
    
    # Section 3: Information sur les cotes si disponibles
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        message.append("*💰 COTES:*")
        message.append(f"  • {team1}: {odds['team1']}")
        message.append(f"  • {team2}: {odds['team2']}")
        
        # Analyse de la valeur
        try:
            odds1_value = float(odds["team1"])
            odds2_value = float(odds["team2"])
            winner = winner_ft["team"]
            probability = winner_ft["probability"] / 100
            
            if winner == team1 and probability > 1/odds1_value:
                message.append(f"  💎 Valeur potentielle sur {team1}")
            elif winner == team2 and probability > 1/odds2_value:
                message.append(f"  💎 Valeur potentielle sur {team2}")
        except (ValueError, ZeroDivisionError):
            pass
    
    # Note finale
    message.append("\n*📝 NOTE:* FIFA 4x4 est connu pour ses matchs à buts élevés, tenez-en compte dans vos décisions.")
    
    return "\n".join(message)
