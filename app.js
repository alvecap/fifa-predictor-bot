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
    
    // Initialiser les événements
    initEvents();
    
    // Charger la liste des équipes
    loadTeamsList();
});

// Configuration
const config = {
    // ID de votre canal Telegram
    channelId: '@alvecapital1',
    // URL de l'API pour la vérification d'abonnement
    apiUrl: 'https://api.telegram.org/bot',
    // Token du bot (à garder secret dans une vraie application)
    botToken: '7115420946:AAGGMxo-b4qK9G3cmC2aqscV7hg2comjqxQ'
};

// Initialisation des événements
function initEvents() {
    console.log("Initialisation des événements");
    
    // Bouton de vérification d'abonnement
    const verifyBtn = document.getElementById('verify-subscription');
    if (verifyBtn) {
        verifyBtn.addEventListener('click', checkSubscription);
        console.log("Événement attaché au bouton de vérification");
    }
    
    // Bouton pour continuer après vérification d'abonnement
    const continueBtn = document.getElementById('continue-to-app');
    if (continueBtn) {
        continueBtn.addEventListener('click', function() {
            showPage('dashboard-page');
        });
        console.log("Événement attaché au bouton continuer");
    }
    
    // Bouton pour commencer les prédictions
    const startBtn = document.getElementById('start-prediction');
    if (startBtn) {
        startBtn.addEventListener('click', function() {
            showPage('teams-selection-page');
        });
        console.log("Événement attaché au bouton commencer");
    }
    
    // Bouton pour aller à la page des cotes
    const nextToOddsBtn = document.getElementById('next-to-odds');
    if (nextToOddsBtn) {
        nextToOddsBtn.addEventListener('click', function() {
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
    }
    
    // Bouton pour lancer la prédiction
    const generateBtn = document.getElementById('generate-prediction');
    if (generateBtn) {
        generateBtn.addEventListener('click', function() {
            const team1 = document.getElementById('team1').value;
            const team2 = document.getElementById('team2').value;
            const odds1 = document.getElementById('odds1').value;
            const odds2 = document.getElementById('odds2').value;
            
            if (!odds1 || !odds2) {
                alert('Veuillez entrer les cotes pour les deux équipes.');
                return;
            }
            
            if (parseFloat(odds1) < 1.01 || parseFloat(odds2) < 1.01) {
                alert('Les cotes doivent être supérieures à 1.01.');
                return;
            }
            
            // Lancer l'animation d'analyse
            showPage('analysis-page');
            
            // Afficher les messages d'analyse
            startAnalysisAnimation();
            
            // Simuler l'analyse pendant quelques secondes
            setTimeout(() => {
                getPrediction(team1, team2, odds1, odds2);
            }, 4000);
        });
    }
    
    // Boutons pour retourner
    document.querySelectorAll('.back-button').forEach(button => {
        button.addEventListener('click', function() {
            const targetPage = this.getAttribute('data-target');
            if (targetPage) {
                showPage(targetPage);
            }
        });
    });
    
    // Bouton nouvelle prédiction
    document.getElementById('new-prediction-btn').addEventListener('click', function() {
        showPage('teams-selection-page');
    });
}

// Animation d'analyse
function startAnalysisAnimation() {
    const messageContainer = document.getElementById('analysis-messages');
    if (!messageContainer) return;
    
    messageContainer.innerHTML = '';
    
    const messages = [
        { text: "Chargement des données historiques...", delay: 600 },
        { text: "Analyse des confrontations directes...", delay: 1200 },
        { text: "Évaluation des performances récentes...", delay: 1800 },
        { text: "Calcul des probabilités de scores...", delay: 2400 },
        { text: "Génération des prédictions finales...", delay: 3000 },
        { text: "Prédictions prêtes!", delay: 3600 }
    ];
    
    messages.forEach((message, index) => {
        setTimeout(() => {
            const messageElement = document.createElement('div');
            messageElement.className = 'analysis-message';
            messageElement.innerHTML = `<i class="fas fa-angle-right"></i> ${message.text}`;
            messageContainer.appendChild(messageElement);
            
            // Animation d'apparition
            messageElement.style.opacity = 0;
            messageElement.style.transform = 'translateY(10px)';
            
            setTimeout(() => {
                messageElement.style.opacity = 1;
                messageElement.style.transform = 'translateY(0)';
            }, 50);
            
            // Faire défiler automatiquement
            messageContainer.scrollTop = messageContainer.scrollHeight;
        }, message.delay);
    });
}

// Vérification d'abonnement au canal
function checkSubscription() {
    console.log("Début de vérification d'abonnement");
    
    const loadingEl = document.getElementById('loading-verification');
    const verifyBtn = document.getElementById('verify-subscription');
    const continueBtn = document.getElementById('continue-to-app');
    const confirmationEl = document.getElementById('subscription-confirmed');
    
    // Afficher le chargement
    loadingEl.style.display = 'flex';
    verifyBtn.style.display = 'none';
    
    // Dans une vraie application, il faudrait un backend sécurisé pour cette vérification
    // Pour cette démo, nous simulons une vérification positive après un délai
    setTimeout(function() {
        // Masquer le chargement
        loadingEl.style.display = 'none';
        
        // Afficher la confirmation et le bouton pour continuer
        confirmationEl.classList.add('show');
        continueBtn.style.display = 'block';
        
        // Animer la confirmation
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

// Changement de page
function showPage(pageId) {
    console.log(`Changement de page vers ${pageId}`);
    
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
    
    console.log(`${teams.length} équipes chargées`);
    populateTeamDropdowns(teams);
}

// Fonction pour remplir les dropdown avec les équipes
function populateTeamDropdowns(teams) {
    // Remplir les listes déroulantes
    const team1Select = document.getElementById('team1');
    const team2Select = document.getElementById('team2');
    
    if (team1Select && team2Select) {
        // Vider les listes pour éviter les doublons
        team1Select.innerHTML = '<option value="" disabled selected>Sélectionner une équipe</option>';
        team2Select.innerHTML = '<option value="" disabled selected>Sélectionner une équipe</option>';
        
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
        
        console.log("Listes déroulantes d'équipes remplies");
    } else {
        console.error("Les éléments select pour les équipes n'ont pas été trouvés");
    }
}

// Récupération des prédictions
function getPrediction(team1, team2, odds1, odds2) {
    console.log("Génération de prédiction");
    
    // Générer des prédictions
    const prediction = generatePrediction(team1, team2, odds1, odds2);
    console.log("Prédiction générée", prediction);
    
    // Afficher les résultats
    displayPrediction(prediction);
    
    // Afficher la page des résultats
    showPage('results-page');
}

// Fonction pour générer des prédictions
function generatePrediction(team1, team2, odds1, odds2) {
    // Dans une version réelle, cette fonction appelerait votre API backend
    // Génération de données aléatoires pour la démo
    
    // Scores mi-temps (exactement 2)
    const halfTimeScores = [
        { score: Math.floor(Math.random() * 3) + ":" + Math.floor(Math.random() * 3), confidence: Math.floor(Math.random() * 30) + 60 },
        { score: Math.floor(Math.random() * 3) + ":" + Math.floor(Math.random() * 3), confidence: Math.floor(Math.random() * 20) + 50 }
    ];
    
    // Scores temps réglementaire (exactement 2)
    const fullTimeScores = [
        { score: Math.floor(Math.random() * 5) + ":" + Math.floor(Math.random() * 5), confidence: Math.floor(Math.random() * 30) + 60 },
        { score: Math.floor(Math.random() * 5) + ":" + Math.floor(Math.random() * 5), confidence: Math.floor(Math.random() * 20) + 50 }
    ];
    
    // Déterminer le gagnant mi-temps
    const halfTimeWinnerRandom = Math.random();
    let halfTimeWinner;
    if (halfTimeWinnerRandom < 0.4) {
        halfTimeWinner = team1;
    } else if (halfTimeWinnerRandom < 0.8) {
        halfTimeWinner = team2;
    } else {
        halfTimeWinner = "Nul";
    }
    
    // Déterminer le gagnant temps réglementaire
    const fullTimeWinnerRandom = Math.random();
    let fullTimeWinner;
    if (fullTimeWinnerRandom < 0.4) {
        fullTimeWinner = team1;
    } else if (fullTimeWinnerRandom < 0.8) {
        fullTimeWinner = team2;
    } else {
        fullTimeWinner = "Nul";
    }
    
    // Générer les moyennes de buts au format paris sportif
    const halfTimeGoalsThresholds = [0.5, 1.5, 2.5, 3.5];
    const fullTimeGoalsThresholds = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5];
    
    const halfTimeGoals = halfTimeGoalsThresholds[Math.floor(Math.random() * halfTimeGoalsThresholds.length)];
    const fullTimeGoals = fullTimeGoalsThresholds[Math.floor(Math.random() * fullTimeGoalsThresholds.length)];
    
    return {
        teams: {
            team1: team1,
            team2: team2
        },
        odds: {
            team1: odds1,
            team2: odds2
        },
        direct_matches: Math.floor(Math.random() * 50) + 10,
        half_time_scores: halfTimeScores,
        full_time_scores: fullTimeScores,
        winner_half_time: {
            team: halfTimeWinner,
            probability: Math.floor(Math.random() * 30) + 60
        },
        winner_full_time: {
            team: fullTimeWinner,
            probability: Math.floor(Math.random() * 30) + 60
        },
        goals_thresholds: {
            half_time: halfTimeGoals,
            full_time: fullTimeGoals
        },
        avg_goals_half_time: (Math.random() * 3 + 1).toFixed(1),
        avg_goals_full_time: (Math.random() * 5 + 2).toFixed(1),
        confidence_level: Math.floor(Math.random() * 30) + 60
    };
}

// Affichage des prédictions
function displayPrediction(prediction) {
    console.log("Affichage des résultats de prédiction");
    
    // Mettre à jour les éléments du DOM
    document.getElementById('match-teams').textContent = `${prediction.teams.team1} vs ${prediction.teams.team2}`;
    
    // Afficher les scores mi-temps
    const halfTimeScores = document.getElementById('half-time-scores');
    halfTimeScores.innerHTML = '';
    prediction.half_time_scores.forEach(score => {
        const scoreItem = document.createElement('div');
        scoreItem.className = 'score-card';
        scoreItem.innerHTML = `
            <div class="score-value">${score.score}</div>
            <div class="score-confidence">Confiance: ${score.confidence}%</div>
        `;
        halfTimeScores.appendChild(scoreItem);
    });
    
    // Afficher les scores temps réglementaire
    const fullTimeScores = document.getElementById('full-time-scores');
    fullTimeScores.innerHTML = '';
    prediction.full_time_scores.forEach(score => {
        const scoreItem = document.createElement('div');
        scoreItem.className = 'score-card';
        scoreItem.innerHTML = `
            <div class="score-value">${score.score}</div>
            <div class="score-confidence">Confiance: ${score.confidence}%</div>
        `;
        fullTimeScores.appendChild(scoreItem);
    });
    
    // Afficher les gagnants
    document.getElementById('half-time-winner').textContent = prediction.winner_half_time.team === "Nul" ? "Match nul" : prediction.winner_half_time.team;
    document.getElementById('half-time-probability').textContent = prediction.winner_half_time.probability + '%';
    
    document.getElementById('full-time-winner').textContent = prediction.winner_full_time.team === "Nul" ? "Match nul" : prediction.winner_full_time.team;
    document.getElementById('full-time-probability').textContent = prediction.winner_full_time.probability + '%';
    
    // Afficher les seuils de buts
    document.getElementById('half-time-goals').textContent = prediction.goals_thresholds.half_time;
    document.getElementById('full-time-goals').textContent = prediction.goals_thresholds.full_time;
    
    // Afficher les cotes
    document.getElementById('team1-name').textContent = prediction.teams.team1;
    document.getElementById('team1-odds').textContent = prediction.odds.team1;
    document.getElementById('team2-name').textContent = prediction.teams.team2;
    document.getElementById('team2-odds').textContent = prediction.odds.team2;
    
    // Afficher le nombre de confrontations
    document.getElementById('direct-matches').textContent = prediction.direct_matches;
}
