import requests
import json
import os
from datetime import datetime

url = "https://ardonyjjtwljfzszhcko.supabase.co/rest/v1/"
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
headers = {"apikey": key, "Authorization": f"Bearer {key}"}

data = {"metadata": {"updated": datetime.utcnow().isoformat()}}

tables = ["props", "model_edges", "model_predictions"]
for t in tables:
    r = requests.get(url + t, headers=headers, params={"limit": 300})
    if r.ok:
        data[t] = r.json()

with open("rotobot_data.json", "w") as f:
    json.dump(data, f, indent=2)

print("RotoBot refresh completed")
