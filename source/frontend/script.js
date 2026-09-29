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
let uploadedCompanyClients = {};
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

// Memoria di sessione per le vie/coordinate di partenza dell'agente per azienda
// Struttura: { "WINES": { address: "...", lat: null, lon: null }, ... }
let agentStartLocations = {};
try {
    const stored = sessionStorage.getItem('agent_start_locations');
    if (stored) agentStartLocations = JSON.parse(stored);
} catch (e) {
    agentStartLocations = {};
}

function saveAgentStartLocation(company, address, lat, lon) {
    if (!company) return;
    agentStartLocations[company] = {
        address: address ? address.trim() : '',
        lat: (lat !== null && lat !== '' && !isNaN(parseFloat(lat))) ? parseFloat(lat) : null,
        lon: (lon !== null && lon !== '' && !isNaN(parseFloat(lon))) ? parseFloat(lon) : null
    };
    try {
        sessionStorage.setItem('agent_start_locations', JSON.stringify(agentStartLocations));
    } catch (e) {}
    updateStartLocationUI(company);
}

function getAgentStartLocation(company) {
    if (!company) return null;
    const loc = agentStartLocations[company];
    if (loc && (loc.address || (loc.lat !== null && loc.lon !== null))) {
        return loc;
    }
    return null;
}

let startHouseMarker = null;
let currentEditingOriginalAddress = '';

function showStartHouseOnMap(company, address, lat, lon, zoomTo = false) {
    const overlay = document.getElementById('map-overlay');
    if (overlay) overlay.style.display = 'none';
    map.invalidateSize();

    if (lat === null || lon === null || isNaN(parseFloat(lat)) || isNaN(parseFloat(lon))) {
        if (startHouseMarker) {
            map.removeLayer(startHouseMarker);
            startHouseMarker = null;
        }
        return;
    }

    const latNum = parseFloat(lat);
    const lonNum = parseFloat(lon);

    if (startHouseMarker) {
        map.removeLayer(startHouseMarker);
        startHouseMarker = null;
    }

    const houseIcon = L.divIcon({
        html: `
            <div class="start-house-marker" style="
                background: linear-gradient(135deg, #f59e0b, #ea580c);
                width: 40px;
                height: 40px;
                border-radius: 50%;
                border: 3px solid white;
                box-shadow: 0 4px 16px rgba(245, 158, 11, 0.8);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 22px;
                cursor: pointer;
                transition: transform 0.2s ease;
            ">🏠</div>
        `,
        className: 'custom-house-marker',
        iconSize: [40, 40],
        iconAnchor: [20, 20]
    });

    const popupHtml = `
        <div style="font-family:'Inter',sans-serif; min-width:220px; padding:4px;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                <span style="font-size:24px;">🏠</span>
                <div>
                    <h4 style="margin:0; color:#0f172a; font-size:1rem; font-weight:700;">Sede Partenza Agente</h4>
                    <span style="font-size:0.75rem; font-weight:700; color:white; padding:2px 8px; border-radius:4px; background:${getCompanyColor(company)};">${company}</span>
                </div>
            </div>
            ${address ? `<div style="font-size:0.85rem; color:#334155; margin-bottom:6px; font-weight:500;">📍 ${address}</div>` : ''}
            <div style="background:#f8fafc; border:1px solid #e2e8f0; padding:6px 10px; border-radius:8px; font-size:0.8rem; color:#64748b;">
                Coordinate GPS: <strong style="color:#0f172a;">${latNum.toFixed(5)}, ${lonNum.toFixed(5)}</strong>
            </div>
        </div>
    `;

    startHouseMarker = L.marker([latNum, lonNum], { icon: houseIcon, zIndexOffset: 2500 })
        .bindPopup(popupHtml)
        .addTo(map);

    if (zoomTo) {
        map.setView([latNum, lonNum], 14, { animate: true });
        setTimeout(() => {
            if (startHouseMarker) startHouseMarker.openPopup();
        }, 250);
    }
}

