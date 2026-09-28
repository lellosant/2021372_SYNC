const map = L.map('map', { zoomControl: false }).setView([41.9028, 12.4964], 6);
L.control.zoom({ position: 'bottomright' }).addTo(map);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
}).addTo(map);

let markersLayer = L.layerGroup().addTo(map);

// Rileva dinamicamente l'URL del backend
const API_BASE = window.location.port === '8080' ? `${window.location.protocol}//${window.location.hostname}:8000` : '';

// Cache client-side dei piani calcolati per passaggio istantaneo senza ricalcoli
// Chiave: `${fileName}__${company}__${days}__${hours}__${startDate}`
const clientScenarioCache = new Map();
let availableCompanies = [];
let activeScenarioData = null;

// Palette colori per aziende/gruppi
const PALETTE = [
    '#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#06b6d4', '#ef4444', '#14b8a6', '#f97316'
];
const companyColors = {};
let colorIndex = 0;

function getCompanyColor(company) {
    if (!company) return '#94a3b8';
    if (!companyColors[company]) {
        companyColors[company] = PALETTE[colorIndex % PALETTE.length];
        colorIndex++;
    }
    return companyColors[company];
}

// Imposta la data di inizio di default (oggi o prossimo lunedì se weekend)
const startDateInput = document.getElementById('start-date');
const today = new Date();
const currentLocal = new Date(today.getTime() - (today.getTimezoneOffset() * 60000));
if (currentLocal.getDay() === 6) currentLocal.setDate(currentLocal.getDate() + 2);
else if (currentLocal.getDay() === 0) currentLocal.setDate(currentLocal.getDate() + 1);
startDateInput.value = currentLocal.toISOString().split('T')[0];

function getCacheKey(company) {
    const fileInput = document.getElementById('dataset');
    const fileName = fileInput.files[0] ? fileInput.files[0].name : 'nofile';
    const days = document.getElementById('days').value;
    const hours = document.getElementById('hours').value;
    const startDate = document.getElementById('start-date').value;
    return `${fileName}__${company}__${days}__${hours}__${startDate}`;
}

// Listener cambio file Excel/CSV
document.getElementById('dataset').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    clientScenarioCache.clear();
    const formData = new FormData();
    formData.append('file', file);

    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Caricamento aziende...';

    try {
        const response = await fetch(`${API_BASE}/api/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errDetail = await response.text().catch(() => '');
            throw new Error(`Errore caricamento file (${response.status}): ${errDetail || response.statusText}`);
        }

        const data = await response.json();
        availableCompanies = data.companies || [];
        populateCompanySelector(availableCompanies);

        // Se ci sono aziende, avvia automaticamente l'ottimizzazione della prima azienda
        if (availableCompanies.length > 0) {
            performAnalysis();
        }
    } catch (error) {
        alert(error.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Calcola Scenario';
    }
});

function populateCompanySelector(companies) {
    const mainSelect = document.getElementById('company-select');
    mainSelect.innerHTML = '';

    if (!companies || companies.length === 0) {
        mainSelect.innerHTML = '<option value="" disabled selected>Nessun gruppo rilevato</option>';
        return;
    }

    companies.forEach((comp, idx) => {
        const opt = document.createElement('option');
        opt.value = comp;
        opt.textContent = comp;
        if (idx === 0) opt.selected = true;
        mainSelect.appendChild(opt);
    });
}

// Quando l'utente cambia l'azienda selezionata
document.getElementById('company-select').addEventListener('change', (e) => {
    const company = e.target.value;
    const key = getCacheKey(company);
    if (clientScenarioCache.has(key)) {
        // Se già calcolato, passaggio istantaneo senza attesa né ricalcolo
        renderScenario(clientScenarioCache.get(key));
    } else {
        // Se non ancora calcolato, calcola lo scenario per quell'azienda
        performAnalysis();
    }
});

// Watch dei parametri: se cambiano giorni, ore o data di inizio
['days', 'hours', 'start-date'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => {
        const selectedCompany = document.getElementById('company-select').value;
        if (!selectedCompany) return;
        const key = getCacheKey(selectedCompany);
        if (clientScenarioCache.has(key)) {
            renderScenario(clientScenarioCache.get(key));
        } else {
            performAnalysis();
        }
    });
});

document.getElementById('analyze-form').addEventListener('submit', (e) => {
    e.preventDefault();
    performAnalysis();
});

async function performAnalysis() {
    const fileInput = document.getElementById('dataset');
    if (fileInput.files.length === 0) {
        alert('Seleziona prima un file Excel o CSV.');
        return;
    }

    const companySelect = document.getElementById('company-select');
    const selectedCompany = companySelect.value;
    if (!selectedCompany) {
        alert('Seleziona un\'azienda da ottimizzare.');
        return;
    }

    const cacheKey = getCacheKey(selectedCompany);
    if (clientScenarioCache.has(cacheKey)) {
        renderScenario(clientScenarioCache.get(cacheKey));
        return;
    }

    const btn = document.getElementById('submit-btn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = `Calcolo ${selectedCompany}...`;

    const overlay = document.getElementById('map-overlay');
    overlay.textContent = `Ottimizzazione visite in corso per ${selectedCompany}...`;
    overlay.style.display = 'flex';

    try {
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('days', document.getElementById('days').value);
        formData.append('hours_per_visit', document.getElementById('hours').value);
        formData.append('work_hours', 8.0);
        formData.append('company', selectedCompany);

        const startDate = document.getElementById('start-date').value;
        if (startDate) {
            formData.append('start_date', startDate);
        }

        const response = await fetch(`${API_BASE}/api/analyze`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errDetail = await response.text().catch(() => '');
            throw new Error(`Errore durante l'analisi (${response.status}): ${errDetail || response.statusText}`);
        }

        const data = await response.json();
        if (data.error) {
            alert(data.error);
            return;
        }

        // Salva in cache client-side
        clientScenarioCache.set(cacheKey, data);
        renderScenario(data);

    } catch (error) {
        alert(error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Avvia nuova ricerca';
    }
}

