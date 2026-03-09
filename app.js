const CATEGORIES = [
    { id: "Bundesinnenpolitik", icon: "🏛️" },
    { id: "Ausland (DE)", icon: "🌍" },
    { id: "Landespolitik von ba-Wü", icon: "🐻" },
    { id: "Wirtschaft", icon: "📈" }
];

let allArticles = [];
let availableDays = [];
let availableWeeks = [];

let currentView = 'täglich'; // 'täglich' or 'wöchentlich'
let currentIndex = 0; // 0 is the most recent (latest date/week)
let showUnimportant = false;

// DOM Elements
const mainContent = document.getElementById('mainContent');
const btnDaily = document.getElementById('btnDaily');
const btnWeekly = document.getElementById('btnWeekly');
const btnPrev = document.getElementById('btnPrev');
const btnNext = document.getElementById('btnNext');
const currentTimeLabel = document.getElementById('currentTimeLabel');
const lastUpdatedEl = document.getElementById('lastUpdated');
const checkUnimportant = document.getElementById('checkUnimportant');
const categoryTemplate = document.getElementById('category-template');
const articleTemplate = document.getElementById('article-template');

// Helper to get ISO week string "YYYY-Www"
function getISOWeekString(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return `${d.getUTCFullYear()}-W${weekNo.toString().padStart(2, '0')}`;
}

function getLocalDayString(date) {
    return date.toLocaleDateString('en-CA'); // strict YYYY-MM-DD format
}

