import subprocess
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "network_config.json")

def simulate_network(config):
    network_type = config.get("networkType", "3G")

    type_map = {
        "2G":  "1",
        "3G":  "3",
        "4G":  "13",
        "5G":  "20",
        "WiFi": None
    }

    # ✅ Write the full config to a shared file for mitmproxy to read
    with open(CONFIG_PATH, "w") as f:
        json.dump({
            "latency":    config.get("latency", 0) / 1000,   # ms → seconds
            "packetLoss": config.get("packetLoss", 0) / 100, # % → 0-1
            "jitter":     config.get("jitter", 0) / 1000,
            "networkType": network_type,
            "enabled":    config.get("enabled", False)
        }, f)

    def adb(cmd):
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"→ {result.stdout.strip() or result.stderr.strip()}")
        return result.returncode

    network_code = type_map.get(network_type)
    return {"network_type": network_type, "applied": bool(network_code)}