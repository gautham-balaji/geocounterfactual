import ee
import json
import os

# Key now lives in backend/secrets/ (gitignored) rather than the repo root.
KEY_PATH = os.path.join('backend', 'secrets', 'gcf-backend.json')

# 1. Load the email directly from your JSON key
with open(KEY_PATH) as f:
    key_data = json.load(f)

# 2. Authenticate using the Service Account
try:
    creds = ee.ServiceAccountCredentials(email=key_data['client_email'], key_file=KEY_PATH)
    ee.Initialize(credentials=creds, project='geocounterfactual-backend')
    
    # 3. Try to fetch a basic elevation map
    dem = ee.Image('USGS/SRTMGL1_003')
    print("✅ SUCCESS: Earth Engine is approved and active!")
    print(f"Test data loaded: {dem.getInfo()['id']}")
except Exception as e:
    print(f"❌ FAILED: Earth Engine is not ready yet. Error: {e}")