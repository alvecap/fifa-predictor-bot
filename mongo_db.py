import os
import logging
from pymongo import MongoClient
from typing import Dict, List, Any, Optional
from datetime import datetime
from bson.objectid import ObjectId

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Connexion à MongoDB
def get_mongodb_uri():
    """Récupère l'URI de connexion MongoDB depuis les variables d'environnement"""
    uri = os.environ.get('MONGODB_URI')
    if uri is None:
        logger.warning("Variable d'environnement MONGODB_URI non trouvée. Utilisation de l'URI local par défaut.")
        return "mongodb://localhost:27017/fifa_predictor"
    return uri

def get_db_connection():
    """Établit une connexion à MongoDB Atlas"""
    try:
        uri = get_mongodb_uri()
        
        # Configuration minimaliste pour laisser l'URI gérer les paramètres
        client = MongoClient(uri)
        
        # Vérifier la connexion
        client.admin.command('ping')
        logger.info("Connexion à MongoDB établie avec succès")
        return client
    except Exception as e:
        logger.error(f"Erreur de connexion à MongoDB: {e}")
        return None

def get_database():
    """Récupère la base de données MongoDB"""
    client = get_db_connection()
    if client is None:
        return None
    
    # Le nom de la base de données est généralement inclus dans l'URI
    # Sinon, nous utilisons un nom par défaut
    db_name = os.environ.get('MONGODB_DB_NAME', 'fifa_predictor_db')
    return client[db_name]

# Fonctions pour les matchs
def get_all_matches_data() -> List[Dict[str, Any]]:
    """Récupère tous les matchs depuis MongoDB"""
    try:
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données")
            return []
        
        # Récupérer tous les matchs
        matches = list(db.matches.find({}))
        
        # Convertir les ObjectId en str pour la sérialisation
        for match in matches:
            if '_id' in match:
                match['_id'] = str(match['_id'])
        
        logger.info(f"Récupération de {len(matches)} matchs réussie")
        return matches
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des matchs: {e}")
        return []

def get_all_teams() -> List[str]:
    """Récupère la liste de toutes les équipes depuis les matchs"""
    try:
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données")
            return []
        
        # Récupérer toutes les équipes uniques (à domicile et à l'extérieur)
        home_teams = db.matches.distinct("team_home")
        away_teams = db.matches.distinct("team_away")
        
        # Fusionner et trier les équipes
        all_teams = sorted(list(set(home_teams + away_teams)))
        
        logger.info(f"Récupération de {len(all_teams)} équipes réussie")
        return all_teams
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des équipes: {e}")
        return []

