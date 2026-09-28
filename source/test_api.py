import requests
import pandas as pd
from io import BytesIO

# create dummy excel
df = pd.DataFrame({
    "Lat": [41.9, 41.91],
    "Lon": [12.5, 12.51],
    "Totale": [1000, 2000],
    "WINES": [1000, 2000]
})
buf = BytesIO()
df.to_excel(buf, index=False)
buf.seek(0)

# test 1
url = "http://localhost:8000/api/analyze"
files = {'file': ('test.xlsx', buf.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
data = {'days': 10, 'hours_per_visit': 2.0, 'start_date': '2026-10-01'}

res = requests.post(url, files=files, data=data)
print(res.json()['schedule'][0]['Data Visita'])

# test 2
buf.seek(0)
files = {'file': ('test.xlsx', buf.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
data = {'days': 10, 'hours_per_visit': 2.0, 'start_date': '2026-10-15'}
res = requests.post(url, files=files, data=data)
print(res.json()['schedule'][0]['Data Visita'])
