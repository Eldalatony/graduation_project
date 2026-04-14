import os
import json
import time
import pandas as pd
import paho.mqtt.client as mqtt
from datetime import datetime, timezone

try:
    MQTT_BROKER = os.environ["MQTT_BROKER"]
    PORT = int(os.environ["MQTT_PORT"])
    GATEWAY_ID = os.environ["GATEWAY_ID"]
    DATASET_FILE = os.environ["DATASET_FILE"]
except KeyError as e:
    print(f"CRITICAL ERROR: Missing environment variable {e}")
    exit(1)

TOPIC = "home/gateway/data"

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[{GATEWAY_ID}] Successfully connected to Local Broker.")
    else:
        print(f"Connection failed with code {rc}")

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=GATEWAY_ID)
    client.on_connect = on_connect
    
    print("Initializing Gateway...")
    try:
        client.connect(MQTT_BROKER, PORT, 60)
    except Exception as e:
        print(f"Error: {e}. Is Mosquitto running?")
        return

    client.loop_start()

    try:
        print(f"Loading node data from {DATASET_FILE}...")
        df = pd.read_csv(DATASET_FILE)
        df = df.dropna(subset=['Sub_metering_1', 'Sub_metering_2', 'Sub_metering_3'])
        print(f"Gateway ready. Managing {len(df)} simulated node readings.")
    except FileNotFoundError:
        print(f"Error: {DATASET_FILE} not found. Did you run the trimming script?")
        return

    print("\n--- Starting Gateway Broadcast (Ctrl+C to stop) ---")

    try:
        while True: 
            for index, row in df.iterrows():
                kitchen_power = float(row['Sub_metering_1'])
                laundry_power = float(row['Sub_metering_2'])
                climate_power = float(row['Sub_metering_3'])

                # FIXED: Keys now perfectly match the Node.js backend parser
                payload = {
                    "gateway_id": GATEWAY_ID,
                    "status": "ONLINE",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "nodes": {
                        "kitchen": {
                            "wattage": kitchen_power,
                            "status": "active" if kitchen_power > 0 else "idle"
                        },
                        "laundry": {
                            "wattage": laundry_power,
                            "status": "active" if laundry_power > 0 else "idle"
                        },
                        "climate": {
                            "wattage": climate_power,
                            "status": "active" if climate_power > 0 else "idle"
                        }
                    }
                }

                json_payload = json.dumps(payload)
                client.publish(TOPIC, json_payload, qos=0)
                
                print(f"Broadcast [{index}]: Kitchen={kitchen_power}W | Laundry={laundry_power}W | Climate={climate_power}W")
                time.sleep(1) 
                
            print("\n--- Reached end of test data. Looping back to start... ---")
            
    except KeyboardInterrupt:
        print("\nGateway shut down by user.")
    finally:
        client.loop_stop()
        client.disconnect()
        print("Disconnected gracefully.")

if __name__ == "__main__":
    main()