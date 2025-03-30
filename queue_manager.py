import logging
import asyncio
import time
from typing import Dict, List, Any, Callable, Optional, Tuple
from collections import deque
from telegram import Bot, Message, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class QueueManager:
    """
    Gestionnaire centralisé des files d'attente pour les requêtes API Telegram.
    Permet de contrôler le débit des requêtes et d'informer les utilisateurs de leur position.
    """
    def __init__(self, max_requests_per_second: int = 28):
        """
        Initialise le gestionnaire de file d'attente.
        
        Args:
            max_requests_per_second (int): Nombre maximal de requêtes par seconde (limite conservative)
        """
        self.max_requests_per_second = max_requests_per_second
        self.high_priority_queue = deque()  # Réponses directes aux commandes
        self.medium_priority_queue = deque() # Prédictions et résultats de jeux
        self.low_priority_queue = deque()   # Vérifications d'abonnement et parrainage
        
        self.last_process_time = time.time()
        self.processed_requests = 0
        self.request_times = deque(maxlen=100)  # Pour calculer le temps moyen par requête
        
        self.running = False
        self.processor_task = None
        
        # Métriques
        self.metrics = {
            "total_requests": 0,
            "high_priority_processed": 0,
            "medium_priority_processed": 0,
            "low_priority_processed": 0,
            "max_queue_length": 0,
            "avg_wait_time": 0,
            "total_wait_time": 0,
            "total_waiting_requests": 0
        }
        
        # Mapping des utilisateurs en attente et leurs notifications
        self.waiting_users = {}  # {user_id: {"message": message_obj, "last_notification": timestamp}}
    
    async def start(self):
        """Démarre le processeur de file d'attente."""
        if self.running:
            return
            
        self.running = True
        self.processor_task = asyncio.create_task(self._process_queue())
        logger.info(f"Gestionnaire de file d'attente démarré (max {self.max_requests_per_second} req/s)")
    
    async def stop(self):
        """Arrête le processeur de file d'attente."""
        self.running = False
        if self.processor_task:
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass
        logger.info("Gestionnaire de file d'attente arrêté")
    
    def add_high_priority(self, func: Callable, *args, **kwargs) -> asyncio.Future:
        """
        Ajoute une requête haute priorité à la file d'attente.
        
        Args:
            func: Fonction à exécuter
            *args, **kwargs: Arguments pour la fonction
            
        Returns:
            asyncio.Future: Future qui sera résolue avec le résultat de la fonction
        """
        future = asyncio.Future()
        entry = {
            "func": func,
            "args": args,
            "kwargs": kwargs,
            "future": future,
            "timestamp": time.time(),
            "user_id": kwargs.get("user_id"),
            "message": kwargs.get("message")
        }
        self.high_priority_queue.append(entry)
        self._update_metrics()
        return future
    
    def add_medium_priority(self, func: Callable, *args, **kwargs) -> asyncio.Future:
        """Ajoute une requête de priorité moyenne à la file d'attente."""
        future = asyncio.Future()
        entry = {
            "func": func,
            "args": args,
            "kwargs": kwargs,
            "future": future,
            "timestamp": time.time(),
            "user_id": kwargs.get("user_id"),
            "message": kwargs.get("message")
        }
        self.medium_priority_queue.append(entry)
        self._update_metrics()
        
        # Notifier l'utilisateur s'il est en attente et si un message peut être envoyé
        user_id = kwargs.get("user_id")
        message = kwargs.get("message")
        
        if user_id and message:
            asyncio.create_task(self._notify_user_queue_position(user_id, message))
            
        return future
    
    def add_low_priority(self, func: Callable, *args, **kwargs) -> asyncio.Future:
        """Ajoute une requête basse priorité à la file d'attente."""
        future = asyncio.Future()
        entry = {
            "func": func,
            "args": args,
            "kwargs": kwargs,
            "future": future,
            "timestamp": time.time(),
            "user_id": kwargs.get("user_id"),
            "message": kwargs.get("message")
        }
        self.low_priority_queue.append(entry)
        self._update_metrics()
        return future
    
    async def _process_queue(self):
        """Traite les files d'attente en respectant les limites de débit."""
        while self.running:
            current_time = time.time()
            elapsed = current_time - self.last_process_time
            
            # Reset le compteur chaque seconde
            if elapsed >= 1.0:
                self.processed_requests = 0
                self.last_process_time = current_time
            
            # Vérifier si on peut traiter plus de requêtes
            if self.processed_requests < self.max_requests_per_second:
                # Sélectionner la file à traiter selon la priorité
                queue_to_process = None
                if self.high_priority_queue:
                    queue_to_process = self.high_priority_queue
                    priority = "high"
                elif self.medium_priority_queue:
                    queue_to_process = self.medium_priority_queue
                    priority = "medium"
                elif self.low_priority_queue:
                    queue_to_process = self.low_priority_queue
                    priority = "low"
                
                if queue_to_process:
                    entry = queue_to_process.popleft()
                    self.processed_requests += 1
                    
                    # Calculer le temps d'attente
                    wait_time = time.time() - entry["timestamp"]
                    self.metrics["total_wait_time"] += wait_time
                    self.metrics["total_waiting_requests"] += 1
                    self.metrics["avg_wait_time"] = self.metrics["total_wait_time"] / self.metrics["total_waiting_requests"]
                    
                    # Mettre à jour les métriques
                    self.metrics[f"{priority}_priority_processed"] += 1
                    
                    try:
                        # Exécution de la fonction
                        start_time = time.time()
                        result = await entry["func"](*entry["args"], **entry["kwargs"])
                        execution_time = time.time() - start_time
                        
                        # Ajouter le temps d'exécution à notre historique
                        self.request_times.append(execution_time)
                        
                        # Résoudre la future avec le résultat
                        entry["future"].set_result(result)
                        
                        # Retirer l'utilisateur de la liste d'attente
                        user_id = entry.get("user_id")
                        if user_id and user_id in self.waiting_users:
                            del self.waiting_users[user_id]
                            
                    except Exception as e:
                        logger.error(f"Erreur lors de l'exécution d'une tâche: {e}")
                        entry["future"].set_exception(e)
            
            # Mettre à jour les notifications des utilisateurs en attente toutes les 3 secondes
            if int(current_time) % 3 == 0:
                asyncio.create_task(self._update_all_waiting_users())
            
            # Attendre un court délai pour ne pas surcharger le CPU
            await asyncio.sleep(0.01)
    
    async def _notify_user_queue_position(self, user_id: int, message: Message) -> None:
        """
        Notifie un utilisateur de sa position dans la file d'attente.
        
        Args:
            user_id (int): ID de l'utilisateur
            message (Message): Message Telegram pour répondre
        """
        try:
            # Position totale dans toutes les files d'attente
            position = self._get_user_position(user_id)
            
            if position == 0:
                # L'utilisateur n'est pas dans la file d'attente ou est en cours de traitement
                return
            
            # Calculer le temps d'attente estimé
            avg_request_time = self._get_average_request_time()
            estimated_wait = position * avg_request_time
            
            # Formater le temps d'attente
            if estimated_wait < 60:
                wait_str = f"{estimated_wait:.1f} secondes"
            else:
                wait_str = f"{estimated_wait / 60:.1f} minutes"
            
            # Créer un message d'attente
            wait_message = (
                f"⏳ *File d'attente active*\n\n"
                f"Position: *{position}*\n"
                f"Temps d'attente estimé: *{wait_str}*\n\n"
                f"Merci de votre patience!"
            )
            
            # Envoyer ou mettre à jour le message
            current_time = time.time()
            
            if user_id in self.waiting_users:
                # Ne mettre à jour que toutes les 3 secondes pour éviter trop de requêtes
                last_notification = self.waiting_users[user_id]["last_notification"]
                if current_time - last_notification >= 3.0:
                    try:
                        # Mettre à jour le message existant
                        notification_msg = self.waiting_users[user_id]["message"]
                        await notification_msg.edit_text(wait_message, parse_mode='Markdown')
                        self.waiting_users[user_id]["last_notification"] = current_time
                    except Exception as e:
                        logger.warning(f"Impossible de mettre à jour la notification d'attente: {e}")
            else:
                # Envoyer un nouveau message
                try:
                    notification_msg = await message.reply_text(wait_message, parse_mode='Markdown')
                    self.waiting_users[user_id] = {
                        "message": notification_msg,
                        "last_notification": current_time
                    }
                except Exception as e:
                    logger.warning(f"Impossible d'envoyer la notification d'attente: {e}")
        
        except Exception as e:
            logger.error(f"Erreur lors de la notification de position: {e}")
    
    async def _update_all_waiting_users(self) -> None:
        """Met à jour les notifications de tous les utilisateurs en attente."""
        users_to_update = list(self.waiting_users.keys())
        
        for user_id in users_to_update:
            if user_id in self.waiting_users:
                try:
                    position = self._get_user_position(user_id)
                    
                    if position == 0:
                        # L'utilisateur n'est plus dans la file d'attente
                        # Pas besoin de faire une requête API supplémentaire pour supprimer le message
                        del self.waiting_users[user_id]
                        continue
                    
                    message = self.waiting_users[user_id]["message"]
                    await self._notify_user_queue_position(user_id, message)
                except Exception as e:
                    logger.warning(f"Erreur lors de la mise à jour d'un utilisateur en attente: {e}")
    
    def _get_user_position(self, user_id: int) -> int:
        """
        Calcule la position d'un utilisateur dans les files d'attente.
        
        Args:
            user_id (int): ID de l'utilisateur
            
        Returns:
            int: Position dans la file (0 si non trouvé)
        """
        position = 0
        
        # Vérifier dans chaque file d'attente
        for entry in self.high_priority_queue:
            if entry.get("user_id") == user_id:
                return position + 1
            position += 1
        
        for entry in self.medium_priority_queue:
            if entry.get("user_id") == user_id:
                return position + 1
            position += 1
        
        for entry in self.low_priority_queue:
            if entry.get("user_id") == user_id:
                return position + 1
            position += 1
        
        return 0  # Utilisateur non trouvé dans les files d'attente
    
    def _get_average_request_time(self) -> float:
        """
        Calcule le temps moyen par requête.
        
        Returns:
            float: Temps moyen en secondes (par défaut 0.2s)
        """
        if not self.request_times:
            return 0.2  # Valeur par défaut si aucune donnée
            
        return sum(self.request_times) / len(self.request_times)
    
    def _update_metrics(self) -> None:
        """Met à jour les métriques internes."""
        self.metrics["total_requests"] += 1
        
        # Calculer la longueur totale des files d'attente
        total_queue_length = len(self.high_priority_queue) + len(self.medium_priority_queue) + len(self.low_priority_queue)
        
        if total_queue_length > self.metrics["max_queue_length"]:
            self.metrics["max_queue_length"] = total_queue_length
            
        # Journaliser les métriques toutes les 60 secondes
        if self.metrics["total_requests"] % 100 == 0:
            logger.info(f"Métriques de la file d'attente: {self.metrics}")
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Récupère le statut actuel des files d'attente.
        
        Returns:
            Dict[str, Any]: Statistiques des files d'attente
        """
        high_length = len(self.high_priority_queue)
        medium_length = len(self.medium_priority_queue)
        low_length = len(self.low_priority_queue)
        total_length = high_length + medium_length + low_length
        
        status = {
            "high_priority": high_length,
            "medium_priority": medium_length,
            "low_priority": low_length,
            "total_waiting": total_length,
            "processed_per_second": self.processed_requests,
            "avg_wait_time": self.metrics["avg_wait_time"],
            "waiting_users": len(self.waiting_users)
        }
        
        # Ajouter l'état du système
        if total_length == 0:
            status["system_load"] = "normal"
        elif total_length < 50:
            status["system_load"] = "moderate"
        elif total_length < 100:
            status["system_load"] = "high"
        else:
            status["system_load"] = "critical"
            
        return status

# Instance globale du gestionnaire de file d'attente
queue_manager = QueueManager()

# Fonction asynchrone pour démarrer le gestionnaire
async def start_queue_manager():
    """Démarre le gestionnaire de file d'attente."""
    await queue_manager.start()

