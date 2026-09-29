# Speaker Notes - Sales Visit Optimizer

## Slide 1: Business Problem

### 1. COSA SIGNIFICA
Spieghiamo qual è la sfida. Abbiamo i dati dal gestionale (ERP) ma poco tempo per visitarli tutti.

### 2. COSA DIRE
"Buongiorno. Questo progetto aiuta i direttori commerciali a pianificare le visite dei propri agenti. Partiamo dai dati estratti dal gestionale aziendale. Essendo il tempo limitato, dobbiamo decidere chi visitare, quando e in che ordine, cercando di recuperare il massimo fatturato possibile. Il sistema supporta l'analisi what-if, permettendo di testare scenari con durate di visita diverse."

### 3. TERMINI DA CONOSCERE
- **ERP**: Enterprise Resource Planning, il gestionale dell'azienda (es. SAP) da cui provengono i dati.

## Slide 2: Main User Stories (1/2)

### 1. COSA SIGNIFICA
Elenchiamo le prime necessità pratiche degli utenti con la loro formulazione originale.

### 2. COSA DIRE
"Abbiamo raccolto i requisiti in vere e proprie storie utente. L'utente vuole poter caricare l'Excel e vedere subito su mappa i clienti della sua azienda in modo da analizzare solo i dati rilevanti e capire la loro distribuzione geografica."

### 3. TERMINI DA CONOSCERE
Nessuno.

## Slide 3: Main User Stories (2/2)

### 1. COSA SIGNIFICA
Altre storie utente importanti riguardanti l'ottimizzazione.

### 2. COSA DIRE
"Inoltre, l'utente vuole poter impostare la data di inizio della campagna. Il sistema deve restituirgli un'agenda suggerita e il valore del fatturato recuperabile. Infine, è essenziale poter cambiare il numero di giorni disponibili per confrontare simulazioni diverse."

### 3. TERMINI DA CONOSCERE
Nessuno.

## Slide 4: Non-Functional Requirements

### 1. COSA SIGNIFICA
Sono le regole "tecniche" e di usabilità.

### 2. COSA DIRE
"Dal punto di vista tecnico e di usabilità, il sistema deve essere semplice, deve poter riutilizzare gli Excel degli anni futuri e deve essere facilmente installabile su altri computer. Inoltre, deve sempre usare vere coordinate geografiche."

### 3. TERMINI DA CONOSCERE
Nessuno.

## Slide 5: From Requirements to Interface

### 1. COSA SIGNIFICA
I tre mockup grafici originali.

### 2. COSA DIRE
"Prima di scrivere il codice abbiamo disegnato queste bozze: una schermata di caricamento e impostazione parametri, la mappa per i risultati e infine l'agenda con le visite pianificate."

### 3. TERMINI DA CONOSCERE
- **Mockup**: Disegno preliminare dell'interfaccia grafica.

## Slide 6: Software Architecture

### 1. COSA SIGNIFICA
L'architettura del sistema spiegata in macro blocchi chiari.

### 2. COSA DIRE
"Il sistema è diviso in tre blocchi. Dal browser usiamo il Frontend, costruito in HTML e JavaScript, dove la mappa è gestita da Leaflet e la pagina è servita da Nginx. Dietro le quinte c'è il Backend, scritto in Python con FastAPI, che elabora i dati e lancia l'ottimizzazione. Questo backend chiama servizi esterni: Nominatim per trovare le coordinate e OSRM per stimare i tempi di guida tra un cliente e l'altro."

### 3. TERMINI DA CONOSCERE
- **Frontend / Backend**: Il frontend è ciò che l'utente vede, il backend è il motore nascosto che fa i calcoli.
- **FastAPI**: Libreria Python per creare l'interfaccia di comunicazione (API) del backend.
- **Nginx**: Il web server che invia la pagina web al browser.
- **Leaflet**: La libreria per far funzionare le mappe interattive.
- **Nominatim / OSRM**: Nominatim trasforma un indirizzo in coordinate. OSRM è usato per avere una stima del tempo necessario per viaggiare da un cliente all'altro (driving times).

