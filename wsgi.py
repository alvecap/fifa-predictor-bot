"""
Point d'entrée WSGI pour le déploiement sur Render.com
"""

import os
import sys

# Assurez-vous que le répertoire du projet est dans sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importer l'application Flask depuis fifa_games.py
try:
    from fifa_games import main_webhook
    application = main_webhook()
except ImportError as e:
    print(f"Erreur lors de l'importation de l'application: {e}")
    # Si l'importation échoue, créer une application Flask simple pour indiquer l'erreur
    from flask import Flask, jsonify
    application = Flask(__name__)
    
    @application.route('/')
    def error_page():
        return f"Erreur lors de l'initialisation du bot: {str(e)}", 500
    
    @application.route('/health')
    def health_check():
        return jsonify({"status": "error", "message": str(e)})

# L'objet 'application' sera utilisé par Gunicorn
