from fastapi.testclient import TestClient
from src.apis.main import app

client = TestClient(app, raise_server_exceptions=True)

try:
    print("\n--- TESTING /api/profile ---")
    r1 = client.get("/api/profile")
    print("Status:", r1.status_code)
except Exception as e:
    print("PROFILE EXCEPTION:")
    import traceback
    traceback.print_exc()

try:
    print("\n--- TESTING /api/workouts/history ---")
    r2 = client.get("/api/workouts/history")
    print("Status:", r2.status_code)
except Exception as e:
    print("HISTORY EXCEPTION:")
    import traceback
    traceback.print_exc()
