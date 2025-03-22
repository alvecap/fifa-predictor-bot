from collections import defaultdict, Counter
import logging
from typing import Dict, List, Tuple, Optional, Any
import math
from datetime import datetime, timedelta
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
        """Initialise le prédicteur de match avec des données améliorées"""
        # Charger les données de matchs
        self.matches = get_all_matches_data()
        self.team_stats = None
        self.match_id_trends = None
        self.current_date = datetime.now()
        
        if self.matches:
            # Pré-calculer les statistiques pour améliorer les performances
            self.team_stats = get_team_statistics(self.matches)
            self.match_id_trends = get_match_id_trends(self.matches)
            # Ajouter des statistiques avancées
            self.calculate_advanced_statistics()
        else:
            logger.warning("Aucune donnée de match disponible!")

    def calculate_advanced_statistics(self):
        """Calcule des statistiques avancées pour les équipes"""
        # Initialiser le dictionnaire pour les statistiques avancées
        self.advanced_stats = {}
        
        for team_name in self.team_stats.keys():
            self.advanced_stats[team_name] = {
                'form_last_5': self.calculate_team_form(team_name, 5),
                'form_last_10': self.calculate_team_form(team_name, 10),
                'goals_trend': self.calculate_goals_trend(team_name),
                'defensive_strength': self.calculate_defensive_strength(team_name),
                'offensive_strength': self.calculate_offensive_strength(team_name),
                'consistency_rating': self.calculate_consistency(team_name),
                'home_advantage': self.calculate_home_advantage(team_name),
                'away_performance': self.calculate_away_performance(team_name),
                'first_half_performance': self.calculate_half_time_performance(team_name)
            }
    
    def calculate_team_form(self, team_name: str, last_n_matches: int = 5) -> float:
        """Calcule la forme d'une équipe basée sur ses derniers matchs
        
        Returns:
            float: Score de forme entre 0 (mauvais) et 1 (excellent)
        """
        # Récupérer tous les matchs de l'équipe
        team_matches = []
        for match in self.matches:
            is_home = match.get('team_home', '') == team_name
            is_away = match.get('team_away', '') == team_name
            
            if is_home or is_away:
                try:
                    score_parts = match.get('score_final', '0:0').split(':')
                    home_goals = int(score_parts[0])
                    away_goals = int(score_parts[1])
                    
                    # Déterminer le résultat pour l'équipe
                    if is_home:
                        if home_goals > away_goals:
                            result = 'W'  # Victoire
                        elif home_goals < away_goals:
                            result = 'L'  # Défaite
                        else:
                            result = 'D'  # Match nul
                    else:  # is_away
                        if away_goals > home_goals:
                            result = 'W'  # Victoire
                        elif away_goals < home_goals:
                            result = 'L'  # Défaite
                        else:
                            result = 'D'  # Match nul
                    
                    # Ajouter à la liste avec la date si disponible
                    match_date = match.get('match_date', None)
                    team_matches.append({
                        'result': result,
                        'date': match_date,
                        'is_home': is_home,
                        'goals_for': home_goals if is_home else away_goals,
                        'goals_against': away_goals if is_home else home_goals
                    })
                except (ValueError, IndexError):
                    continue
        
        # Trier les matchs par date si disponible, sinon utiliser l'ordre actuel
        # qui suppose que les matchs récents sont en premier
        if any(m.get('date') for m in team_matches):
            team_matches.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Prendre les N derniers matchs
        recent_matches = team_matches[:last_n_matches]
        
        if not recent_matches:
            return 0.5  # Valeur par défaut si pas de données
        
        # Calculer le score de forme
        total_points = 0
        max_points = len(recent_matches) * 3  # Maximum possible (toutes victoires)
        
        for i, match in enumerate(recent_matches):
            # Points selon le résultat
            match_points = 3 if match['result'] == 'W' else (1 if match['result'] == 'D' else 0)
            
            # Pondérer les matchs plus récents
            recency_weight = 1.0 + (len(recent_matches) - i) / (2 * len(recent_matches))
            
            # Ajouter au total avec pondération
            total_points += match_points * recency_weight
        
        # Le dénominateur doit également prendre en compte les pondérations
        weighted_max = sum(1.0 + (len(recent_matches) - i) / (2 * len(recent_matches)) for i in range(len(recent_matches))) * 3
        
        # Normaliser entre 0 et 1
        form_score = total_points / weighted_max if weighted_max > 0 else 0.5
        
        return form_score
    
    def calculate_goals_trend(self, team_name: str) -> Dict[str, float]:
        """Analyse la tendance des buts marqués et encaissés par une équipe
        
        Returns:
            Dict: Contient 'scoring_trend' et 'conceding_trend' entre -1 (détérioration) et 1 (amélioration)
        """
        # Récupérer tous les matchs de l'équipe
        team_matches = []
        for match in self.matches:
            is_home = match.get('team_home', '') == team_name
            is_away = match.get('team_away', '') == team_name
            
            if is_home or is_away:
                try:
                    score_parts = match.get('score_final', '0:0').split(':')
                    home_goals = int(score_parts[0])
                    away_goals = int(score_parts[1])
                    
                    # Ajouter à la liste avec la date si disponible
                    match_date = match.get('match_date', None)
                    team_matches.append({
                        'date': match_date,
                        'goals_for': home_goals if is_home else away_goals,
                        'goals_against': away_goals if is_home else home_goals
                    })
                except (ValueError, IndexError):
                    continue
        
        # Trier les matchs par date si disponible
        if any(m.get('date') for m in team_matches):
            team_matches.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # S'il y a moins de 5 matchs, pas assez de données pour une tendance
        if len(team_matches) < 5:
            return {
                'scoring_trend': 0,
                'conceding_trend': 0
            }
        
        # Diviser en matchs récents et moins récents
        recent_count = min(5, len(team_matches) // 2)
        recent_matches = team_matches[:recent_count]
        older_matches = team_matches[recent_count:recent_count*2]
        
        if not older_matches:
            return {
                'scoring_trend': 0,
                'conceding_trend': 0
            }
        
        # Calculer les moyennes
        recent_goals_for = sum(m['goals_for'] for m in recent_matches) / len(recent_matches)
        recent_goals_against = sum(m['goals_against'] for m in recent_matches) / len(recent_matches)
        
        older_goals_for = sum(m['goals_for'] for m in older_matches) / len(older_matches)
        older_goals_against = sum(m['goals_against'] for m in older_matches) / len(older_matches)
        
        # Calculer les tendances (-1 à 1)
        scoring_diff = recent_goals_for - older_goals_for
        conceding_diff = older_goals_against - recent_goals_against  # Inversé car moins encaisser est positif
        
        # Normaliser entre -1 et 1
        max_diff = 3.0  # Différence maximale raisonnable pour normaliser
        scoring_trend = max(min(scoring_diff / max_diff, 1.0), -1.0)
        conceding_trend = max(min(conceding_diff / max_diff, 1.0), -1.0)
        
        return {
            'scoring_trend': scoring_trend,
            'conceding_trend': conceding_trend
        }
    
    def calculate_defensive_strength(self, team_name: str) -> float:
        """Calcule la force défensive d'une équipe
        
        Returns:
            float: Score entre 0 (faible) et 1 (excellent)
        """
        # Récupérer les stats d'équipe
        team_data = self.team_stats.get(team_name, {})
        
        # Si pas de données, retourner valeur par défaut
        if not team_data or team_data.get('home_matches', 0) + team_data.get('away_matches', 0) == 0:
            return 0.5
        
        # Calculer les buts encaissés par match à domicile et à l'extérieur
        home_matches = team_data.get('home_matches', 0)
        away_matches = team_data.get('away_matches', 0)
        
        home_goals_against = team_data.get('home_goals_against', [])
        away_goals_against = team_data.get('away_goals_against', [])
        
        # Moyenne des buts encaissés
        home_avg_conceded = sum(home_goals_against) / home_matches if home_matches > 0 else 0
        away_avg_conceded = sum(away_goals_against) / away_matches if away_matches > 0 else 0
        
        # Calculer la moyenne globale, pondérée selon nombre de matchs
        total_matches = home_matches + away_matches
        avg_conceded = (home_avg_conceded * home_matches + away_avg_conceded * away_matches) / total_matches if total_matches > 0 else 0
        
        # Calculer le score défensif (moins de buts encaissés = meilleur)
        # Normaliser sur l'échelle: 0 = très mauvais (3+ buts/match), 1 = excellent (0 but/match)
        defensive_score = max(0, 1 - (avg_conceded / 3))
        
        return defensive_score
    
    def calculate_offensive_strength(self, team_name: str) -> float:
        """Calcule la force offensive d'une équipe
        
        Returns:
            float: Score entre 0 (faible) et 1 (excellent)
        """
        # Récupérer les stats d'équipe
        team_data = self.team_stats.get(team_name, {})
        
        # Si pas de données, retourner valeur par défaut
        if not team_data or team_data.get('home_matches', 0) + team_data.get('away_matches', 0) == 0:
            return 0.5
        
        # Calculer les buts marqués par match à domicile et à l'extérieur
        home_matches = team_data.get('home_matches', 0)
        away_matches = team_data.get('away_matches', 0)
        
        home_goals_for = team_data.get('home_goals_for', [])
        away_goals_for = team_data.get('away_goals_for', [])
        
        # Moyenne des buts marqués
        home_avg_scored = sum(home_goals_for) / home_matches if home_matches > 0 else 0
        away_avg_scored = sum(away_goals_for) / away_matches if away_matches > 0 else 0
        
        # Calculer la moyenne globale, pondérée selon nombre de matchs
        total_matches = home_matches + away_matches
        avg_scored = (home_avg_scored * home_matches + away_avg_scored * away_matches) / total_matches if total_matches > 0 else 0
        
        # Calculer le score offensif (plus de buts marqués = meilleur)
        # Normaliser sur l'échelle: 0 = très mauvais (0 but/match), 1 = excellent (3+ buts/match)
        offensive_score = min(1, avg_scored / 3)
        
        return offensive_score
    
    def calculate_consistency(self, team_name: str) -> float:
        """Calcule la consistance des performances d'une équipe
        
        Returns:
            float: Score entre 0 (inconsistant) et 1 (très consistant)
        """
        # Récupérer les stats d'équipe
        team_data = self.team_stats.get(team_name, {})
        
        # Si pas de données, retourner valeur par défaut
        if not team_data:
            return 0.5
        
        # Calculer les écarts-types des buts marqués et encaissés
        home_goals_for = team_data.get('home_goals_for', [])
        away_goals_for = team_data.get('away_goals_for', [])
        home_goals_against = team_data.get('home_goals_against', [])
        away_goals_against = team_data.get('away_goals_against', [])
        
        # Combiner tous les buts
        all_goals_for = home_goals_for + away_goals_for
        all_goals_against = home_goals_against + away_goals_against
        
        # Si pas assez de données, retourner valeur par défaut
        if len(all_goals_for) < 5 or len(all_goals_against) < 5:
            return 0.5
        
        # Calculer les écarts-types
        def stdev(values):
            # Calcul simple d'écart-type pour éviter d'importer statistics ou numpy
            if not values:
                return 0
            avg = sum(values) / len(values)
            variance = sum((x - avg) ** 2 for x in values) / len(values)
            return math.sqrt(variance)
        
        stdev_goals_for = stdev(all_goals_for)
        stdev_goals_against = stdev(all_goals_against)
        
        # Combinaison des écarts-types (moyenne)
        combined_stdev = (stdev_goals_for + stdev_goals_against) / 2
        
        # Normaliser le score de consistance (plus l'écart-type est faible, plus la consistance est élevée)
        # Utiliser une fonction exponentielle pour la normalisation
        consistency_score = math.exp(-combined_stdev) if combined_stdev > 0 else 1.0
        
        # S'assurer que le score est entre 0 et 1
        consistency_score = max(0, min(1, consistency_score))
        
        return consistency_score
    
    def calculate_home_advantage(self, team_name: str) -> float:
        """Calcule l'avantage à domicile d'une équipe
        
        Returns:
            float: Score entre 0 (faible) et 1 (fort)
        """
        # Récupérer les stats d'équipe
        team_data = self.team_stats.get(team_name, {})
        
        # Si pas de données ou pas assez de matchs à domicile, retourner valeur par défaut
        home_matches = team_data.get('home_matches', 0)
        if not team_data or home_matches < 3:
            return 0.5
        
        # Calculer le ratio de victoires à domicile
        home_wins = team_data.get('home_wins', 0)
        home_win_ratio = home_wins / home_matches
        
        # Calculer la différence moyenne de buts à domicile
        home_goals_for = team_data.get('home_goals_for', [])
        home_goals_against = team_data.get('home_goals_against', [])
        
        if not home_goals_for or not home_goals_against:
            return home_win_ratio  # Si pas de données de buts, utiliser juste le ratio de victoires
        
        avg_home_goals_for = sum(home_goals_for) / len(home_goals_for)
        avg_home_goals_against = sum(home_goals_against) / len(home_goals_against)
        
        goal_diff = avg_home_goals_for - avg_home_goals_against
        
        # Normaliser la différence de buts (entre -1 et 1)
        normalized_goal_diff = max(-1, min(1, goal_diff / 3))
        
        # Combinaison du ratio de victoires et de la différence de buts
        home_advantage = (home_win_ratio + (normalized_goal_diff + 1) / 2) / 2
        
        return home_advantage
    
    def calculate_away_performance(self, team_name: str) -> float:
        """Calcule la performance à l'extérieur d'une équipe
        
        Returns:
            float: Score entre 0 (faible) et 1 (fort)
        """
        # Récupérer les stats d'équipe
        team_data = self.team_stats.get(team_name, {})
        
        # Si pas de données ou pas assez de matchs à l'extérieur, retourner valeur par défaut
        away_matches = team_data.get('away_matches', 0)
        if not team_data or away_matches < 3:
            return 0.5
        
        # Calculer le ratio de victoires à l'extérieur
        away_wins = team_data.get('away_wins', 0)
        away_win_ratio = away_wins / away_matches
        
        # Calculer la différence moyenne de buts à l'extérieur
        away_goals_for = team_data.get('away_goals_for', [])
        away_goals_against = team_data.get('away_goals_against', [])
        
        if not away_goals_for or not away_goals_against:
            return away_win_ratio  # Si pas de données de buts, utiliser juste le ratio de victoires
        
        avg_away_goals_for = sum(away_goals_for) / len(away_goals_for)
        avg_away_goals_against = sum(away_goals_against) / len(away_goals_against)
        
        goal_diff = avg_away_goals_for - avg_away_goals_against
        
        # Normaliser la différence de buts (entre -1 et 1)
        normalized_goal_diff = max(-1, min(1, goal_diff / 3))
        
        # Combinaison du ratio de victoires et de la différence de buts
        away_performance = (away_win_ratio + (normalized_goal_diff + 1) / 2) / 2
        
        return away_performance
    
    def calculate_half_time_performance(self, team_name: str) -> Dict[str, float]:
        """Analyse la performance en première mi-temps
        
        Returns:
            Dict: Scores pour différents aspects de la performance en première mi-temps
        """
        # Récupérer les stats d'équipe
        team_data = self.team_stats.get(team_name, {})
        
        # Initialiser avec des valeurs par défaut
        half_time_stats = {
            'avg_goals_scored': 0.0,
            'avg_goals_conceded': 0.0,
            'win_ratio': 0.5,
            'leading_ratio': 0.5
        }
        
        # Si pas de données, retourner valeurs par défaut
        if not team_data:
            return half_time_stats
        
        # Analyser les scores de première mi-temps
        home_first_half = team_data.get('home_first_half', [])
        away_first_half = team_data.get('away_first_half', [])
        
        home_goals_scored = []
        home_goals_conceded = []
        home_leads = 0
        home_wins = 0
        
        # Analyser scores à domicile
        for score in home_first_half:
            try:
                parts = score.split(':')
                goals_for = int(parts[0])
                goals_against = int(parts[1])
                
                home_goals_scored.append(goals_for)
                home_goals_conceded.append(goals_against)
                
                if goals_for > goals_against:
                    home_leads += 1
                    home_wins += 1
                elif goals_for == goals_against:
                    home_leads += 0.5  # Match nul compte partiellement
            except (ValueError, IndexError):
                continue
        
        away_goals_scored = []
        away_goals_conceded = []
        away_leads = 0
        away_wins = 0
        
        # Analyser scores à l'extérieur
        for score in away_first_half:
            try:
                parts = score.split(':')
                goals_against = int(parts[0])  # Inversé car c'est l'équipe à l'extérieur
                goals_for = int(parts[1])
                
                away_goals_scored.append(goals_for)
                away_goals_conceded.append(goals_against)
                
                if goals_for > goals_against:
                    away_leads += 1
                    away_wins += 1
                elif goals_for == goals_against:
                    away_leads += 0.5  # Match nul compte partiellement
            except (ValueError, IndexError):
                continue
        
        # Calculer les statistiques combinées
        total_first_half = len(home_first_half) + len(away_first_half)
        if total_first_half > 0:
            # Moyennes des buts
            all_goals_scored = home_goals_scored + away_goals_scored
            all_goals_conceded = home_goals_conceded + away_goals_conceded
            
            half_time_stats['avg_goals_scored'] = sum(all_goals_scored) / len(all_goals_scored) if all_goals_scored else 0
            half_time_stats['avg_goals_conceded'] = sum(all_goals_conceded) / len(all_goals_conceded) if all_goals_conceded else 0
            
            # Ratio de victoires et de leads
            total_wins = home_wins + away_wins
            total_leads = home_leads + away_leads
            
            half_time_stats['win_ratio'] = total_wins / total_first_half
            half_time_stats['leading_ratio'] = total_leads / total_first_half
        
        return half_time_stats
    
    def get_match_recency_weight(self, match_date=None, current_date=None):
        """Calcule un facteur de pondération basé sur la récence du match"""
        if current_date is None:
            current_date = self.current_date
        
        if match_date is None:
            return 1.0  # Pas de date, poids neutre
        
        # Convertir en datetime si c'est une chaîne
        if isinstance(match_date, str):
            try:
                match_date = datetime.strptime(match_date, "%Y-%m-%d")
            except ValueError:
                return 1.0  # Format de date invalide
        
        # Calculer différence en jours
        days_diff = (current_date - match_date).days
        
        # Plus récent = plus de poids (maximum 1.5, minimum 0.5)
        if days_diff <= 30:  # Dernier mois
            return 1.5
        elif days_diff <= 90:  # Derniers 3 mois
            return 1.2
        elif days_diff <= 180:  # Derniers 6 mois
            return 1.0
        else:  # Plus vieux
            return 0.7
    
    def predict_match(self, team1: str, team2: str, odds1: float = None, odds2: float = None) -> Optional[Dict[str, Any]]:
        """Prédit le résultat d'un match entre team1 et team2 avec une précision améliorée"""
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
        
        # 1. Analyse des confrontations directes avec pondération par récence
        direct_final_scores = []
        direct_first_half = []
        direct_weights = []
        
        for match in direct_matches:
            home = match.get('team_home', '')
            away = match.get('team_away', '')
            score_final = match.get('score_final', '')
            score_1ere = match.get('score_1ere', '')
            match_date = match.get('match_date', None)
            
            # Calculer le poids basé sur la récence
            recency_weight = self.get_match_recency_weight(match_date)
            
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
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        direct_final_scores.append((inverted_score, recency_weight))
                        
                        if score_1ere:
                            half_parts = score_1ere.split(':')
                            inverted_half = f"{half_parts[1]}:{half_parts[0]}"
                            direct_first_half.append((inverted_half, recency_weight))
                    except (ValueError, IndexError):
                        pass
                
                direct_weights.append(recency_weight)
        
        # Analyse des scores les plus fréquents dans les confrontations directes avec pondération
        # Regrouper les scores avec leurs poids
        weighted_final_scores = defaultdict(float)
        for score, weight in direct_final_scores:
            weighted_final_scores[score] += weight
        
        weighted_half_scores = defaultdict(float)
        for score, weight in direct_first_half:
            weighted_half_scores[score] += weight
        
        # Convertir en liste triée par poids
        common_direct_final = sorted(weighted_final_scores.items(), key=lambda x: x[1], reverse=True)
        common_direct_half = sorted(weighted_half_scores.items(), key=lambda x: x[1], reverse=True)
        
        # 2. Préparation pour les prédictions multiples
        all_final_scores = []
        all_half_scores = []
        
        # Ajouter les scores des confrontations directes avec leur poids
        if common_direct_final:
            for score, weight in common_direct_final[:MAX_PREDICTIONS_FULL_TIME]:
                # Confrontations directes ont un poids plus important (1.5x)
                all_final_scores.append((score, weight * 1.5))
        
        if common_direct_half:
            for score, weight in common_direct_half[:MAX_PREDICTIONS_HALF_TIME]:
                all_half_scores.append((score, weight * 1.5))
        
        # 3. Analyse des forces relatives des équipes
        team1_adv_stats = self.advanced_stats.get(team1, {})
        team2_adv_stats = self.advanced_stats.get(team2, {})
        
        # Calculer un score de force relative (utilisé pour ajuster les probabilités)
        team1_form = team1_adv_stats.get('form_last_5', 0.5)
        team2_form = team2_adv_stats.get('form_last_5', 0.5)
        
        # Team1 à domicile, team2 à l'extérieur
        team1_home_advantage = team1_adv_stats.get('home_advantage', 0.5)
        team2_away_performance = team2_adv_stats.get('away_performance', 0.5)
        
        # Forces offensives et défensives
        team1_offensive = team1_adv_stats.get('offensive_strength', 0.5)
        team1_defensive = team1_adv_stats.get('defensive_strength', 0.5)
        team2_offensive = team2_adv_stats.get('offensive_strength', 0.5)
        team2_defensive = team2_adv_stats.get('defensive_strength', 0.5)
        
        # Calculer un score de force combiné pour chaque équipe
        team1_strength = (team1_form * 0.3) + (team1_home_advantage * 0.3) + (team1_offensive * 0.2) + (team1_defensive * 0.2)
        team2_strength = (team2_form * 0.3) + (team2_away_performance * 0.3) + (team2_offensive * 0.2) + (team2_defensive * 0.2)
        
        # Ajuster en fonction des cotes si disponibles
        if odds1 and odds2:
            # Les cotes inversées reflètent la probabilité estimée par les bookmakers
            implied_prob1 = 1 / odds1
            implied_prob2 = 1 / odds2
            
            # Normaliser ces probabilités (somme = 1)
            total_prob = implied_prob1 + implied_prob2
            bookmaker_strength1 = implied_prob1 / total_prob
            bookmaker_strength2 = implied_prob2 / total_prob
            
            # Intégrer les cotes dans l'analyse (avec un poids de 40%)
            team1_strength = (team1_strength * 0.6) + (bookmaker_strength1 * 0.4)
            team2_strength = (team2_strength * 0.6) + (bookmaker_strength2 * 0.4)
        
        # Calculer les probabilités de victoire/match nul
        total_strength = team1_strength + team2_strength
        win_prob_team1 = team1_strength / total_strength * 0.85  # 85% des matchs ont un gagnant
        win_prob_team2 = team2_strength / total_strength * 0.85
        draw_prob = 1 - win_prob_team1 - win_prob_team2
        
        # 4. Analyse des performances à domicile/extérieur pour générer des scores typiques
        # Team1 à domicile
        home_matches = self.team_stats[team1]['home_matches']
        if home_matches > 0:
            # Scores les plus fréquents à domicile
            home_scores = [f"{g_for}:{g_against}" for g_for, g_against in zip(
                self.team_stats[team1]['home_goals_for'], self.team_stats[team1]['home_goals_against'])]
            common_home = get_common_scores(home_scores)
            
            if common_home:
                for score, count, pct in common_home[:MAX_PREDICTIONS_FULL_TIME]:
                    all_final_scores.append((score, pct * team1_strength))
            
            # 1ère mi-temps à domicile
            common_home_half = get_common_scores(self.team_stats[team1]['home_first_half'])
            if common_home_half:
                for score, count, pct in common_home_half[:MAX_PREDICTIONS_HALF_TIME]:
                    all_half_scores.append((score, pct * team1_strength))
        
        # Team2 à l'extérieur
        away_matches = self.team_stats[team2]['away_matches']
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
                        all_final_scores.append((inverted_score, pct * team2_strength))
                    except (ValueError, IndexError):
                        pass
            
            # 1ère mi-temps à l'extérieur
            common_away_half = get_common_scores(self.team_stats[team2]['away_first_half'])
            if common_away_half:
                for score, count, pct in common_away_half[:MAX_PREDICTIONS_HALF_TIME]:
                    try:
                        parts = score.split(':')
                        inverted_score = f"{parts[1]}:{parts[0]}"
                        all_half_scores.append((inverted_score, pct * team2_strength))
                    except (ValueError, IndexError):
                        pass
        
        # 5. Calculs de prédiction basés sur les tendances de buts
        # Utiliser les moyennes de buts marqués/encaissés pour générer des scores probables
        team1_avg_scored_home = team1_adv_stats.get('first_half_performance', {}).get('avg_goals_scored', 0) * 2  # Multiplier par 2 pour passer à une estimation temps complet
        team1_avg_conceded_home = team1_adv_stats.get('first_half_performance', {}).get('avg_goals_conceded', 0) * 2
        
        team2_avg_scored_away = team2_adv_stats.get('first_half_performance', {}).get('avg_goals_scored', 0) * 2
        team2_avg_conceded_away = team2_adv_stats.get('first_half_performance', {}).get('avg_goals_conceded', 0) * 2
        
        # Prédiction basée sur la moyenne
        expected_goals_team1 = (team1_avg_scored_home + team2_avg_conceded_away) / 2
        expected_goals_team2 = (team2_avg_scored_away + team1_avg_conceded_home) / 2
        
        # Ajuster en fonction des forces offensives/défensives relatives
        offensive_factor_team1 = team1_offensive / (team1_offensive + team2_defensive) if team1_offensive + team2_defensive > 0 else 0.5
        offensive_factor_team2 = team2_offensive / (team2_offensive + team1_defensive) if team2_offensive + team1_defensive > 0 else 0.5
        
        expected_goals_team1 *= (offensive_factor_team1 + 0.5)  # Ajustement entre 0.5x et 1.5x
        expected_goals_team2 *= (offensive_factor_team2 + 0.5)
        
        # Générer quelques scores possibles autour de ces moyennes
        from itertools import product
        
        # Scores possibles pour le temps complet
        team1_goals_range = range(max(0, int(expected_goals_team1 - 1)), int(expected_goals_team1 + 2))
        team2_goals_range = range(max(0, int(expected_goals_team2 - 1)), int(expected_goals_team2 + 2))
        
        possible_scores = list(product(team1_goals_range, team2_goals_range))
        
        # Calculer les probabilités de chaque score en fonction de la distribution de Poisson
        def poisson_probability(mean, k):
            return math.exp(-mean) * (mean ** k) / math.factorial(k)
        
        for team1_goals, team2_goals in possible_scores:
            prob_team1 = poisson_probability(expected_goals_team1, team1_goals)
            prob_team2 = poisson_probability(expected_goals_team2, team2_goals)
            
            # Probabilité combinée
            combined_prob = prob_team1 * prob_team2 * 100
            
            # Ajouter à la liste des scores finaux
            score = f"{team1_goals}:{team2_goals}"
            all_final_scores.append((score, combined_prob * 1.2))  # Donner un peu plus de poids à cette méthode
        
        # Faire de même pour la mi-temps (avec des valeurs divisées par 2)
        half_expected_goals_team1 = expected_goals_team1 / 2
        half_expected_goals_team2 = expected_goals_team2 / 2
        
        team1_half_range = range(max(0, int(half_expected_goals_team1 - 0.5)), int(half_expected_goals_team1 + 1.5))
        team2_half_range = range(max(0, int(half_expected_goals_team2 - 0.5)), int(half_expected_goals_team2 + 1.5))
        
        possible_half_scores = list(product(team1_half_range, team2_half_range))
        
        for team1_goals, team2_goals in possible_half_scores:
            prob_team1 = poisson_probability(half_expected_goals_team1, team1_goals)
            prob_team2 = poisson_probability(half_expected_goals_team2, team2_goals)
            
            combined_prob = prob_team1 * prob_team2 * 100
            
            score = f"{team1_goals}:{team2_goals}"
            all_half_scores.append((score, combined_prob * 1.2))
        
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
                            prediction_results["winner_full_time"] = {"team": team1, "probability": round(win_prob_team1 * 100)}
                        elif team2_goals > team1_goals:
                            prediction_results["winner_full_time"] = {"team": team2, "probability": round(win_prob_team2 * 100)}
                        else:
                            prediction_results["winner_full_time"] = {"team": "Nul", "probability": round(draw_prob * 100)}
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
        
        # Facteur 4: Consistance des équipes
        team1_consistency = team1_adv_stats.get('consistency_rating', 0.5)
        team2_consistency = team2_adv_stats.get('consistency_rating', 0.5)
        avg_consistency = (team1_consistency + team2_consistency) / 2
        consistency_confidence = 50 + round(avg_consistency * 40)  # Entre 50 et 90
        confidence_factors.append(consistency_confidence)
        
        # Facteur 5: Cohérence des prédictions
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
            else:
                confidence_factors.append(60)
        
        # Calcul de la confiance globale (moyenne pondérée)
        if confidence_factors:
            prediction_results["confidence_level"] = round(sum(confidence_factors) / len(confidence_factors))
        
        # Arrondir les moyennes de buts
        prediction_results["avg_goals_half_time"] = round(prediction_results["avg_goals_half_time"], 1)
        prediction_results["avg_goals_full_time"] = round(prediction_results["avg_goals_full_time"], 1)
        
        # Ajouter des informations supplémentaires pour le débogage et l'analyse
        prediction_results["debug_info"] = {
            "team1_strength": round(team1_strength * 100),
            "team2_strength": round(team2_strength * 100),
            "win_probability_team1": round(win_prob_team1 * 100),
            "win_probability_team2": round(win_prob_team2 * 100),
            "draw_probability": round(draw_prob * 100),
            "expected_goals_team1": round(expected_goals_team1, 2),
            "expected_goals_team2": round(expected_goals_team2, 2),
            "team1_form": round(team1_form * 100),
            "team2_form": round(team2_form * 100)
        }
        
        return prediction_results


def format_prediction_message(prediction: Dict[str, Any]) -> str:
    """Formate le résultat de prédiction en message lisible avec plus de détails"""
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
    
    # Section 1: Probabilités de résultat global
    message.append("*📊 PROBABILITÉS DE RÉSULTAT:*")
    debug_info = prediction.get("debug_info", {})
    win_prob_team1 = debug_info.get("win_probability_team1", 0)
    win_prob_team2 = debug_info.get("win_probability_team2", 0)
    draw_prob = debug_info.get("draw_probability", 0)
    
    message.append(f"  • Victoire {team1}: {win_prob_team1}%")
    message.append(f"  • Match nul: {draw_prob}%")
    message.append(f"  • Victoire {team2}: {win_prob_team2}%")
    message.append("")
    
    # Section 2: Scores exacts à la première mi-temps
    message.append("*⏱️ SCORES PRÉVUS (1ÈRE MI-TEMPS):*")
    if prediction["half_time_scores"]:
        for i, score_data in enumerate(prediction["half_time_scores"], 1):
            message.append(f"  {i}. *{score_data['score']}* ({score_data['confidence']}%)")
    else:
        message.append("  Pas assez de données pour prédire le score à la mi-temps")
    
    # Gagnant à la mi-temps
    winner_ht = prediction["winner_half_time"]
    if winner_ht["team"]:
        if winner_ht["team"] == "Nul":
            message.append(f"  👉 Mi-temps: *Match nul probable* ({winner_ht['probability']}%)")
        else:
            message.append(f"  👉 Mi-temps: *{winner_ht['team']} gagnant probable* ({winner_ht['probability']}%)")
    
    # Proposer un pari Over/Under pour la mi-temps
    avg_goals_ht = prediction['avg_goals_half_time']
    common_lines_ht = [0.5, 1.5, 2.5]
    closest_line_ht = min(common_lines_ht, key=lambda x: abs(x - avg_goals_ht))
    over_under_recommendation_ht = "Plus" if avg_goals_ht > closest_line_ht else "Moins"
    confidence_ht = min(90, max(60, round(abs(avg_goals_ht - closest_line_ht) * 50 + 65)))
    
    message.append(f"  🎯 Recommandation buts: *{over_under_recommendation_ht} de {closest_line_ht}* ({confidence_ht}%)")
    message.append("")
    
    # Section 3: Scores exacts au temps réglementaire
    message.append("*⚽ SCORES PRÉVUS (TEMPS RÉGLEMENTAIRE):*")
    if prediction["full_time_scores"]:
        for i, score_data in enumerate(prediction["full_time_scores"], 1):
            message.append(f"  {i}. *{score_data['score']}* ({score_data['confidence']}%)")
    else:
        message.append("  Pas assez de données pour prédire le score final")
    
    # Gagnant du match
    winner_ft = prediction["winner_full_time"]
    if winner_ft["team"]:
        if winner_ft["team"] == "Nul":
            message.append(f"  👉 Résultat final: *Match nul probable* ({winner_ft['probability']}%)")
        else:
            message.append(f"  👉 Résultat final: *{winner_ft['team']} gagnant probable* ({winner_ft['probability']}%)")
    
    # Proposer un pari Over/Under pour le temps complet
    avg_goals_ft = prediction['avg_goals_full_time']
    common_lines_ft = [0.5, 1.5, 2.5, 3.5, 4.5]
    closest_line_ft = min(common_lines_ft, key=lambda x: abs(x - avg_goals_ft))
    over_under_recommendation_ft = "Plus" if avg_goals_ft > closest_line_ft else "Moins"
    confidence_ft = min(90, max(60, round(abs(avg_goals_ft - closest_line_ft) * 50 + 65)))
    
    message.append(f"  🎯 Recommandation buts: *{over_under_recommendation_ft} de {closest_line_ft}* ({confidence_ft}%)")
    message.append("")
    
    # Section 4: Statistiques des équipes
    message.append("*📈 STATISTIQUES COMPARATIVES:*")
    
    team1_form = debug_info.get("team1_form", 0)
    team2_form = debug_info.get("team2_form", 0)
    team1_strength = debug_info.get("team1_strength", 0)
    team2_strength = debug_info.get("team2_strength", 0)
    
    message.append(f"  • Forme récente: {team1} ({team1_form}%) vs {team2} ({team2_form}%)")
    message.append(f"  • Force globale: {team1} ({team1_strength}%) vs {team2} ({team2_strength}%)")
    message.append(f"  • Buts attendus: {team1} ({debug_info.get('expected_goals_team1', 0)}) vs {team2} ({debug_info.get('expected_goals_team2', 0)})")
    message.append("")
    
    # Section 5: Meilleurs paris recommandés
    message.append("*🏆 PARIS RECOMMANDÉS:*")
    
    # Déterminer les paris les plus fiables
    recommendations = []
    
    # 1. Résultat du match
    if winner_ft["team"] != "Nul" and winner_ft["probability"] > 65:
        recommendations.append(f"• Victoire de {winner_ft['team']} ({winner_ft['probability']}%)")
    elif draw_prob > 30:
        recommendations.append(f"• Match nul ({draw_prob}%)")
    
    # 2. Nombre de buts total
    if confidence_ft > 70:
        recommendations.append(f"• {over_under_recommendation_ft} de {closest_line_ft} buts ({confidence_ft}%)")
    
    # 3. Mi-temps / Fin de match
    if winner_ht["team"] == winner_ft["team"] and winner_ht["team"] != "Nul" and winner_ht["probability"] > 60:
        recommendations.append(f"• {winner_ht['team']} gagne à la mi-temps et au final ({min(winner_ht['probability'], winner_ft['probability'])}%)")
    
    # 4. Score exact le plus probable
    if prediction["full_time_scores"] and prediction["full_time_scores"][0]["confidence"] > 70:
        most_likely_score = prediction["full_time_scores"][0]["score"]
        recommendations.append(f"• Score exact: {most_likely_score} ({prediction['full_time_scores'][0]['confidence']}%)")
    
    # Ajouter les recommandations au message
    if recommendations:
        for rec in recommendations:
            message.append(rec)
    else:
        message.append("• Données insuffisantes pour des paris très fiables")
    
    # Section 6: Information sur les cotes si disponibles
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        message.append("")
        message.append("*💰 COTES UTILISÉES:*")
        message.append(f"  • {team1}: {odds['team1']}")
        message.append(f"  • {team2}: {odds['team2']}")
    
    return "\n".join(message)
    # Section 6: Information sur les cotes si disponibles
    odds = prediction["odds"]
    if odds["team1"] and odds["team2"]:
        message.append("")
        message.append("*💰 COTES UTILISÉES:*")
        message.append(f"  • {team1}: {odds['team1']}")
        message.append(f"  • {team2}: {odds['team2']}")
    
    return "\n".join(message)
