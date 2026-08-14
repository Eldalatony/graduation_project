#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <time.h>
#include <mbedtls/aes.h>
#include <mbedtls/base64.h>
#include "esp_system.h"
#include "secrets.h"

#define CURRENT_PIN 34
#define VOLTAGE_PIN 35

const char* GATEWAY_ID = "esp32-01";
const char* NODE_KEY   = "node1";

LiquidCrystal_I2C lcd(0x27, 16, 2);

float voltageCalibration = 600.0;
float currentCalibration = 0.50;

float voltageOffset = 2048;
float currentOffset = 2048;

float smoothV = 0;
float smoothI = 0;

const char* WIFI_SSID      = WIFI_SSID_VALUE;
const char* WIFI_PASSWORD  = WIFI_PASSWORD_VALUE;
const char* MQTT_BROKER    = MQTT_BROKER_VALUE;
const char* MQTT_USERNAME  = MQTT_USERNAME_VALUE;
const char* MQTT_PASSWORD  = MQTT_PASSWORD_VALUE;
const int   MQTT_PORT      = 8883;
const char* MQTT_CLIENT_ID = "esp32-01-client";
const char* MQTT_TOPIC     = "home/gateway/data";
const char* MQTT_CMD_TOPIC = "home/gateway/cmd";

WiFiClientSecure net;
PubSubClient mqtt(net);

uint8_t aesKey[32] = AES_KEY_BYTES;

bool encryptPayload(const char* plaintext, char* outBase64, size_t outBase64Size) {
  size_t plainLen = strlen(plaintext);
  size_t paddedLen = ((plainLen / 16) + 1) * 16;

  if (paddedLen > 576) return false;

  uint8_t padded[576];
  memcpy(padded, plaintext, plainLen);
  uint8_t padValue = (uint8_t)(paddedLen - plainLen);
  for (size_t i = plainLen; i < paddedLen; i++) {
    padded[i] = padValue;
  }

  uint8_t iv[16];
  esp_fill_random(iv, 16);

  uint8_t ivForCrypt[16];
  memcpy(ivForCrypt, iv, 16);

  mbedtls_aes_context aes;
  mbedtls_aes_init(&aes);
  mbedtls_aes_setkey_enc(&aes, aesKey, 256);

  uint8_t cipher[576];
  int ret = mbedtls_aes_crypt_cbc(&aes, MBEDTLS_AES_ENCRYPT, paddedLen, ivForCrypt, padded, cipher);
  mbedtls_aes_free(&aes);

  if (ret != 0) return false;

  uint8_t combined[16 + 576];
  memcpy(combined, iv, 16);
  memcpy(combined + 16, cipher, paddedLen);

  size_t outLen = 0;
  ret = mbedtls_base64_encode((unsigned char*)outBase64, outBase64Size, &outLen,
                              combined, 16 + paddedLen);
  if (ret != 0) return false;

  outBase64[outLen] = '\0';
  return true;
}

bool decryptPayload(const char* base64in, char* outPlain, size_t outPlainSize) {
  uint8_t combined[608];
  size_t decodedLen = 0;
  size_t inLen = strlen(base64in);

  int ret = mbedtls_base64_decode(combined, sizeof(combined), &decodedLen,
                                  (const unsigned char*)base64in, inLen);
  if (ret != 0) return false;
  if (decodedLen < 16) return false;

  uint8_t iv[16];
  memcpy(iv, combined, 16);

  size_t cipherLen = decodedLen - 16;
  if (cipherLen == 0 || cipherLen % 16 != 0) return false;

  mbedtls_aes_context aes;
  mbedtls_aes_init(&aes);
  mbedtls_aes_setkey_dec(&aes, aesKey, 256);

  uint8_t decrypted[608];
  ret = mbedtls_aes_crypt_cbc(&aes, MBEDTLS_AES_DECRYPT, cipherLen, iv, combined + 16, decrypted);
  mbedtls_aes_free(&aes);
  if (ret != 0) return false;

  uint8_t padValue = decrypted[cipherLen - 1];
  if (padValue == 0 || padValue > 16 || padValue > cipherLen) return false;

  size_t plainLen = cipherLen - padValue;
  if (plainLen >= outPlainSize) return false;

  memcpy(outPlain, decrypted, plainLen);
  outPlain[plainLen] = '\0';
  return true;
}

