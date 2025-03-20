// Initialisation de l'application
document.addEventListener("DOMContentLoaded", function() {
    // Initialiser l'API Telegram WebApp si disponible
    if (window.Telegram && window.Telegram.WebApp) {
        window.Telegram.WebApp.ready();
        console.log("Telegram WebApp initialisé avec succès");
        
        // Changer les couleurs pour correspondre au thème Telegram
        const webAppData = window.Telegram.WebApp;
        if (webAppData.themeParams) {
            document.documentElement.style.setProperty('--background-color', webAppData.themeParams.bg_color || '#f7f9fb');
            document.documentElement.style.setProperty('--card-color', webAppData.themeParams.secondary_bg_color || '#ffffff');
            document.documentElement.style.setProperty('--text-color', webAppData.themeParams.text_color || '#333333');
            document.documentElement.style.setProperty('--text-secondary', webAppData.themeParams.hint_color || '#666666');
        }
    } else {
        console.warn("Telegram WebApp non disponible - l'application peut avoir des fonctionnalités limitées");
    }
    
    // Initialiser les gestionnaires d'événements
    initEventHandlers();
    
    // Charger la liste des équipes
    loadTeamsList();
    
    // Initialiser la gestion du clavier pour iOS
    setupKeyboardHandling();
});

// Configuration
const config = {
    // ID de votre canal Telegram
    channelId: '@alvecapital1',
    // Bot username
    botUsername: '@FIFA4x4PredictorBot'
};

// Mise en place de tous les gestionnaires d'événements
function initEventHandlers() {
    console.log("Initialisation des gestionnaires d'événements");
    
    // Bouton de vérification d'abonnement
    document.getElementById('verify-subscription')?.addEventListener('click', checkSubscription);
    
    // Bouton pour continuer après vérification d'abonnement
    document.getElementById('continue-to-app')?.addEventListener('click', function() {
        showPage('dashboard-page');
    });
    
    // Bouton pour commencer une prédiction
    document.getElementById('start-prediction')?.addEventListener('click', function() {
        showPage('teams-selection-page');
    });
    
    // Bouton pour aller à la page des cotes
    document.getElementById('next-to-odds')?.addEventListener('click', function() {
        const team1 = document.getElementById('team1').value;
        const team2 = document.getElementById('team2').value;
        
        if (!team1 || !team2) {
            alert('Veuillez sélectionner les deux équipes.');
            return;
        }
        
        if (team1 === team2) {
            alert('Veuillez sélectionner deux équipes différentes.');
            return;
        }
        
        // Mettre à jour les labels avec les noms des équipes
        const team1Label = document.getElementById('odds1-label');
        const team2Label = document.getElementById('odds2-label');
        
        if (team1Label) team1Label.textContent = `Cote ${team1}`;
        if (team2Label) team2Label.textContent = `Cote ${team2}`;
        
        showPage('odds-page');
    });
    
    // Bouton pour générer une prédiction
    document.getElementById('generate-prediction')?.addEventListener('click', function() {
        const team1 = document.getElementById('team1').value;
        const team2 = document.getElementById('team2').value;
        const odds1 = document.getElementById('odds1').value;
        const odds2 = document.getElementById('odds2').value;
        
        // Validation
        if (!odds1 || !odds2) {
            alert('Veuillez entrer les cotes pour les deux équipes.');
            return;
        }
        
        if (parseFloat(odds1) < 1.01 || parseFloat(odds2) < 1.01) {
            alert('Les cotes doivent être supérieures à 1.01.');
            return;
        }
        
        // Afficher la page d'analyse
        showPage('analysis-page');
        
        // Démarrer l'animation d'analyse
        startAnalysisAnimation();
        
        // Attendre quelques secondes puis générer la prédiction
        setTimeout(function() {
            generatePrediction(team1, team2, odds1, odds2);
        }, 4000);
    });
    
    // Boutons de retour
    document.querySelectorAll('.back-btn').forEach(button => {
        button.addEventListener('click', function() {
            const targetPage = this.getAttribute('data-target');
            if (targetPage) {
                showPage(targetPage);
            }
        });
    });
    
    // Bouton nouvelle prédiction
    document.getElementById('new-prediction-btn')?.addEventListener('click', function() {
        showPage('teams-selection-page');
    });
}

// Configuration pour gérer le clavier sur iOS
function setupKeyboardHandling() {
    const inputs = document.querySelectorAll('input');
    const dismissLayer = document.getElementById('keyboard-dismiss');
    
    inputs.forEach(input => {
        input.addEventListener('focus', function() {
            document.body.classList.add('keyboard-open');
            dismissLayer.classList.add('active');
        });
        
        input.addEventListener('blur', function() {
            document.body.classList.remove('keyboard-open');
            dismissLayer.classList.remove('active');
        });
    });
    
    dismissLayer.addEventListener('click', function() {
        document.activeElement.blur();
    });
}

