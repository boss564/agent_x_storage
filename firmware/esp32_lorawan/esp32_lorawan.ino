/**
 * @file esp32_lorawan.ino
 * @title Agent X — ESP32 LoRaWAN IoT Resource Oracle Firmware
 *
 * @notice Signiert physische Ressourcen-Messungen (kWh, Liter, kg) via ECDSA
 *         und sendet sie als CBOR-komprimierte LoRa-Pakete (<150 Bytes) an
 *         den Agent X CommodityToken Smart Contract.
 *
 * Hardware: ESP32-WROOM-32E + SX1262 (868 MHz) + ATECC608A Secure Element
 * Power:    Solar (2.4W Panel) + 18650 Li-Ion (3.000 mAh) — autark
 *
 * LoRa-Parameter:
 *   - Frequenz:    868.1 MHz (EU SRD Band, Duty Cycle 1%)
 *   - Bandbreite:  125 kHz (SF10 = 980 bps)
 *   - TX-Power:    +14 dBm (25 mW)
 *   - Reichweite:  ~15 km urban, ~50 km rural (Line-of-Sight)
 *   - Payload:     max. 150 Bytes (LoRaWAN Fair Use)
 *
 * Datenfluss:
 *   Sensor (ADC/I2C) → CBOR-Komprimierung → ECDSA-Signatur → SX1262 TX
 *
 * @author Agent X Engineering
 * @license BUSL-1.1
 */

#include <Arduino.h>
#include "cbor_payload.h"
#include "sig_engine.h"
#include "sx1262_interface.h"
#include "sensor_reader.h"

// ==========================================================================
// Configuration (via config.h oder Build-Flags)
// ==========================================================================

#ifndef DEVICE_ID
  #define DEVICE_ID "ESP32_SOLAR_MUC_01"
#endif

#ifndef RESOURCE_TYPE
  #define RESOURCE_TYPE "ENERGY_KWH"
#endif

#ifndef TX_INTERVAL_S
  #define TX_INTERVAL_S 300  // Alle 5 Minuten senden (Duty-Cycle-konform)
#endif

#ifndef LORA_FREQUENCY
  #define LORA_FREQUENCY 868100000  // 868.1 MHz
#endif

#ifndef LORA_SPREADING_FACTOR
  #define LORA_SPREADING_FACTOR 10  // SF10 = 980 bps, ~50 km Reichweite
#endif

#ifndef DEEP_SLEEP_ENABLED
  #define DEEP_SLEEP_ENABLED true   // Solar-Optimierung
#endif

// ==========================================================================
// Global State
// ==========================================================================

static uint32_t   g_nonce          = 0;
static uint32_t   g_tx_count       = 0;
static uint32_t   g_fail_count     = 0;
static float      g_battery_v      = 0.0;
static uint64_t   g_total_energy_wh = 0;  // Kumulierte Produktion

// Timing
static uint32_t   g_last_tx_ms     = 0;
static uint32_t   g_boot_ms        = 0;

// ==========================================================================
// Forward Declarations
// ==========================================================================

static bool   init_hardware(void);
static bool   read_sensors(float *measurement_out, float *battery_v_out);
static bool   prepare_and_send_packet(float measurement);
static void   enter_deep_sleep(uint32_t duration_s);
static void   blink_status(uint8_t count, uint16_t duration_ms);

// ==========================================================================
// SETUP — Einmalig nach Boot
// ==========================================================================

