"""
Sends encrypted relay commands to the ESP32 over MQTT.

Install deps first:
    pip install paho-mqtt pycryptodome

Configure via environment (same values as backend/.env):
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_AES_KEY

Usage:
    python send_command.py RELAY1_ON
    python send_command.py RELAY1_OFF
    python send_command.py RELAY2_ON
    python send_command.py RELAY2_OFF
"""

import base64
import sys
import os
import ssl

import paho.mqtt.client as mqtt
from Crypto.Cipher import AES

MQTT_CMD_TOPIC = "home/gateway/cmd"
VALID_COMMANDS = ("RELAY1_ON", "RELAY1_OFF", "RELAY2_ON", "RELAY2_OFF")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}")
        sys.exit(1)
    return value


def load_key() -> bytes:
    key = bytes.fromhex(require_env("MQTT_AES_KEY"))
    if len(key) != 32:
        print("MQTT_AES_KEY must be 64 hex characters (32 bytes)")
        sys.exit(1)
    return key


def encrypt_command(plaintext: str, key: bytes) -> str:
    data = plaintext.encode("utf-8")
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len]) * pad_len

    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(padded)

    return base64.b64encode(iv + ciphertext).decode("utf-8")


def main():
    if len(sys.argv) != 2 or sys.argv[1].upper() not in VALID_COMMANDS:
        print(f"Usage: python send_command.py {'|'.join(VALID_COMMANDS)}")
        sys.exit(1)

    command = sys.argv[1].upper()
    encrypted = encrypt_command(command, load_key())

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(require_env("MQTT_USERNAME"), require_env("MQTT_PASSWORD"))
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    client.connect(require_env("MQTT_BROKER"), int(os.environ.get("MQTT_PORT", "8883")), 60)
    client.loop_start()
    client.publish(MQTT_CMD_TOPIC, encrypted)
    print(f"Sent command: {command}")

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