function renderScenario(data) {
    activeScenarioData = data;
    const comp = data.target_company;
    const kpis = data.kpis || {};
    const formatter = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' });

    // 1. Aggiorna KPI Dashboard
    document.getElementById('kpi-company-badge').textContent = comp;
    document.getElementById('kpi-company-badge').style.backgroundColor = getCompanyColor(comp);
    document.getElementById('kpi-recovered-revenue').textContent = formatter.format(kpis.recovered_revenue || 0);

    document.getElementById('kpi-potential-revenue').textContent = formatter.format(kpis.company_potential || 0);
    document.getElementById('kpi-company-pot-name').textContent = comp;

    document.getElementById('kpi-visits').textContent = `${kpis.visits || 0} / ${kpis.geocoded_clients || 0}`;
    document.getElementById('kpi-recovery-rate').textContent = `${kpis.recovery_rate_pct || 0}%`;

    // 2. Aggiorna header agenda
    const subtitle = document.getElementById('table-company-subtitle');
    const droppedCount = (kpis.total_clients || 0) - (kpis.geocoded_clients || 0);
    const droppedText = droppedCount > 0 ? ` (esclusi ${droppedCount} senza coordinate valide)` : '';
    subtitle.innerHTML = `Piano per <strong style="color:${getCompanyColor(comp)}">${comp}</strong> — Fatturato Recuperabile: <strong>${formatter.format(kpis.recovered_revenue || 0)}</strong> (${kpis.visits || 0} visite su ${kpis.geocoded_clients || 0} clienti totali localizzabili${droppedText})`;

    // 3. Render Mappa
    markersLayer.clearLayers();
    const mapPoints = data.map_points || [];
    mapPoints.forEach(point => {
        const color = getCompanyColor(point.main_company);
        const markerHtml = `
            <div style="
                background-color: ${color};
                width: 14px;
                height: 14px;
                border-radius: 50%;
                border: 2px solid white;
                box-shadow: 0 0 5px rgba(0,0,0,0.5);
            "></div>
        `;
        const icon = L.divIcon({
            html: markerHtml,
            className: 'custom-marker',
            iconSize: [14, 14],
            iconAnchor: [7, 7]
        });

        const popupContent = `
            <div style="font-family:'Inter',sans-serif; min-width:210px;">
                <h4 style="margin:0 0 6px 0; color:#0f172a; font-weight:700;">${point.name}</h4>
                <div style="font-size:0.85rem; color:#475569; margin-bottom:10px;">
                    <div>${point.address}</div>
                    <div>${point.city}</div>
                </div>
                <div style="background:#f1f5f9; padding:8px; border-radius:6px; margin-bottom:8px;">
                    <strong style="color:#0f172a; display:block; margin-bottom:2px; font-size:0.8rem;">Visita Programmata</strong>
                    <div style="color:#3b82f6; font-weight:600; font-size:0.9rem;">${point.date} (${point.day})</div>
                    <div style="color:#64748b; font-size:0.82rem;">${point.time}</div>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #e2e8f0; padding-top:8px;">
                    <span style="font-size:0.75rem; font-weight:700; color:white; padding:2px 8px; border-radius:4px; background:${color};">${point.main_company}</span>
                    <strong style="color:#10b981; font-size:1.05rem;">${formatter.format(point.revenue)}</strong>
                </div>
            </div>
        `;

        L.marker([point.lat, point.lon], { icon })
            .bindPopup(popupContent)
            .addTo(markersLayer);
    });

    if (mapPoints.length > 0) {
        const group = new L.featureGroup(markersLayer.getLayers());
        map.fitBounds(group.getBounds().pad(0.1));
    }

    document.getElementById('map-overlay').style.display = 'none';
    document.getElementById('table-container').style.display = 'block';

    // 4. Render Tabella Agenda
    const tbody = document.querySelector('#schedule-table tbody');
    tbody.innerHTML = '';

    const schedule = data.schedule || [];
    schedule.forEach(row => {
        const tr = document.createElement('tr');
        const color = getCompanyColor(row['Gruppo'] || comp);
        tr.innerHTML = `
            <td style="font-weight:600;">${row['Data Visita']}</td>
            <td><span style="background:rgba(255,255,255,0.08);padding:4px 8px;border-radius:4px;font-size:0.8rem;">${row['Giorno']}</span></td>
            <td><span style="color:#38bdf8;font-weight:600;font-size:0.85rem;">${row['Orario']}</span></td>
            <td><strong>${row['Cliente']}</strong></td>
            <td><span class="dot" style="background:${color}; margin-right:6px; vertical-align:middle;"></span>${row['Gruppo'] || comp}</td>
            <td>${row['Città']}</td>
            <td><small style="color:#94a3b8;">${row['Indirizzo']}</small></td>
            <td style="color:var(--accent); font-weight:700;">${formatter.format(row['Fatturato Stimato'])}</td>
        `;
        tbody.appendChild(tr);
    });
}
