import os
import logging
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from pymongo import MongoClient
import time

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration Google Sheets
def get_google_credentials():
    """Récupère les credentials Google Sheets"""
    try:
        # Pour le déploiement, nous pouvons recevoir les credentials sous forme de JSON string
        google_creds = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if google_creds is not None:
            import tempfile
            from pathlib import Path
            # Créer un fichier temporaire pour stocker les credentials
            temp_dir = tempfile.gettempdir()
            credentials_file = Path(temp_dir) / "google_credentials.json"
            with open(credentials_file, 'w') as f:
                f.write(google_creds)
            return str(credentials_file)
        else:
            # En local, utilise le fichier
            return 'google_credentials.json'
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des credentials Google: {e}")
        return None

def connect_to_sheets():
    """Établit la connexion avec Google Sheets"""
    try:
        credentials_file = get_google_credentials()
        if credentials_file is None:
            logger.error("Impossible de récupérer les credentials Google")
            return None
            
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
        client = gspread.authorize(credentials)
        
        spreadsheet_id = os.environ.get('SPREADSHEET_ID', '')
        if not spreadsheet_id:
            logger.error("ID de spreadsheet non trouvé dans les variables d'environnement")
            return None
            
        return client.open_by_key(spreadsheet_id)
    except Exception as e:
        logger.error(f"Erreur de connexion à Google Sheets: {e}")
        return None

# Configuration MongoDB
def get_mongodb_uri():
    """Récupère l'URI de connexion MongoDB depuis les variables d'environnement"""
    uri = os.environ.get('MONGODB_URI')
    if uri is None:
        logger.warning("Variable d'environnement MONGODB_URI non trouvée")
        return None
    return uri

def connect_to_mongodb():
    """Établit une connexion à la base de données MongoDB"""
    try:
        uri = get_mongodb_uri()
        if uri is None:
            logger.error("URI MongoDB non trouvé")
            return None
            
        client = MongoClient(uri)
        # Vérifier la connexion
        client.admin.command('ping')
        logger.info("Connexion à MongoDB établie avec succès")
        
        # Le nom de la base de données est généralement inclus dans l'URI
        # Sinon, nous utilisons un nom par défaut
        db_name = os.environ.get('MONGODB_DB_NAME', 'fifa_predictor_db')
        return client[db_name]
    except Exception as e:
        logger.error(f"Erreur de connexion à MongoDB: {e}")
        return None

def migrate_matches(spreadsheet, db):
    """Migre les données des matchs de Google Sheets vers MongoDB"""
    try:
        logger.info("Migration des données de matchs...")
        # Récupérer la feuille principale
        main_sheet = spreadsheet.worksheet("Tous les matchs")
        
        # Récupérer toutes les valeurs brutes
        all_values = main_sheet.get_all_values()
        
        # Déterminer la ligne d'en-tête (ligne 3 normalement)
        header_row_index = 2  # 0-based index pour la ligne 3
        
        # S'assurer qu'il y a assez de lignes
        if len(all_values) <= header_row_index:
            logger.warning("Pas assez de données dans la feuille des matchs")
            return 0
        
        # Récupérer les en-têtes
        headers = all_values[header_row_index]
        
        # Créer l'index des colonnes importantes
        column_indices = {
            'match_id': next((i for i, h in enumerate(headers) if 'Match ID' in h or 'match' in h.lower()), None),
            'team_home': next((i for i, h in enumerate(headers) if 'Domicile' in h), None),
            'team_away': next((i for i, h in enumerate(headers) if 'Extérieur' in h), None),
            'score_final': next((i for i, h in enumerate(headers) if 'Final' in h), None),
            'score_1ere': next((i for i, h in enumerate(headers) if '1ère' in h or '1ere' in h), None)
        }
        
        # Vérifier que les colonnes essentielles sont présentes
        missing_columns = [k for k, v in column_indices.items() if v is None]
        if missing_columns:
            logger.warning(f"Colonnes manquantes: {missing_columns}")
            logger.warning(f"En-têtes disponibles: {headers}")
            return 0
        
        # Supprimer les matchs existants pour éviter les doublons
        db.matches.delete_many({})
        
        # Extraire et insérer les données
        matches = []
        for i in range(header_row_index + 1, len(all_values)):
            row = all_values[i]
            if len(row) <= max(column_indices.values()):
                continue  # Ignorer les lignes trop courtes
            
            match = {
                'match_id': row[column_indices['match_id']] if column_indices['match_id'] < len(row) else '',
                'team_home': row[column_indices['team_home']] if column_indices['team_home'] < len(row) else '',
                'team_away': row[column_indices['team_away']] if column_indices['team_away'] < len(row) else '',
                'score_final': row[column_indices['score_final']] if column_indices['score_final'] < len(row) else '',
                'score_1ere': row[column_indices['score_1ere']] if column_indices['score_1ere'] < len(row) else ''
            }
            
            if match['team_home'] and match['team_away']:
                matches.append(match)
        
        # Insertion par lots pour de meilleures performances
        if matches:
            db.matches.insert_many(matches)
            
        logger.info(f"Migration de {len(matches)} matchs réussie")
        return len(matches)
    except Exception as e:
        logger.error(f"Erreur lors de la migration des matchs: {e}")
        return 0

