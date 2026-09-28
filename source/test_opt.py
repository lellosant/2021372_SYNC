import datetime
import pandas as pd
from backend.optimizer import optimize_visits, _next_business_day

df = pd.DataFrame({
    "Lat": [41.9, 41.91],
    "Lon": [12.5, 12.51],
    "WINES": [1000, 2000]
})
df["SelectedRevenue"] = df["WINES"]

# Simulate optimize_visits behavior
res1 = optimize_visits(df, 2, 2.0, 8.0, ["WINES"], start_date="2026-10-01")
print(res1[["Data Visita", "Giorno", "Fatturato Stimato"]])

res2 = optimize_visits(df, 2, 2.0, 8.0, ["WINES"], start_date="2026-10-15")
print(res2[["Data Visita", "Giorno", "Fatturato Stimato"]])