#define RELAY1_PIN 25
#define RELAY2_PIN 26
#define RELAY_ACTIVE_LOW true

void setRelay(uint8_t pin, bool turnOn) {
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(pin, turnOn ? LOW : HIGH);
  } else {
    digitalWrite(pin, turnOn ? HIGH : LOW);
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  if (length >= 800) {
    Serial.println("[CMD] Payload too long, ignoring");
    return;
  }

  char b64[800];
  memcpy(b64, payload, length);
  b64[length] = '\0';

  char plain[600];
  if (!decryptPayload(b64, plain, sizeof(plain))) {
    Serial.println("[AES] Command decrypt failed");
    return;
  }

  Serial.print("[CMD] ");
  Serial.println(plain);

  String cmd = String(plain);

  if (cmd == "RELAY1_ON")       setRelay(RELAY1_PIN, true);
  else if (cmd == "RELAY1_OFF") setRelay(RELAY1_PIN, false);
  else if (cmd == "RELAY2_ON")  setRelay(RELAY2_PIN, true);
  else if (cmd == "RELAY2_OFF") setRelay(RELAY2_PIN, false);
  else Serial.println("[CMD] Unknown command");
}

void calibrate() {
  lcd.clear();
  lcd.print("Calibrating");

  for (int x = 0; x < 2000; x++) {
    int rawV = analogRead(VOLTAGE_PIN);
    int rawI = analogRead(CURRENT_PIN);

    voltageOffset += (rawV - voltageOffset) / 64.0;
    currentOffset += (rawI - currentOffset) / 64.0;

    delay(1);
  }

  lcd.clear();
  lcd.print("Ready");
  delay(1000);
  lcd.clear();
}

float readVoltage() {
  const int samples = 1000;
  float sum = 0;
  int maxRaw = 0;
  int minRaw = 4095;

  for (int i = 0; i < samples; i++) {
    int raw = analogRead(VOLTAGE_PIN);

    if (raw > maxRaw) maxRaw = raw;
    if (raw < minRaw) minRaw = raw;

    voltageOffset += (raw - voltageOffset) / 1024.0;

    float centered = raw - voltageOffset;
    float v = centered * (3.3 / 4095.0);

    sum += v * v;
    delayMicroseconds(200);
  }

  int p2p = maxRaw - minRaw;
  if (p2p < 25) return 0;

  float sensorVrms = sqrt(sum / samples);
  float mainsVoltage = sensorVrms * voltageCalibration;

  if (mainsVoltage < 45) return 0;

  return mainsVoltage;
}

float readCurrent() {
  const int samples = 1000;
  float sum = 0;
  int maxRaw = 0;
  int minRaw = 4095;

  for (int i = 0; i < samples; i++) {
    int raw = analogRead(CURRENT_PIN);

    if (raw > maxRaw) maxRaw = raw;
    if (raw < minRaw) minRaw = raw;

    currentOffset += (raw - currentOffset) / 1024.0;

    float centered = raw - currentOffset;
    float v = centered * (3.3 / 4095.0);

    sum += v * v;
    delayMicroseconds(200);
  }

  int p2p = maxRaw - minRaw;
  if (p2p < 8) return 0;

  float amps = sqrt(sum / samples) * currentCalibration;
  if (amps < 0.005) return 0;

  return amps;
}

void connectWiFi() {
  Serial.println("[WiFi] Connecting...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    attempts++;

    if (attempts > 40) {
      Serial.println("\n[WiFi] Failed");
      lcd.clear();
      lcd.print("WiFi Failed");
      while (true) delay(1000);
    }
  }

  Serial.println("\n[WiFi] Connected");
  Serial.print("[WiFi] IP: ");
  Serial.println(WiFi.localIP());
}