# Fonction asynchrone pour arrêter le gestionnaire
async def stop_queue_manager():
    """Arrête le gestionnaire de file d'attente."""
    await queue_manager.stop()

# Décorateur pour ajouter une fonction à la file d'attente haute priorité
def high_priority(func):
    """Décorateur pour ajouter une fonction à la file haute priorité."""
    async def wrapper(*args, **kwargs):
        future = queue_manager.add_high_priority(func, *args, **kwargs)
        return await future
    return wrapper

# Décorateur pour ajouter une fonction à la file d'attente moyenne priorité
def medium_priority(func):
    """Décorateur pour ajouter une fonction à la file moyenne priorité."""
    async def wrapper(*args, **kwargs):
        future = queue_manager.add_medium_priority(func, *args, **kwargs)
        return await future
    return wrapper

# Décorateur pour ajouter une fonction à la file d'attente basse priorité
def low_priority(func):
    """Décorateur pour ajouter une fonction à la file basse priorité."""
    async def wrapper(*args, **kwargs):
        future = queue_manager.add_low_priority(func, *args, **kwargs)
        return await future
    return wrapper

# Fonction helper pour ajouter une tâche d'envoi/édition de message à la file
async def send_message_queued(chat_id, text, parse_mode=None, reply_markup=None, user_id=None, high_priority=True):
    """
    Envoie un message via la file d'attente.
    
    Args:
        chat_id: ID du chat
        text: Texte du message
        parse_mode: Mode de formatage ('Markdown', 'HTML', etc.)
        reply_markup: Markup pour les boutons
        user_id: ID de l'utilisateur pour le suivi
        high_priority: Si True, utilise la file haute priorité
    
    Returns:
        Message: Le message envoyé
    """
    from telegram import Bot
    from config import TELEGRAM_TOKEN
    
    async def _send_message():
        bot = Bot(token=TELEGRAM_TOKEN)
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    
    if high_priority:
        future = queue_manager.add_high_priority(_send_message, user_id=user_id)
    else:
        future = queue_manager.add_medium_priority(_send_message, user_id=user_id)
    
    return await future

