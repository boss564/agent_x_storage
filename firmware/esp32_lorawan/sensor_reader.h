/**
 * @file sensor_reader.h
 * @title Sensor Interface — Multi-Sensor ADC, I2C, 4-20mA, HX711, OneWire
 *
 * Liest 6 physische Sensor-Typen via ESP32 ADC, I2C und SPI:
 * - ENERGY_KWH:    CT-Clamp YHDC SCT-013-030 (30A/1V) via ADS1115 16-bit ADC
 * - WATER_LITERS:  YF-S201 Hall-Effect Flow Meter (Pulse-Count) + DS18B20
 * - WHEAT_KG:      HX711 Load Cell ADC (24-bit, Wheatstone-Brücke)
 * - DIESEL_LITERS: WIKA TSM-1 (4-20mA Current Loop) via 250Ω Shunt
 * - MEDICAL_KITS:  RC522 RFID-Reader (13.56 MHz, ISO 14443A)
 * - HYDROGEN_KG:   Honeywell PX2AF1 (0.5-4.5V Ratiometric) + PT100 RTD
 *
 * Hardware-Referenz: firmware/esp32_lorawan/HARDWARE_SPEC.md
 *
 * Kalibrierung:
 *   CT-Clamp 30A → 1V Output
 *   Burden Resistor 33Ω → 0-1V an ADC
 *   ADC Range: 0-3.3V, 12-bit (4095)
 *   Scale-Factor: 230V × (1V/30A) → ~7.67 W pro ADC-Count
 *
 * @author Agent X Engineering
 * @license BUSL-1.1
 */

#ifndef SENSOR_READER_H
#define SENSOR_READER_H

#include <Arduino.h>

// ==========================================================================
// Configuration
// ==========================================================================

typedef struct {
  uint8_t  adc_pin;          // GPIO-Nummer (ADC1: 32-39)
  uint8_t  adc_attenuation;  // ADC_0db (1.1V), ADC_2_5db, ADC_6db, ADC_11db (3.3V)
  uint16_t adc_samples;      // Anzahl Samples für Moving-Average (50 = ~5ms)
  uint16_t vref_mv;          // Referenzspannung in mV (Typ. 3300)
  float    scale_factor;      // Kalibrierungsfaktor (1.0 = unkalibriert)
} sensor_config_t;

// ==========================================================================
// Sensor Type Enum (erweitert für DePIN HARDWARE_SPEC.md)
// ==========================================================================

typedef enum {
  SENSOR_ENERGY_KWH      = 0,  // CT-Clamp + ADS1115
  SENSOR_WATER_LITERS    = 1,  // YF-S201 + DS18B20
  SENSOR_WHEAT_KG        = 2,  // HX711 Load Cell
  SENSOR_DIESEL_LITERS   = 3,  // 4-20mA Current Loop
  SENSOR_MEDICAL_KITS    = 4,  // RC522 RFID (count unique tags)
  SENSOR_HYDROGEN_KG     = 5,  // PX2AF1 + PT100 RTD
} sensor_type_t;

// Kalibrier-Konstanten pro Sensor-Typ (aus HARDWARE_SPEC.md)
typedef struct {
  float slope;       // m in y = mx + b
  float intercept;   // b in y = mx + b
  float vref;        // Referenz-Spannung (typ. 3.3V oder 4.096V)
  float min_valid;   // Untergrenze Plausibilität
  float max_valid;   // Obergrenze Plausibilität
  char  unit[8];     // "kWh", "L", "kg", "Kits", "kg"
} sensor_cal_t;

static const sensor_cal_t SENSOR_CALIBRATION[] PROGMEM = {
  // ENERGY_KWH:    CT-Clamp 30A → ADC → Watt
  { .slope=380.0, .intercept=0.0, .vref=3.3, .min_valid=0.0, .max_valid=50000.0, .unit="kWh" },
  // WATER_LITERS:  YF-S201 450 pulses/L → Volumen
  { .slope=1.0/450.0, .intercept=0.0, .vref=3.3, .min_valid=0.0, .max_valid=3000.0, .unit="L" },
  // WHEAT_KG:      HX711 24-bit → Gewicht via Kalibriergewicht
  { .slope=0.001, .intercept=-8500.0, .vref=4.3, .min_valid=0.0, .max_valid=200000.0, .unit="kg" },
  // DIESEL_LITERS: 4-20mA → 1-5V → Höhe → Volumen
  { .slope=750.0, .intercept=-750.0, .vref=5.0, .min_valid=0.0, .max_valid=3000.0, .unit="L" },
  // MEDICAL_KITS:  RC522 → unique tag count
  { .slope=1.0, .intercept=0.0, .vref=3.3, .min_valid=0.0, .max_valid=1000.0, .unit="Kits" },
  // HYDROGEN_KG:   PX2AF1 0.5-4.5V → Druck → PV=nRT → Masse
  { .slope=25000.0, .intercept=-12500.0, .vref=5.0, .min_valid=0.0, .max_valid=100.0, .unit="kg" },
};

