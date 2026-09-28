# SPECIFICS OF THE DEPLOYED SYSTEM

# SYSTEM OVERVIEW

Sales Visit Optimizer is a web application for geographic customer analysis and sales visit planning.

The system is composed of two main parts:

- a Backend API developed in Python with FastAPI;
- a Frontend developed with HTML, CSS and JavaScript and served by Nginx.

The application is deployed using Docker and Docker Compose.

The user uploads an ERP dataset and selects the parameters of the visit campaign.
The Backend processes the dataset, geocodes customer addresses and creates a suggested visit plan.
The Frontend shows the results through a map, some main indicators and a visit agenda.

# USER STORIES
1) As a Business Analyst, I want to upload an Excel file, so that I can work with the latest data extracted from the ERP.

2) As a Business Analyst, I want the system to detect the companies contained in the uploaded file, so that I do not have to configure them manually.

3) As a Business Analyst, I want the system to work with future ERP files having the same logical structure, so that I can reuse the application with new yearly data.

4) As a Business Analyst, I want the system to group duplicate ERP rows referring to the same delivery point, so that the same physical customer location is not considered as multiple visits.

5) As a Sales Manager, I want to select a company, so that I can analyze only the customers and revenue related to that company.

6) As a Sales Manager, I want to see the customers of the selected company on a map, so that I can understand their geographic distribution.

7) As a Sales Manager, I want to see the customer name, address and revenue on the map, so that I can understand the commercial value of each location.

8) As a Sales Manager, I want the system to geocode customer addresses, so that delivery points can be shown in their real geographic position.

9) As a Sales Manager, I want the system to report customers that cannot be geocoded, so that I know which data cannot be used for geographic planning.

10) As a Sales Manager, I want to choose the starting date of the visit campaign, so that I can plan visits for a specific commercial period.

11) As a Sales Manager, I want to define the number of working days available, so that I can test different plans.

12) As a Sales Manager, I want to define the expected duration of each customer visit, so that the visit plan reflects different scenarios.

13) As a Sales Manager, I want the system to use only working days from Monday to Friday, so that visits are not planned during weekends.

14) As a Sales Manager, I want the system to exclude Italian national holidays, so that visits are not planned on non-working days.

15) As a Sales Manager, I want the system to consider travel time between customers, so that the suggested agenda is realistic.

16) As a Sales Manager, I want the system to create a suggested sequence of customer visits, so that I can organize the working day.

17) As a Sales Manager, I want each planned visit to show date, time, customer, city, address and estimated revenue, so that I can use the agenda for daily planning.

18) As a Sales Manager, I want to see how many visits can be completed in the selected period, so that I can understand the capacity of the sales campaign.

19) As a Sales Manager, I want to see the estimated recoverable revenue of the proposed plan, so that I can understand the economic value of the campaign.

20) As a Sales Manager, I want to see how many customers are available and how many have valid geographic coordinates, so that I can understand the coverage of the analysis.

21) As a Sales Manager, I want to change the number of available days and run the analysis again, so that I can compare different what-if scenarios.

22) As a Sales Manager, I want to change the duration of a visit and run the analysis again, so that I can understand how visit duration changes the number of customers that can be visited.

23) As a User, I want clear error messages when the uploaded file cannot be processed, so that I can understand what went wrong.


# CONTAINERS


## CONTAINER_NAME: Backend

### DESCRIPTION:

The Backend container manages the main application logic.

It reads and processes the uploaded dataset, detects the available companies, groups duplicated ERP rows referring to the same delivery point, geocodes customer addresses and creates the data used for the visit plan.

It also calculates the values returned to the Frontend, such as the number of visits, the number of customers with valid coordinates and the recoverable revenue.

### RELATED USER STORIES:

1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 21, 22, 23

### PORTS:

8000:8000

### PERSISTENCE EVALUATION:

The Backend does not use a relational database.

The application does not need to permanently store the uploaded ERP dataset.
Some technical data may be stored locally to avoid repeating operations that have already been completed.

