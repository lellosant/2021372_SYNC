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

// ==========================================
// INTERNAZIONALIZZAZIONE (i18n) / MULTILINGUA
// ==========================================
const TRANSLATIONS = {
    ITALIANO: {
        app_title: "GeoAnalytics Planner",
        sidebar_title: "Parametri di Ottimizzazione",
        label_dataset: "Carica Dataset (Excel/CSV)",
        btn_choose_file: "Scegli file",
        no_file_chosen: "Nessun file selezionato",
        label_start_date: "Data inizio scenario",
        label_days: "Giorni Lavorativi a Disposizione",
        label_hours: "Ore Richieste per Visita",
        time_settings_tooltip: "Clicca per aprire o chiudere i dettagli di orario e pausa",
        time_settings_label: "Orari Lavoro & Pausa",
        time_section_daily: "Orario Giornaliero",
        label_work_start: "Inizio Lavoro",
        label_work_end: "Fine Lavoro",
        time_section_lunch: "Pausa Pranzo Flessibile",
        label_lunch_earliest: "Inizio Da",
        label_lunch_latest_start: "Inizio Entro",
        label_lunch_duration: "Durata Pausa (minuti)",
        net_work_hours_label: "Ore lavorative nette:",
        per_day: "h / giorno",
        trasferte_label: "Pianifica Trasferte remote",
        trasferte_desc: "Permette di raggiungere località remote dalla base dell'agente pianificandole in più giorni per sostenere il viaggio di andata e ritorno per visitare il cliente lontano dalla sede",
        label_giorni_trasferta: "Massimo di giornate per trasferta",
        label_company: "Azienda",
        company_select_default: "Prima carica un file Excel/CSV...",
        no_groups_detected: "Nessun gruppo rilevato",
        agent_departure: "Partenza agente:",
        btn_edit: "Modifica",
        card_start_title: "Punto di Partenza Agente",
        card_start_desc: "Indica la sede o l'indirizzo da cui parte l'agente per le visite di questa azienda:",
        label_start_address: "Via / Indirizzo completo",
        placeholder_start_address: "es. Via del Corso 120, Roma",
        or_coords: "oppure coordinate GPS",
        label_start_lat: "Latitudine",
        label_start_lon: "Longitudine",
        btn_save_start_loc: "Salva Punto di Partenza",
        btn_submit: "Avvia pianificazione",
        btn_submit_loading: "Caricamento aziende...",
        btn_submit_calculating: "Calcolo",
        kpi_recovered_title: "Fatturato Recuperabile Totale",
        kpi_recovered_sub: "Valore stimato visite programmate",
        kpi_potential_title: "Fatturato Potenziale Globale",
        kpi_potential_sub_prefix: "Portafoglio totale per",
        kpi_visits_title: "Visite Pianificate",
        kpi_visits_sub: "Clienti inseriti nel calendario",
        kpi_recovery_title: "Tasso di Recupero",
        kpi_recovery_sub: "Fatturato recuperato su potenziale",
        map_overlay_initial: "Mappa Interattiva: Carica il file e seleziona l'azienda da ottimizzare",
        map_overlay_optimizing: "Ottimizzazione visite in corso per",
        legend_depot: "Sede Agente",
        legend_planned: "Visita Programmata",
        legend_unplanned: "Altro Cliente Azienda",
        table_title: "Agenda Ottimizzata Consigliata",
        table_subtitle_default: "Piano visite per l'azienda selezionata",
        th_date: "Data",
        th_day: "Giorno",
        th_time: "Orario",
        th_client: "Cliente / Ragione Sociale",
        th_group: "Gruppo",
        th_city: "Città",
        th_address: "Indirizzo",
        th_revenue: "Fatturato Stimato",
        no_break: "Nessuna pausa",
        no_break_lower: "nessuna pausa",
        break_label: "Pausa",
        break_label_lower: "pausa",
        hq_title: "Sede Partenza Agente",
        gps_coords: "Coordinate GPS:",
        planned_visit: "Visita Programmata",
        unplanned_client: "⚪ Cliente non pianificato nel periodo",
        alert_select_file: "Seleziona prima un file Excel o CSV.",
        alert_select_company: "Seleziona un'azienda da ottimizzare.",
        alert_geocode_req_1: "Devi geocodificare un indirizzo di partenza valido (con coordinate) per",
        alert_geocode_req_2: "prima di continuare. Salvati o ricontrolla la sede di partenza!",
        alert_addr_or_coords: "Inserisci un indirizzo oppure entrambe le coordinate (Latitudine e Longitudine).",
        searching_coords: "Ricerca nuove coordinate per",
        geocoding_in_progress: "Geocodifica in corso... ⏳",
        acquired: "✓ Acquisito",
        civic: "Civico",
        addr_not_found: "Indirizzo non trovato su OpenStreetMap. Inserisci manualmente le coordinate GPS.",
        geocode_error: "Errore durante la geocodifica della via. Inserisci manualmente le coordinate.",
        departure_set_for: "Punto di partenza impostato per",
        departure_click_edit: "(clicca per modificare)",
        set_departure_for: "Imposta punto di partenza per",
        progress_geocoding_title: "Geocodifica Indirizzi in Corso",
        progress_geocoding_desc: "Localizzazione dei punti visita e normalizzazione toponomastica...",
        progress_optimizing_title: "Ottimizzazione Visite in Corso",
        progress_optimizing_desc: "Algoritmo ALNS e pianificazione calendario...",
        progress_initializing: "Inizializzazione...",
        progress_solving_routes: "Calcolo tragitti e vincoli orari..."
    },
    ENGLISH: {
        app_title: "GeoAnalytics Planner",
        sidebar_title: "Optimization Parameters",
        label_dataset: "Upload Dataset (Excel/CSV)",
        btn_choose_file: "Choose file",
        no_file_chosen: "No file chosen",
        label_start_date: "Scenario Start Date",
        label_days: "Available Business Days",
        label_hours: "Required Hours per Visit",
        time_settings_tooltip: "Click to expand or collapse time and break settings",
        time_settings_label: "Working Hours & Break",
        time_section_daily: "Daily Schedule",
        label_work_start: "Work Start",
        label_work_end: "Work End",
        time_section_lunch: "Flexible Lunch Break",
        label_lunch_earliest: "Earliest Start",
        label_lunch_latest_start: "Latest Start",
        label_lunch_duration: "Break Duration (minutes)",
        net_work_hours_label: "Net working hours:",
        per_day: "h / day",
        trasferte_label: "Plan Remote Trips",
        trasferte_desc: "Allows reaching remote locations from the agent base by planning multi-day trips for round trips to distant clients",
        label_giorni_trasferta: "Max days per trip",
        label_company: "Company",
        company_select_default: "Upload an Excel/CSV file first...",
        no_groups_detected: "No groups detected",
        agent_departure: "Agent departure:",
        btn_edit: "Edit",
        card_start_title: "Agent Departure Point",
        card_start_desc: "Specify the headquarters or address where the agent departs for visits of this company:",
        label_start_address: "Street / Full address",
        placeholder_start_address: "e.g. 10 Downing Street or Via del Corso 120, Rome",
        or_coords: "or GPS coordinates",
        label_start_lat: "Latitude",
        label_start_lon: "Longitude",
        btn_save_start_loc: "Save Departure Point",
        btn_submit: "Start Planning",
        btn_submit_loading: "Loading companies...",
        btn_submit_calculating: "Calculating",
        kpi_recovered_title: "Total Recoverable Revenue",
        kpi_recovered_sub: "Estimated value of planned visits",
        kpi_potential_title: "Global Potential Revenue",
        kpi_potential_sub_prefix: "Total portfolio for",
        kpi_visits_title: "Planned Visits",
        kpi_visits_sub: "Clients scheduled in calendar",
        kpi_recovery_title: "Recovery Rate",
        kpi_recovery_sub: "Recovered revenue over potential",
        map_overlay_initial: "Interactive Map: Upload file and select company to optimize",
        map_overlay_optimizing: "Optimizing visits in progress for",
        legend_depot: "Agent Departure",
        legend_planned: "Planned Visit",
        legend_unplanned: "Other Company Client",
        table_title: "Recommended Optimized Agenda",
        table_subtitle_default: "Visit plan for the selected company",
        th_date: "Date",
        th_day: "Day",
        th_time: "Time",
        th_client: "Client / Company Name",
        th_group: "Group",
        th_city: "City",
        th_address: "Address",
        th_revenue: "Estimated Revenue",
        no_break: "No break",
        no_break_lower: "no break",
        break_label: "Break",
        break_label_lower: "break",
        hq_title: "Agent Departure",
        gps_coords: "GPS Coordinates:",
        planned_visit: "Planned Visit",
        unplanned_client: "⚪ Client not planned in this period",
        alert_select_file: "Please select an Excel or CSV file first.",
        alert_select_company: "Please select a company to optimize.",
        alert_geocode_req_1: "You must geocode a valid starting address (with coordinates) for",
        alert_geocode_req_2: "before continuing. Save or check the departure location!",
        alert_addr_or_coords: "Please enter an address or both coordinates (Latitude and Longitude).",
        searching_coords: "Searching new coordinates for",
        geocoding_in_progress: "Geocoding in progress... ⏳",
        acquired: "✓ Acquired",
        civic: "Civic",
        addr_not_found: "Address not found on OpenStreetMap. Please enter GPS coordinates manually.",
        geocode_error: "Error during street geocoding. Please enter coordinates manually.",
        departure_set_for: "Departure point set for",
        departure_click_edit: "(click to edit)",
        set_departure_for: "Set departure point for",
        progress_geocoding_title: "Geocoding Addresses",
        progress_geocoding_desc: "Localizing visit points and normalizing street names...",
        progress_optimizing_title: "Route Optimization in Progress",
        progress_optimizing_desc: "Running ALNS algorithm and schedule planning...",
        progress_initializing: "Initializing...",
        progress_solving_routes: "Solving routes & time windows..."
    }
};