def migrate_team_stats(spreadsheet, db):
    """Migre les statistiques des équipes de Google Sheets vers MongoDB"""
    try:
        logger.info("Migration des statistiques d'équipes...")
        
        try:
            stats_sheet = spreadsheet.worksheet("Statistiques")
        except gspread.exceptions.WorksheetNotFound:
            logger.warning("Feuille 'Statistiques' non trouvée, aucune donnée à migrer")
            return 0
        
        # Récupérer toutes les valeurs
        all_values = stats_sheet.get_all_values()
        
        # Vérifier qu'il y a au moins une ligne d'en-tête
        if len(all_values) < 1:
            logger.warning("Aucune donnée dans la feuille 'Statistiques'")
            return 0
        
        # Récupérer les en-têtes
        headers = all_values[0]
        
        # Supprimer les statistiques existantes pour éviter les doublons
        db.team_stats.delete_many({})
        
        # Extraire et insérer les données
        stats_list = []
        for i in range(1, len(all_values)):  # Commencer à 1 pour ignorer l'en-tête
            row = all_values[i]
            if len(row) < len(headers):
                continue  # Ignorer les lignes trop courtes
            
            # Créer un dictionnaire avec toutes les colonnes
            stat_entry = {}
            for j, header in enumerate(headers):
                if j < len(row):
                    # Essayer de convertir en nombre si possible
                    try:
                        if '.' in row[j]:
                            stat_entry[header] = float(row[j])
                        elif row[j].isdigit():
                            stat_entry[header] = int(row[j])
                        else:
                            stat_entry[header] = row[j]
                    except (ValueError, TypeError):
                        stat_entry[header] = row[j]
            
            # Ajouter seulement si on a des données significatives
            if stat_entry and any(stat_entry.values()):
                stats_list.append(stat_entry)
        
        # Insertion par lots
        if stats_list:
            db.team_stats.insert_many(stats_list)
            
        logger.info(f"Migration de {len(stats_list)} entrées de statistiques réussie")
        return len(stats_list)
    except Exception as e:
        logger.error(f"Erreur lors de la migration des statistiques: {e}")
        return 0