function renderCompanyClientsOnMap(company, fit = true) {
    if (!company) {
        markersLayer.clearLayers();
        showStartHouseOnMap(null, null, null, null);
        const legend = document.getElementById('map-legend');
        if (legend) legend.style.display = 'none';
        return;
    }

    const clients = uploadedCompanyClients[company] || [];
    markersLayer.clearLayers();

    const color = getCompanyColor(company);
    const formatter = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' });

    clients.forEach(client => {
        if (client.lat === null || client.lon === null || isNaN(client.lat) || isNaN(client.lon)) return;

        const markerHtml = `
            <div style="
                background-color: ${color};
                width: 14px;
                height: 14px;
                border-radius: 50%;
                border: 2px solid white;
                box-shadow: 0 0 6px rgba(0,0,0,0.45);
                cursor: pointer;
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
                <h4 style="margin:0 0 6px 0; color:#0f172a; font-weight:700;">${client.name}</h4>
                <div style="font-size:0.85rem; color:#475569; margin-bottom:10px;">
                    <div>${client.address || ''}</div>
                    <div>${client.city || ''}</div>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #e2e8f0; padding-top:8px;">
                    <span style="font-size:0.75rem; font-weight:700; color:white; padding:2px 8px; border-radius:4px; background:${color};">${company}</span>
                    <strong style="color:#10b981; font-size:1.05rem;">${formatter.format(client.revenue || 0)}</strong>
                </div>
            </div>
        `;

        L.marker([client.lat, client.lon], { icon })
            .bindPopup(popupContent)
            .addTo(markersLayer);
    });

    const overlay = document.getElementById('map-overlay');
    if (overlay && (clients.length > 0 || getAgentStartLocation(company))) {
        overlay.style.display = 'none';
    }

    const legend = document.getElementById('map-legend');
    if (legend && (clients.length > 0 || startHouseMarker)) {
        legend.style.display = 'flex';
        const dots = legend.querySelectorAll('.legend-dot');
        dots.forEach(d => {
            if (d.classList.contains('planned')) d.style.backgroundColor = color;
            if (d.classList.contains('unplanned')) d.style.borderColor = color;
        });
    }

    // Mostra la sede dell'agente se presente
    const loc = getAgentStartLocation(company);
    if (loc && loc.lat !== null && loc.lon !== null) {
        showStartHouseOnMap(company, loc.address, loc.lat, loc.lon, false);
    } else {
        showStartHouseOnMap(null, null, null, null);
    }

    if (fit) {
        const allMarkers = [...markersLayer.getLayers()];
        if (startHouseMarker) allMarkers.push(startHouseMarker);
        if (allMarkers.length > 0) {
            const group = new L.featureGroup(allMarkers);
            map.fitBounds(group.getBounds().pad(0.12));
        }
    }
}

function updateStartLocationUI(company) {
    const editBtn = document.getElementById('edit-start-loc-btn');
    const badge = document.getElementById('start-loc-badge');
    const badgeText = document.getElementById('start-loc-badge-text');
    const card = document.getElementById('start-loc-card');
    const companyTag = document.getElementById('card-company-tag');

    if (!company) {
        if (editBtn) {
            editBtn.disabled = true;
            editBtn.classList.remove('has-location');
        }
        badge.style.display = 'none';
        card.style.display = 'none';
        showStartHouseOnMap(null, null, null, null);
        markersLayer.clearLayers();
        const legend = document.getElementById('map-legend');
        if (legend) legend.style.display = 'none';
        return;
    }

    if (editBtn) editBtn.disabled = false;
    if (companyTag) {
        companyTag.textContent = company;
        companyTag.style.backgroundColor = getCompanyColor(company);
    }

    const loc = getAgentStartLocation(company);
    if (loc) {
        if (editBtn) {
            editBtn.classList.add('has-location');
            editBtn.title = `Punto di partenza impostato per ${company} (clicca per modificare)`;
        }
        let desc = loc.address;
        if (loc.lat !== null && loc.lon !== null) {
            const coordStr = `${loc.lat.toFixed(4)}, ${loc.lon.toFixed(4)}`;
            desc = loc.address ? `${loc.address} (${coordStr})` : `Coord: ${coordStr}`;
        }
        badgeText.textContent = desc;
        badge.style.display = 'flex';
        card.style.display = 'none';
    } else {
        if (editBtn) {
            editBtn.classList.remove('has-location');
            editBtn.title = `Imposta punto di partenza per ${company}`;
        }
        badge.style.display = 'none';
        openStartLocCard(company);
    }

    // Renderizza sempre tutti i clienti dell'azienda sulla mappa insieme alla casa (sede di partenza)
    const key = getCacheKey(company);
    if (clientScenarioCache.has(key)) {
        renderScenario(clientScenarioCache.get(key));
    } else {
        renderCompanyClientsOnMap(company, true);
    }
}

