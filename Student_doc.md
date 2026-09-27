# Specifiche del Sistema Rilasciato

## Architettura del Sistema
Il sistema è sviluppato seguendo un approccio distribuito a **Microservizi**, nettamente separato tra Frontend (Client) e Backend (API).

- **Backend (API):** Sviluppato in Python con il framework `FastAPI`. Gestisce l'elaborazione dei dataset (`pandas`), la geocodifica spaziale, e calcola l'algoritmo di ottimizzazione (What-If analysis) per restituire JSON al client. Gira sulla porta `8000`.
- **Frontend (Interfaccia):** Web Application moderna sviluppata in HTML5, CSS3 Vanilla (con un design Premium Glassmorphism e Dark Mode) e JavaScript. Integra `Leaflet.js` per il rendering della mappa vettoriale dei clienti. Servito tramite `Nginx` sulla porta `8080`.

## Infrastruttura (IaC)
- **Docker e Docker Compose:** Utilizzati per definire e orchestrare in maniera indipendente i container `frontend` e `backend`.
- **.env**: Parametri di sistema configurabili agilmente dall'infrastruttura (ore di default).

## Setup & Avvio
Per eseguire il progetto (che emulerà un server on-premise/cloud), spostarsi nella cartella `source` ed eseguire:
```bash
docker-compose up --build
```
Una volta avviato:
- **Interfaccia Web**: `http://localhost:8080`
- **Documentazione API (Swagger)**: `http://localhost:8000/docs`