def migrate_trends(spreadsheet, db):
    """Migre les tendances de Google Sheets vers MongoDB"""
    try:
        logger.info("Migration des tendances...")
        
        try:
            trends_sheet = spreadsheet.worksheet("Tendances")
        except gspread.exceptions.WorksheetNotFound:
            logger.warning("Feuille 'Tendances' non trouvée, aucune donnée à migrer")
            return 0
        
        # Récupérer toutes les valeurs
        all_values = trends_sheet.get_all_values()
        
        # Vérifier qu'il y a au moins une ligne d'en-tête
        if len(all_values) < 1:
            logger.warning("Aucune donnée dans la feuille 'Tendances'")
            return 0
        
        # Récupérer les en-têtes
        headers = all_values[0]
        
        # Supprimer les tendances existantes pour éviter les doublons
        db.trends.delete_many({})
        
        # Extraire et insérer les données
        trends_list = []
        for i in range(1, len(all_values)):  # Commencer à 1 pour ignorer l'en-tête
            row = all_values[i]
            if len(row) < len(headers):
                continue  # Ignorer les lignes trop courtes
            
            # Créer un dictionnaire avec toutes les colonnes
            trend_entry = {}
            for j, header in enumerate(headers):
                if j < len(row):
                    # Essayer de convertir en nombre si possible
                    try:
                        if '.' in row[j]:
                            trend_entry[header] = float(row[j])
                        elif row[j].isdigit():
                            trend_entry[header] = int(row[j])
                        else:
                            trend_entry[header] = row[j]
                    except (ValueError, TypeError):
                        trend_entry[header] = row[j]
            
            # Ajouter seulement si on a des données significatives
            if trend_entry and any(trend_entry.values()):
                trends_list.append(trend_entry)
        
        # Insertion par lots
        if trends_list:
            db.trends.insert_many(trends_list)
            
        logger.info(f"Migration de {len(trends_list)} entrées de tendances réussie")
        return len(trends_list)
    except Exception as e:
        logger.error(f"Erreur lors de la migration des tendances: {e}")
        return 0

def migrate_users(spreadsheet, db):
    """Migre les données des utilisateurs de Google Sheets vers MongoDB"""
    try:
        logger.info("Migration des données utilisateurs...")
        
        try:
            users_sheet = spreadsheet.worksheet("Utilisateurs")
        except gspread.exceptions.WorksheetNotFound:
            logger.warning("Feuille 'Utilisateurs' non trouvée, aucune donnée à migrer")
            return 0
        
        # Récupérer toutes les valeurs
        all_values = users_sheet.get_all_values()
        
        # Vérifier qu'il y a au moins une ligne d'en-tête
        if len(all_values) < 1:
            logger.warning("Aucune donnée dans la feuille 'Utilisateurs'")
            return 0
        
        # S'assurer que les en-têtes correspondent à ce que nous attendons
        headers = all_values[0]
        
        # Adapter selon les en-têtes détectés
        expected_headers_options = [
            ['ID Telegram', 'Username', 'Date d\'inscription', 'Dernière activité', 'Parrainé par'],
            ['ID', 'Username', 'Date inscription', 'Parrain ID', 'Parrainages', 'Dernier accès']
        ]
        
        # Mapper les indices de colonnes de manière dynamique
        column_indices = {}
        
        # Vérifier quel ensemble d'en-têtes correspond le mieux
        best_match_count = 0
        best_match_index = 0
        
        for i, expected_set in enumerate(expected_headers_options):
            match_count = sum(1 for header in expected_set if header in headers)
            if match_count > best_match_count:
                best_match_count = match_count
                best_match_index = i
        
        # Utiliser le meilleur ensemble d'en-têtes
        expected_headers = expected_headers_options[best_match_index]
        
        # Informer de la correspondance
        logger.info(f"Utilisation de l'ensemble d'en-têtes {best_match_index+1}: {expected_headers}")
        
        # Correspondance détectée avec le premier ensemble (format original)
        if best_match_index == 0:
            column_indices = {
                'user_id': headers.index('ID Telegram') if 'ID Telegram' in headers else None,
                'username': headers.index('Username') if 'Username' in headers else None,
                'registration_date': headers.index('Date d\'inscription') if 'Date d\'inscription' in headers else None,
                'last_activity': headers.index('Dernière activité') if 'Dernière activité' in headers else None,
                'referred_by': headers.index('Parrainé par') if 'Parrainé par' in headers else None
            }
        # Correspondance avec le deuxième ensemble (format actuel)
        elif best_match_index == 1:
            column_indices = {
                'user_id': headers.index('ID') if 'ID' in headers else None,
                'username': headers.index('Username') if 'Username' in headers else None,
                'registration_date': headers.index('Date inscription') if 'Date inscription' in headers else None,
                'referred_by': headers.index('Parrain ID') if 'Parrain ID' in headers else None,
                'referrals_count': headers.index('Parrainages') if 'Parrainages' in headers else None,
                'last_activity': headers.index('Dernier accès') if 'Dernier accès' in headers else None
            }
        
        # Vérifier les colonnes manquantes
        missing_columns = [k for k, v in column_indices.items() if v is None]
        if missing_columns:
            logger.warning(f"Colonnes utilisateur manquantes: {missing_columns}")
        
        # Supprimer les utilisateurs existants pour éviter les doublons
        db.users.delete_many({})
        
        # Extraire et insérer les données
        users = []
        for i in range(1, len(all_values)):  # Commencer à 1 pour ignorer l'en-tête
            row = all_values[i]
            if len(row) < max([v for v in column_indices.values() if v is not None]):
                continue  # Ignorer les lignes trop courtes
            
            user = {}
            
            # Ajouter les champs disponibles
            for field, index in column_indices.items():
                if index is not None and index < len(row):
                    user[field] = row[index]
            
            # S'assurer que l'ID utilisateur n'est pas vide
            if user.get('user_id'):
                users.append(user)
        
        # Insertion par lots
        if users:
            db.users.insert_many(users)
            
        logger.info(f"Migration de {len(users)} utilisateurs réussie")
        return len(users)
    except Exception as e:
        logger.error(f"Erreur lors de la migration des utilisateurs: {e}")
        return 0