async def edit_message_queued(message, text, parse_mode=None, reply_markup=None, user_id=None, high_priority=True):
    """
    Édite un message via la file d'attente.
    
    Args:
        message: Message à éditer
        text: Nouveau texte
        parse_mode: Mode de formatage ('Markdown', 'HTML', etc.)
        reply_markup: Markup pour les boutons
        user_id: ID de l'utilisateur pour le suivi
        high_priority: Si True, utilise la file haute priorité
    
    Returns:
        Message: Le message édité
    """
    async def _edit_message():
        return await message.edit_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    
    if high_priority:
        future = queue_manager.add_high_priority(_edit_message, user_id=user_id)
    else:
        future = queue_manager.add_medium_priority(_edit_message, user_id=user_id)
    
    return await future

# Fonction pour obtenir le statut actuel du système
def get_system_load_status(total_queue_length=None):
    """
    Évalue la charge du système en fonction de la longueur de la file d'attente.
    
    Args:
        total_queue_length (int, optional): Longueur totale de la file d'attente
        
    Returns:
        str: Statut de charge ("normal", "moderate", "high", "critical")
    """
    if total_queue_length is None:
        status = queue_manager.get_queue_status()
        total_queue_length = status["total_waiting"]
    
    if total_queue_length == 0:
        return "normal"
    elif total_queue_length < 50:
        return "moderate"
    elif total_queue_length < 100:
        return "high"
    else:
        return "critical"