def get_team_statistics(matches: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Calcule les statistiques pour chaque équipe"""
    team_stats = {}
    
    for match in matches:
        team_home = match.get('team_home', '')
        team_away = match.get('team_away', '')
        score_final = match.get('score_final', '')
        score_1ere = match.get('score_1ere', '')
        
        if not team_home or not team_away or not score_final:
            continue
        
        # Initialiser les équipes si nécessaire
        if team_home not in team_stats:
            team_stats[team_home] = {
                'home_matches': 0, 'away_matches': 0,
                'home_goals_for': [], 'home_goals_against': [],
                'away_goals_for': [], 'away_goals_against': [],
                'home_first_half': [], 'away_first_half': [],
                'home_wins': 0, 'home_losses': 0, 'home_draws': 0,
                'away_wins': 0, 'away_losses': 0, 'away_draws': 0
            }
        
        if team_away not in team_stats:
            team_stats[team_away] = {
                'home_matches': 0, 'away_matches': 0,
                'home_goals_for': [], 'home_goals_against': [],
                'away_goals_for': [], 'away_goals_against': [],
                'home_first_half': [], 'away_first_half': [],
                'home_wins': 0, 'home_losses': 0, 'home_draws': 0,
                'away_wins': 0, 'away_losses': 0, 'away_draws': 0
            }
        
        # Extraire les scores finaux
        try:
            score_parts = score_final.split(':')
            home_goals = int(score_parts[0])
            away_goals = int(score_parts[1])
            
            # Mettre à jour les statistiques domicile/extérieur
            team_stats[team_home]['home_matches'] += 1
            team_stats[team_home]['home_goals_for'].append(home_goals)
            team_stats[team_home]['home_goals_against'].append(away_goals)
            
            team_stats[team_away]['away_matches'] += 1
            team_stats[team_away]['away_goals_for'].append(away_goals)
            team_stats[team_away]['away_goals_against'].append(home_goals)
            
            # Déterminer le résultat
            if home_goals > away_goals:
                team_stats[team_home]['home_wins'] += 1
                team_stats[team_away]['away_losses'] += 1
            elif away_goals > home_goals:
                team_stats[team_home]['home_losses'] += 1
                team_stats[team_away]['away_wins'] += 1
            else:
                team_stats[team_home]['home_draws'] += 1
                team_stats[team_away]['away_draws'] += 1
        except (ValueError, IndexError):
            pass
        
        # Extraire les scores de première période
        if score_1ere:
            try:
                half_parts = score_1ere.split(':')
                half_home = int(half_parts[0])
                half_away = int(half_parts[1])
                
                # Stocker les scores de première période
                team_stats[team_home]['home_first_half'].append(f"{half_home}:{half_away}")
                team_stats[team_away]['away_first_half'].append(f"{half_home}:{half_away}")
            except (ValueError, IndexError):
                pass
    
    return team_stats

def get_match_id_trends(matches: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[str]]]:
    """Analyse les tendances par numéro de match"""
    from collections import defaultdict
    
    match_id_trends = defaultdict(lambda: {'final_scores': [], 'first_half_scores': []})
    
    for match in matches:
        match_id = match.get('match_id', '')
        score_final = match.get('score_final', '')
        score_1ere = match.get('score_1ere', '')
        
        if match_id and score_final:
            match_id_trends[match_id]['final_scores'].append(score_final)
        
        if match_id and score_1ere:
            match_id_trends[match_id]['first_half_scores'].append(score_1ere)
    
    return match_id_trends

def get_common_scores(scores_list, top_n=5):
    """Retourne les scores les plus communs avec leur fréquence"""
    from collections import Counter
    
    if not scores_list:
        return []
    
    counter = Counter(scores_list)
    total = len(scores_list)
    
    # Trier par fréquence et prendre les top_n plus fréquents
    most_common = counter.most_common(top_n)
    return [(score, count, round(count/total*100, 1)) for score, count in most_common]

def get_direct_confrontations(matches: List[Dict[str, Any]], team1: str, team2: str) -> List[Dict[str, Any]]:
    """Récupère l'historique des confrontations directes entre deux équipes"""
    confrontations = []
    
    for match in matches:
        home = match.get('team_home', '')
        away = match.get('team_away', '')
        
        # Vérifier si c'est une confrontation entre ces deux équipes
        if (home == team1 and away == team2) or (home == team2 and away == team1):
            confrontations.append(match)
    
    return confrontations

def save_prediction_log(user_id, username, team1, team2, odds1=None, odds2=None, prediction_result=None):
    """Enregistre les prédictions demandées par les utilisateurs"""
    try:
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données pour enregistrer la prédiction")
            logger.info(f"Prédiction non stockée pour {username} (ID: {user_id}): {team1} vs {team2}")
            return False
        
        # Créer l'entrée de log
        prediction_log = {
            "user_id": str(user_id),
            "username": username,
            "date": datetime.now().isoformat(),
            "team1": team1,
            "team2": team2,
            "odds1": float(odds1) if odds1 is not None else None,
            "odds2": float(odds2) if odds2 is not None else None,
            "prediction_result": prediction_result,
            "status": "success" if prediction_result and "error" not in prediction_result else "failed"
        }
        
        # Insérer dans la collection
        db.prediction_logs.insert_one(prediction_log)
        
        logger.info(f"Prédiction enregistrée pour {username} (ID: {user_id}): {team1} vs {team2}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de la prédiction: {e}")
        # Fallback - au moins logger l'événement
        logger.info(f"Prédiction non stockée pour {username} (ID: {user_id}): {team1} vs {team2}")
        return False

async def check_user_subscription(user_id):
    """
    Vérifie si un utilisateur est abonné au canal @alvecapitalofficiel.
    
    Args:
        user_id (int): L'ID de l'utilisateur Telegram à vérifier
        
    Returns:
        bool: True si l'utilisateur est abonné, False sinon
    """
    try:
        from telegram import Bot
        from telegram.error import TelegramError
        from config import TELEGRAM_TOKEN
        
        # Vérifier si c'est un admin
        from admin_access import is_admin
        if is_admin(user_id):
            logger.info(f"Vérification d'abonnement contournée pour l'admin (ID: {user_id})")
            return True
        
        bot = Bot(token=TELEGRAM_TOKEN)
        
        # Identifiant du canal @alvecapitalofficiel
        channel_id = "@alvecapitalofficiel"
        
        # Vérifier si l'utilisateur est membre du canal
        chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        
        # Les statuts qui indiquent une adhésion active au canal
        valid_statuses = ['creator', 'administrator', 'member']
        
        is_member = chat_member.status in valid_statuses
        logger.info(f"Utilisateur {user_id} est{'' if is_member else ' non'} abonné au canal {channel_id}")
        
        return is_member
    
    except TelegramError as e:
        logger.error(f"Erreur lors de la vérification de l'abonnement: {e}")
        return False
    except Exception as e:
        logger.error(f"Erreur générale lors de la vérification de l'abonnement: {e}")
        return False

# Fonctions pour les utilisateurs
async def register_user(user_id, username, referrer_id=None):
    """
    Enregistre ou met à jour un utilisateur dans la base de données.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str): Nom d'utilisateur Telegram
        referrer_id (int, optional): ID Telegram du parrain
    
    Returns:
        bool: True si l'opération a réussi, False sinon
    """
    try:
        from admin_access import is_admin
        
        # Vérifier si c'est un admin
        if is_admin(user_id, username):
            logger.info(f"Enregistrement d'un administrateur: {username} (ID: {user_id})")
            # Les admins n'ont pas besoin d'être enregistrés
            return True
            
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données pour enregistrer l'utilisateur")
            return False
        
        # Vérifier si l'utilisateur existe déjà
        existing_user = db.users.find_one({"user_id": str(user_id)})
        current_time = datetime.now().isoformat()
        
        if existing_user is not None:
            # Si l'utilisateur existe, mise à jour
            update_data = {
                "$set": {
                    "username": username or "Inconnu",
                    "last_activity": current_time
                }
            }
            
            # Si un parrain est spécifié et que l'utilisateur n'a pas déjà un parrain
            if referrer_id and referrer_id != user_id and (not existing_user.get("referred_by")):
                update_data["$set"]["referred_by"] = str(referrer_id)
                
                # Créer la relation de parrainage
                await create_referral_relationship(user_id, referrer_id)
            
            db.users.update_one({"user_id": str(user_id)}, update_data)
            logger.info(f"Utilisateur mis à jour: {username} (ID: {user_id})")
        else:
            # Si l'utilisateur n'existe pas, création
            new_user = {
                "user_id": str(user_id),
                "username": username or "Inconnu",
                "registration_date": current_time,
                "last_activity": current_time,
                "referred_by": str(referrer_id) if referrer_id and referrer_id != user_id else None
            }
            
            db.users.insert_one(new_user)
            logger.info(f"Nouvel utilisateur enregistré: {username} (ID: {user_id})")
            
            # Si un parrain est spécifié, créer la relation
            if referrer_id and referrer_id != user_id:
                await create_referral_relationship(user_id, referrer_id)
        
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de l'utilisateur: {e}")
        return False

async def create_referral_relationship(user_id, referrer_id):
    """
    Crée une relation de parrainage dans la base de données.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur parrainé
        referrer_id (int): ID Telegram du parrain
    """
    try:
        from admin_access import is_admin
        
        # Vérifier si un des utilisateurs est admin
        if is_admin(user_id) or is_admin(referrer_id):
            logger.info(f"Relation de parrainage impliquant un admin. ID Utilisateur: {user_id}, ID Parrain: {referrer_id}")
            # Les admins n'ont pas besoin de relations de parrainage
            return
            
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données pour créer un parrainage")
            return
        
        # Vérifier si la relation existe déjà
        existing_referral = db.referrals.find_one({
            "referrer_id": str(referrer_id),
            "referred_id": str(user_id)
        })
        
        if existing_referral is None:
            # Vérifier s'il n'y a pas de boucle de parrainage (A parraine B qui parraine A)
            reverse_relation = db.referrals.find_one({
                "referrer_id": str(user_id),
                "referred_id": str(referrer_id)
            })
            
            if reverse_relation is not None:
                logger.warning(f"Boucle de parrainage détectée: {user_id} et {referrer_id} se parrainent mutuellement")
                return
            
            # Vérifier si l'utilisateur est déjà parrainé par quelqu'un d'autre
            other_referrer = db.referrals.find_one({
                "referred_id": str(user_id)
            })
            
            if other_referrer is not None and other_referrer["referrer_id"] != str(referrer_id):
                logger.warning(f"L'utilisateur {user_id} est déjà parrainé par {other_referrer['referrer_id']}")
                return
            
            # Créer la relation de parrainage
            current_time = datetime.now().isoformat()
            new_referral = {
                "referrer_id": str(referrer_id),
                "referred_id": str(user_id),
                "date": current_time,
                "verified": False,
                "verification_date": None
            }
            
            db.referrals.insert_one(new_referral)
            logger.info(f"Relation de parrainage créée: Parrain {referrer_id} -> Filleul {user_id}")
            
            # Lancer la vérification d'abonnement en arrière-plan
            import asyncio
            asyncio.create_task(verify_and_update_referral(user_id, referrer_id))
        else:
            logger.info(f"Relation de parrainage déjà existante: {referrer_id} -> {user_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de la création de la relation de parrainage: {e}")

async def verify_and_update_referral(user_id, referrer_id):
    """
    Vérifie si l'utilisateur est abonné au canal et met à jour le statut de parrainage.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        referrer_id (int): ID Telegram du parrain
    """
    try:
        # Attendre 30 secondes avant de vérifier
        # Cela donne plus de temps à l'utilisateur pour s'abonner au canal
        import asyncio
        await asyncio.sleep(30)
        
        # Vérifier l'abonnement
        is_subscribed = await check_user_subscription(user_id)
        logger.info(f"Vérification d'abonnement pour user {user_id}: {is_subscribed}")
        
        if is_subscribed:
            db = get_database()
            if db is None:
                logger.error("Impossible de se connecter à la base de données pour vérifier un parrainage")
                return
            
            # Mettre à jour le statut de vérification
            current_time = datetime.now().isoformat()
            result = db.referrals.update_one(
                {
                    "referrer_id": str(referrer_id),
                    "referred_id": str(user_id)
                },
                {
                    "$set": {
                        "verified": True,
                        "verification_date": current_time
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Parrainage vérifié: {referrer_id} -> {user_id}")
                
                # Notification au parrain
                try:
                    from telegram import Bot
                    from config import TELEGRAM_TOKEN
                    
                    bot = Bot(token=TELEGRAM_TOKEN)
                    referral_count = await count_referrals(referrer_id)
                    
                    await bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 *Félicitations!* Un nouvel utilisateur a utilisé votre lien et s'est abonné au canal.\n\n"
                             f"Vous avez maintenant *{referral_count}/{await get_max_referrals()}* parrainages vérifiés.",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Erreur lors de l'envoi de la notification au parrain: {e}")
            else:
                logger.warning(f"Aucune mise à jour du statut de parrainage pour {referrer_id} -> {user_id}")
        else:
            logger.info(f"Utilisateur {user_id} non abonné, parrainage non vérifié")
    
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du parrainage: {e}")

async def has_completed_referrals(user_id, username=None):
    """
    Vérifie si l'utilisateur a atteint le nombre requis de parrainages.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        username (str, optional): Nom d'utilisateur Telegram pour vérification admin
        
    Returns:
        bool: True si l'utilisateur a complété ses parrainages ou est admin, False sinon
    """
    try:
        from admin_access import is_admin
        
        # Vérifier si c'est un admin
        if is_admin(user_id, username):
            logger.info(f"Vérification de parrainage contournée pour l'admin {username} (ID: {user_id})")
            return True
        
        referral_count = await count_referrals(user_id)
        max_referrals = await get_max_referrals()
        
        completed = referral_count >= max_referrals
        logger.info(f"Utilisateur {user_id} a {referral_count}/{max_referrals} parrainages - Statut: {'Complété' if completed else 'En cours'}")
        
        return completed
    except Exception as e:
        logger.error(f"Erreur lors de la vérification des parrainages: {e}")
        return False

async def count_referrals(user_id):
    """
    Compte le nombre de parrainages vérifiés pour un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        int: Le nombre de parrainages vérifiés
    """
    try:
        from admin_access import is_admin
        
        # Vérifier si c'est un admin
        if is_admin(user_id):
            logger.info(f"Comptage de parrainage contourné pour l'admin (ID: {user_id})")
            max_referrals = await get_max_referrals()
            return max_referrals
        
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données pour compter les parrainages")
            return 0
        
        # Compter les parrainages vérifiés
        count = db.referrals.count_documents({
            "referrer_id": str(user_id),
            "verified": True
        })
        
        return count
    
    except Exception as e:
        logger.error(f"Erreur lors du comptage des parrainages: {e}")
        return 0

async def get_referred_users(user_id):
    """
    Récupère la liste des utilisateurs parrainés par un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        
    Returns:
        list: Liste des utilisateurs parrainés avec leurs informations
    """
    try:
        from admin_access import is_admin
        
        # Vérifier si c'est un admin
        if is_admin(user_id):
            logger.info(f"Récupération des parrainages contournée pour l'admin (ID: {user_id})")
            return []
        
        db = get_database()
        if db is None:
            logger.error("Impossible de se connecter à la base de données pour récupérer les parrainages")
            return []
        
        # Récupérer les parrainages
        referrals = list(db.referrals.find({"referrer_id": str(user_id)}))
        
        referred_users = []
        for referral in referrals:
            referred_id = referral.get("referred_id")
            if referred_id:
                # Récupérer l'information de l'utilisateur parrainé
                user_info = db.users.find_one({"user_id": referred_id})
                
                username = "Inconnu"
                if user_info is not None and "username" in user_info:
                    username = user_info["username"]
                
                referred_users.append({
                    'id': referred_id,
                    'username': username,
                    'is_verified': referral.get("verified", False)
                })
        
        return referred_users
    
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des utilisateurs parrainés: {e}")
        return []

async def generate_referral_link(user_id, bot_username):
    """
    Génère un lien de parrainage pour un utilisateur.
    
    Args:
        user_id (int): ID Telegram de l'utilisateur
        bot_username (str): Nom d'utilisateur du bot
        
    Returns:
        str: Lien de parrainage
    """
    return f"https://t.me/{bot_username}?start=ref{user_id}"

async def get_max_referrals():
    """
    Récupère le nombre maximum de parrainages requis.
    
    Returns:
        int: Nombre maximum de parrainages requis
    """
    try:
        # Essayer d'importer depuis config
        from config import MAX_REFERRALS
        return MAX_REFERRALS
    except ImportError:
        try:
            # Essayer d'importer depuis config_supabase.py
            from config_supabase import MAX_REFERRALS
            return MAX_REFERRALS
        except ImportError:
            # Valeur par défaut si non disponible
            return 1

def get_referral_instructions():
    """
    Retourne les instructions pour qu'un parrainage soit validé.
    
    Returns:
        str: Message formaté avec les instructions
    """
    return (
        "*📋 Conditions pour qu'un parrainage soit validé:*\n\n"
        "1️⃣ *L'invité doit cliquer sur votre lien de parrainage*\n"
        "2️⃣ *L'invité doit démarrer le bot* avec la commande /start\n"
        "3️⃣ *L'invité doit s'abonner* au canal [AL VE CAPITAL](https://t.me/alvecapitalofficiel)\n\n"
        "_Note: Le parrainage sera automatiquement vérifié et validé une fois ces conditions remplies_"
    )
