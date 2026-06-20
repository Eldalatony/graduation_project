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

# Seconds between published messages.
STEP_SLEEP = float(os.environ.get("SIM_STEP_SLEEP", "1.0"))
# Smoothing: how fast the published value moves toward each new target.
# Lower = smoother glide, 1.0 = no smoothing (instant). Keeps the dashboard
# from teleporting and stops the anomaly detector from over-firing.
SMOOTH = float(os.environ.get("SIM_SMOOTHING", "0.3"))

# Map each node_key (must match the appliance's node_key in the app) to a
# realistic appliance PROFILE. Override without editing code via:
#   SIM_NODES="kitchen:light,laundry:washer,climate:ac,node2:fridge"
DEFAULT_NODES = "kitchen:light,laundry:washer,climate:ac"


# ── Appliance profiles ───────────────────────────────────────────────────────
# Each profile is stateful and returns a target wattage each tick, modelling how
# the real appliance behaves (compressor cycles, wash phases, bursts, etc.).
# Durations are in ticks (~seconds) and kept demo-friendly so cycles are visible.

class AirConditioner:
    """Compressor cycles on/off; while on, hovers around a setpoint."""
    def __init__(self):
        self.on = False
        self.timer = random.randint(5, 15)

    def target(self):
        self.timer -= 1
        if self.timer <= 0:
            self.on = not self.on
            self.timer = random.randint(25, 45) if self.on else random.randint(15, 30)
        return random.uniform(1200, 1700) if self.on else random.uniform(0, 3)


class WashingMachine:
    """Runs a multi-phase wash cycle, idles, then repeats."""
    PHASES = [("heat", 2000, 8), ("wash", 500, 20), ("rinse", 350, 12), ("spin", 850, 10)]

    def __init__(self):
        self.running = False
        self.idle_timer = random.randint(10, 25)
        self.phase_i = 0
        self.phase_timer = 0

    def target(self):
        if not self.running:
            self.idle_timer -= 1
            if self.idle_timer <= 0:
                self.running = True
                self.phase_i = 0
                self.phase_timer = self.PHASES[0][2]
            return random.uniform(0, 3)

        _, watts, _ = self.PHASES[self.phase_i]
        self.phase_timer -= 1
        if self.phase_timer <= 0:
            self.phase_i += 1
            if self.phase_i >= len(self.PHASES):
                self.running = False
                self.idle_timer = random.randint(20, 40)
                return random.uniform(0, 3)
            self.phase_timer = self.PHASES[self.phase_i][2]
        return watts * random.uniform(0.95, 1.05)


class Refrigerator:
    """Compressor cycles ~120-180 W on, near-zero off."""
    def __init__(self):
        self.on = True
        self.timer = random.randint(10, 20)

    def target(self):
        self.timer -= 1
        if self.timer <= 0:
            self.on = not self.on
            self.timer = random.randint(15, 30) if self.on else random.randint(20, 40)
        return random.uniform(110, 180) if self.on else random.uniform(0, 4)


class Microwave:
    """Mostly off, occasional high-power bursts."""
    def __init__(self):
        self.on = False
        self.timer = random.randint(20, 50)

    def target(self):
        self.timer -= 1
        if self.timer <= 0:
            self.on = not self.on
            self.timer = random.randint(8, 25) if self.on else random.randint(40, 120)
        return random.uniform(1100, 1500) if self.on else random.uniform(0, 2)


class Light:
    """Steady low draw, occasionally switched off."""
    def __init__(self):
        self.on = True
        self.timer = random.randint(20, 60)

    def target(self):
        self.timer -= 1
        if self.timer <= 0:
            self.on = not self.on
            self.timer = random.randint(30, 90) if self.on else random.randint(10, 30)
        return random.uniform(12, 18) if self.on else random.uniform(0, 1)


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
                # Glide toward the target instead of jumping.
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