const DAY_TRANSLATIONS = {
    'Lunedì': 'Monday',
    'Martedì': 'Tuesday',
    'Mercoledì': 'Wednesday',
    'Giovedì': 'Thursday',
    'Venerdì': 'Friday',
    'Sabato': 'Saturday',
    'Domenica': 'Sunday'
};

let currentLanguage = localStorage.getItem('geoanalytics_lang') || 'ITALIANO';
if (currentLanguage !== 'ITALIANO' && currentLanguage !== 'ENGLISH') {
    currentLanguage = 'ITALIANO';
}

function t(key) {
    const dict = TRANSLATIONS[currentLanguage] || TRANSLATIONS.ITALIANO;
    return dict[key] !== undefined ? dict[key] : (TRANSLATIONS.ITALIANO[key] || key);
}

function formatScheduleDay(dayStr, lang) {
    if (!dayStr) return '';
    if (lang !== 'ENGLISH') return dayStr;
    let res = dayStr;
    for (const [it, en] of Object.entries(DAY_TRANSLATIONS)) {
        res = res.replace(it, en);
    }
    res = res.replace('Partenza trasferta', 'Trip departure')
             .replace('partenza trasferta', 'trip departure')
             .replace(/(\+\d+)gg/, '$1d');
    return res;
}

