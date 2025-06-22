import os
import json

creds = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

print("✅ DEBUG - Raw Env Value:", repr(creds))

if not creds:
    print("❌ ERROR - Environment variable is missing or empty.")
else:
    try:
        parsed = json.loads(creds)
        print("✅ JSON parsed successfully! Project ID:", parsed.get("project_id"))
    except json.JSONDecodeError as e:
        print("❌ ERROR - JSON decode failed:", e)