## Slide 7: Docker Deployment

### 1. COSA SIGNIFICA
Spiega come impacchettare il software.

### 2. COSA DIRE
"Per l'installazione usiamo Docker, che impacchetta l'applicazione. Con il tool Docker Compose facciamo partire sia frontend che backend assieme. Il frontend ascolta sulla porta 8080, il backend sulla 8000. Il grandissimo vantaggio è che questo setup girerà sempre nello stesso modo su qualsiasi altro computer. (Nota tecnica per l'esposizione: per lanciare il tutto noi eseguiamo da terminale il comando 'docker compose up --build')."

### 3. TERMINI DA CONOSCERE
- **Docker**: Sistema che crea "contenitori" isolati con l'app e tutto il necessario per farla funzionare.
- **Docker Compose**: Strumento per gestire più contenitori contemporaneamente.

## Slide 8: Data Processing

### 1. COSA SIGNIFICA
Spiega come raggruppiamo i dati Excel.

### 2. COSA DIRE
"Nel file Excel la stessa sede fisica può comparire più volte per divisioni o marchi diversi. Noi puliamo i dati e raggruppiamo per Cliente e Indirizzo. Le due fatture di Via Roma diventano così un'unica tappa da visitare con un fatturato totale. Dopo aver unito i dati, troviamo le coordinate e calcoliamo i tempi stradali."

### 3. TERMINI DA CONOSCERE
- **Driving times**: Stima del tempo necessario per viaggiare da un cliente all'altro (fondamentale per rispettare gli orari).

## Slide 9: Optimization Problem

### 1. COSA SIGNIFICA
Input, vincoli e obiettivi in parole semplici.

### 2. COSA DIRE
"Il cuore del sistema è il problema di ottimizzazione. Gli input sono clienti, fatturato e parametri inseriti dall'utente. I vincoli sono rigidi: solo giorni lavorativi, niente feste, orari precisi e calcolo dei tempi di viaggio. L'obiettivo è massimizzare il fatturato recuperato. Dato che testare tutte le rotte richiederebbe un tempo infinito, usiamo un algoritmo euristico."

### 3. TERMINI DA CONOSCERE
- **Heuristic (Euristica)**: Un algoritmo che trova soluzioni utili molto rapidamente, senza testare tutte le combinazioni possibili.

## Slide 10: How the Optimizer Works

### 1. COSA SIGNIFICA
Flusso concettuale dell'algoritmo (K-means + ALNS).

### 2. COSA DIRE
"L'algoritmo funziona così: prima usa K-means per raggruppare i clienti vicini sulla mappa. Viene poi creata un'agenda di base. Da qui parte il miglioramento con ALNS, che rimuove alcune visite (destroy) e prova a reinserirle (repair) per migliorare il risultato. Controlla i vincoli di fattibilità e tiene l'agenda migliore. Essendo un'euristica, offre una soluzione pratica molto valida e rapida."

### 3. TERMINI DA CONOSCERE
- **K-means**: Un metodo per creare gruppi (cluster) di clienti vicini sulla mappa.
- **Cluster**: Gruppo di clienti molto vicini geograficamente.
- **ALNS**: Adaptive Large Neighborhood Search. Cambia il piano smontandolo (destroy) e rimontandolo (repair).
- **Destroy / Repair**: Fasi dell'ALNS (distruzione temporanea di una parte e ricostruzione intelligente).
- **Feasible solution (Soluzione fattibile)**: Un piano che rispetta tutte le regole di orari e giorni lavorativi.
- **Global optimum**: La soluzione matematica assolutamente perfetta e imbattibile, che la nostra euristica non garantisce di raggiungere.

## Slide 11: Simplified Algorithm

### 1. COSA SIGNIFICA
Lo pseudocodice del ciclo ALNS.

### 2. COSA DIRE
"Qui vedete la logica concettuale. C'è un ciclo continuo: la fase 'destroy' rimuove alcune visite, e la fase 'repair' prova a reinserirle per formare un candidato. Se il candidato rispetta i vincoli ed è meglio del piano precedente, diventa la nostra nuova 'best solution'."