function getCurrencyFormatter() {
    return new Intl.NumberFormat(currentLanguage === 'ENGLISH' ? 'en-US' : 'it-IT', {
        style: 'currency',
        currency: 'EUR'
    });
}

function updateFileInputDisplay() {
    const fileInput = document.getElementById('dataset');
    const nameSpan = document.getElementById('dataset-name');
    if (!nameSpan) return;

    if (fileInput && fileInput.files && fileInput.files.length > 0) {
        nameSpan.textContent = fileInput.files[0].name;
        nameSpan.classList.add('has-file');
        nameSpan.removeAttribute('data-i18n');
    } else {
        nameSpan.classList.remove('has-file');
        nameSpan.setAttribute('data-i18n', 'no_file_chosen');
        nameSpan.textContent = t('no_file_chosen');
    }
}

function applyTranslations() {
    const dict = TRANSLATIONS[currentLanguage] || TRANSLATIONS.ITALIANO;

    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (dict[key] !== undefined) {
            el.textContent = dict[key];
        }
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (dict[key] !== undefined) {
            el.placeholder = dict[key];
        }
    });

    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (dict[key] !== undefined) {
            el.title = dict[key];
        }
    });

    const langSelect = document.getElementById('language-selector');
    if (langSelect && langSelect.value !== currentLanguage) {
        langSelect.value = currentLanguage;
    }

    document.documentElement.lang = (currentLanguage === 'ENGLISH') ? 'en' : 'it';

    updateFileInputDisplay();

    updateTimeSummaryAndCalculations();

    const compSelect = document.getElementById('company-select');
    if (compSelect && compSelect.value) {
        updateStartLocationUI(compSelect.value);
    }

    if (activeScenarioData) {
        renderScenario(activeScenarioData);
    } else {
        const selectedCompany = compSelect ? compSelect.value : null;
        if (selectedCompany) {
            renderCompanyClientsOnMap(selectedCompany, false);
        }
    }
}

