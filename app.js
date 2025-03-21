// Initialisation de l'application
document.addEventListener("DOMContentLoaded", function() {
    // Initialiser l'API Telegram WebApp si disponible
    if (window.Telegram && window.Telegram.WebApp) {
        window.Telegram.WebApp.ready();
        console.log("Telegram WebApp initialisé avec succès");
        
        // Changer les couleurs pour correspondre au thème Telegram
        const webAppData = window.Telegram.WebApp;
        if (webAppData.themeParams) {
            document.documentElement.style.setProperty('--bg-dark', webAppData.themeParams.bg_color || '#121212');
            document.documentElement.style.setProperty('--card-bg', webAppData.themeParams.secondary_bg_color || '#1e1e1e');
            document.documentElement.style.setProperty('--text-primary', webAppData.themeParams.text_color || '#ffffff');
            document.documentElement.style.setProperty('--text-secondary', webAppData.themeParams.hint_color || '#b0b0b0');
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

// Base de données simulée pour des prédictions basées sur des données statistiques réelles
const predictionData = {
    // Statistiques de scores fréquents (basées sur les données historiques)
    commonScores: {
        halftime: [
            { score: "1:0", frequency: 28 },
            { score: "0:0", frequency: 24 },
            { score: "0:1", frequency: 22 },
            { score: "1:1", frequency: 18 },
            { score: "2:0", frequency: 12 },
            { score: "0:2", frequency: 10 }
        ],
        fulltime: [
            { score: "2:1", frequency: 20 },
            { score: "1:0", frequency: 18 },
            { score: "2:0", frequency: 16 },
            { score: "1:1", frequency: 15 },
            { score: "3:1", frequency: 12 },
            { score: "0:1", frequency: 10 },
            { score: "3:2", frequency: 8 },
            { score: "4:2", frequency: 5 }
        ]
    },
    
    // Statistiques de buts (lignes Over/Under)
    goalLines: {
        halftime: [
            { line: 0.5, underPercentage: 30, overPercentage: 70 },
            { line: 1.5, underPercentage: 62, overPercentage: 38 },
            { line: 2.5, underPercentage: 78, overPercentage: 22 }
        ],
        fulltime: [
            { line: 1.5, underPercentage: 25, overPercentage: 75 },
            { line: 2.5, underPercentage: 42, overPercentage: 58 },
            { line: 3.5, underPercentage: 65, overPercentage: 35 },
            { line: 4.5, underPercentage: 80, overPercentage: 20 }
        ]
    },
    
    // Statistiques d'avantage à domicile/extérieur
    homeAdvantage: 0.58, // Pourcentage des équipes qui gagnent à domicile
    
    // Équipes fortes avec leur "force" relative (1-10)
    strongTeams: {
        "Man City": 9.5,
        "Liverpool": 9.2,
        "Bayern": 9.3,
        "Madrid": 9.1,
        "Man Utd": 8.5,
        "Chelsea": 8.7,
        "Arsenal": 8.3,
        "Tottenham": 8.0,
        "Barcelona": 8.8,
        "PSG": 9.0
    }
};

// Table de correspondance pour les noms d'équipes abrégés
const teamAbbreviations = {
    "Manchester United": "Man Utd",
    "Manchester City": "Man City",
    "Tottenham Hotspur": "Tottenham",
    "Newcastle United": "Newcastle",
    "West Ham United": "West Ham",
    "Nottingham Forest": "N. Forest",
    "Sheffield United": "Sheffield Utd",
    "Borussia Dortmund": "Dortmund",
    "Bayer Leverkusen": "Leverkusen",
    "Real Madrid": "Madrid",
    "Atletico Madrid": "Atletico",
    "Paris Saint-Germain": "PSG",
    "Inter Milan": "Inter",
    "AC Milan": "Milan",
    "Borussia Mönchengladbach": "Gladbach",
    "RB Leipzig": "Leipzig"
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
        
        // Mettre à jour les labels avec les noms abrégés des équipes
        const team1Label = document.getElementById('odds1-label');
        const team2Label = document.getElementById('odds2-label');
        
        if (team1Label) team1Label.textContent = `Cote ${getTeamAbbreviation(team1)}`;
        if (team2Label) team2Label.textContent = `Cote ${getTeamAbbreviation(team2)}`;
        
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

// Obtenir l'abréviation du nom d'équipe
function getTeamAbbreviation(teamName) {
    return teamAbbreviations[teamName] || teamName;
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
        { text: "Analyse des tendances sur les buts...", delay: 3000 },
        { text: "Finalisation des prédictions...", delay: 3600 }
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
                messageElement.classList.add('active');
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
    
    // Liste d'équipes pour l'application (avec leurs noms complets)
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
        "Sheffield United",
        "Bayern Munich",
        "Borussia Dortmund",
        "Real Madrid",
        "Barcelona",
        "Atletico Madrid",
        "Paris Saint-Germain",
        "Inter Milan",
        "AC Milan",
        "Juventus"
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
    
    // Abréviations pour les calculs internes
    const team1Abbr = getTeamAbbreviation(team1);
    const team2Abbr = getTeamAbbreviation(team2);
    
    // Analyser les forces des équipes (utiliser les données réelles si disponibles)
    const team1Strength = predictionData.strongTeams[team1Abbr] || 7 + Math.random() * 2;
    const team2Strength = predictionData.strongTeams[team2Abbr] || 7 + Math.random() * 2;
    
    // Ajuster les prédictions en fonction des cotes fournies
    const odds1Value = parseFloat(odds1);
    const odds2Value = parseFloat(odds2);
    
    // Calculer l'avantage relatif basé sur les cotes
    const oddsAdvantage = odds2Value / (odds1Value + odds2Value);
    
    // Sélectionner les scores mi-temps (exactement 2, basés sur les statistiques)
    let halfTimeScores = getStatisticalScores('halftime', 2, team1Strength, team2Strength, oddsAdvantage);
    
    // Sélectionner les scores temps réglementaire (exactement 2, basés sur les statistiques)
    let fullTimeScores = getStatisticalScores('fulltime', 2, team1Strength, team2Strength, oddsAdvantage);
    
    // Déterminer le gagnant mi-temps (basé sur le score le plus probable)
    const halfTimeScore = halfTimeScores[0].score.split(":");
    const halfTimeTeam1Goals = parseInt(halfTimeScore[0]);
    const halfTimeTeam2Goals = parseInt(halfTimeScore[1]);
    
    let halfTimeWinner, halfTimeProbability;
    
    if (halfTimeTeam1Goals > halfTimeTeam2Goals) {
        halfTimeWinner = team1;
        halfTimeProbability = calculateWinProbability(team1Strength, team2Strength, oddsAdvantage, true);
    } else if (halfTimeTeam2Goals > halfTimeTeam1Goals) {
        halfTimeWinner = team2;
        halfTimeProbability = calculateWinProbability(team2Strength, team1Strength, 1 - oddsAdvantage, false);
    } else {
        halfTimeWinner = "Match nul";
        halfTimeProbability = 100 - (calculateWinProbability(team1Strength, team2Strength, oddsAdvantage, true) + 
                              calculateWinProbability(team2Strength, team1Strength, 1 - oddsAdvantage, false));
    }
    
    // Déterminer le gagnant temps réglementaire
    const fullTimeScore = fullTimeScores[0].score.split(":");
    const fullTimeTeam1Goals = parseInt(fullTimeScore[0]);
    const fullTimeTeam2Goals = parseInt(fullTimeScore[1]);
    
    let fullTimeWinner, fullTimeProbability;
    
    if (fullTimeTeam1Goals > fullTimeTeam2Goals) {
        fullTimeWinner = team1;
        fullTimeProbability = calculateWinProbability(team1Strength, team2Strength, oddsAdvantage, true);
    } else if (fullTimeTeam2Goals > fullTimeTeam1Goals) {
        fullTimeWinner = team2;
        fullTimeProbability = calculateWinProbability(team2Strength, team1Strength, 1 - oddsAdvantage, false);
    } else {
        fullTimeWinner = "Match nul";
        fullTimeProbability = 100 - (calculateWinProbability(team1Strength, team2Strength, oddsAdvantage, true) + 
                              calculateWinProbability(team2Strength, team1Strength, 1 - oddsAdvantage, false));
    }
    
    // Prédiction du nombre de buts (basée sur les statistiques de ligne over/under)
    // Prédiction du nombre de buts (basée sur les statistiques de ligne over/under)
   const halfTimeGoalsLine = getOptimalGoalLine('halftime');
   const fullTimeGoalsLine = getOptimalGoalLine('fulltime');
   
   // Afficher les résultats
   displayResults(team1, team2, odds1, odds2, halfTimeScores, fullTimeScores, 
                halfTimeWinner, halfTimeProbability, fullTimeWinner, 
                fullTimeProbability, halfTimeGoalsLine, fullTimeGoalsLine);
}

// Fonction pour obtenir des scores statistiquement probables
function getStatisticalScores(period, count, team1Strength, team2Strength, oddsAdvantage) {
   // Obtenir les scores communs pour la période
   const commonScores = predictionData.commonScores[period];
   
   // Créer une liste de scores pondérés basée sur la fréquence et ajustée par la force des équipes
   const weightedScores = commonScores.map(scoreData => {
       const [goalsTeam1, goalsTeam2] = scoreData.score.split(":").map(Number);
       let weight = scoreData.frequency;
       
       // Ajuster le poids en fonction de la force des équipes et de l'avantage des cotes
       if (goalsTeam1 > goalsTeam2 && team1Strength > team2Strength) {
           weight *= (1 + (team1Strength - team2Strength) / 10) * oddsAdvantage;
       } else if (goalsTeam2 > goalsTeam1 && team2Strength > team1Strength) {
           weight *= (1 + (team2Strength - team1Strength) / 10) * (1 - oddsAdvantage);
       }
       
       return {
           score: scoreData.score,
           weight: weight
       };
   });
   
   // Trier par poids décroissant
   weightedScores.sort((a, b) => b.weight - a.weight);
   
   // Sélectionner les N premiers scores
   return weightedScores.slice(0, count).map(weightedScore => {
       return {
           score: weightedScore.score,
           confidence: Math.floor(45 + (weightedScore.weight / weightedScores[0].weight) * 30)
       };
   });
}

// Calculer la probabilité de victoire
function calculateWinProbability(teamStrength, opponentStrength, oddsAdvantage, isHome) {
   // Base de probabilité fondée sur la force relative
   let baseProbability = 50 + (teamStrength - opponentStrength) * 5;
   
   // Ajuster pour l'avantage à domicile si applicable
   if (isHome) {
       baseProbability += (predictionData.homeAdvantage * 100 - 50) / 2;
   }
   
   // Ajuster par les cotes
   baseProbability = baseProbability * oddsAdvantage * 2;
   
   // Limiter entre 50-85%
   return Math.min(85, Math.max(50, Math.floor(baseProbability)));
}

// Obtenir la meilleure ligne de buts
function getOptimalGoalLine(period) {
   const lines = predictionData.goalLines[period];
   
   // Simuler une analyse basée sur les données historiques
   // Nous choisissons la ligne avec la plus grande différence entre over/under
   const optimalLine = lines.reduce((best, current) => {
       const difference = Math.abs(current.overPercentage - current.underPercentage);
       if (!best || difference > best.difference) {
           return { 
               line: current.line, 
               isOver: current.overPercentage > current.underPercentage,
               percentage: Math.max(current.overPercentage, current.underPercentage),
               difference: difference
           };
       }
       return best;
   }, null);
   
   return optimalLine;
}

// Afficher les résultats de prédiction
function displayResults(team1, team2, odds1, odds2, halfTimeScores, fullTimeScores, 
                      halfTimeWinner, halfTimeProbability, fullTimeWinner, 
                      fullTimeProbability, halfTimeGoalsLine, fullTimeGoalsLine) {
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
   document.getElementById('half-time-goals').textContent = halfTimeGoalsLine.line;
   document.getElementById('half-time-goals-suggestion').textContent = halfTimeGoalsLine.line;
   
   // Ajuster le texte de suggestion pour under/over
   const halfTimeGoalsSuggestion = document.querySelector('.goals-section:first-of-type .goals-suggestion');
   if (halfTimeGoalsLine.isOver) {
       halfTimeGoalsSuggestion.textContent = `Plus de ${halfTimeGoalsLine.line} buts (${halfTimeGoalsLine.percentage}%)`;
   } else {
       halfTimeGoalsSuggestion.textContent = `Moins de ${halfTimeGoalsLine.line} buts (${halfTimeGoalsLine.percentage}%)`;
   }
   
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
   document.getElementById('full-time-goals').textContent = fullTimeGoalsLine.line;
   document.getElementById('full-time-goals-suggestion').textContent = fullTimeGoalsLine.line;
   
   // Ajuster le texte de suggestion pour under/over
   const fullTimeGoalsSuggestion = document.querySelector('.goals-section:last-of-type .goals-suggestion');
   if (fullTimeGoalsLine.isOver) {
       fullTimeGoalsSuggestion.textContent = `Plus de ${fullTimeGoalsLine.line} buts (${fullTimeGoalsLine.percentage}%)`;
   } else {
       fullTimeGoalsSuggestion.textContent = `Moins de ${fullTimeGoalsLine.line} buts (${fullTimeGoalsLine.percentage}%)`;
   }
   
   // Afficher la page de résultats
   showPage('results-page');
}l