### EXTERNAL SERVICES CONNECTIONS:

The Backend connects to:

- Nominatim / OpenStreetMap for customer address geocoding;
- OSRM for road travel time calculations between customer locations.

If the routing service is not available, the application can use an approximate geographic distance as a fallback.

### MICROSERVICES:

#### MICROSERVICE: visits-api

- TYPE: backend
- DESCRIPTION: Manages dataset processing, geocoding, analytics and visit planning.
- PORTS: 8000

### TECHNOLOGICAL SPECIFICATION:

The Backend is developed in Python.

The main technologies are:

- FastAPI: used to expose the REST API;
- pandas: used to read, clean, group and analyze the ERP dataset;
- Uvicorn: used to run the FastAPI application;
- Nominatim / OpenStreetMap: used for geocoding;
- OSRM: used to calculate travel times.

FastAPI also provides automatic API documentation through Swagger at:

`http://localhost:8000/docs`

### SERVICE ARCHITECTURE:

The main Backend files are:

- `main.py`: exposes the API endpoints and manages the application flow;
- `data_processor.py`: reads and normalizes the uploaded file, groups delivery points and manages geocoding;
- `optimizer.py`: creates the suggested visit plan according to the selected parameters.

### ENDPOINTS:

| HTTP METHOD | URL | Description | Related User Stories |
| ----------- | --- | ----------- | -------------------- |
| POST | /api/extract-companies | Reads the uploaded file and returns the companies detected in the dataset | 1, 2, 3 |
| POST | /api/analyze | Processes the dataset and returns map points, indicators and the suggested visit plan | 4-23 |
| GET | /docs | Opens the automatic Swagger API documentation | - |


## CONTAINER_NAME: Frontend

### DESCRIPTION:

The Frontend container provides the user interface of Sales Visit Optimizer.

The user can upload the ERP file, select a company, choose the starting date, the number of working days and the expected duration of each visit.

The Frontend displays the customer map, the main indicators and the suggested visit agenda.

### RELATED USER STORIES:

1, 5, 6, 7, 9, 10, 11, 12, 17, 18, 19, 20, 21, 22, 23

### PORTS:

8080:80

### PERSISTENCE EVALUATION:

The Frontend does not use a database.

The uploaded ERP file is sent to the Backend for processing.

### EXTERNAL SERVICES CONNECTIONS:

The Frontend uses Leaflet to display the interactive map.

The map uses OpenStreetMap tiles.

### MICROSERVICES:

#### MICROSERVICE: web-interface

- TYPE: frontend
- DESCRIPTION: Provides the graphical user interface of the application.
- PORTS: 80 inside the container, exposed as port 8080 on the host.

### TECHNOLOGICAL SPECIFICATION:

The Frontend is developed using:

- HTML5;
- CSS3;
- JavaScript;
- Leaflet.js for the interactive map;
- Nginx to serve the web application.

### SERVICE ARCHITECTURE:

The main Frontend files are:

- `index.html`: contains the main page structure;
- `style.css`: contains the graphical style;
- `script.js`: manages user actions, API calls, map updates and result visualization.

### PAGES:

| Name | Description | Related Service | Related User Stories |
| ---- | ----------- | --------------- | -------------------- |
| index.html | Main page used to upload the dataset, set the scenario parameters, view the map, indicators and visit agenda | visits-api | 1, 5-7, 9-12, 17-23 |


# INFRASTRUCTURE

The application is deployed using Docker and Docker Compose.

Two containers are started:

- `backend`: FastAPI application exposed on port 8000;
- `frontend`: Nginx web server exposed on port 8080.

The project can be started from the `source` directory with:

```bash
docker compose up --build
```

After startup:

- Web Application: `http://localhost:8080`
- Swagger API Documentation: `http://localhost:8000/docs`

Configuration values are stored in the `.env` file.

The Docker configuration allows the application to be rebuilt and deployed on another machine without manually installing all the required dependencies.
