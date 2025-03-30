from collections import defaultdict, Counter
import logging
from typing import Dict, List, Tuple, Optional, Any
import math
import re
import time
from datetime import datetime, timedelta
from config import MAX_PREDICTIONS_HALF_TIME, MAX_PREDICTIONS_FULL_TIME

# Importer notre nouveau système de cache
from cache_system import (
    get_cached_prediction, cache_prediction,
    get_cached_teams, cache_teams,
    get_cached_matches, cache_matches
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MatchPredictor:
    """
    Classe optimisée pour la prédiction de matchs FIFA 4x4.
    Utilise un cache centralisé pour améliorer les performances.
    """
    def __init__(self):
        """Initialise le prédicteur de match"""
        self.team_stats = None
        self.match_id_trends = None
        self.teams_mapping = {}  # Dictionnaire pour normaliser les noms d'équipes
        
        # Précharger les données au démarrage
        self._preload_data()
    
    async def _preload_data(self):
        """Précharge les données statiques en arrière-plan"""
        try:
            # Vérifier d'abord si les données sont déjà en cache
            cached_matches = await get_cached_matches()
            
            if cached_matches:
                logger.info("Données de matches trouvées en cache")
                self.matches = cached_matches
                
                # Calculer les statistiques à partir des matches en cache
                self.team_stats = self._calculate_team_statistics(self.matches)
                self.match_id_trends = self._calculate_match_id_trends(self.matches)
                self._create_teams_mapping()
                
                # Mettre en cache la liste des équipes si ce n'est pas déjà fait
                teams = list(self.team_stats.keys())
                cached_teams = await get_cached_teams()
                if not cached_teams:
                    await cache_teams(teams)
                    
                logger.info(f"Données préchargées depuis le cache: {len(self.matches)} matches, {len(teams)} équipes")
                return
            
            # Si pas en cache, charger depuis la base de données
            logger.info("Préchargement des données depuis la base de données...")
            from database_adapter import get_all_matches_data
            self.matches = get_all_matches_data()
            
            if self.matches:
                # Mettre en cache pour utilisation future
                await cache_matches(self.matches)
                
                # Calculer les statistiques pour améliorer les performances
                self.team_stats = self._calculate_team_statistics(self.matches)
                self.match_id_trends = self._calculate_match_id_trends(self.matches)
                
                # Créer un dictionnaire de correspondance des noms d'équipes
                # Créer un dictionnaire de correspondance des noms d'équipes
                self._create_teams_mapping()
                
                # Mettre en cache la liste des équipes
                teams = list(self.team_stats.keys())
                await cache_teams(teams)
                
                logger.info(f"Données préchargées: {len(self.matches)} matches, {len(teams)} équipes")
            else:
                logger.warning("Aucune donnée de match disponible!")
        except Exception as e:
            logger.error(f"Erreur lors du préchargement des données: {e}")
    
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

    async def predict_match(self, team1: str, team2: str, odds1: float = None, odds2: float = None) -> Optional[Dict[str, Any]]:
        """
        Prédit le résultat d'un match entre team1 et team2.
        Version optimisée qui utilise le cache et réduit les opérations inutiles.
        """
        logger.info(f"Tentative d'analyse du match: {team1} vs {team2}")
        
        # Vérifier si la prédiction est dans le cache
        cached_prediction = await get_cached_prediction(team1, team2, odds1, odds2)
        if cached_prediction:
            logger.info(f"Prédiction trouvée en cache pour {team1} vs {team2}")
            return cached_prediction
        
        # Vérifier si les statistiques sont disponibles
        if not self.team_stats:
            logger.error("Statistiques d'équipes non disponibles")
            await self._preload_data()  # Essayer de recharger les données
            
            # Vérifier à nouveau après le rechargement
            if not self.team_stats:
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
        from database_adapter import get_direct_confrontations
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
        from database_adapter import get_common_scores
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
        home_win_pct = 0
        home_draw_pct = 0
        home_loss_pct = 0
        
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
        away_win_pct = 0
        away_draw_pct = 0
        away_loss_pct = 0
        
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
        
        # 4. Calculer la forme récente des équipes
        team1_form = self._calculate_team_form(team1, 5)
        team2_form = self._calculate_team_form(team2, 5)
        
        # 5. Ajuster les prédictions en fonction des cotes si disponibles
        if odds1 is not None and odds2 is not None:
            # Calculer les probabilités implicites des cotes
            prob1 = 1 / odds1
            prob2 = 1 / odds2
            # Normaliser
            total_prob = prob1 + prob2
            prob1 = prob1 / total_prob
            prob2 = prob2 / total_prob
            
            # Ajuster les poids pour les équipes en fonction des cotes
            for i, (score, weight) in enumerate(all_final_scores):
                try:
                    parts = score.split(':')
                    goals1 = int(parts[0])
                    goals2 = int(parts[1])
                    
                    # Si team1 gagne dans ce score et les cotes favorisent team1
                    if goals1 > goals2 and prob1 > 0.5:
                        all_final_scores[i] = (score, weight * (1 + (prob1 - 0.5) * 2))
                    # Si team2 gagne dans ce score et les cotes favorisent team2
                    elif goals2 > goals1 and prob2 > 0.5:
                        all_final_scores[i] = (score, weight * (1 + (prob2 - 0.5) * 2))
                    # Si match nul et les cotes sont proches
                    elif goals1 == goals2 and abs(prob1 - prob2) < 0.1:
                        all_final_scores[i] = (score, weight * 1.3)
                except (ValueError, IndexError):
                    continue
        
        # 6. Ajustement spécifique pour FIFA 4x4 (beaucoup de buts)
        # Favoriser légèrement les scores avec plus de buts
        for i, (score, weight) in enumerate(all_final_scores):
            try:
                parts = score.split(':')
                total_goals = int(parts[0]) + int(parts[1])
                # Pour FIFA 4x4, favoriser davantage les scores avec 6+ buts
                if total_goals >= 6:
                    all_final_scores[i] = (score, weight * 1.3)
                elif total_goals >= 4:
                    all_final_scores[i] = (score, weight * 1.15)
            except (ValueError, IndexError):
                continue
                
        for i, (score, weight) in enumerate(all_half_scores):
            try:
                parts = score.split(':')
                total_goals = int(parts[0]) + int(parts[1])
                # Pour mi-temps FIFA 4x4, favoriser davantage les scores avec 3+ buts
                if total_goals >= 3:
                    all_half_scores[i] = (score, weight * 1.2)
            except (ValueError, IndexError):
                continue
        
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
        
        # 7. Remplir les résultats de prédiction
        
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
        
        # Facteur 5: Forme récente des équipes
        if team1_form is not None and team2_form is not None:
            # Si les deux équipes ont une bonne forme récente
            avg_form = (team1_form + team2_form) / 2
            if avg_form > 0.7:
                confidence_factors.append(85)
            elif avg_form > 0.5:
                confidence_factors.append(75)
            else:
                confidence_factors.append(65)
        
        # Calcul de la confiance globale (moyenne pondérée)
        if confidence_factors:
            prediction_results["confidence_level"] = round(sum(confidence_factors) / len(confidence_factors))
        
        # Arrondir les moyennes de buts
        prediction_results["avg_goals_half_time"] = round(prediction_results["avg_goals_half_time"], 1)
        prediction_results["avg_goals_full_time"] = round(prediction_results["avg_goals_full_time"], 1)
        
        # Stocker la prédiction dans le cache
        await cache_prediction(team1, team2, odds1, odds2, prediction_results)
        
        logger.info(f"Prédiction générée avec succès pour {team1} vs {team2}")
        return prediction_results
    
    def _calculate_team_form(self, team, last_n=5):
        """
        Calcule la forme récente d'une équipe (proportion de victoires sur les derniers matchs)
        Retourne un score entre 0 et 1
        """
        # Collecter les derniers matchs de l'équipe (domicile et extérieur)
        team_matches = []
        for match in self.matches:
            team_home = match.get('team_home', '')
            team_away = match.get('team_away', '')
            score_final = match.get('score_final', '')
            
            if not score_final:
                continue
                
            if team_home == team or team_away == team:
                try:
                    parts = score_final.split(':')
                    home_goals = int(parts[0])
                    away_goals = int(parts[1])
                    
                    # Déterminer si l'équipe a gagné, perdu ou fait match nul
                    if team_home == team:
                        if home_goals > away_goals:
                            result = 'win'
                        elif home_goals < away_goals:
                            result = 'loss'
                        else:
                            result = 'draw'
                    else:  # team_away == team
                        if away_goals > home_goals:
                            result = 'win'
                        elif away_goals < home_goals:
                            result = 'loss'
                        else:
                            result = 'draw'
                    
                    team_matches.append({
                        'score': score_final,
                        'result': result
                    })
                except (ValueError, IndexError):
                    continue
        
        # Prendre les n derniers matchs
        recent_matches = team_matches[-last_n:] if len(team_matches) >= last_n else team_matches
        
        if not recent_matches:
            return None
        
        # Calculer le score de forme (1 point pour victoire, 0.5 pour nul, 0 pour défaite)
        form_score = 0
        for match in recent_matches:
            if match['result'] == 'win':
                form_score += 1
            elif match['result'] == 'draw':
                form_score += 0.5
        
        # Normaliser entre 0 et 1
        return form_score / len(recent_matches)
        
    def _calculate_team_statistics(self, matches):
        """
        Calcule les statistiques pour chaque équipe à partir des matchs.
        Version optimisée qui précharge les statistiques au lieu de les calculer à chaque prédiction.
        """
        from database_adapter import get_team_statistics
        return get_team_statistics(matches)
    
    def _calculate_match_id_trends(self, matches):
        """
        Analyse les tendances par numéro de match.
        Version optimisée qui précharge les tendances au lieu de les calculer à chaque prédiction.
        """
        from database_adapter import get_match_id_trends
        return get_match_id_trends(matches)

# Fonction formatage message prédiction optimisée
def format_prediction_message(prediction: Dict[str, Any]) -> str:
    """Formate le résultat de prédiction en message lisible et attrayant"""
    if not prediction:
        return "❌ Erreur: Impossible de générer une prédiction"
        
    if "error" in prediction:
        return f"❌ Erreur: {prediction['error']}"
    
    teams = prediction["teams"]
    team1 = teams["team1"]
    team2 = teams["team2"]
    
    message = [
        f"🔮 *PRÉDICTION:* {team1} vs {team2}",
        f"🤝 Confrontations directes: {prediction['direct_matches']}",
        "\n"
    ]
    
    # Section 1: Scores exacts simplifiés - Mi-temps
    message.append("*⏱️ MI-TEMPS:*")
    
    # Scores alignés côte à côte avec des espaces entre eux
    half_time_scores = []
    if prediction["half_time_scores"] and len(prediction["half_time_scores"]) > 0:
        for i in range(min(3, len(prediction["half_time_scores"]))):
            half_time_scores.append(prediction["half_time_scores"][i]["score"])
        
        message.append(f"  *{half_time_scores[0]}*    {half_time_scores[1] if len(half_time_scores) > 1 else ''}    {half_time_scores[2] if len(half_time_scores) > 2 else ''}")
    else:
        message.append("  Pas assez de données pour prédire")
    
    # Gagnant à la mi-temps - version simplifiée
    winner_ht = prediction["winner_half_time"]
    if winner_ht["team"]:
        if winner_ht["team"] == "Nul":
            message.append(f"  👉 *Match nul*")
        else:
            message.append(f"  👉 *{winner_ht['team']}* gagnant")
    message.append("")
    
    # Section 2: Scores exacts simplifiés - Temps réglementaire
    message.append("*⚽ TEMPS RÉGLEMENTAIRE:*")
    
    # Scores alignés côte à côte
    full_time_scores = []
    if prediction["full_time_scores"] and len(prediction["full_time_scores"]) > 0:
        for i in range(min(3, len(prediction["full_time_scores"]))):
            full_time_scores.append(prediction["full_time_scores"][i]["score"])
        
        message.append(f"  *{full_time_scores[0]}*    {full_time_scores[1] if len(full_time_scores) > 1 else ''}    {full_time_scores[2] if len(full_time_scores) > 2 else ''}")
    else:
        message.append("  Pas assez de données pour prédire")
    
    # Gagnant du match - version simplifiée
    # Gagnant du match - version simplifiée
    winner_ft = prediction["winner_full_time"]
    if winner_ft["team"]:
        if winner_ft["team"] == "Nul":
            message.append(f"  👉 *Match nul*")
        else:
            message.append(f"  👉 *{winner_ft['team']}* gagnant")
    message.append("")
    
    # Section 3: Prédictions recommandées au format paris sportif
    message.append("*📈 PRÉDICTIONS RECOMMANDÉES:*")
    
    # Format paris sportif correct pour les buts en mi-temps
    avg_ht_goals = prediction['avg_goals_half_time']
    # Pour FIFA 4x4, augmenter légèrement le nombre moyen de buts attendus
    avg_ht_goals = avg_ht_goals * 1.1  # +10% pour tenir compte du contexte FIFA 4x4
    
    # Calculer la ligne de pari exacte (0.5 près) au lieu de l'arrondir
    half_time_expected = round(avg_ht_goals)
    # Déterminer la ligne de pari pour over/under
    half_time_line = half_time_expected - 0.5 if avg_ht_goals <= half_time_expected else half_time_expected + 0.5
    # Déterminer si c'est un pari over ou under
    is_over_ht = avg_ht_goals > half_time_line
    half_time_label = f"+{half_time_line}" if is_over_ht else f"-{half_time_line}"
    
    # Format paris sportif correct pour les buts en temps réglementaire
    avg_ft_goals = prediction['avg_goals_full_time']
    # Pour FIFA 4x4, augmenter légèrement le nombre moyen de buts attendus
    avg_ft_goals = avg_ft_goals * 1.1  # +10% pour tenir compte du contexte FIFA 4x4
    
    # Calculer la ligne de pari exacte (0.5 près)
    full_time_expected = round(avg_ft_goals)
    # Déterminer la ligne de pari pour over/under
    full_time_line = full_time_expected - 0.5 if avg_ft_goals <= full_time_expected else full_time_expected + 0.5
    # Déterminer si c'est un pari over ou under
    is_over_ft = avg_ft_goals > full_time_line
    full_time_label = f"+{full_time_line}" if is_over_ft else f"-{full_time_line}"
    
    # Ajouter une information sur le nombre moyen de buts
    message.append(f"  • *Mi-temps:* {half_time_label} buts (moyenne: {avg_ht_goals:.1f})")
    message.append(f"  • *Temps réglementaire:* {full_time_label} buts (moyenne: {avg_ft_goals:.1f})")
    
    # Ajouter le niveau de confiance
    confidence = prediction.get("confidence_level", 0)
    confidence_emoji = "✅" if confidence >= 75 else "⚠️" if confidence >= 60 else "❓"
    message.append(f"  • *Confiance:* {confidence_emoji} {confidence}%")
    message.append("")
    
    # Message de prévention sur les paris sportifs
    message.append("_Les paris sportifs comportent des risques. Ne misez pas plus de 5% de votre capital._")
    
    return "\n".join(message)

# Créer une instance unique du prédicteur (singleton)
match_predictor = MatchPredictor()

# Fonction asynchrone pour précharger les données au démarrage
async def preload_prediction_data():
    """Précharge les données pour le prédicteur au démarrage de l'application."""
    await match_predictor._preload_data()
    logger.info("Préchargement des données de prédiction terminé")
