const map = L.map('map').setView([41.9028, 12.4964], 8);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);

let markersLayer = L.layerGroup().addTo(map);

// Palette per l'assegnazione dinamica dei colori ai gruppi/aziende rilevati
const PALETTE = [
    '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', 
    '#ec4899', '#06b6d4', '#14b8a6', '#f97316', '#a855f7'
];
const companyColors = {};

function getCompanyColor(companyName) {
    if (!companyName) return '#94a3b8';
    if (!companyColors[companyName]) {
        const idx = Object.keys(companyColors).length % PALETTE.length;
        companyColors[companyName] = PALETTE[idx];
    }
    return companyColors[companyName];
}

document.getElementById('analyze-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    performAnalysis();
});

// Listener per file upload immediato
document.getElementById('dataset').addEventListener('change', () => {
    // Reset loaded companies cache per forzare il refresh con il nuovo file
    document.getElementById('companies-group').dataset.loadedCompanies = '';
    performAnalysis();
});

// Parametri What-If in tempo reale
const inputsToWatch = ['days', 'hours'];
inputsToWatch.forEach(id => {
    document.getElementById(id).addEventListener('change', () => {
        if (document.getElementById('dataset').files.length > 0) {
            performAnalysis();
        }
    });
});

async function performAnalysis() {
    const fileInput = document.getElementById('dataset');
    if (fileInput.files.length === 0) return;

    const form = document.getElementById('analyze-form');
    const submitBtn = form.querySelector('button');
    submitBtn.textContent = 'Ricalcolo scenario in corso...';
    submitBtn.disabled = true;

    const file = fileInput.files[0];
    const days = document.getElementById('days').value;
    const hours = document.getElementById('hours').value;
    
    const checkboxes = document.querySelectorAll('input[name="company"]:checked');
    const companies = Array.from(checkboxes).map(cb => cb.value).join(',');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('days', days);
    formData.append('hours_per_visit', hours);
    formData.append('work_hours', 8.0);
    if (companies) {
        formData.append('companies', companies);
    }

    try {
        const response = await fetch('http://localhost:8000/api/analyze', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        updateDashboard(data);
        document.getElementById('map-overlay').style.display = 'none';
    } catch (error) {
        alert("Errore di connessione al backend (Assicurati che Docker compose sia in esecuzione).");
        console.error(error);
    } finally {
        submitBtn.textContent = 'Calcola Scenario';
        submitBtn.disabled = false;
    }
}

function renderCompanyCheckboxes(availableCompanies, selectedCompanies) {
    const container = document.getElementById('companies-group');
    if (!availableCompanies || availableCompanies.length === 0) {
        container.innerHTML = '<span style="font-size:0.8rem;color:#94a3b8;font-style:italic;">Nessun gruppo aziendale rilevato nelle colonne</span>';
        return;
    }
    
    const key = availableCompanies.join(',');
    if (container.dataset.loadedCompanies !== key) {
        container.dataset.loadedCompanies = key;
        container.innerHTML = '';
        
        availableCompanies.forEach(comp => {
            const color = getCompanyColor(comp);
            const label = document.createElement('label');
            label.style.display = 'flex';
            label.style.alignItems = 'center';
            label.style.gap = '8px';
            label.style.cursor = 'pointer';
            label.style.fontSize = '0.9rem';
            label.style.color = '#f1f5f9';
            
            const isChecked = selectedCompanies ? selectedCompanies.includes(comp) : true;
            
            label.innerHTML = `
                <input type="checkbox" name="company" value="${comp}" ${isChecked ? 'checked' : ''}>
                <span>${comp}</span>
                <span class="dot" style="background: ${color}; width: 10px; height: 10px; border-radius: 50%; display: inline-block;"></span>
            `;
            
            label.querySelector('input').addEventListener('change', () => {
                performAnalysis();
            });
            
            container.appendChild(label);
        });
    }
}

function updateDashboard(data) {
    renderCompanyCheckboxes(data.available_companies, data.selected_companies);

    document.getElementById('kpis').style.display = 'grid';
    document.getElementById('table-container').style.display = 'block';

    const formatter = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' });

    document.getElementById('kpi-revenue').textContent = formatter.format(data.metrics.expected_revenue);
    document.getElementById('kpi-visits').textContent = data.metrics.total_visits;
    document.getElementById('kpi-companies').textContent = data.metrics.companies_count;

    markersLayer.clearLayers();
    data.map_points.forEach(pt => {
        const color = getCompanyColor(pt.azienda);
        const marker = L.circleMarker([pt.lat, pt.lon], {
            radius: 7,
            fillColor: color,
            color: '#1e293b',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.9
        });
        marker.bindPopup(`
            <div style="font-family:'Inter',sans-serif;">
                <b>${pt.cliente}</b><br>
                Fatturato stimato: <b style="color:${color}">${formatter.format(pt.totale)}</b><br>
                <small>Gruppo: <b>${pt.azienda}</b></small>
            </div>
        `);
        markersLayer.addLayer(marker);
    });

    if (data.map_points.length > 0) {
        const group = new L.featureGroup(markersLayer.getLayers());
        map.fitBounds(group.getBounds().pad(0.1));
    }

    const tbody = document.querySelector('#schedule-table tbody');
    tbody.innerHTML = '';
    data.schedule.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight:600;">${row['Data Visita']}</td>
            <td><span style="background:rgba(255,255,255,0.1);padding:4px 8px;border-radius:4px;font-size:0.8rem;">${row['Giorno']}</span></td>
            <td><span style="color:#38bdf8;font-weight:600;font-size:0.85rem;">${row['Orario']}</span></td>
            <td>${row['Cliente']}</td>
            <td>${row['Città']}</td>
            <td style="color:var(--accent); font-weight:600;">${formatter.format(row['Fatturato Stimato'])}</td>
        `;
        tbody.appendChild(tr);
    });
}