void syncTime() {
  Serial.println("[NTP] Syncing...");
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  time_t now = 0;
  int attempts = 0;

  while ((now = time(nullptr)) < 1700000000 && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  Serial.println();

  if (now < 1700000000) {
    Serial.println("[NTP] Failed");
  } else {
    Serial.println("[NTP] Synced");
  }
}

bool isoTimestamp(char* out, size_t len) {
  time_t now = time(nullptr);
  if (now < 1700000000) return false;

  struct tm tm_utc;
  gmtime_r(&now, &tm_utc);
  strftime(out, len, "%Y-%m-%dT%H:%M:%SZ", &tm_utc);

  return true;
}

void connectMQTT() {
  net.setInsecure();

  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setBufferSize(1024);
  mqtt.setKeepAlive(60);

  int attempts = 0;

  while (!mqtt.connected()) {
    attempts++;

    Serial.print("[MQTT] Connecting... attempt ");
    Serial.println(attempts);

    if (mqtt.connect(MQTT_CLIENT_ID, MQTT_USERNAME, MQTT_PASSWORD)) {
      Serial.println("[MQTT] Connected");
      mqtt.subscribe(MQTT_CMD_TOPIC);
    } else {
      Serial.print("[MQTT] Failed rc=");
      Serial.println(mqtt.state());

      if (attempts >= 5) {
        lcd.clear();
        lcd.print("MQTT Failed");
        while (true) delay(1000);
      }

      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  analogReadResolution(12);
  analogSetPinAttenuation(CURRENT_PIN, ADC_11db);
  analogSetPinAttenuation(VOLTAGE_PIN, ADC_11db);

  Wire.begin(21, 22);

  pinMode(RELAY1_PIN, OUTPUT);
  pinMode(RELAY2_PIN, OUTPUT);
  setRelay(RELAY1_PIN, false);
  setRelay(RELAY2_PIN, true);

  lcd.init();
  lcd.backlight();

  calibrate();

  lcd.clear();
  lcd.print("WiFi...");
  connectWiFi();

  lcd.clear();
  lcd.print("Time...");
  syncTime();

  lcd.clear();
  lcd.print("MQTT...");
  mqtt.setCallback(mqttCallback);
  connectMQTT();

  lcd.clear();
}

void loop() {
  if (!mqtt.connected()) {
    connectMQTT();
  }

  mqtt.loop();

  float v = readVoltage();
  float i = readCurrent();

  if (v == 0) {
    smoothV = 0;
    smoothI = 0;
  } else {
    smoothV = v;

    if (i < 0.001) {
      smoothI = 0;
    } else {
      smoothI = i;
    }
  }

  float p = smoothV * smoothI;

  const char* nodeStatus = (p > 0.5) ? "active" : "idle";

  char ts[32];
  bool haveTs = isoTimestamp(ts, sizeof(ts));

  char payload[512];

  if (haveTs) {
    snprintf(payload, sizeof(payload),
      "{\"gateway_id\":\"%s\",\"status\":\"ONLINE\",\"timestamp\":\"%s\","
      "\"nodes\":{\"%s\":{\"wattage\":%.1f,\"status\":\"%s\"}}}",
      GATEWAY_ID, ts, NODE_KEY, p, nodeStatus);
  } else {
    snprintf(payload, sizeof(payload),
      "{\"gateway_id\":\"%s\",\"status\":\"ONLINE\","
      "\"nodes\":{\"%s\":{\"wattage\":%.1f,\"status\":\"%s\"}}}",
      GATEWAY_ID, NODE_KEY, p, nodeStatus);
  }

  char encrypted[800];
  bool encOk = encryptPayload(payload, encrypted, sizeof(encrypted));

  if (!encOk) {
    Serial.println("[AES] Encryption failed, payload too long?");
    return;
  }

  bool published = mqtt.publish(MQTT_TOPIC, encrypted);

  Serial.print("V=");
  Serial.print(smoothV, 1);
  Serial.print(" I=");
  Serial.print(smoothI, 3);
  Serial.print(" P=");
  Serial.print(p, 1);
  Serial.print(" Published=");
  Serial.println(published ? "OK" : "FAILED");

  lcd.setCursor(0, 0);
  lcd.print("V:");
  lcd.print(smoothV, 0);
  lcd.print(" I:");
  lcd.print(smoothI, 3);
  lcd.print("   ");

  lcd.setCursor(0, 1);
  lcd.print("P:");
  lcd.print(p, 1);
  lcd.print(" S:");
  lcd.print(smoothV, 0);
  lcd.print("   ");

  delay(500);
}