function setLanguage(lang) {
    if (lang !== 'ITALIANO' && lang !== 'ENGLISH') return;
    currentLanguage = lang;
    try {
        localStorage.setItem('geoanalytics_lang', lang);
    } catch (e) {}
    applyTranslations();
}

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

    const isEn = (currentLanguage === 'ENGLISH');
    const popupHtml = `
        <div style="font-family:'Inter',sans-serif; min-width:220px; padding:4px;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                <span style="font-size:24px;">🏠</span>
                <div>
                    <h4 style="margin:0; color:#0f172a; font-size:1rem; font-weight:700;">${isEn ? 'Agent Departure' : 'Sede Partenza Agente'}</h4>
                    <span style="font-size:0.75rem; font-weight:700; color:white; padding:2px 8px; border-radius:4px; background:${getCompanyColor(company)};">${company}</span>
                </div>
            </div>
            ${address ? `<div style="font-size:0.85rem; color:#334155; margin-bottom:6px; font-weight:500;">📍 ${address}</div>` : ''}
            <div style="background:#f8fafc; border:1px solid #e2e8f0; padding:6px 10px; border-radius:8px; font-size:0.8rem; color:#64748b;">
                ${isEn ? 'GPS Coordinates:' : 'Coordinate GPS:'} <strong style="color:#0f172a;">${latNum.toFixed(5)}, ${lonNum.toFixed(5)}</strong>
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
    window.renderedMapMarkers = [];
    if(window.lastHighlightedRow) { window.lastHighlightedRow.style.backgroundColor = ''; window.lastHighlightedRow = null; }
        showStartHouseOnMap(null, null, null, null);
        const legend = document.getElementById('map-legend');
        if (legend) legend.style.display = 'none';
        return;
    }

    const clients = uploadedCompanyClients[company] || [];
    markersLayer.clearLayers();
    window.renderedMapMarkers = [];
    if(window.lastHighlightedRow) { window.lastHighlightedRow.style.backgroundColor = ''; window.lastHighlightedRow = null; }

    const color = getCompanyColor(company);
    const formatter = getCurrencyFormatter();

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
    window.renderedMapMarkers = [];
    if(window.lastHighlightedRow) { window.lastHighlightedRow.style.backgroundColor = ''; window.lastHighlightedRow = null; }
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
    const isEn = (currentLanguage === 'ENGLISH');
    if (loc) {
        if (editBtn) {
            editBtn.classList.add('has-location');
            editBtn.title = isEn ? `Departure point set for ${company} (click to edit)` : `Punto di partenza impostato per ${company} (clicca per modificare)`;
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
            editBtn.title = isEn ? `Set departure point for ${company}` : `Imposta punto di partenza per ${company}`;
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
    const lunchDurationInput = document.getElementById('lunch-duration');
    const lunchDuration = (lunchDurationInput && lunchDurationInput.value !== '') ? lunchDurationInput.value : '60';
    
    // Trasferte
    const enTr = document.getElementById('enable-trasferte')?.checked ? '1' : '0';
    const ggTr = document.getElementById('giorni-trasferta')?.value || '3';

    return `${fileName}__${company}__${days}__${hours}__${startDate}__${locStr}__${workStart}__${workEnd}__${lunchEarliest}__${lunchLatestStart}__${lunchDuration}__${enTr}_${ggTr}`;
}

// Listener cambio file Excel/CSV
document.getElementById('dataset').addEventListener('change', async (e) => {
    updateFileInputDisplay();
    const file = e.target.files[0];
    if (!file) return;

    clientScenarioCache.clear();
    const formData = new FormData();
    formData.append('file', file);

    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = (currentLanguage === 'ENGLISH') ? 'Loading companies...' : 'Caricamento aziende...';

    startProgressPolling('geocoding');

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
        stopProgressPolling();
        submitBtn.disabled = false;
        submitBtn.textContent = (currentLanguage === 'ENGLISH') ? 'Start Planning' : 'Avvia pianificazione';
    }
});

function populateCompanySelector(companies) {
    const mainSelect = document.getElementById('company-select');
    mainSelect.innerHTML = '';

    if (!companies || companies.length === 0) {
        mainSelect.innerHTML = `<option value="" disabled selected>${currentLanguage === 'ENGLISH' ? 'No groups detected' : 'Nessun gruppo rilevato'}</option>`;
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

    const isEn = (currentLanguage === 'ENGLISH');
    if (!hasAddress && (!hasLat || !hasLon)) {
        msg.className = 'card-msg error';
        msg.textContent = isEn ?
            'Please enter an address or both coordinates (Latitude and Longitude).' :
            'Inserisci un indirizzo oppure entrambe le coordinate (Latitudine e Longitudine).';
        msg.style.display = 'block';
        return;
    }

    let finalLat = hasLat ? parseFloat(latVal) : null;
    let finalLon = hasLon ? parseFloat(lonVal) : null;

    const isAddressChanged = (address !== currentEditingOriginalAddress);

    // Se l'utente ha inserito la via e (è cambiata rispetto all'originale oppure mancano le coordinate), geocodifica sempre!
    if (hasAddress && (isAddressChanged || finalLat === null || finalLon === null)) {
        saveBtn.disabled = true;
        saveBtn.textContent = isEn ? 'Geocoding in progress... ⏳' : 'Geocodifica in corso... ⏳';
        msg.className = 'card-msg';
        msg.style.display = 'block';
        msg.textContent = isEn ? `Searching coordinates for "${address}"...` : `Ricerca nuove coordinate per "${address}"...`;

        try {
            const resp = await fetch(`${API_BASE}/api/geocode?address=${encodeURIComponent(address)}`);
            const geoData = await resp.json();
            if (geoData.success && geoData.lat !== undefined && geoData.lon !== undefined) {
                finalLat = geoData.lat;
                finalLon = geoData.lon;
                latInput.value = finalLat;
                lonInput.value = finalLon;
                msg.className = 'card-msg success';
                const civWord = isEn ? 'Civic' : 'Civico';
                const civInfo = geoData.house_number ? ` (${civWord} ${geoData.house_number}${geoData.house_number_exact ? ' ✓' : ''})` : '';
                const foundDesc = geoData.display_name ? ` - ${geoData.display_name.split(',').slice(0, 2).join(',')}` : '';
                const acqWord = isEn ? '✓ Acquired' : '✓ Acquisito';
                msg.textContent = `${acqWord}${civInfo}: ${finalLat.toFixed(5)}, ${finalLon.toFixed(5)}${foundDesc}`;

            } else {
                saveBtn.disabled = false;
                saveBtn.textContent = isEn ? 'Save Departure Point' : 'Salva Punto di Partenza';
                msg.className = 'card-msg error';
                msg.textContent = geoData.message || (isEn ? 'Address not found on OpenStreetMap. Please enter GPS coordinates manually.' : 'Indirizzo non trovato su OpenStreetMap. Inserisci manualmente le coordinate GPS.');
                return;
            }
        } catch (err) {
            saveBtn.disabled = false;
            saveBtn.textContent = isEn ? 'Save Departure Point' : 'Salva Punto di Partenza';
            msg.className = 'card-msg error';
            msg.textContent = isEn ? 'Error during street geocoding. Please enter coordinates manually.' : 'Errore durante la geocodifica della via. Inserisci manualmente le coordinate.';
            return;
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = isEn ? 'Save Departure Point' : 'Salva Punto di Partenza';
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
    const lunchDurationInput = document.getElementById('lunch-duration');
    const pause = (lunchDurationInput && lunchDurationInput.value !== '') ? lunchDurationInput.value : '60';

    const summaryEl = document.getElementById('time-settings-summary');
    if (summaryEl) {
        const pauseNum = parseInt(pause, 10);
        let pauseLabel;
        if (currentLanguage === 'ENGLISH') {
            pauseLabel = (!isNaN(pauseNum) && pauseNum === 0) ? 'No break' : `Break ${pause}m`;
        } else {
            pauseLabel = (!isNaN(pauseNum) && pauseNum === 0) ? 'Nessuna pausa' : `Pausa ${pause}m`;
        }
        summaryEl.textContent = `${start} - ${end} • ${pauseLabel}`;
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
            if (cfg.lunch_duration_minutes !== undefined && cfg.lunch_duration_minutes !== null && document.getElementById('lunch-duration')) {
                document.getElementById('lunch-duration').value = cfg.lunch_duration_minutes;
            }
            updateTimeSummaryAndCalculations();
        }
    } catch (e) {
        console.warn('Config endpoint non raggiungibile, utilizzo valori predefiniti:', e);
    }
}
loadConfigDefaults();

function syncMaxGiorniTrasferta() {
    const daysEl = document.getElementById('days');
    const trasfertaEl = document.getElementById('giorni-trasferta');
    if (!daysEl || !trasfertaEl) return;
    const daysVal = parseInt(daysEl.value, 10);
    if (!isNaN(daysVal) && daysVal >= 1) {
        trasfertaEl.max = daysVal;
    }
}

// Se l'utente modifica parametri già precedentemente calcolati in questa sessione, mostra dalla cache
['days', 'hours', 'start-date', 'work-start', 'work-end', 'lunch-earliest', 'lunch-latest-start', 'lunch-duration', 'enable-trasferte', 'giorni-trasferta'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', () => {
        if (id === 'days') {
            syncMaxGiorniTrasferta();
        }
        updateTimeSummaryAndCalculations();
        const selectedCompany = document.getElementById('company-select').value;
        if (!selectedCompany) return;
        const key = getCacheKey(selectedCompany);
        if (clientScenarioCache.has(key)) {
            renderScenario(clientScenarioCache.get(key));
        }
    });
    el.addEventListener('input', () => {
        if (id === 'days') {
            syncMaxGiorniTrasferta();
        }
        updateTimeSummaryAndCalculations();
    });
});
syncMaxGiorniTrasferta();

const analyzeForm = document.getElementById('analyze-form');
if (analyzeForm) {
    analyzeForm.addEventListener('submit', (e) => {
        e.preventDefault();
        performAnalysis();
    });
}

const submitBtnEl = document.getElementById('submit-btn');
if (submitBtnEl) {
    submitBtnEl.addEventListener('click', (e) => {
        // Se non è già in submit, avvia analisi
        if (analyzeForm) {
            e.preventDefault();
            performAnalysis();
        }
    });
}

let progressInterval = null;
let currentProgressMode = 'geocoding';

function startProgressPolling(mode = 'geocoding') {
    currentProgressMode = mode;
    const overlay = document.getElementById('progress-overlay');
    const barFill = document.getElementById('progress-bar-fill');
    const title = document.getElementById('progress-title');
    const icon = document.getElementById('progress-icon');

    if (overlay) overlay.style.display = 'flex';

    if (mode === 'optimizing') {
        if (icon) icon.textContent = '⚡';
        if (title) title.textContent = t('progress_optimizing_title');
        if (barFill) barFill.style.width = '100%';
    } else {
        if (icon) icon.textContent = '📍';
        if (title) title.textContent = t('progress_geocoding_title');
        if (barFill) barFill.style.width = '0%';
    }

    if (progressInterval) clearInterval(progressInterval);

    const poll = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/progress`);
            if (!res.ok) return;
            const p = await res.json();
            if (!p.active) return;

            if (currentProgressMode === 'optimizing' || p.stage === 'optimizing') {
                if (title) title.textContent = t('progress_optimizing_title');
                if (icon) icon.textContent = '⚡';
                if (barFill) barFill.style.width = '100%';
            } else if (p.stage === 'geocoding' && currentProgressMode !== 'optimizing') {
                if (title) title.textContent = t('progress_geocoding_title');
                if (icon) icon.textContent = '📍';
                const total = p.total || 1;
                const current = p.current || 0;
                const pct = Math.min(100, Math.round((current / total) * 100));
                if (barFill) barFill.style.width = `${pct}%`;
            }
        } catch (e) {
            // Polling non-bloccante
        }
    };

    poll();
    progressInterval = setInterval(poll, 250);
}

