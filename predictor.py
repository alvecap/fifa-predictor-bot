from collections import defaultdict, Counter
import logging
from typing import Dict, List, Tuple, Optional, Any
import math
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

class MatchPredictor:
    def __init__(self):
        """Initialise le prédicteur de match"""
        # Charger les données de matchs
        self.matches = get_all_matches_data()
        self.team_stats = None
        self.match_id_trends = None
        self.teams_mapping = {}  # Dictionnaire pour normaliser les noms d'équipes
        
        if self.matches:
            # Pré-calculer les statistiques pour améliorer les performances
            self.team_stats = get_team_statistics(self.matches)
            self.match_id_trends = get_match_id_trends(self.matches)
            
            # Créer un dictionnaire de correspondance des noms d'équipes
            if self.team_stats:
                self._create_teams_mapping()
        else:
            logger.warning("Aucune donnée de match disponible!")

    def _create_teams_mapping(self):
        """Crée un dictionnaire de correspondance pour gérer les variations de noms d'équipes"""
        for team_name in self.team_stats.keys():
            # Version normalisée (minuscules, sans caractères spéciaux)
            normalized_name = self._normalize_team_name(team_name)
            self.teams_mapping[normalized_name] = team_name
            
            # Ajouter aussi la version sans espaces
            no_spaces = normalized_name.replace(" ", "")
            self.teams_mapping[no_spaces] = team_name
            
            # Ajouter la version avec underscores à la place des espaces
            with_underscores = normalized_name.replace(" ", "_")
            self.teams_mapping[with_underscores] = team_name

    def _normalize_team_name(self, team_name):
        """Normalise le nom d'une équipe pour faciliter la correspondance"""
        if not team_name:
            return ""
        
        # Convertir en minuscules et supprimer les caractères spéciaux
        normalized = team_name.lower()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = normalized.strip()
        
        return normalized

    def _get_canonical_team_name(self, team_name):
        """Obtient le nom canonique d'une équipe à partir du nom fourni par l'utilisateur"""
        if not team_name:
            return None
            
        # D'abord, vérifier si le nom tel quel existe dans les stats
        if team_name in self.team_stats:
            return team_name
            
        # Normaliser le nom pour la recherche
        normalized = self._normalize_team_name(team_name)
        
        # Vérifier s'il existe dans notre mapping
        if normalized in self.teams_mapping:
            return self.teams_mapping[normalized]
            
        # Vérifier sans les espaces ou avec underscores
        no_spaces = normalized.replace(" ", "")
        if no_spaces in self.teams_mapping:
            return self.teams_mapping[no_spaces]
            
        with_underscores = normalized.replace(" ", "_")
        if with_underscores in self.teams_mapping:
            return self.teams_mapping[with_underscores]
        
        # Recherche partielle si tout le reste échoue
        for key, value in self.teams_mapping.items():
            if normalized in key or key in normalized:
                logger.info(f"Correspondance approximative trouvée: '{team_name}' -> '{value}'")
                return value
        
        return None

    def predict_match(self, team1: str, team2: str, odds1: float = None, odds2: float = None) -> Optional[Dict[str, Any]]:
        """Prédit le résultat d'un match entre team1 et team2"""
        logger.info(f"Tentative d'analyse du match: {team1} vs {team2}")
        
        # Vérifier si les statistiques sont disponibles
        if not self.team_stats:
            logger.error("Statistiques d'équipes non disponibles")
            return {"error": "Données d'équipes non disponibles. Veuillez réessayer ultérieurement."}
        
        # Obtenir les noms canoniques des équipes
        canonical_team1 = self._get_canonical_team_name(team1)
        canonical_team2 = self._get_canonical_team_name(team2)
        
        logger.info(f"Noms canoniques: {team1} -> {canonical_team1}, {team2} -> {canonical_team2}")
        
        # Vérifier si les équipes existent dans nos données
        if not canonical_team1:
            logger.warning(f"Équipe '{team1}' non trouvée dans les données historiques")
            return {"error": f"Équipe '{team1}' non trouvée dans notre base de données"}
        
        if not canonical_team2:
            logger.warning(f"Équipe '{team2}' non trouvée dans les données historiques")
            return {"error": f"Équipe '{team2}' non trouvée dans notre base de données"}
        
        # Utiliser les noms canoniques pour le reste du traitement
        team1 = canonical_team1
        team2 = canonical_team2
        
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
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Erreur lors de l'analyse du score: {e}")
        
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
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Erreur lors de l'inversion du score: {e}")
            
            # 1ère mi-temps à l'extérieur
            common_away_half = get_common_scores(self.team_stats[team2]['away_first_half'])
            if common_away_half:
                for score, count, pct in common_away_half[:MAX_PREDICTIONS_HALF_TIME]:
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        all_half_scores.append((inverted_score, pct))
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Erreur lors de l'inversion du score mi-temps: {e}")
        
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
                except (ValueError, IndexError) as e:
                    logger.warning(f"Erreur lors de l'analyse du score mi-temps: {e}")
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
                except (ValueError, IndexError) as e:
                    logger.warning(f"Erreur lors de l'analyse du score temps réglementaire: {e}")
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
                except (ValueError, IndexError) as e:
                    logger.warning(f"Erreur lors de l'analyse de la cohérence: {e}")
                    confidence_factors.append(65)
        
        # Calcul de la confiance globale (moyenne pondérée)
        if confidence_factors:
            prediction_results["confidence_level"] = round(sum(confidence_factors) / len(confidence_factors))
        
        # Arrondir les moyennes de buts
        prediction_results["avg_goals_half_time"] = round(prediction_results["avg_goals_half_time"], 1)
        prediction_results["avg_goals_full_time"] = round(prediction_results["avg_goals_full_time"], 1)
        
        logger.info(f"Prédiction générée avec succès pour {team1} vs {team2}")
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
    
    # Section 3: Modifier "Statistiques moyennes" par "Prédiction recommandée" et format paris sportif
    message.append("*📈 PRÉDICTIONS RECOMMANDÉES:*")
    
    # Format paris sportif pour les buts en 1ère mi-temps
    avg_ht_goals = prediction['avg_goals_half_time']
    half_time_line = round(avg_ht_goals * 2) / 2  # Arrondir à 0.5 près
    half_time_over = half_time_line + 0.5
    half_time_under = half_time_line - 0.5
    
    # Pour le temps réglementaire
    avg_ft_goals = prediction['avg_goals_full_time']
    full_time_line = round(avg_ft_goals * 2) / 2  # Arrondir à 0.5 près
    full_time_over = full_time_line + 0.5
    full_time_under = full_time_line - 0.5
    
    # Probabilité pour over/under
    over_prob_ht = 60 if half_time_line < 2 else 45
    under_prob_ht = 100 - over_prob_ht
    
    over_prob_ft = 55 if full_time_line < 3 else 45
    under_prob_ft = 100 - over_prob_ft
    
    # Afficher les options de paris
    message.append(f"  • *Mi-temps:* {half_time_under} buts ou moins ({under_prob_ht}%)")
    message.append(f"  • *Mi-temps:* {half_time_over} buts ou plus ({over_prob_ht}%)")
    message.append(f"  • *Temps réglementaire:* {full_time_under} buts ou moins ({under_prob_ft}%)")
    message.append(f"  • *Temps réglementaire:* {full_time_over} buts ou plus ({over_prob_ft}%)")
    
    # Section 4: Information sur les cotes si disponibles
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        message.append("")
        message.append("*💰 COTES:*")
        message.append(f"  • {team1}: {odds['team1']}")
        message.append(f"  • {team2}: {odds['team2']}")
    
    return "\n".join(message)
