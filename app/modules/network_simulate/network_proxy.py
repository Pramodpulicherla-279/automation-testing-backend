from mitmproxy import http
import time
import json
import random
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "network_config.json")

def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Safe defaults if file not found
        return {"latency": 0, "packetLoss": 0, "jitter": 0, "enabled": False}

def request(flow: http.HTTPFlow):
    config = load_config()
    if not config.get("enabled"):
        return

    # Packet loss — drop request randomly
    if random.random() < config.get("packetLoss", 0):
        flow.kill()
        return

    # Latency + jitter
    latency = config.get("latency", 0)
    jitter  = config.get("jitter", 0)
    delay   = latency + random.uniform(-jitter, jitter)
    time.sleep(max(0, delay))

def response(flow: http.HTTPFlow):
    config = load_config()
    if not config.get("enabled"):
        return

    latency = config.get("latency", 0)
    jitter  = config.get("jitter", 0)
    delay   = latency + random.uniform(-jitter, jitter)
    time.sleep(max(0, delay))