function stopProgressPolling() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    const overlay = document.getElementById('progress-overlay');
    if (overlay) overlay.style.display = 'none';
}

async function performAnalysis() {
    const isEn = (currentLanguage === 'ENGLISH');
    const fileInput = document.getElementById('dataset');
    if (fileInput.files.length === 0) {
        alert(isEn ? 'Please select an Excel or CSV file first.' : 'Seleziona prima un file Excel o CSV.');
        return;
    }

    const companySelect = document.getElementById('company-select');
    const selectedCompany = companySelect.value;
    if (!selectedCompany) {
        alert(isEn ? 'Please select a company to optimize.' : 'Seleziona un\'azienda da ottimizzare.');
        return;
    }

    const startLoc = getAgentStartLocation(selectedCompany);
    if (!startLoc || startLoc.lat === null || startLoc.lon === null) {
        openStartLocCard(selectedCompany);
        const msg = document.getElementById('start-loc-msg');
        msg.className = 'card-msg error';
        msg.textContent = isEn ?
            `You must geocode a valid starting address (with coordinates) for ${selectedCompany} before continuing. Save or check the departure location!` :
            `Devi geocodificare un indirizzo di partenza valido (con coordinate) per ${selectedCompany} prima di continuare. Salvati o ricontrolla la sede di partenza!`;
        msg.style.display = 'block';
        return;
    }

    const cacheKey = getCacheKey(selectedCompany);
    if (clientScenarioCache.has(cacheKey)) {
        renderScenario(clientScenarioCache.get(cacheKey));
        return;
    }

    const btn = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = isEn ? `Calculating ${selectedCompany}...` : `Calcolo ${selectedCompany}...`;

    const overlay = document.getElementById('map-overlay');
    if (overlay) overlay.style.display = 'none';

    startProgressPolling('optimizing');

    try {
        const workStart = document.getElementById('work-start')?.value || '09:00';
        const workEnd = document.getElementById('work-end')?.value || '18:00';
        const lunchEarliest = document.getElementById('lunch-earliest')?.value || '12:00';
        const lunchLatestStart = document.getElementById('lunch-latest-start')?.value || '14:00';
        const lunchDurationInput = document.getElementById('lunch-duration');
        const lunchDuration = (lunchDurationInput && lunchDurationInput.value !== '') ? lunchDurationInput.value : '60';
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
            const maxDaysVal = parseInt(document.getElementById('days').value, 10) || 30;
            let trasfertaVal = parseInt(document.getElementById('giorni-trasferta').value, 10) || 3;
            if (trasfertaVal > maxDaysVal) {
                trasfertaVal = maxDaysVal;
            }
            formData.append('max_giorni_trasferta', trasfertaVal);
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
        stopProgressPolling();
        btn.disabled = false;
        btn.textContent = isEn ? 'Start Planning' : 'Avvia pianificazione';
    }
}