function openStartLocCard(company) {
    const card = document.getElementById('start-loc-card');
    const companyTag = document.getElementById('card-company-tag');
    const addrInput = document.getElementById('start-address');
    const latInput = document.getElementById('start-lat');
    const lonInput = document.getElementById('start-lon');
    const msg = document.getElementById('start-loc-msg');

    if (companyTag) {
        companyTag.textContent = company;
        companyTag.style.backgroundColor = getCompanyColor(company);
    }

    const loc = getAgentStartLocation(company);
    currentEditingOriginalAddress = loc && loc.address ? loc.address.trim() : '';
    addrInput.value = currentEditingOriginalAddress;
    latInput.value = loc && loc.lat !== null ? loc.lat : '';
    lonInput.value = loc && loc.lon !== null ? loc.lon : '';

    msg.style.display = 'none';
    msg.textContent = '';
    msg.className = 'card-msg';

    card.style.display = 'block';
    addrInput.focus();
}

// Se l'utente digita una via diversa, azzera le coordinate preesistenti così vengono ricalcolate
document.getElementById('start-address').addEventListener('input', (e) => {
    const newAddr = e.target.value.trim();
    if (newAddr !== currentEditingOriginalAddress) {
        document.getElementById('start-lat').value = '';
        document.getElementById('start-lon').value = '';
    }
});

function closeStartLocCard() {
    const card = document.getElementById('start-loc-card');
    card.style.display = 'none';
}

function getCacheKey(company) {
    const fileInput = document.getElementById('dataset');
    const fileName = fileInput.files[0] ? fileInput.files[0].name : 'nofile';
    const days = document.getElementById('days').value;
    const hours = document.getElementById('hours').value;
    const startDate = document.getElementById('start-date').value;
    const loc = getAgentStartLocation(company);
    const locStr = loc ? `${loc.address || ''}_${loc.lat || ''}_${loc.lon || ''}` : 'noloc';

    const workStart = document.getElementById('work-start')?.value || '09:00';
    const workEnd = document.getElementById('work-end')?.value || '18:00';
    const lunchEarliest = document.getElementById('lunch-earliest')?.value || '12:00';
    const lunchLatestStart = document.getElementById('lunch-latest-start')?.value || '14:00';
    const lunchDuration = document.getElementById('lunch-duration')?.value || '60';
    
    // Trasferte
    const enTr = document.getElementById('enable-trasferte')?.checked ? '1' : '0';
    const ggTr = document.getElementById('giorni-trasferta')?.value || '3';

    return `${fileName}__${company}__${days}__${hours}__${startDate}__${locStr}__${workStart}__${workEnd}__${lunchEarliest}__${lunchLatestStart}__${lunchDuration}__${enTr}_${ggTr}`;
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
        uploadedCompanyClients = data.company_clients || {};
        populateCompanySelector(availableCompanies);

        // Caricamento aziende completato con successo: l'utente seleziona parametri e clicca su "Avvia pianificazione"
    } catch (error) {
        alert(error.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Avvia pianificazione';
    }
});

function populateCompanySelector(companies) {
    const mainSelect = document.getElementById('company-select');
    mainSelect.innerHTML = '';

    if (!companies || companies.length === 0) {
        mainSelect.innerHTML = '<option value="" disabled selected>Nessun gruppo rilevato</option>';
        updateStartLocationUI(null);
        return;
    }

    companies.forEach((comp, idx) => {
        const opt = document.createElement('option');
        opt.value = comp;
        opt.textContent = comp;
        if (idx === 0) opt.selected = true;
        mainSelect.appendChild(opt);
    });

    // All'inizializzazione del selettore, verifica se la prima azienda ha un punto di partenza salvato
    updateStartLocationUI(companies[0]);
}

// Quando l'utente cambia l'azienda selezionata: aggiorna UI punto di partenza e recupera scenario se in cache
document.getElementById('company-select').addEventListener('change', (e) => {
    const company = e.target.value;
    updateStartLocationUI(company);

    const key = getCacheKey(company);
    if (clientScenarioCache.has(key)) {
        renderScenario(clientScenarioCache.get(key));
    }
});