def migrate_referrals(spreadsheet, db):
    """Migre les données des parrainages de Google Sheets vers MongoDB"""
    try:
        logger.info("Migration des données de parrainages...")
        
        try:
            referrals_sheet = spreadsheet.worksheet("Parrainages")
        except gspread.exceptions.WorksheetNotFound:
            # Essayer un nom alternatif
            try:
                referrals_sheet = spreadsheet.worksheet("Parrainage")
            except gspread.exceptions.WorksheetNotFound:
                logger.warning("Feuille 'Parrainages' ou 'Parrainage' non trouvée, aucune donnée à migrer")
                # Création d'une structure vide pour les parrainages
                db.referrals.delete_many({})
                logger.info("Structure de parrainage créée sans données")
                return 0
        
        # Récupérer toutes les valeurs
        all_values = referrals_sheet.get_all_values()
        
        # Vérifier qu'il y a au moins une ligne d'en-tête
        if len(all_values) < 1:
            logger.warning("Aucune donnée dans la feuille 'Parrainages'")
            return 0
        
        # Récupérer les en-têtes
        headers = all_values[0]
        
        # Options d'en-têtes possibles
        expected_headers_options = [
            ['Parrain ID', 'Filleul ID', 'Date', 'Vérifié', 'Date de vérification'],
            ['Referrer ID', 'Referred ID', 'Date', 'Verified', 'Verification Date']
        ]
        
        # Trouver la meilleure correspondance
        best_match_count = 0
        best_match_index = 0
        
        for i, expected_set in enumerate(expected_headers_options):
            match_count = sum(1 for header in expected_set if header in headers)
            if match_count > best_match_count:
                best_match_count = match_count
                best_match_index = i
        
        # Utiliser le meilleur ensemble d'en-têtes
        expected_headers = expected_headers_options[best_match_index]
        logger.info(f"Utilisation de l'ensemble d'en-têtes parrainages {best_match_index+1}: {expected_headers}")
        
        # Mapper les indices de colonnes
        column_indices = {}
        
        # Format français
        if best_match_index == 0:
            column_indices = {
                'referrer_id': headers.index('Parrain ID') if 'Parrain ID' in headers else None,
                'referred_id': headers.index('Filleul ID') if 'Filleul ID' in headers else None,
                'date': headers.index('Date') if 'Date' in headers else None,
                'verified': headers.index('Vérifié') if 'Vérifié' in headers else None,
                'verification_date': headers.index('Date de vérification') if 'Date de vérification' in headers else None
            }
        # Format anglais
        else:
            column_indices = {
                'referrer_id': headers.index('Referrer ID') if 'Referrer ID' in headers else None,
                'referred_id': headers.index('Referred ID') if 'Referred ID' in headers else None,
                'date': headers.index('Date') if 'Date' in headers else None,
                'verified': headers.index('Verified') if 'Verified' in headers else None,
                'verification_date': headers.index('Verification Date') if 'Verification Date' in headers else None
            }
        
        # Vérifier les colonnes manquantes
        missing_columns = [k for k, v in column_indices.items() if v is None]
        if missing_columns:
            logger.warning(f"Colonnes parrainage manquantes: {missing_columns}")
        
        # Supprimer les parrainages existants pour éviter les doublons
        db.referrals.delete_many({})
        
        # Extraire et insérer les données
        referrals = []
        for i in range(1, len(all_values)):  # Commencer à 1 pour ignorer l'en-tête
            row = all_values[i]
            max_index = max([v for v in column_indices.values() if v is not None], default=0)
            if len(row) <= max_index:
                continue  # Ignorer les lignes trop courtes
            
            referral = {}
            
            # Ajouter les champs disponibles
            for field, index in column_indices.items():
                if index is not None and index < len(row):
                    if field == 'verified':
                        # Convertir les différentes façons d'exprimer "vérifié"
                        value = row[index].lower()
                        referral[field] = value in ['oui', 'yes', 'true', '1', 'vrai']
                    else:
                        referral[field] = row[index]
            
            # S'assurer que les IDs ne sont pas vides
            if referral.get('referrer_id') and referral.get('referred_id'):
                referrals.append(referral)
        
        # Insertion par lots
        if referrals:
            db.referrals.insert_many(referrals)
            
        logger.info(f"Migration de {len(referrals)} parrainages réussie")
        return len(referrals)
    except Exception as e:
        logger.error(f"Erreur lors de la migration des parrainages: {e}")
        return 0

