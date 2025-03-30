import logging
import time
import json
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timedelta
import os

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Essayer d'importer Redis si disponible (optionnel)
REDIS_AVAILABLE = False
try:
    import redis
    REDIS_AVAILABLE = True
    logger.info("Redis est disponible et sera utilisé pour le cache")
except ImportError:
    logger.info("Redis n'est pas disponible, utilisation du cache en mémoire")

class Cache:
    """
    Système de cache centralisé qui supporte soit Redis soit un dictionnaire en mémoire.
    Permet de stocker et récupérer des données avec différentes durées d'expiration.
    """
    def __init__(self, use_redis=False, redis_url=None):
        """
        Initialise le cache.
        
        Args:
            use_redis (bool): Si True et Redis est disponible, utilise Redis
            redis_url (str, optional): URL Redis (redis://user:password@host:port/db)
        """
        self.use_redis = use_redis and REDIS_AVAILABLE
        self.redis_client = None
        self.memory_cache = {}  # Fallback pour le cache en mémoire
        self.last_cleanup = time.time()
        
        # Statistiques pour le monitoring
        self.stats = {
            "set_operations": 0,
            "get_operations": 0,
            "hits": 0,
            "misses": 0,
            "expired": 0,
            "cleanup_operations": 0
        }
        
        # Initialiser Redis si nécessaire
        if self.use_redis:
            try:
                # Si l'URL est fournie, utiliser celle-ci
                if redis_url:
                    self.redis_client = redis.from_url(redis_url)
                # Sinon, utiliser les variables d'environnement ou valeurs par défaut
                else:
                    self.redis_client = redis.Redis(
                        host=os.environ.get('REDIS_HOST', 'localhost'),
                        port=int(os.environ.get('REDIS_PORT', 6379)),
                        password=os.environ.get('REDIS_PASSWORD', ''),
                        db=int(os.environ.get('REDIS_DB', 0)),
                        socket_timeout=5,
                        socket_connect_timeout=5
                    )
                # Vérifier la connexion
                self.redis_client.ping()
                logger.info("Connexion au cache Redis établie avec succès")
            except Exception as e:
                logger.error(f"Erreur lors de la connexion à Redis: {e}")
                self.use_redis = False
                logger.warning("Retour au cache en mémoire")
    
    async def set(self, key: str, value: Any, expiration: int = 300) -> bool:
        """
        Stocke une valeur dans le cache avec une durée d'expiration.
        
        Args:
            key (str): Clé pour identifier la valeur
            value (Any): Valeur à stocker (doit être sérialisable en JSON)
            expiration (int): Durée d'expiration en secondes (défaut: 5 minutes)
            
        Returns:
            bool: True si l'opération a réussi
        """
        self.stats["set_operations"] += 1
        
        try:
            # Sérialiser la valeur en JSON
            serialized = json.dumps(value)
            
            if self.use_redis and self.redis_client:
                # Utiliser Redis avec expiration automatique
                self.redis_client.setex(key, expiration, serialized)
            else:
                # Utiliser le cache en mémoire
                self.memory_cache[key] = {
                    'value': serialized,
                    'expiration': time.time() + expiration
                }
                
                # Nettoyer le cache périodiquement (toutes les 100 opérations)
                if self.stats["set_operations"] % 100 == 0:
                    await self._cleanup_memory_cache()
            
            return True
        except Exception as e:
            logger.error(f"Erreur lors du stockage dans le cache: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Récupère une valeur du cache.
        
        Args:
            key (str): Clé de la valeur à récupérer
            
        Returns:
            Any: Valeur stockée ou None si non trouvée ou expirée
        """
        self.stats["get_operations"] += 1
        
        try:
            if self.use_redis and self.redis_client:
                # Récupérer depuis Redis
                data = self.redis_client.get(key)
                
                if data:
                    self.stats["hits"] += 1
                    return json.loads(data)
                else:
                    self.stats["misses"] += 1
                    return None
            else:
                # Récupérer depuis le cache en mémoire
                if key in self.memory_cache:
                    cached_item = self.memory_cache[key]
                    
                    # Vérifier si la valeur a expiré
                    if cached_item['expiration'] > time.time():
                        self.stats["hits"] += 1
                        return json.loads(cached_item['value'])
                    else:
                        # Supprimer l'entrée expirée
                        del self.memory_cache[key]
                        self.stats["expired"] += 1
                        self.stats["misses"] += 1
                        return None
                else:
                    self.stats["misses"] += 1
                    return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération depuis le cache: {e}")
            self.stats["misses"] += 1
            return None
    
    async def delete(self, key: str) -> bool:
        """
        Supprime une valeur du cache.
        
        Args:
            key (str): Clé de la valeur à supprimer
            
        Returns:
            bool: True si l'opération a réussi ou si la clé n'existait pas
        """
        try:
            if self.use_redis and self.redis_client:
                # Supprimer depuis Redis
                self.redis_client.delete(key)
            else:
                # Supprimer depuis le cache en mémoire
                if key in self.memory_cache:
                    del self.memory_cache[key]
            
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression depuis le cache: {e}")
            return False
    
    async def clear_all(self) -> bool:
        """
        Vide complètement le cache.
        
        Returns:
            bool: True si l'opération a réussi
        """
        try:
            if self.use_redis and self.redis_client:
                # Vider Redis (ATTENTION: cela supprime tout dans la DB Redis sélectionnée)
                self.redis_client.flushdb()
            else:
                # Vider le cache en mémoire
                self.memory_cache = {}
            
            # Réinitialiser les statistiques
            for key in self.stats:
                self.stats[key] = 0
                
            logger.info("Cache entièrement vidé")
            return True
        except Exception as e:
            logger.error(f"Erreur lors du vidage du cache: {e}")
            return False
    
    async def _cleanup_memory_cache(self) -> None:
        """Supprime les entrées expirées du cache en mémoire."""
        current_time = time.time()
        
        # Ne nettoyer que toutes les 60 secondes pour éviter trop de calculs
        if current_time - self.last_cleanup < 60:
            return
        
        self.last_cleanup = current_time
        self.stats["cleanup_operations"] += 1
        
        # Identifier les clés expirées
        expired_keys = [
            key for key, item in self.memory_cache.items()
            if item['expiration'] <= current_time
        ]
        
        # Supprimer les entrées expirées
        for key in expired_keys:
            del self.memory_cache[key]
            self.stats["expired"] += 1
        
        if expired_keys:
            logger.debug(f"Nettoyage du cache: {len(expired_keys)} entrées expirées supprimées")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Récupère les statistiques du cache.
        
        Returns:
            Dict[str, Any]: Statistiques du cache
        """
        stats = self.stats.copy()
        
        # Calculer le taux de succès du cache
        total_gets = stats["hits"] + stats["misses"]
        if total_gets > 0:
            stats["hit_rate"] = stats["hits"] / total_gets * 100
        else:
            stats["hit_rate"] = 0
        
        # Ajouter la taille du cache mémoire
        if not self.use_redis:
            stats["cache_size"] = len(self.memory_cache)
        
        return stats
    
    async def monitor_and_report(self, interval: int = 900) -> None:
        """
        Surveille le cache et rapporte les statistiques périodiquement.
        
        Args:
            interval (int): Intervalle entre les rapports en secondes (défaut: 15 minutes)
        """
        try:
            # Boucle infinie pour rapporter les statistiques
            while True:
                await asyncio.sleep(interval)
                
                # Nettoyer le cache si nécessaire
                if not self.use_redis:
                    await self._cleanup_memory_cache()
                
                # Journaliser les statistiques
                stats = self.get_stats()
                logger.info(f"Statistiques du cache: {json.dumps(stats)}")
                
                # Réinitialiser certaines statistiques
                self.stats["set_operations"] = 0
                self.stats["get_operations"] = 0
                self.stats["hits"] = 0
                self.stats["misses"] = 0
                self.stats["expired"] = 0
                self.stats["cleanup_operations"] = 0
                
        except asyncio.CancelledError:
            logger.info("Surveillance du cache arrêtée")
        except Exception as e:
            logger.error(f"Erreur lors de la surveillance du cache: {e}")

# Durées de cache prédéfinies pour différents types de données
CACHE_DURATIONS = {
    "subscription": 86400,   # 24 heures pour l'abonnement
    "referral": 3600,        # 1 heure pour les parrainages
    "teams": 86400,          # 24 heures pour les équipes (rarement modifiées)
    "matches": 86400,        # 24 heures pour les matchs (rarement modifiés)
    "prediction": 1800,      # 30 minutes pour les prédictions
    "user": 3600,            # 1 heure pour les données utilisateur
    "short": 300,            # 5 minutes pour les données à courte durée de vie
    "temporary": 60          # 1 minute pour les données très temporaires
}

# Initialiser l'instance du cache global
# Le Redis est utilisé si disponible et que REDIS_URL est défini
use_redis = REDIS_AVAILABLE and 'REDIS_URL' in os.environ
redis_url = os.environ.get('REDIS_URL') if use_redis else None

cache = Cache(use_redis=use_redis, redis_url=redis_url)

# Version async de set avec des préfixes par type de données
async def set_cached_data(data_type: str, key: str, value: Any, custom_expiration: int = None) -> bool:
    """
    Stocke une valeur dans le cache avec un préfixe pour le type de données.
    Utilise les durées d'expiration prédéfinies par type.
    
    Args:
        data_type (str): Type de données (ex: "subscription", "referral", etc.)
        key (str): Clé unique pour les données
        value (Any): Valeur à stocker
        custom_expiration (int, optional): Durée d'expiration personnalisée
        
    Returns:
        bool: True si l'opération a réussi
    """
    # Préfixer la clé avec le type de données
    cache_key = f"{data_type}:{key}"
    
    # Utiliser la durée d'expiration par défaut pour ce type ou la durée personnalisée
    expiration = custom_expiration or CACHE_DURATIONS.get(data_type, CACHE_DURATIONS["short"])
    
    return await cache.set(cache_key, value, expiration)

# Version async de get avec des préfixes par type de données
async def get_cached_data(data_type: str, key: str) -> Optional[Any]:
    """
    Récupère une valeur du cache avec un préfixe pour le type de données.
    
    Args:
        data_type (str): Type de données (ex: "subscription", "referral", etc.)
        key (str): Clé unique pour les données
        
    Returns:
        Any: Valeur stockée ou None si non trouvée
    """
    # Préfixer la clé avec le type de données
    cache_key = f"{data_type}:{key}"
    
    return await cache.get(cache_key)

# Fonctions d'aide pour les types de données spécifiques
async def cache_subscription_status(user_id: int, is_subscribed: bool) -> bool:
    """
    Cache le statut d'abonnement d'un utilisateur.
    
    Args:
        user_id (int): ID de l'utilisateur
        is_subscribed (bool): Si l'utilisateur est abonné
        
    Returns:
        bool: True si l'opération a réussi
    """
    return await set_cached_data("subscription", str(user_id), is_subscribed)

async def get_cached_subscription_status(user_id: int) -> Optional[bool]:
    """
    Récupère le statut d'abonnement d'un utilisateur depuis le cache.
    
    Args:
        user_id (int): ID de l'utilisateur
        
    Returns:
        bool: Statut d'abonnement ou None si non trouvé
    """
    return await get_cached_data("subscription", str(user_id))

async def cache_referral_count(user_id: int, count: int) -> bool:
    """
    Cache le nombre de parrainages d'un utilisateur.
    
    Args:
        user_id (int): ID de l'utilisateur
        count (int): Nombre de parrainages
        
    Returns:
        bool: True si l'opération a réussi
    """
    return await set_cached_data("referral", str(user_id), count)

async def get_cached_referral_count(user_id: int) -> Optional[int]:
    """
    Récupère le nombre de parrainages d'un utilisateur depuis le cache.
    
    Args:
        user_id (int): ID de l'utilisateur
        
    Returns:
        int: Nombre de parrainages ou None si non trouvé
    """
    return await get_cached_data("referral", str(user_id))

async def cache_prediction(team1: str, team2: str, odds1: Optional[float], odds2: Optional[float], prediction: Dict) -> bool:
    """
    Cache une prédiction pour un match.
    
    Args:
        team1 (str): Nom de l'équipe 1
        team2 (str): Nom de l'équipe 2
        odds1 (float, optional): Cote de l'équipe 1
        odds2 (float, optional): Cote de l'équipe 2
        prediction (Dict): Résultat de la prédiction
        
    Returns:
        bool: True si l'opération a réussi
    """
    # Créer une clé unique pour cette prédiction
    odds1_str = f"{odds1:.2f}" if odds1 is not None else "None"
    odds2_str = f"{odds2:.2f}" if odds2 is not None else "None"
    key = f"{team1}_{team2}_{odds1_str}_{odds2_str}"
    
    return await set_cached_data("prediction", key, prediction)

async def get_cached_prediction(team1: str, team2: str, odds1: Optional[float], odds2: Optional[float]) -> Optional[Dict]:
    """
    Récupère une prédiction depuis le cache.
    
    Args:
        team1 (str): Nom de l'équipe 1
        team2 (str): Nom de l'équipe 2
        odds1 (float, optional): Cote de l'équipe 1
        odds2 (float, optional): Cote de l'équipe 2
        
    Returns:
        Dict: Prédiction ou None si non trouvée
    """
    # Créer une clé unique pour cette prédiction
    odds1_str = f"{odds1:.2f}" if odds1 is not None else "None"
    odds2_str = f"{odds2:.2f}" if odds2 is not None else "None"
    key = f"{team1}_{team2}_{odds1_str}_{odds2_str}"
    
    return await get_cached_data("prediction", key)

async def cache_teams(teams: List[str]) -> bool:
    """
    Cache la liste des équipes.
    
    Args:
        teams (List[str]): Liste des équipes
        
    Returns:
        bool: True si l'opération a réussi
    """
    return await set_cached_data("teams", "all", teams)

async def get_cached_teams() -> Optional[List[str]]:
    """
    Récupère la liste des équipes depuis le cache.
    
    Returns:
        List[str]: Liste des équipes ou None si non trouvée
    """
    return await get_cached_data("teams", "all")

async def cache_matches(matches: List[Dict]) -> bool:
    """
    Cache la liste des matchs.
    
    Args:
        matches (List[Dict]): Liste des matchs
        
    Returns:
        bool: True si l'opération a réussi
    """
    return await set_cached_data("matches", "all", matches)

async def get_cached_matches() -> Optional[List[Dict]]:
    """
    Récupère la liste des matchs depuis le cache.
    
    Returns:
        List[Dict]: Liste des matchs ou None si non trouvée
    """
    return await get_cached_data("matches", "all")

# Fonction pour démarrer la surveillance du cache
async def start_cache_monitoring():
    """Démarre la surveillance et le rapport des statistiques du cache."""
    monitoring_task = asyncio.create_task(cache.monitor_and_report())
    return monitoring_task