// Toggle button accanto al selettore per aprire/chiudere la card di modifica (se presente nel DOM)
const editStartLocBtn = document.getElementById('edit-start-loc-btn');
if (editStartLocBtn) {
    editStartLocBtn.addEventListener('click', () => {
        const company = document.getElementById('company-select').value;
        if (!company) return;
        const card = document.getElementById('start-loc-card');
        if (card.style.display === 'none' || !card.style.display) {
            openStartLocCard(company);
        } else {
            closeStartLocCard();
        }
    });
}

// Tasto "Modifica" sul badge riepilogo
document.getElementById('badge-edit-btn').addEventListener('click', () => {
    const company = document.getElementById('company-select').value;
    if (company) openStartLocCard(company);
});

// Chiusura della card
document.getElementById('close-start-loc-card').addEventListener('click', () => {
    closeStartLocCard();
});

// Salvataggio del punto di partenza dalla card (con geocodifica automatica della via se non specificate coordinate)
document.getElementById('save-start-loc-btn').addEventListener('click', async () => {
    const company = document.getElementById('company-select').value;
    if (!company) return;

    const addressInput = document.getElementById('start-address');
    const latInput = document.getElementById('start-lat');
    const lonInput = document.getElementById('start-lon');
    const msg = document.getElementById('start-loc-msg');
    const saveBtn = document.getElementById('save-start-loc-btn');

    const address = addressInput.value.trim();
    const latVal = latInput.value.trim();
    const lonVal = lonInput.value.trim();

    const hasAddress = address.length > 0;
    const hasLat = latVal.length > 0 && !isNaN(parseFloat(latVal));
    const hasLon = lonVal.length > 0 && !isNaN(parseFloat(lonVal));

    if (!hasAddress && (!hasLat || !hasLon)) {
        msg.className = 'card-msg error';
        msg.textContent = 'Inserisci un indirizzo oppure entrambe le coordinate (Latitudine e Longitudine).';
        msg.style.display = 'block';
        return;
    }

    let finalLat = hasLat ? parseFloat(latVal) : null;
    let finalLon = hasLon ? parseFloat(lonVal) : null;

    const isAddressChanged = (address !== currentEditingOriginalAddress);

    // Se l'utente ha inserito la via e (è cambiata rispetto all'originale oppure mancano le coordinate), geocodifica sempre!
    if (hasAddress && (isAddressChanged || finalLat === null || finalLon === null)) {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Geocodifica in corso... ⏳';
        msg.className = 'card-msg';
        msg.style.display = 'block';
        msg.textContent = `Ricerca nuove coordinate per "${address}"...`;

        try {
            const resp = await fetch(`${API_BASE}/api/geocode?address=${encodeURIComponent(address)}`);
            const geoData = await resp.json();
            if (geoData.success && geoData.lat !== undefined && geoData.lon !== undefined) {
                finalLat = geoData.lat;
                finalLon = geoData.lon;
                latInput.value = finalLat;
                lonInput.value = finalLon;
                msg.className = 'card-msg success';
                const civInfo = geoData.house_number ? ` (Civico ${geoData.house_number}${geoData.house_number_exact ? ' ✓' : ''})` : '';
                const foundDesc = geoData.display_name ? ` - ${geoData.display_name.split(',').slice(0, 2).join(',')}` : '';
                msg.textContent = `✓ Acquisito${civInfo}: ${finalLat.toFixed(5)}, ${finalLon.toFixed(5)}${foundDesc}`;

            } else {
                saveBtn.disabled = false;
                saveBtn.textContent = 'Salva Punto di Partenza';
                msg.className = 'card-msg error';
                msg.textContent = geoData.message || 'Indirizzo non trovato su OpenStreetMap. Inserisci manualmente le coordinate GPS.';
                return;
            }
        } catch (err) {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Salva Punto di Partenza';
            msg.className = 'card-msg error';
            msg.textContent = 'Errore durante la geocodifica della via. Inserisci manualmente le coordinate.';
            return;
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Salva Punto di Partenza';
        }
    }

    saveAgentStartLocation(company, address, finalLat, finalLon);
    currentEditingOriginalAddress = address;

    // Invalida eventuali scenari calcolati precedentemente col vecchio punto di partenza per questa azienda
    for (let k of clientScenarioCache.keys()) {
        if (k.includes(`__${company}__`)) clientScenarioCache.delete(k);
    }
    activeScenarioData = null;

    // Aggiorna subito la mappa con tutti i clienti e la nuova sede, e centra la vista
    renderCompanyClientsOnMap(company, true);
});

