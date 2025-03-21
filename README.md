# FIFA 4x4 Predictor Bot

Un bot Telegram qui fournit des prédictions précises pour les matchs FIFA 4x4 en utilisant l'analyse de données historiques.

## Fonctionnalités

- 🔮 Prédictions de scores précises basées sur l'intelligence artificielle
- 📊 Analyses statistiques détaillées des matchs
- 💰 Intégration des cotes pour des prédictions plus précises
- 📱 Interface utilisateur Web Telegram pour une expérience fluide
- 🔄 Mise à jour automatique des données

## Prérequis

- Python 3.9+
- Un compte Google pour Google Sheets
- Un token de bot Telegram (obtenu via [@BotFather](https://t.me/BotFather))

## Installation locale

1. Clonez ce dépôt:
   ```bash
   git clone https://github.com/username/fifa-predictor-bot.git
   cd fifa-predictor-bot
   ```

2. Installez les dépendances:
   ```bash
   pip install -r requirements.txt
   ```

3. Configurez les variables d'environnement:
   - Copiez `.env.example` vers `.env`
   - Mettez à jour les variables avec vos propres valeurs

4. Placez votre fichier `google_credentials.json` dans le répertoire racine.

5. Lancez le bot:
   ```bash
   python fifa_bot.py
   ```

## Déploiement sur Render

1. Connectez votre repository GitHub à Render.

2. Créez trois services en utilisant le fichier `render.yaml`:
   - Service API: pour l'API Flask
   - Service Worker: pour le bot Telegram
   - Service Statique: pour l'interface utilisateur Web

3. Définissez les variables d'environnement dans Render:
   - `TELEGRAM_TOKEN`: Votre token de bot Telegram
   - `GOOGLE_CREDENTIALS_JSON`: Le contenu de votre fichier google_credentials.json (encodé en base64)
   - `SPREADSHEET_ID`: L'ID de votre Google Sheet

## Structure du projet

- `fifa_bot.py`: Point d'entrée principal du bot Telegram
- `api.py`: API Flask pour l'interface Web
- `predictor.py`: Logique de prédiction des matchs
- `database.py`: Interaction avec Google Sheets
- `config.py`: Configuration et paramètres
- `index.html`, `app.js`: Interface utilisateur Web

## Structure de la base de données

Le bot utilise Google Sheets pour stocker et récupérer les données des matchs. La feuille de calcul doit avoir les colonnes suivantes:
- Match ID
- Équipe domicile
- Équipe extérieur
- Score final
- Score 1ère mi-temps

## Commandes disponibles

- `/start` - Démarrer le bot
- `/help` - Afficher l'aide
- `/predict [Équipe1] vs [Équipe2]` - Obtenir une prédiction pour un match
- `/odds [Équipe1] vs [Équipe2] [cote1] [cote2]` - Prédiction avec cotes
- `/teams` - Voir toutes les équipes disponibles
- `/check` - Vérifier l'abonnement au canal

## Contribution

Les contributions sont les bienvenues! N'hésitez pas à ouvrir une issue ou à soumettre une pull request.

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.
