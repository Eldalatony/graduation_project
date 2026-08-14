import os
import json
import time
import random
import paho.mqtt.client as mqtt
from datetime import datetime, timezone

try:
    MQTT_BROKER = os.environ["MQTT_BROKER"]
    PORT = int(os.environ["MQTT_PORT"])
    GATEWAY_ID = os.environ["GATEWAY_ID"]
except KeyError as e:
    print(f"CRITICAL ERROR: Missing environment variable {e}")
    exit(1)

MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
MQTT_TLS = os.environ.get("MQTT_TLS", "false").lower() == "true"

TOPIC = "home/gateway/data"

STEP_SLEEP = float(os.environ.get("SIM_STEP_SLEEP", "1.0"))
SMOOTH = float(os.environ.get("SIM_SMOOTHING", "0.3"))

DEFAULT_NODES = "kitchen:light,laundry:washer,climate:ac"

class AirConditioner:
    """Always cooling; hovers around its setpoint."""
    def target(self):
        return random.uniform(1300, 1600)

class WashingMachine:
    """Always running; rotates continuously through its wash phases (no idle)."""
    PHASES = [("heat", 2000, 8), ("wash", 500, 20), ("rinse", 350, 12), ("spin", 850, 10)]

    def __init__(self):
        self.phase_i = 0
        self.phase_timer = self.PHASES[0][2]

    def target(self):
        _, watts, _ = self.PHASES[self.phase_i]
        self.phase_timer -= 1
        if self.phase_timer <= 0:
            self.phase_i = (self.phase_i + 1) % len(self.PHASES)
            self.phase_timer = self.PHASES[self.phase_i][2]
        return watts * random.uniform(0.95, 1.05)

class Refrigerator:
    """Always running; steady compressor draw."""
    def target(self):
        return random.uniform(120, 170)

class Microwave:
    """Always running; steady high draw."""
    def target(self):
        return random.uniform(1100, 1400)

class Light:
    """Always on; steady low draw."""
    def target(self):
        return random.uniform(12, 18)

PROFILES = {
    "ac": AirConditioner,
    "washer": WashingMachine,
    "fridge": Refrigerator,
    "microwave": Microwave,
    "light": Light,
}

def build_nodes():
    spec = os.environ.get("SIM_NODES", DEFAULT_NODES)
    nodes = {}
    for pair in spec.split(","):
        pair = pair.strip()
        if not pair:
            continue
        node_key, _, kind = pair.partition(":")
        node_key, kind = node_key.strip(), kind.strip().lower()
        cls = PROFILES.get(kind)
        if not cls:
            print(f"⚠️  Unknown profile '{kind}' for node '{node_key}', using light.")
            cls = Light
        nodes[node_key] = cls()
    return nodes

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[{GATEWAY_ID}] Successfully connected to broker {MQTT_BROKER}:{PORT}.")
    else:
        print(f"Connection failed with code {rc}")

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=GATEWAY_ID)
    client.on_connect = on_connect

    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS:
        client.tls_set()

    print("Initializing Gateway...")
    try:
        client.connect(MQTT_BROKER, PORT, 60)
    except Exception as e:
        print(f"Error connecting to broker: {e}")
        return

    client.loop_start()

    nodes = build_nodes()
    smoothed = {key: 0.0 for key in nodes}
    print(f"Gateway ready. Simulating nodes: {', '.join(f'{k}({type(v).__name__})' for k, v in nodes.items())}")
    print("\n--- Starting Gateway Broadcast (Ctrl+C to stop) ---")

    try:
        while True:
            node_payload = {}
            parts = []
            for key, profile in nodes.items():
                target = profile.target()
                smoothed[key] += SMOOTH * (target - smoothed[key])
                watts = round(max(0.0, smoothed[key]), 2)
                node_payload[key] = {
                    "wattage": watts,
                    "status": "active" if watts > 5 else "idle",
                }
                parts.append(f"{key}={watts}W")

            payload = {
                "gateway_id": GATEWAY_ID,
                "status": "ONLINE",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "nodes": node_payload,
            }

            client.publish(TOPIC, json.dumps(payload), qos=0)
            print(f"Broadcast: {' | '.join(parts)}")
            time.sleep(STEP_SLEEP)

    except KeyboardInterrupt:
        print("\nGateway shut down by user.")
    finally:
        client.loop_stop()
        client.disconnect()
        print("Disconnected gracefully.")

if __name__ == "__main__":
    main()
