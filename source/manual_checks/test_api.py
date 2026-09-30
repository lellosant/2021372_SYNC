import sys
import os
import io
import uuid
import urllib.request
import urllib.error
import json
import pandas as pd

# Create dummy excel
df = pd.DataFrame({
    "Lat": [41.9, 41.91],
    "Lon": [12.5, 12.51],
    "Totale": [1000, 2000],
    "WINES": [1000, 2000],
    "Cliente": ["Cliente 1", "Cliente 2"],
    "Citta": ["ROMA", "ROMA"],
    "Indirizzo": ["Via Roma 1", "Via Roma 2"]
})

def encode_multipart_formdata(fields, files):
    boundary = uuid.uuid4().hex
    body = bytearray()
    
    for key, value in fields.items():
        body.extend(f'--{boundary}\r\n'.encode('utf-8'))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode('utf-8'))
        body.extend(f'{value}\r\n'.encode('utf-8'))
        
    for key, (filename, file_bytes, content_type) in files.items():
        body.extend(f'--{boundary}\r\n'.encode('utf-8'))
        body.extend(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode('utf-8'))
        body.extend(f'Content-Type: {content_type}\r\n\r\n'.encode('utf-8'))
        body.extend(file_bytes)
        body.extend(b'\r\n')
        
    body.extend(f'--{boundary}--\r\n'.encode('utf-8'))
    content_type_header = f'multipart/form-data; boundary={boundary}'
    return content_type_header, bytes(body)

def run_tests():
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    file_bytes = buf.getvalue()
    
    url = "http://localhost:8000/api/analyze"
    fields = {
        'days': '5',
        'hours_per_visit': '2.0',
        'start_date': '2026-10-01',
        'start_lat': '41.9',
        'start_lon': '12.5'
    }
    files = {
        'file': ('test.xlsx', file_bytes, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    
    content_type, body = encode_multipart_formdata(fields, files)
    req = urllib.request.Request(url, data=body, headers={'Content-Type': content_type}, method='POST')
    
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            data = json.loads(resp.read().decode('utf-8'))
            print("Test API Status:", status)
            schedule = data.get('schedule', [])
            print("Numero visite restituite:", len(schedule))
            if schedule:
                print("Prima data visita:", schedule[0].get('Data Visita'))
            print("Test API completato con successo!")
    except urllib.error.URLError as e:
        print("Errore connessione all'API (porta 8000):", e)

if __name__ == "__main__":
    run_tests()