def migrate_prediction_logs(spreadsheet, db):
    """Migre les logs de prédictions de Google Sheets vers MongoDB"""
    try:
        logger.info("Migration des logs de prédictions...")
        
        try:
            logs_sheet = spreadsheet.worksheet("Logs des prédictions")
        except gspread.exceptions.WorksheetNotFound:
            logger.warning("Feuille 'Logs des prédictions' non trouvée, aucune donnée à migrer")
            return 0
        
        # Récupérer toutes les valeurs
        all_values = logs_sheet.get_all_values()
        
        # Vérifier qu'il y a au moins une ligne d'en-tête
        if len(all_values) < 1:
            logger.warning("Aucune donnée dans la feuille 'Logs des prédictions'")
            return 0
        
        # S'assurer que les en-têtes correspondent à ce que nous attendons
        headers = all_values[0]
        expected_headers = ['Date', 'User ID', 'Username', 'Équipe 1', 'Équipe 2', 'Cote 1', 'Cote 2', 'Résultats prédits', 'Statut']
        
        # Vérifier que les colonnes attendues sont présentes
        columns_found = all([header in headers for header in expected_headers])
        if not columns_found:
            logger.warning(f"Les en-têtes ne correspondent pas. Attendu: {expected_headers}, Trouvé: {headers}")
        
        # Mapper les indices de colonnes
        column_indices = {
            'date': headers.index('Date') if 'Date' in headers else 0,
            'user_id': headers.index('User ID') if 'User ID' in headers else 1,
            'username': headers.index('Username') if 'Username' in headers else 2,
            'team1': headers.index('Équipe 1') if 'Équipe 1' in headers else 3,
            'team2': headers.index('Équipe 2') if 'Équipe 2' in headers else 4,
            'odds1': headers.index('Cote 1') if 'Cote 1' in headers else 5,
            'odds2': headers.index('Cote 2') if 'Cote 2' in headers else 6,
            'prediction_result': headers.index('Résultats prédits') if 'Résultats prédits' in headers else 7,
            'status': headers.index('Statut') if 'Statut' in headers else 8
        }
        
        # Supprimer les logs existants pour éviter les doublons
        db.prediction_logs.delete_many({})
        
        # Extraire et insérer les données
        logs = []
        for i in range(1, len(all_values)):  # Commencer à 1 pour ignorer l'en-tête
            row = all_values[i]
            if len(row) <= max(column_indices.values()):
                continue  # Ignorer les lignes trop courtes
            
            log = {
                'date': row[column_indices['date']],
                'user_id': row[column_indices['user_id']],
                'username': row[column_indices['username']],
                'team1': row[column_indices['team1']],
                'team2': row[column_indices['team2']],
                'odds1': row[column_indices['odds1']],
                'odds2': row[column_indices['odds2']],
                'prediction_result': row[column_indices['prediction_result']],
                'status': row[column_indices['status']]
            }
            
            if log['user_id'] and log['date']:  # S'assurer que les infos essentielles ne sont pas vides
                logs.append(log)
        
        # Insertion par lots
        if logs:
            db.prediction_logs.insert_many(logs)
            
        logger.info(f"Migration de {len(logs)} logs de prédictions réussie")
        return len(logs)
    except Exception as e:
        logger.error(f"Erreur lors de la migration des logs de prédictions: {e}")
        return 0