// Helpers per gestione parametri orari e pausa pranzo
function timeToMinutes(timeStr) {
    if (!timeStr) return 0;
    const parts = timeStr.split(':');
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1] || '0', 10);
}

function calculateNetWorkHours(startStr, endStr, pauseMin) {
    const start = timeToMinutes(startStr);
    const end = timeToMinutes(endStr);
    const pause = parseInt(pauseMin, 10) || 0;
    const netMinutes = Math.max(30, end - start - pause);
    return Math.round((netMinutes / 60) * 10) / 10;
}

function updateTimeSummaryAndCalculations() {
    const start = document.getElementById('work-start')?.value || '09:00';
    const end = document.getElementById('work-end')?.value || '18:00';
    const pause = document.getElementById('lunch-duration')?.value || '60';

    const summaryEl = document.getElementById('time-settings-summary');
    if (summaryEl) {
        summaryEl.textContent = `${start} - ${end} • Pausa ${pause}m`;
    }

    const netHours = calculateNetWorkHours(start, end, pause);
    const computedHoursEl = document.getElementById('computed-work-hours');
    if (computedHoursEl) {
        computedHoursEl.textContent = netHours.toFixed(1);
    }
}

// Accordion toggle per card orari
const toggleTimeSettings = document.getElementById('toggle-time-settings');
const timeSettingsBody = document.getElementById('time-settings-body');
const timeSettingsChevron = document.getElementById('time-settings-chevron');
if (toggleTimeSettings && timeSettingsBody && timeSettingsChevron) {
    toggleTimeSettings.addEventListener('click', () => {
        const isCollapsed = timeSettingsBody.style.display === 'none';
        timeSettingsBody.style.display = isCollapsed ? 'block' : 'none';
        timeSettingsChevron.textContent = isCollapsed ? '▾' : '▸';
    });
}

// Caricamento configurazioni iniziali da /api/config
async function loadConfigDefaults() {
    try {
        const res = await fetch(`${API_BASE}/api/config`);
        if (res.ok) {
            const cfg = await res.json();
            if (cfg.work_start && document.getElementById('work-start')) {
                document.getElementById('work-start').value = cfg.work_start;
            }
            if (cfg.work_end && document.getElementById('work-end')) {
                document.getElementById('work-end').value = cfg.work_end;
            }
            if (cfg.lunch_earliest && document.getElementById('lunch-earliest')) {
                document.getElementById('lunch-earliest').value = cfg.lunch_earliest;
            }
            if (cfg.lunch_latest_start && document.getElementById('lunch-latest-start')) {
                document.getElementById('lunch-latest-start').value = cfg.lunch_latest_start;
            }
            if (cfg.lunch_duration_minutes && document.getElementById('lunch-duration')) {
                document.getElementById('lunch-duration').value = cfg.lunch_duration_minutes;
            }
            updateTimeSummaryAndCalculations();
        }
    } catch (e) {
        console.warn('Config endpoint non raggiungibile, utilizzo valori predefiniti:', e);
    }
}
loadConfigDefaults();