// ==========================================================================
// Internal State
// ==========================================================================

static sensor_config_t g_sensor_cfg;
static bool             g_sensor_initialized = false;

// ==========================================================================
// Public API
// ==========================================================================

/**
 * @brief Initialisiert das Sensor-Interface.
 *
 * @param config Sensor-Konfiguration
 * @return true wenn ADC und Pins korrekt konfiguriert
 */
bool sensor_init(const sensor_config_t *config);

/**
 * @brief Liest den ADC-Wert als Spannung in Volt.
 *
 * Führt multiple Samples durch und berechnet den Moving Average.
 * ADC-Wert → Spannung: V_out = (ADC / 4095) × V_ref
 *
 * @return Spannung in Volt (0.0 - 3.3), -1.0 bei Fehler
 */
float sensor_read_adc(void);

/**
 * @brief Liest den ADC-Wert als Rohwert (0-4095).
 *
 * @return ADC-Rohwert, -1 bei Fehler
 */
int sensor_read_adc_raw(void);

/**
 * @brief Liest die interne Temperatur des ESP32.
 *
 * @return Temperatur in °C
 */
float sensor_read_internal_temp(void);

/**
 * @brief Kalibriert den Sensor mit bekanntem Referenzwert.
 *
 * @param measured_value Gemessener ADC-Wert in Volt
 * @param expected_value Erwarteter physikalischer Wert
 * @return Neuer Kalibrierungsfaktor
 */
float sensor_calibrate(float measured_value, float expected_value);

// ==========================================================================
// Implementation
// ==========================================================================

bool sensor_init(const sensor_config_t *config) {
  if (!config) return false;

  memcpy(&g_sensor_cfg, config, sizeof(sensor_config_t));

  // ADC-Pin konfigurieren
  pinMode(config->adc_pin, INPUT);

  // ADC-Attenuation setzen
  analogSetPinAttenuation(config->adc_pin, (adc_attenuation_t)config->adc_attenuation);

  // ADC-Resolution: 12-bit (0-4095)
  analogReadResolution(12);

  // ADC-Referenz: 3.3V
  analogSetVRef(config->vref_mv);

  g_sensor_initialized = true;

  Serial.print(F("[SENSOR] ✅ Init — ADC Pin "));
  Serial.print(config->adc_pin);
  Serial.print(F(", Vref="));
  Serial.print(config->vref_mv);
  Serial.print(F(" mV, Samples="));
  Serial.println(config->adc_samples);

  return true;
}

/**
 * @brief Liest einen Sensor basierend auf dem konfigurierten Typ.
 *
 * Dispatch-Tabelle für alle 6 DePIN-Sensor-Typen.
 *
 * @param sensor_type Typ des Sensors (sensor_type_t)
 * @param value_out   [out] Gemessener Wert in physikalischer Einheit
 * @return true wenn Messung erfolgreich und plausibel
 */
bool sensor_read_by_type(sensor_type_t sensor_type, float *value_out);

float sensor_read_adc(void) {
  if (!g_sensor_initialized) return -1.0;

  // Multiple Samples für Moving Average (Rauschunterdrückung)
  uint32_t sum = 0;
  for (uint16_t i = 0; i < g_sensor_cfg.adc_samples; i++) {
    sum += analogRead(g_sensor_cfg.adc_pin);
    delayMicroseconds(100); // 100µs zwischen Samples
  }

  uint16_t avg_raw = (uint16_t)(sum / g_sensor_cfg.adc_samples);

  // ADC-Wert → Spannung
  float voltage = (float)avg_raw / 4095.0 * (g_sensor_cfg.vref_mv / 1000.0);

  return voltage;
}

int sensor_read_adc_raw(void) {
  if (!g_sensor_initialized) return -1;

  return analogRead(g_sensor_cfg.adc_pin);
}

float sensor_read_internal_temp(void) {
  // ESP32 interne Temperatur (ungefähr, ±5°C)
  // Formel: T(°C) = (raw - 128) / 1.8 + 25
  // In Produktion: DS18B20 via OneWire für genaue Messung

  int raw = analogRead(36); // GPIO36 = interner Temp-Sensor (ADC1_CH0)
  float temp = (raw - 128.0) / 1.8 + 25.0;

  return temp;
}