async function loadData() {
    try {
        const response = await fetch(`data.json?t=${new Date().getTime()}`);
        if (!response.ok) throw new Error('Data not found');
        const data = await response.json();
        
        allArticles = data.articles || [];
        updateTimestamp(data.lastUpdated);
        
        processTimelines();
        renderView();
    } catch (error) {
        console.error('Error loading data:', error);
        mainContent.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1;">
            Fehler beim Laden der Nachrichten. (Noch keine Daten vorhanden?)
        </div>`;
    }
}

function processTimelines() {
    const daysSet = new Set();
    const weeksSet = new Set();
    
    allArticles.forEach(article => {
        const d = new Date(article.date);
        const dayStr = getLocalDayString(d);
        const weekStr = getISOWeekString(d);
        
        article._dayStr = dayStr;
        article._weekStr = weekStr;
        
        daysSet.add(dayStr);
        weeksSet.add(weekStr);
    });
    
    // Sort descending (newest first)
    availableDays = Array.from(daysSet).sort().reverse();
    availableWeeks = Array.from(weeksSet).sort().reverse();
    
    // Fallback if empty
    if (availableDays.length === 0) availableDays.push(getLocalDayString(new Date()));
    if (availableWeeks.length === 0) availableWeeks.push(getISOWeekString(new Date()));
}

function updateTimestamp(isoString) {
    if (!isoString) return;
    const date = new Date(isoString);
    const timeStr = date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    const dateStr = date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
    lastUpdatedEl.textContent = `Letztes Update: ${dateStr}, ${timeStr} Uhr`;
}

// direction: 1 means going back in time (older), -1 means going forward in time (newer)
function navigateTime(direction) {
    const maxIndex = currentView === 'täglich' ? availableDays.length - 1 : availableWeeks.length - 1;
    currentIndex += direction;
    
    if (currentIndex < 0) currentIndex = 0;
    if (currentIndex > maxIndex) currentIndex = maxIndex;
    
    renderView();
}

window.navigateTime = navigateTime; // Export for inline HTML click handler

function switchView(view) {
    if (view === currentView) return;
    
    currentView = view;
    currentIndex = 0; // Reset to latest on view change
    
    if (view === 'täglich') {
        btnDaily.classList.add('active');
        btnWeekly.classList.remove('active');
    } else {
        btnDaily.classList.remove('active');
        btnWeekly.classList.add('active');
    }
    
    renderView();
}

window.switchView = switchView; // Export for inline HTML click handler

function toggleUnimportant() {
    showUnimportant = checkUnimportant.checked;
    renderView();
}

window.toggleUnimportant = toggleUnimportant;

function formatTimeAgo(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);

    if (currentView === 'täglich') {
        if (diffMins < 60) return `vor ${diffMins} Min`;
        if (diffHours < 24) return `vor ${diffHours} Std`;
        return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute:'2-digit' });
    } else {
        return date.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' });
    }
}

function updateTimeLabel() {
    const maxIndex = currentView === 'täglich' ? availableDays.length - 1 : availableWeeks.length - 1;
    
    btnNext.disabled = currentIndex <= 0; // Can't go to future
    btnPrev.disabled = currentIndex >= maxIndex || maxIndex === -1; // Can't go past oldest
    
    if (currentView === 'täglich') {
        const currentDay = availableDays[currentIndex];
        if (!currentDay) {
            currentTimeLabel.textContent = "Keine Daten";
            return;
        }
        
        const today = getLocalDayString(new Date());
        
        // Yesterday calculation
        const yestDate = new Date();
        yestDate.setDate(yestDate.getDate() - 1);
        const yesterday = getLocalDayString(yestDate);
        
        if (currentDay === today) {
            currentTimeLabel.textContent = "Heute";
        } else if (currentDay === yesterday) {
            currentTimeLabel.textContent = "Gestern";
        } else {
            const dParts = currentDay.split('-');
            currentTimeLabel.textContent = `${dParts[2]}.${dParts[1]}.${dParts[0]}`;
        }
    } else {
        const currentWeek = availableWeeks[currentIndex];
        if (!currentWeek) {
            currentTimeLabel.textContent = "Keine Daten";
            return;
        }
        const thisWeek = getISOWeekString(new Date());
        if (currentWeek === thisWeek) {
            currentTimeLabel.textContent = "Diese Woche";
        } else {
            // e.g. "2026-W11" -> "Woche 11, 2026"
            const parts = currentWeek.split('-W');
            currentTimeLabel.textContent = `Woche ${parts[1]}, ${parts[0]}`;
        }
    }
}

function renderView() {
    updateTimeLabel();
    
    mainContent.innerHTML = '';
    
    const timeFilterStr = currentView === 'täglich' ? availableDays[currentIndex] : availableWeeks[currentIndex];
    
    // Filter articles for current time period
    let activeArticles = allArticles.filter(a => {
        if (currentView === 'täglich') return a._dayStr === timeFilterStr;
        return a._weekStr === timeFilterStr;
    });
    
    // Filter unimportant
    if (!showUnimportant) {
        activeArticles = activeArticles.filter(a => a.is_important !== false);
    }
    
    // Group by category
    const grouped = {};
    CATEGORIES.forEach(c => grouped[c.id] = []);
    
    activeArticles.forEach(a => {
        if (grouped[a.category]) {
            grouped[a.category].push(a);
        }
    });
    
    CATEGORIES.forEach(cat => {
        const clone = categoryTemplate.content.cloneNode(true);
        
        clone.querySelector('.category-icon').textContent = cat.icon;
        clone.querySelector('.category-title').textContent = cat.id;
        
        const container = clone.querySelector('.articles-container');
        const articles = grouped[cat.id] || [];
        
        if (articles.length === 0) {
            container.innerHTML = `<div class="empty-state">Keine Nachrichten gefunden.</div>`;
        } else {
            articles.forEach(article => {
                const articleClone = articleTemplate.content.cloneNode(true);
                const card = articleClone.querySelector('.news-card');
                
                // Add important flag style
                if (article.is_important === false) {
                    card.classList.add('important-false');
                }
                
                const tagSpan = articleClone.querySelector('.source-tag');
                tagSpan.textContent = article.source;
                tagSpan.classList.add(`source-${article.source}`);
                
                articleClone.querySelector('.time-tag').textContent = formatTimeAgo(article.date);
                
                articleClone.querySelector('.card-title').textContent = article.title;
                
                const link = articleClone.querySelector('.read-more-btn');
                link.href = article.link;
                
                articleClone.querySelector('.card-description').textContent = article.description || "Keine Beschreibung verfügbar.";
                
                container.appendChild(articleClone);
            });
        }
        
        mainContent.appendChild(clone);
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Sync checkbox initial state
    showUnimportant = checkUnimportant.checked;
    loadData();
});