void setup() {
  g_boot_ms = millis();

  // 1. Serielle Konsole (Debug)
  Serial.begin(115200);
  delay(100);
  Serial.println(F("\n╔══════════════════════════════════════════════╗"));
  Serial.println(F("║  Agent X — ESP32 IoT Resource Oracle v1.0  ║"));
  Serial.println(F("║  Zero-Trust-Telemetrie für Commodity-Token  ║"));
  Serial.println(F("╚══════════════════════════════════════════════╝"));

  // 2. Hardware initialisieren
  if (!init_hardware()) {
    Serial.println(F("[FATAL] Hardware-Init fehlgeschlagen — Deep-Sleep 60s"));
    blink_status(5, 200);
    enter_deep_sleep(60);
    return; // Never reached (ESP.restart() in deep sleep wake)
  }

  // 3. Boot-Info
  Serial.print(F("[BOOT] Device: "));
  Serial.println(F(DEVICE_ID));
  Serial.print(F("[BOOT] Resource: "));
  Serial.println(F(RESOURCE_TYPE));
  Serial.print(F("[BOOT] LoRa: "));
  Serial.print(LORA_FREQUENCY / 1000000);
  Serial.print(F(" MHz, SF"));
  Serial.println(LORA_SPREADING_FACTOR);
  Serial.print(F("[BOOT] Interval: "));
  Serial.print(TX_INTERVAL_S);
  Serial.println(F(" s"));

  Serial.println(F("[BOOT] ✅ Alle Module initialisiert"));
  blink_status(3, 300);
}

// ==========================================================================
// LOOP — Hauptschleife (wird periodisch durch Deep-Sleep unterbrochen)
// ==========================================================================

void loop() {
  float measurement = 0.0;

  // 1. Sensoren auslesen
  if (!read_sensors(&measurement, &g_battery_v)) {
    Serial.println(F("[WARN] Sensor-Read fehlgeschlagen"));
    g_fail_count++;
    delay(1000);
    return;
  }

  // 2. Messung signieren und senden
  if (measurement > 0.0) {
    if (prepare_and_send_packet(measurement)) {
      g_tx_count++;
      g_total_energy_wh += (uint64_t)(measurement * 1000); // kWh → Wh
      blink_status(1, 500); // Erfolg: 1× lang
    } else {
      g_fail_count++;
      blink_status(3, 150); // Fehler: 3× kurz
    }
  } else {
    Serial.println(F("[INFO] Keine signifikante Messung — skip TX"));
  }

  // 3. Status-Report
  Serial.println(F("═══════════════════════════════════════"));
  Serial.print(F("[STATS] TX: "));
  Serial.print(g_tx_count);
  Serial.print(F(" | Fail: "));
  Serial.print(g_fail_count);
  Serial.print(F(" | Nonce: "));
  Serial.println(g_nonce);
  Serial.print(F("[STATS] Battery: "));
  Serial.print(g_battery_v);
  Serial.print(F(" V | Uptime: "));
  Serial.print((millis() - g_boot_ms) / 1000);
  Serial.println(F(" s"));
  Serial.println(F("═══════════════════════════════════════"));

  // 4. Deep-Sleep (Solar-Optimierung)
  if (DEEP_SLEEP_ENABLED) {
    uint32_t elapsed_s = (millis() - g_last_tx_ms) / 1000;
    if (elapsed_s < TX_INTERVAL_S) {
      uint32_t sleep_s = TX_INTERVAL_S - elapsed_s;
      Serial.print(F("[SLEEP] Deep-Sleep für "));
      Serial.print(sleep_s);
      Serial.println(F(" s"));
      enter_deep_sleep(sleep_s);
    }
  } else {
    // Ohne Deep-Sleep: Einfach warten
    delay(TX_INTERVAL_S * 1000);
  }
}

// ==========================================================================
// Hardware-Initialisierung
// ==========================================================================