def create_indexes(db):
    """Crée les index nécessaires pour optimiser les requêtes"""
    try:
        logger.info("Création des index dans MongoDB...")
        
        # Index pour les matchs
        db.matches.create_index("match_id")
        db.matches.create_index("team_home")
        db.matches.create_index("team_away")
        
        # Index pour les statistiques
        if "team_stats" in db.list_collection_names():
            # Supposons qu'il y a un champ 'team' qui identifie l'équipe
            for field in ["team", "équipe", "name", "nom"]:
                try:
                    # Vérifier si le champ existe
                    if db.team_stats.count_documents({field: {"$exists": True}}) > 0:
                        db.team_stats.create_index(field)
                        break
                except:
                    pass
        
        # Index pour les tendances
        if "trends" in db.list_collection_names():
            # Supposons qu'il y a un champ 'trend_type' ou 'category'
            for field in ["trend_type", "category", "type", "catégorie"]:
                try:
                    # Vérifier si le champ existe
                    if db.trends.count_documents({field: {"$exists": True}}) > 0:
                        db.trends.create_index(field)
                        break
                except:
                    pass
        
        # Index pour les utilisateurs
        db.users.create_index("user_id", unique=True)
        db.users.create_index("username")
        db.users.create_index("referred_by")
        
        # Index pour les parrainages
        db.referrals.create_index([("referrer_id", 1), ("referred_id", 1)], unique=True)
        db.referrals.create_index("verified")
        
        # Index pour les logs de prédictions
        db.prediction_logs.create_index("user_id")
        db.prediction_logs.create_index("date")
        
        logger.info("Création des index terminée avec succès")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la création des index: {e}")
        return False

def main():
    """Fonction principale pour exécuter la migration"""
    try:
        logger.info("Démarrage de la migration Google Sheets vers MongoDB...")
        
        # Se connecter à Google Sheets
        spreadsheet = connect_to_sheets()
        if spreadsheet is None:
            logger.error("Impossible de se connecter à Google Sheets, arrêt de la migration")
            return False
        
        # Se connecter à MongoDB
        db = connect_to_mongodb()
        if db is None:
            logger.error("Impossible de se connecter à MongoDB, arrêt de la migration")
            return False
        
        # Migrer les données
total_matches = migrate_matches(spreadsheet, db)
total_stats = migrate_team_stats(spreadsheet, db)
total_trends = migrate_trends(spreadsheet, db)
total_users = migrate_users(spreadsheet, db)
total_referrals = migrate_referrals(spreadsheet, db)
total_logs = migrate_prediction_logs(spreadsheet, db)

# Créer les index
create_indexes(db)

# Résumé de la migration
logger.info("=== Résumé de la migration ===")
logger.info(f"Matchs migrés: {total_matches}")
logger.info(f"Statistiques d'équipes migrées: {total_stats}")
logger.info(f"Tendances migrées: {total_trends}")
logger.info(f"Utilisateurs migrés: {total_users}")
logger.info(f"Parrainages migrés: {total_referrals}")
logger.info(f"Logs de prédictions migrés: {total_logs}")
logger.info("Migration terminée avec succès!")

return True
except Exception as e:
    logger.error(f"Erreur lors de la migration: {e}")
    return False

if __name__ == "__main__":
    # Exécuter la migration
    success = main()
    if success:
        logger.info("Migration terminée avec succès!")
    else:
        logger.error("La migration a échoué.")