### 3. TERMINI DA CONOSCERE
Nessuno in aggiunta.

## Slide 12: Real Optimizer Code - Destroy

### 1. COSA SIGNIFICA
La prima fase (Destroy) mostrata col codice. Spiegazione dettagliata per i non-programmatori.

### 2. COSA DIRE
"Qui vediamo vero codice. Nella fase Destroy, la variabile num_remove usa random.uniform per decidere casualmente la percentuale di visite da eliminare dal percorso corrente, registrato in route.client_indices. Con random.sample peschiamo esattamente quali togliere. Infine, il comando 'pop' le cancella. Rimuovere queste visite crea spazio e permette alla fase successiva di tentare un percorso radicalmente diverso e potenzialmente migliore."

### 3. TERMINI DA CONOSCERE
- **num_remove**: Decide quante visite togliere calcolando un limite minimo e massimo.
- **random.uniform**: Estrae una percentuale casuale tra due numeri (qui 10% e 20%).
- **random.sample**: Seleziona a caso gli elementi precisi da rimuovere, garantendo che non siano ripetuti.
- **route.client_indices**: È la "lista" in cui l'algoritmo si è segnato le visite di quella specifica giornata.
- **pop**: Comando informatico che letteralmente stacca ed espelle l'elemento scelto dalla lista.
- **Why visits are removed**: Si fa per evitare che l'algoritmo si incastri in una soluzione mediocre, forzandolo a rimescolare le carte.

## Slide 13: Real Optimizer Code - Repair

### 1. COSA SIGNIFICA
La seconda fase (Repair) mostrata col codice.

### 2. COSA DIRE
"E questo è il Repair. Immaginate di aver appena tolto un cliente dall'agenda. Il repair testa varie combinazioni: ad esempio prova a inserirlo il giorno 1 al primo posto, ma magari viola un orario e non è fattibile. Prova al secondo posto ed è fattibile. Prova il giorno 2 ed è fattibile e persino più redditizio in termini logistici. La funzione find_best_insertion fa proprio questo: sceglie la posizione migliore possibile e, se è valida, aggiorna la rotta ricollegando il cliente in agenda."

### 3. TERMINI DA CONOSCERE
- **Repair**: Ripara l'agenda tentando di reinserire i clienti tolti negli spazi liberatisi in modo più intelligente o in altre giornate.

## Slide 14: Testing

### 1. COSA SIGNIFICA
I 6 test automatizzati per controllare la robustezza dei vincoli.

### 2. COSA DIRE
"Per essere certi che il motore generi agende realistiche, i nostri test automatici verificano i limiti orari, il calendario lavorativo e i vincoli stradali. Se una visita sfora l'orario o cade in una festività, il test se ne accorge. È importante ribadire che questi test verificano che le regole siano rigorosamente rispettate, non provano che troviamo l'ottimo globale."

### 3. TERMINI DA CONOSCERE
Nessuno.

## Slide 15: Conclusions

### 1. COSA SIGNIFICA
Sommario pulito di cosa abbiamo imparato, senza i possibili miglioramenti.

### 2. COSA DIRE
"In sintesi, cosa ci portiamo a casa? Che pulire i dati grezzi e l'accuratezza geografica sono assolutamente critici per un risultato affidabile. Abbiamo visto che bilanciare fatturato e tempistiche stradali richiede l'uso intelligente di algoritmi euristici. Infine, l'uso di Docker è la chiave per poter prendere questo sistema complesso e farlo girare con un solo click altrove."

### 3. TERMINI DA CONOSCERE
Nessuno.

## Slide 16: Live Demo

### 1. COSA SIGNIFICA
Transizione visiva per l'inizio della dimostrazione reale.

### 2. COSA DIRE
"E a proposito di vederlo girare, abbandoniamo le slide tecniche. Ora andiamo a vedere il Sales Visit Optimizer in azione. Caricheremo un dataset vero, imposteremo i parametri ed esploreremo l'agenda generata dal vivo!"

### 3. TERMINI DA CONOSCERE
Nessuno.