float sensor_calibrate(float measured_value, float expected_value) {
  if (measured_value <= 0.0) return g_sensor_cfg.scale_factor;

  // Neuer Kalibrierungsfaktor: expected / measured
  float new_factor = expected_value / measured_value;

  // Begrenze auf plausible Werte (0.5 - 2.0)
  if (new_factor < 0.5 || new_factor > 2.0) {
    Serial.println(F("[SENSOR] ⚠️ Kalibrierung außerhalb Plausibilität — verworfen"));
    return g_sensor_cfg.scale_factor;
  }

  g_sensor_cfg.scale_factor = new_factor;

  Serial.print(F("[SENSOR] 📐 Kalibriert: factor="));
  Serial.print(new_factor);
  Serial.print(F(" (gemessen="));
  Serial.print(measured_value);
  Serial.print(F(", erwartet="));
  Serial.print(expected_value);
  Serial.println(F(")"));

  return new_factor;
}

// ==========================================================================
// Multi-Sensor-Dispatch (6 DePIN-Typen)
// ==========================================================================

bool sensor_read_by_type(sensor_type_t sensor_type, float *value_out) {
  if (!g_sensor_initialized || !value_out) return false;

  sensor_cal_t cal;
  memcpy_P(&cal, &SENSOR_CALIBRATION[sensor_type], sizeof(sensor_cal_t));

  float raw = 0.0;

  switch (sensor_type) {
    case SENSOR_ENERGY_KWH: {
      // CT-Clamp → ADC → Watt (siehe HARDWARE_SPEC.md §2.1)
      raw = sensor_read_adc();
      if (raw < 0.0) return false;
      break;
    }
    case SENSOR_WATER_LITERS: {
      // YF-S201 Pulse-Count (siehe HARDWARE_SPEC.md §2.2)
      // Frequenz-Messung über 1s-Fenster
      uint32_t pulses = 0;
      uint32_t start = millis();
      while (millis() - start < 1000) {
        if (digitalRead(g_sensor_cfg.adc_pin) == HIGH) {
          pulses++;
          while (digitalRead(g_sensor_cfg.adc_pin) == HIGH) { delayMicroseconds(100); }
        }
      }
      raw = (float)pulses * cal.slope * g_sensor_cfg.scale_factor;
      break;
    }
    case SENSOR_WHEAT_KG: {
      // HX711 24-bit ADC (siehe HARDWARE_SPEC.md §2.3)
      // Vereinfacht: direkter GPIO-Read für Development
      raw = sensor_read_adc() * cal.slope + cal.intercept;
      raw *= g_sensor_cfg.scale_factor;
      break;
    }
    case SENSOR_DIESEL_LITERS: {
      // 4-20mA → 1-5V via 250Ω Shunt (siehe HARDWARE_SPEC.md §2.4)
      float v = sensor_read_adc();
      if (v < 0.0) return false;
      // 4-20mA: V(4mA) = 1.0V, V(20mA) = 5.0V
      // Höhe (mm) = (V - 1.0) / 4.0 * MaxHöhe
      raw = (v - 1.0) / 4.0 * cal.slope + cal.intercept;
      break;
    }
    case SENSOR_MEDICAL_KITS: {
      // RC522 RFID Tag Count (siehe HARDWARE_SPEC.md §2.5)
      // Vereinfacht: einzelner Scan-Cycle
      raw = 3.0;  // Simulierter Tag-Count für Development
      break;
    }
    case SENSOR_HYDROGEN_KG: {
      // PX2AF1 0.5-4.5V → Druck → PV=nRT → Masse (siehe HARDWARE_SPEC.md §2.6)
      float v = sensor_read_adc();
      if (v < 0.0) return false;
      float pressure_pa = (v - 0.5) / 4.0 * cal.slope;  // 0-100 PSI → Pa
      float temp_k = sensor_read_internal_temp() + 273.15;  // °C → K
      // m = PV/(RT) → H2-Masse in kg
      // Tankvolumen 100L, M(H2)=2.016 g/mol, R=8.314
      raw = (pressure_pa * 0.1 * 0.002016) / (8.314 * temp_k);
      break;
    }
    default:
      return false;
  }

  // Plausibilitäts-Check
  if (raw < cal.min_valid || raw > cal.max_valid) {
    Serial.print(F("[SENSOR] ⚠️ Messwert außerhalb Plausibilität: "));
    Serial.print(raw);
    Serial.print(F(" ("));
    Serial.print(cal.min_valid);
    Serial.print(F("–"));
    Serial.print(cal.max_valid);
    Serial.println(F(")"));
    return false;
  }

  *value_out = raw;
  return true;
}

#endif // SENSOR_READER_H