function renderScenario(data) {
    activeScenarioData = data;
    const comp = data.target_company;
    const kpis = data.kpis || {};
    const formatter = getCurrencyFormatter();
    const isEn = (currentLanguage === 'ENGLISH');

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
    const lunchDurationInput = document.getElementById('lunch-duration');
    const timeInfo = data.time_params || {
        work_start: document.getElementById('work-start')?.value || '09:00',
        work_end: document.getElementById('work-end')?.value || '18:00',
        lunch_duration_minutes: (lunchDurationInput && lunchDurationInput.value !== '') ? lunchDurationInput.value : 60
    };
    const durMin = parseInt(timeInfo.lunch_duration_minutes, 10);
    const pauseLabel = isEn ?
        ((!isNaN(durMin) && durMin === 0) ? 'no break' : `${timeInfo.lunch_duration_minutes}m break`) :
        ((!isNaN(durMin) && durMin === 0) ? 'nessuna pausa' : `pausa ${timeInfo.lunch_duration_minutes}m`);

    const daysCount = data.days || document.getElementById('days')?.value || 30;

    if (isEn) {
        subtitle.innerHTML = `
            <div>Plan for: <strong style="color:${getCompanyColor(comp)}">${comp}</strong> (${daysCount} work days)</div>
            <div>Recoverable Revenue: <strong>${formatter.format(kpis.recovered_revenue || 0)}</strong></div>
            <div>${kpis.visits || 0}/${kpis.geocoded_clients || 0} total visits (Hours: <strong>${timeInfo.work_start} - ${timeInfo.work_end}</strong>, ${pauseLabel})</div>
            <div>Actual Calendar Span: <strong>${kpis.total_days_spanned || 0} days</strong> utilized to schedule all visits</div>
            ${kpis.is_fallback === true ? '<div style="color: #ef4444; margin-top: 5px; font-weight: 600;"><span style="font-size:1.1rem;">⚠️</span> INACCURATE TRAVEL DETAILS DUE TO MISSING CONNECTION TO OSRM SERVER</div>' : ''}
            <div>${droppedCount} visits without valid coordinates</div>
        `;
    } else {
        subtitle.innerHTML = `
            <div>Piano per: <strong style="color:${getCompanyColor(comp)}">${comp}</strong> (${daysCount} giorni lavorativi)</div>
            <div>Fatturato Recuperabile: <strong>${formatter.format(kpis.recovered_revenue || 0)}</strong></div>
            <div>${kpis.visits || 0}/${kpis.geocoded_clients || 0} visite totali (Orario: <strong>${timeInfo.work_start} - ${timeInfo.work_end}</strong>, ${pauseLabel})</div>
            <div>Occupazione Calendario: <strong>${kpis.total_days_spanned || 0} giornate</strong> effettivamente necessarie per schedulare tutto</div>
            ${kpis.is_fallback === true ? '<div style="color: #ef4444; margin-top: 5px; font-weight: 600;"><span style="font-size:1.1rem;">⚠️</span> DETTAGLI DI VIAGGIO NON ACCURATI POICHÉ CONNESSIONE AL SERVER OSRM ASSENTE</div>' : ''}
            <div>${droppedCount} visite senza coordinate valide</div>
        `;
    }

    // 3. Render Mappa
    markersLayer.clearLayers();
    window.renderedMapMarkers = [];
    if(window.lastHighlightedRow) { window.lastHighlightedRow.style.backgroundColor = ''; window.lastHighlightedRow = null; }
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
            const formattedDay = formatScheduleDay(point.day, currentLanguage);
            statusBadgeHtml = `
                <div style="background:#f1f5f9; padding:8px; border-radius:6px; margin-bottom:8px;">
                    <strong style="color:#0f172a; display:block; margin-bottom:2px; font-size:0.8rem;">${isEn ? 'Planned Visit' : 'Visita Programmata'}</strong>
                    <div style="color:#3b82f6; font-weight:600; font-size:0.9rem;">${point.date} (${formattedDay})</div>
                    <div style="color:#64748b; font-size:0.82rem;">${point.time}</div>
                </div>
            `;
        } else {
            statusBadgeHtml = `
                <div style="background:#f8fafc; border:1px dashed #cbd5e1; padding:6px 8px; border-radius:6px; margin-bottom:8px;">
                    <span style="color:#64748b; font-size:0.8rem; font-weight:600;">${isEn ? '⚪ Client not planned in this period' : '⚪ Cliente non pianificato nel periodo'}</span>
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

        const marker = L.marker([point.lat, point.lon], { icon, zIndexOffset: zIndex })
            .bindPopup(popupContent)
            .addTo(markersLayer);
            
        marker.clientName = point.name;
        marker.originalIcon = icon;
        marker.originalZIndex = zIndex;
        window.renderedMapMarkers.push(marker);
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
        try {
            const group = new L.featureGroup(allMarkers);
            const bounds = group.getBounds();
            if (bounds && bounds.isValid && bounds.isValid()) {
                map.fitBounds(bounds.pad(0.12));
            }
        } catch (e) {
            console.warn('Errore calcolo limiti mappa:', e);
        }
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
        const dayFormatted = formatScheduleDay(row['Giorno'], currentLanguage);
        tr.innerHTML = `
            <td style="font-weight:600; white-space:nowrap;">${row['Data Visita']}</td>
            <td style="white-space:nowrap;"><span style="background:rgba(255,255,255,0.08);padding:4px 8px;border-radius:4px;font-size:0.8rem;">${dayFormatted}</span></td>
            <td style="white-space:nowrap;"><span style="color:#38bdf8;font-weight:600;font-size:0.85rem;white-space:nowrap;display:inline-block;letter-spacing:0.02em;">${row['Orario']}</span></td>
            <td><strong>${row['Cliente']}</strong></td>
            <td>${row['Città']}</td>
            <td><small style="color:#94a3b8;">${row['Indirizzo']}</small></td>
            <td style="color:var(--accent); font-weight:700; white-space:nowrap;">${formatter.format(row['Fatturato Stimato'])}</td>
        `;
        
        tr.style.cursor = 'pointer';
        tr.title = isEn ? "Click to view on map" : "Clicca per mostrare sulla mappa";
        tr.addEventListener('click', () => {
            // Restore previous row
            if(window.lastHighlightedRow) {
                window.lastHighlightedRow.style.backgroundColor = '';
            }
            tr.style.backgroundColor = 'rgba(59, 130, 246, 0.15)';
            window.lastHighlightedRow = tr;
        
            // Restore previous markers
            window.renderedMapMarkers.forEach(m => {
                if (m.isHighlighted) {
                    m.setIcon(m.originalIcon);
                    m.setZIndexOffset(m.originalZIndex);
                    m.isHighlighted = false;
                }
            });
            
            // Highlight selected
            const target = window.renderedMapMarkers.find(m => m.clientName === row['Cliente']);
            if (target) {
                const highlightIcon = L.divIcon({
                    html: '<div style="width: 22px; height: 22px; border-radius: 50%; background: #facc15; border: 3px solid white; display: inline-block; box-shadow: 0 0 16px rgba(250, 204, 21, 0.8);"></div>',
                    className: 'custom-marker',
                    iconSize: [22, 22],
                    iconAnchor: [11, 11]
                });
                target.setIcon(highlightIcon);
                target.setZIndexOffset(9999);
                target.isHighlighted = true;
                target.openPopup();
                map.panTo(target.getLatLng());
            }
        });
        
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

// Inizializzazione Selettore Lingua
const langSelectorEl = document.getElementById('language-selector');
if (langSelectorEl) {
    langSelectorEl.value = currentLanguage;
    langSelectorEl.addEventListener('change', (e) => {
        setLanguage(e.target.value);
    });
}

// Applica le traduzioni iniziali
applyTranslations();
