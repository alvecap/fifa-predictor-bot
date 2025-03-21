from flask import Flask, request, jsonify
from flask_cors import CORS
from predictor import MatchPredictor
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialisation de l'application Flask
app = Flask(__name__)
# Permettre les requêtes CORS (important pour les applications web)
CORS(app)

# Initialiser le prédicteur une seule fois au démarrage de l'application
predictor = MatchPredictor()

@app.route('/predict', methods=['POST'])
def predict():
    """Endpoint pour générer une prédiction basée sur deux équipes et leurs cotes"""
    try:
        # Récupérer les données de la requête JSON
        data = request.json
        team1 = data.get('team1')
        team2 = data.get('team2')
        
        # Récupérer les cotes (optionnelles)
        odds1 = data.get('odds1')
        odds2 = data.get('odds2')
        
        # Convertir les cotes en float si elles sont fournies
        if odds1 is not None:
            odds1 = float(odds1)
        if odds2 is not None:
            odds2 = float(odds2)
            
        # Valider les données d'entrée
        if not team1 or not team2:
            return jsonify({'error': 'Les noms des équipes sont requis'}), 400
            
        # Générer la prédiction en utilisant votre fonction existante
        prediction = predictor.predict_match(team1, team2, odds1, odds2)
        
        if not prediction:
            return jsonify({'error': 'Impossible de générer une prédiction pour ces équipes'}), 404
            
        # Formater la réponse pour l'application web
        response = {
            'team1': team1,
            'team2': team2,
            'halfTimeScores': [],
            'fullTimeScores': [],
            'halfTimeWinner': {'team': '', 'probability': 0},
            'fullTimeWinner': {'team': '', 'probability': 0},
            'halfTimeGoals': {'line': 0, 'isOver': False, 'percentage': 0},
            'fullTimeGoals': {'line': 0, 'isOver': False, 'percentage': 0}
        }
        
        # Scores mi-temps
        if prediction.get('half_time_scores'):
            response['halfTimeScores'] = [
                {'score': score['score'], 'confidence': score['confidence']} 
                for score in prediction['half_time_scores']
            ]
        
        # Scores temps réglementaire
        if prediction.get('full_time_scores'):
            response['fullTimeScores'] = [
                {'score': score['score'], 'confidence': score['confidence']} 
                for score in prediction['full_time_scores']
            ]
        
        # Vainqueur mi-temps
        winner_ht = prediction.get('winner_half_time', {})
        if winner_ht:
            response['halfTimeWinner'] = {
                'team': winner_ht.get('team', ''),
                'probability': winner_ht.get('probability', 0)
            }
        
        # Vainqueur temps réglementaire
        winner_ft = prediction.get('winner_full_time', {})
        if winner_ft:
            response['fullTimeWinner'] = {
                'team': winner_ft.get('team', ''),
                'probability': winner_ft.get('probability', 0)
            }
        
        # Nombre de buts mi-temps
        avg_goals_ht = prediction.get('avg_goals_half_time', 0)
        line_ht = round(avg_goals_ht * 2) / 2  # Arrondir à 0.5 près
        response['halfTimeGoals'] = {
            'line': line_ht,
            'isOver': False if line_ht < 2 else True,  # Suggestion basée sur les tendances habituelles
            'percentage': 75 if line_ht < 2 else 60
        }
        
        # Nombre de buts temps réglementaire
        avg_goals_ft = prediction.get('avg_goals_full_time', 0)
        line_ft = round(avg_goals_ft * 2) / 2  # Arrondir à 0.5 près
        response['fullTimeGoals'] = {
            'line': line_ft,
            'isOver': True if line_ft < 3 else False,  # Suggestion basée sur les tendances habituelles
            'percentage': 70 if line_ft < 3 else 65
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Erreur lors de la génération de la prédiction: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/teams', methods=['GET'])
def get_teams():
    """Endpoint pour récupérer la liste des équipes disponibles"""
    try:
        from database import get_all_teams
        teams = get_all_teams()
        return jsonify({'teams': teams})
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des équipes: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