static bool init_hardware(void) {
  Serial.println(F("[INIT] Initialisiere Hardware..."));

  // 1. I2C für ATECC608A + Sensoren
  Wire.begin(21, 22); // SDA=GPIO21, SCL=GPIO22
  Wire.setClock(100000); // 100 kHz Standard-Mode
  Serial.println(F("[INIT] ✅ I2C (GPIO21/22, 100 kHz)"));

  // 2. Signatur-Engine initialisieren (ATECC608A)
  if (!sig_engine_init()) {
    Serial.println(F("[INIT] ❌ ATECC608A nicht gefunden — Soft-ECDSA-Fallback"));
    // Soft-ECDSA-Fallback für Development
    if (!sig_engine_init_soft()) {
      Serial.println(F("[FATAL] Kein Signatur-Backend verfügbar"));
      return false;
    }
  }

  // 3. SX1262 LoRa-Transceiver initialisieren
  sx1262_config_t lora_config = {
    .frequency_hz    = LORA_FREQUENCY,
    .spreading_factor = LORA_SPREADING_FACTOR,
    .bandwidth        = 125000,   // 125 kHz
    .coding_rate      = 5,        // 4/5
    .tx_power_dbm     = 14,       // +14 dBm (25 mW)
    .preamble_length  = 8,
    .sync_word        = 0x12,     // Private LoRa-Netzwerk
    .crc_enabled      = true,
    .invert_iq        = false,
  };

  if (!sx1262_init(&lora_config)) {
    Serial.println(F("[INIT] ❌ SX1262 nicht gefunden"));
    return false;
  }

  // 4. Sensor-Pins konfigurieren
  sensor_config_t sensor_cfg = {
    .adc_pin         = 34,    // GPIO34 = ADC1_CH6 (Stromsensor CT-Clamp)
    .adc_attenuation  = ADC_11db, // 0-3.3V Range
    .adc_samples      = 50,   // 50 Samples für Moving Average
    .vref_mv          = 3300, // 3.3V Referenz
    .scale_factor     = 1.0,  // Kalibrierungsfaktor (via Config)
  };

  if (!sensor_init(&sensor_cfg)) {
    Serial.println(F("[INIT] ❌ Sensor-Init fehlgeschlagen"));
    return false;
  }

  Serial.println(F("[INIT] ✅ Alle Hardware-Module bereit"));
  return true;
}

// ==========================================================================
// Sensor-Read
// ==========================================================================

static bool read_sensors(float *measurement_out, float *battery_v_out) {
  // 1. Hauptsensor (Strom/Leistung)
  float raw_adc = sensor_read_adc();
  if (raw_adc < 0) {
    return false;
  }

  // 2. ADC → physikalische Einheit (kWh)
  //    CT-Clamp: 0-30A → 0-1V (via Burden Resistor)
  //    ADC: 0-3.3V → 0-4095 (12-bit)
  //    Power = V_adc × scale_factor
  float power_w = raw_adc * 380.0; // 380W bei 3.3V (230V × CT-Ratio)
  *measurement_out = power_w / 1000.0; // W → kW (Momentan-Leistung)

  Serial.print(F("[SENSOR] ADC="));
  Serial.print(raw_adc);
  Serial.print(F(" V | Power="));
  Serial.print(power_w);
  Serial.print(F(" W | Measurement="));
  Serial.print(*measurement_out);
  Serial.println(F(" kW"));

  // 3. Batterie-Spannung (Spannungsteiler 1:2 an GPIO35)
  int batt_adc = analogRead(35);
  *battery_v_out = (batt_adc / 4095.0) * 3.3 * 2.0; // Spannungsteiler-Korrektur

  // 4. Kalibrierungs-Check
  if (power_w > 50000) { // >50 kW implausibel für Einzelanlage
    Serial.println(F("[WARN] Implausibler Messwert — verworfen"));
    *measurement_out = 0.0;
    return false;
  }

  return true;
}

// ==========================================================================
// Packet Preparation & Transmission
// ==========================================================================