// Se l'utente modifica parametri già precedentemente calcolati in questa sessione, mostra dalla cache
['days', 'hours', 'start-date', 'work-start', 'work-end', 'lunch-earliest', 'lunch-latest-start', 'lunch-duration', 'enable-trasferte', 'giorni-trasferta'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', () => {
        updateTimeSummaryAndCalculations();
        const selectedCompany = document.getElementById('company-select').value;
        if (!selectedCompany) return;
        const key = getCacheKey(selectedCompany);
        if (clientScenarioCache.has(key)) {
            renderScenario(clientScenarioCache.get(key));
        }
    });
    el.addEventListener('input', () => {
        updateTimeSummaryAndCalculations();
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

    const startLoc = getAgentStartLocation(selectedCompany);
        if (!startLoc || startLoc.lat === null || startLoc.lon === null) {
        openStartLocCard(selectedCompany);
        const msg = document.getElementById('start-loc-msg');
        msg.className = 'card-msg error';
        msg.textContent = `Devi geocodificare un indirizzo di partenza valido (con coordinate) per ${selectedCompany} prima di continuare. Salvati o ricontrolla la sede di partenza!`;
        msg.style.display = 'block';
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
        const workStart = document.getElementById('work-start')?.value || '09:00';
        const workEnd = document.getElementById('work-end')?.value || '18:00';
        const lunchEarliest = document.getElementById('lunch-earliest')?.value || '12:00';
        const lunchLatestStart = document.getElementById('lunch-latest-start')?.value || '14:00';
        const lunchDuration = document.getElementById('lunch-duration')?.value || '60';
        const netWorkHours = calculateNetWorkHours(workStart, workEnd, lunchDuration);

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('days', document.getElementById('days').value);
        formData.append('hours_per_visit', document.getElementById('hours').value);
        formData.append('work_hours', netWorkHours);
        formData.append('company', selectedCompany);
        formData.append('work_start', workStart);
        formData.append('work_end', workEnd);
        formData.append('lunch_earliest', lunchEarliest);
        formData.append('lunch_latest_start', lunchLatestStart);
        formData.append('lunch_duration_minutes', lunchDuration);

        if (startLoc.address) {
            formData.append('start_address', startLoc.address);
        }
        if (startLoc.lat !== null) {
            formData.append('start_lat', startLoc.lat);
        }
        if (startLoc.lon !== null) {
            formData.append('start_lon', startLoc.lon);
        }

        const startDate = document.getElementById('start-date').value;
        if (startDate) {
            formData.append('start_date', startDate);
        }
        
        if (document.getElementById('enable-trasferte')?.checked) {
            formData.append('enable_trasferte', 'true');
            formData.append('max_giorni_trasferta', document.getElementById('giorni-trasferta').value);
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
        btn.textContent = 'Avvia pianificazione';
        if (overlay) overlay.style.display = 'none';
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
    const timeInfo = data.time_params || {
        work_start: document.getElementById('work-start')?.value || '09:00',
        work_end: document.getElementById('work-end')?.value || '18:00',
        lunch_duration_minutes: document.getElementById('lunch-duration')?.value || 60
    };
    subtitle.innerHTML = `
        <div>Piano per: <strong style="color:${getCompanyColor(comp)}">${comp}</strong></div>
        <div>Fatturato Recuperabile: <strong>${formatter.format(kpis.recovered_revenue || 0)}</strong></div>
        <div>${kpis.visits || 0}/${kpis.geocoded_clients || 0} visite totali (Orario: <strong>${timeInfo.work_start} - ${timeInfo.work_end}</strong>, pausa ${timeInfo.lunch_duration_minutes}m)</div>
        <div>${droppedCount} visite senza coordinate valide</div>
    `;

    // 3. Render Mappa
    markersLayer.clearLayers();
    const mapPoints = data.map_points || [];

    // Assicura che anche tutti gli altri clienti dell'azienda presenti nel file siano visualizzati sulla mappa
    const existingNames = new Set(mapPoints.map(p => p.name));
    const allCompanyClients = uploadedCompanyClients[comp] || [];
    allCompanyClients.forEach(c => {
        if (!existingNames.has(c.name) && c.lat !== null && c.lon !== null && !isNaN(c.lat) && !isNaN(c.lon)) {
            mapPoints.push({
                lat: c.lat,
                lon: c.lon,
                name: c.name,
                revenue: c.revenue || 0,
                main_company: comp,
                address: c.address || '',
                city: c.city || '',
                day: '',
                date: '',
                time: '',
                planned: false
            });
            existingNames.add(c.name);
        }
    });

    mapPoints.forEach(point => {
        const isPlanned = point.planned !== false;
        const color = getCompanyColor(point.main_company);

        let markerHtml;
        let iconSize, iconAnchor;
        let zIndex = 100;

        if (isPlanned) {
            markerHtml = `
                <div style="
                    background-color: ${color};
                    width: 16px;
                    height: 16px;
                    border-radius: 50%;
                    border: 2px solid white;
                    box-shadow: 0 0 8px rgba(0,0,0,0.5);
                    cursor: pointer;
                "></div>
            `;
            iconSize = [16, 16];
            iconAnchor = [8, 8];
            zIndex = 500;
        } else {
            // Cliente aziendale non pianificato nel periodo
            markerHtml = `
                <div style="
                    background-color: rgba(15, 23, 42, 0.75);
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    border: 2px solid ${color};
                    box-shadow: 0 0 4px rgba(0,0,0,0.3);
                    cursor: pointer;
                    opacity: 0.85;
                "></div>
            `;
            iconSize = [12, 12];
            iconAnchor = [6, 6];
            zIndex = 200;
        }

        const icon = L.divIcon({
            html: markerHtml,
            className: 'custom-marker',
            iconSize: iconSize,
            iconAnchor: iconAnchor
        });

        let statusBadgeHtml = '';
        if (isPlanned) {
            statusBadgeHtml = `
                <div style="background:#f1f5f9; padding:8px; border-radius:6px; margin-bottom:8px;">
                    <strong style="color:#0f172a; display:block; margin-bottom:2px; font-size:0.8rem;">Visita Programmata</strong>
                    <div style="color:#3b82f6; font-weight:600; font-size:0.9rem;">${point.date} (${point.day})</div>
                    <div style="color:#64748b; font-size:0.82rem;">${point.time}</div>
                </div>
            `;
        } else {
            statusBadgeHtml = `
                <div style="background:#f8fafc; border:1px dashed #cbd5e1; padding:6px 8px; border-radius:6px; margin-bottom:8px;">
                    <span style="color:#64748b; font-size:0.8rem; font-weight:600;">⚪ Cliente non pianificato nel periodo</span>
                </div>
            `;
        }

        const popupContent = `
            <div style="font-family:'Inter',sans-serif; min-width:210px;">
                <h4 style="margin:0 0 6px 0; color:#0f172a; font-weight:700;">${point.name}</h4>
                <div style="font-size:0.85rem; color:#475569; margin-bottom:10px;">
                    <div>${point.address}</div>
                    <div>${point.city}</div>
                </div>
                ${statusBadgeHtml}
                <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #e2e8f0; padding-top:8px;">
                    <span style="font-size:0.75rem; font-weight:700; color:white; padding:2px 8px; border-radius:4px; background:${color};">${point.main_company}</span>
                    <strong style="color:#10b981; font-size:1.05rem;">${formatter.format(point.revenue)}</strong>
                </div>
            </div>
        `;

        L.marker([point.lat, point.lon], { icon, zIndexOffset: zIndex })
            .bindPopup(popupContent)
            .addTo(markersLayer);
    });

    const legend = document.getElementById('map-legend');
    if (legend) {
        legend.style.display = 'flex';
        const dots = legend.querySelectorAll('.legend-dot');
        dots.forEach(d => {
            if (d.classList.contains('planned')) d.style.backgroundColor = getCompanyColor(comp);
            if (d.classList.contains('unplanned')) d.style.borderColor = getCompanyColor(comp);
        });
    }

    // 3b. Sede di partenza dell'agente: mostra l'icona della casa 🏠 sulla mappa
    const startLoc = getAgentStartLocation(comp);
    const startLat = (startLoc && startLoc.lat !== null) ? startLoc.lat : (data.agent_start_location && data.agent_start_location.lat !== null ? data.agent_start_location.lat : null);
    const startLon = (startLoc && startLoc.lon !== null) ? startLoc.lon : (data.agent_start_location && data.agent_start_location.lon !== null ? data.agent_start_location.lon : null);

    showStartHouseOnMap(comp, (startLoc ? startLoc.address : ''), startLat, startLon, false);

    const allMarkers = [...markersLayer.getLayers()];
    if (startHouseMarker) allMarkers.push(startHouseMarker);

    if (allMarkers.length > 0) {
        const group = new L.featureGroup(allMarkers);
        map.fitBounds(group.getBounds().pad(0.12));
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

// Toggle Trasferte UI
const enableTrasferte = document.getElementById('enable-trasferte');
const trasferteBody = document.getElementById('trasferte-body');
if (enableTrasferte && trasferteBody) {
    enableTrasferte.addEventListener('change', (e) => {
        trasferteBody.style.display = e.target.checked ? 'block' : 'none';
    });
}