// Vérification d'abonnement au canal
function checkSubscription() {
    console.log("Vérification d'abonnement initiée");
    
    const loadingEl = document.getElementById('loading-verification');
    const verifyBtn = document.getElementById('verify-subscription');
    const continueBtn = document.getElementById('continue-to-app');
    const confirmationEl = document.getElementById('subscription-confirmed');
    
    // Afficher le chargement
    loadingEl.style.display = 'flex';
    verifyBtn.style.display = 'none';
    
    // Dans une vraie implémentation, cela devrait vérifier avec un backend sécurisé
    // Pour cet exemple, nous simulons une vérification réussie
    setTimeout(function() {
        // Masquer le chargement
        loadingEl.style.display = 'none';
        
        // Afficher la confirmation et le bouton pour continuer
        confirmationEl.classList.add('show');
        continueBtn.style.display = 'block';
        
        // Une animation pour attirer l'attention
        try {
            confirmationEl.animate([
                { transform: 'scale(0.95)' },
                { transform: 'scale(1.05)' },
                { transform: 'scale(1)' }
            ], {
                duration: 600,
                easing: 'ease-out'
            });
        } catch (error) {
            console.warn("Animation non supportée par ce navigateur");
        }
    }, 1500);
}

// Animation de la page d'analyse
function startAnalysisAnimation() {
    const messageContainer = document.getElementById('analysis-messages');
    if (!messageContainer) return;
    
    // Vider le conteneur
    messageContainer.innerHTML = '';
    
    // Définir les messages à afficher
    const messages = [
        { text: "Chargement des données historiques...", delay: 600 },
        { text: "Analyse des confrontations directes...", delay: 1200 },
        { text: "Évaluation des performances récentes...", delay: 1800 },
        { text: "Calcul des probabilités de scores...", delay: 2400 },
        { text: "Génération des prédictions finales...", delay: 3000 },
        { text: "Prédictions prêtes!", delay: 3600 }
    ];
    
    // Afficher chaque message avec un délai
    messages.forEach((message, index) => {
        setTimeout(() => {
            const messageElement = document.createElement('div');
            messageElement.className = 'analysis-message';
            messageElement.innerHTML = `<i class="fas fa-angle-right"></i> ${message.text}`;
            messageContainer.appendChild(messageElement);
            
            // Animation d'apparition
            setTimeout(() => {
                messageElement.style.opacity = 1;
                messageElement.style.transform = 'translateY(0)';
            }, 50);
            
            // Faire défiler automatiquement
            messageContainer.scrollTop = messageContainer.scrollHeight;
        }, message.delay);
    });
}

// Changement de page
function showPage(pageId) {
    console.log(`Changement vers la page: ${pageId}`);
    
    // Masquer toutes les pages
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    
    // Afficher la page demandée
    const targetPage = document.getElementById(pageId);
    if (targetPage) {
        targetPage.classList.add('active');
        
        // Faire défiler vers le haut
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
        console.error(`Page ${pageId} introuvable`);
    }
}

// Chargement de la liste des équipes
function loadTeamsList() {
    console.log("Chargement de la liste des équipes");
    
    // Liste d'équipes pour l'application
    const teams = [
        "Manchester United",
        "Chelsea",
        "Arsenal",
        "Liverpool",
        "Manchester City",
        "Tottenham",
        "Aston Villa",
        "Newcastle United",
        "West Ham United",
        "Brighton",
        "Bournemouth",
        "Everton",
        "Crystal Palace",
        "Brentford",
        "Fulham",
        "Wolverhampton",
        "Nottingham Forest",
        "Luton Town",
        "Burnley",
        "Sheffield United"
    ].sort();
    
    // Remplir les listes déroulantes
    populateTeamDropdowns(teams);
}

// Fonction pour remplir les dropdown avec les équipes
function populateTeamDropdowns(teams) {
    const team1Select = document.getElementById('team1');
    const team2Select = document.getElementById('team2');
    
    if (!team1Select || !team2Select) {
        console.error("Éléments de sélection d'équipe non trouvés");
        return;
    }
    
    // Vider les listes pour éviter les doublons
    team1Select.innerHTML = '<option value="" disabled selected>Sélectionner une équipe</option>';
    team2Select.innerHTML = '<option value="" disabled selected>Sélectionner une équipe</option>';
    
    // Ajouter les équipes aux listes déroulantes
    teams.forEach(team => {
        const option1 = document.createElement('option');
        option1.value = team;
        option1.textContent = team;
        team1Select.appendChild(option1);
        
        const option2 = document.createElement('option');
        option2.value = team;
        option2.textContent = team;
        team2Select.appendChild(option2);
    });
    
    console.log(`${teams.length} équipes chargées dans les menus déroulants`);
}

