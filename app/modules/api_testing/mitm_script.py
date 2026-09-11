import requests
from datetime import datetime

BACKEND_URL = "http://localhost:8000/api-testing/logs"

def response(flow):
    try:
        start = flow.request.timestamp_start
        end = flow.response.timestamp_end
        duration = round((end - start) * 1000, 2)

        log = {
            "method": flow.request.method,
            "endpoint": flow.request.path,
            "url": flow.request.pretty_url,
            "status": flow.response.status_code,
            "response_time_ms": duration,
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3]
        }

        # 🔥 Console log (for debugging)
        print("📡 API:", log)

        # 🔥 Send to backend
        try:
            requests.post(BACKEND_URL, json=log)
        except Exception as e:
            print("Backend error:", e)

    except Exception as e:
        print("MITM Error:", e)