static bool prepare_and_send_packet(float measurement) {
  Serial.println(F("[TX] Bereite LoRa-Paket vor..."));

  g_last_tx_ms = millis();
  uint32_t timestamp = g_boot_ms + g_last_tx_ms;

  // 1. CBOR-Payload erstellen und komprimieren
  uint8_t  cbor_buf[CBOR_MAX_PAYLOAD_SIZE];
  uint16_t cbor_len = 0;

  if (!cbor_encode_measurement(
        DEVICE_ID,
        RESOURCE_TYPE,
        measurement,
        timestamp,
        g_nonce,
        cbor_buf,
        sizeof(cbor_buf),
        &cbor_len
      )) {
    Serial.println(F("[TX] ❌ CBOR-Encoding fehlgeschlagen"));
    return false;
  }

  Serial.print(F("[TX] CBOR-Payload: "));
  Serial.print(cbor_len);
  Serial.println(F(" bytes"));

  // 2. ECDSA-Signatur über CBOR-Payload
  uint8_t  sig_buf[ECDSA_MAX_SIG_SIZE];
  uint16_t sig_len = 0;

  if (!sig_engine_sign(cbor_buf, cbor_len, sig_buf, &sig_len)) {
    Serial.println(F("[TX] ❌ Signatur fehlgeschlagen"));
    return false;
  }

  Serial.print(F("[TX] Signatur: "));
  Serial.print(sig_len);
  Serial.println(F(" bytes"));

  // 3. LoRa-Paket assemblieren
  //    Format: [CBOR_PAYLOAD (N bytes)] [SIGNATURE (65 bytes)]
  uint8_t  lora_buf[SX1262_MAX_PAYLOAD_SIZE];
  uint16_t total_len = cbor_len + sig_len;

  if (total_len > sizeof(lora_buf)) {
    Serial.println(F("[TX] ❌ Paket zu groß für LoRa-Frame"));
    return false;
  }

  memcpy(lora_buf, cbor_buf, cbor_len);
  memcpy(lora_buf + cbor_len, sig_buf, sig_len);

  // 4. Senden via SX1262
  Serial.print(F("[TX] Sende "));
  Serial.print(total_len);
  Serial.print(F(" Bytes @ "));
  Serial.print(LORA_FREQUENCY / 1000000);
  Serial.println(F(" MHz..."));

  if (!sx1262_send(lora_buf, total_len)) {
    Serial.println(F("[TX] ❌ LoRa-TX fehlgeschlagen"));
    return false;
  }

  // 5. Nonce inkrementieren (Replay-Schutz)
  g_nonce++;

  Serial.print(F("[TX] ✅ Paket gesendet — Nonce="));
  Serial.println(g_nonce - 1);

  // 6. Duty-Cycle einhalten (1% = 36s pro Stunde bei SF10)
  //    SF10 @ 125 kHz: ~200ms Time-on-Air für 150 Bytes
  //    1% Duty Cycle → max. 36s TX pro Stunde → 180 TX pro Stunde
  //    Unser Intervall: 300s = 12 TX pro Stunde → WEIT unter Limit ✅

  return true;
}

// ==========================================================================
// Deep-Sleep (Solar-Optimierung)
// ==========================================================================

static void enter_deep_sleep(uint32_t duration_s) {
  Serial.print(F("[SLEEP] Deep-Sleep "));
  Serial.print(duration_s);
  Serial.println(F(" s — Aufwachen via RTC-Timer"));

  // ULP-Co-Prozessor für Low-Power-Sensor-Read in Zukunft
  // Für jetzt: Kompletter Deep-Sleep

  // SX1262 in Sleep-Mode (0.1 µA)
  sx1262_sleep();

  // ESP32 Deep-Sleep konfigurieren
  esp_sleep_enable_timer_wakeup((uint64_t)duration_s * 1000000ULL);

  // Serielle Konsole flushen
  Serial.flush();

  // Deep-Sleep
  esp_deep_sleep_start();
  // Wird nie erreicht — ESP32 startet nach Wakeup neu (setup() wird aufgerufen)
}

// ==========================================================================
// Status-LED
// ==========================================================================

static void blink_status(uint8_t count, uint16_t duration_ms) {
  // GPIO2 = interne LED (ESP32 DevKit)
  pinMode(2, OUTPUT);

  for (uint8_t i = 0; i < count; i++) {
    digitalWrite(2, HIGH);
    delay(duration_ms);
    digitalWrite(2, LOW);
    if (i < count - 1) {
      delay(duration_ms / 2);
    }
  }
}