// Générer une prédiction
function generatePrediction(team1, team2, odds1, odds2) {
    console.log(`Génération de prédiction pour ${team1} vs ${team2}`);
    
    // Scores mi-temps (exactement 2)
    const halfTimeScores = [
        { score: Math.floor(Math.random() * 3) + ":" + Math.floor(Math.random() * 3), confidence: Math.floor(Math.random() * 20) + 50 },
        { score: Math.floor(Math.random() * 3) + ":" + Math.floor(Math.random() * 3), confidence: Math.floor(Math.random() * 15) + 45 }
    ];
    
    // Scores temps réglementaire (exactement 2)
    const fullTimeScores = [
        { score: Math.floor(Math.random() * 5) + ":" + Math.floor(Math.random() * 5), confidence: Math.floor(Math.random() * 20) + 50 },
        { score: Math.floor(Math.random() * 5) + ":" + Math.floor(Math.random() * 5), confidence: Math.floor(Math.random() * 15) + 45 }
    ];
    
    // Déterminer le gagnant mi-temps
    const halfTimeWinner = Math.random() > 0.6 ? team1 : (Math.random() > 0.5 ? team2 : "Match nul");
    const halfTimeProbability = Math.floor(Math.random() * 20) + 55;
    
    // Déterminer le gagnant temps réglementaire
    const fullTimeWinner = Math.random() > 0.6 ? team1 : (Math.random() > 0.5 ? team2 : "Match nul");
    const fullTimeProbability = Math.floor(Math.random() * 20) + 60;
    
    // Nombre de buts
    const halfTimeGoals = [0.5, 1.5, 2.5, 3.5][Math.floor(Math.random() * 4)];
    const fullTimeGoals = [0.5, 1.5, 2.5, 3.5, 4.5][Math.floor(Math.random() * 5)];
    
    // Afficher les résultats
    displayResults(team1, team2, odds1, odds2, halfTimeScores, fullTimeScores, 
                 halfTimeWinner, halfTimeProbability, fullTimeWinner, 
                 fullTimeProbability, halfTimeGoals, fullTimeGoals);
}

// Afficher les résultats de prédiction
function displayResults(team1, team2, odds1, odds2, halfTimeScores, fullTimeScores, 
                      halfTimeWinner, halfTimeProbability, fullTimeWinner, 
                      fullTimeProbability, halfTimeGoals, fullTimeGoals) {
    console.log("Affichage des résultats de prédiction");
    
    // Titre du match
    document.getElementById('match-teams').textContent = `${team1} vs ${team2}`;
    
    // Scores mi-temps
    const halfTimeScoresContainer = document.getElementById('half-time-scores');
    halfTimeScoresContainer.innerHTML = '';
    
    halfTimeScores.forEach(score => {
        const scoreBox = document.createElement('div');
        scoreBox.className = 'score-box';
        scoreBox.innerHTML = `
            <div class="score-result">${score.score}</div>
            <div class="score-confidence">Confiance: ${score.confidence}%</div>
        `;
        halfTimeScoresContainer.appendChild(scoreBox);
    });
    
    // Vainqueur mi-temps
    document.getElementById('half-time-winner').textContent = halfTimeWinner;
    document.getElementById('half-time-probability').textContent = `${halfTimeProbability}%`;
    
    // Nombre de buts mi-temps
    document.getElementById('half-time-goals').textContent = halfTimeGoals;
    
    // Scores temps réglementaire
    const fullTimeScoresContainer = document.getElementById('full-time-scores');
    fullTimeScoresContainer.innerHTML = '';
    
    fullTimeScores.forEach(score => {
        const scoreBox = document.createElement('div');
        scoreBox.className = 'score-box';
        scoreBox.innerHTML = `
            <div class="score-result">${score.score}</div>
            <div class="score-confidence">Confiance: ${score.confidence}%</div>
        `;
        fullTimeScoresContainer.appendChild(scoreBox);
    });
    
    // Vainqueur temps réglementaire
    document.getElementById('full-time-winner').textContent = fullTimeWinner;
    document.getElementById('full-time-probability').textContent = `${fullTimeProbability}%`;
    
    // Nombre de buts temps réglementaire
    document.getElementById('full-time-goals').textContent = fullTimeGoals;
    
    // Afficher la page de résultats
    showPage('results-page');
}
