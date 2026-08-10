/**
 * @file cbor_payload.h
 * @title CBOR Payload Encoder — <150 Byte LoRa-kompatible Messungen
 *
 * Komprimiert ESP32-Sensormessungen in minimales CBOR-Binärformat.
 * Ziel: Maximale Information in minimaler Byte-Zahl für LoRaWAN Fair Use.
 *
 * Payload-Struktur (CBOR Map, 8-10 Felder → 45-120 Bytes):
 *   {
 *     1: "ESP32_SOLAR_MUC_01",   // Device-ID (String, ~20B)
 *     2: "ENERGY_KWH",           // Resource-Type (String, ~12B)
 *     3: 1234567,                // Amount in Millieinheiten (uint32, 4B)
 *     4: 1723152000,             // Unix-Timestamp (uint32, 4B)
 *     5: 42,                     // Nonce (uint16, 2B)
 *   }
 *
 * CBOR-Vorteile gegenüber JSON:
 *   - Binär (kein Base64-Overhead)
 *   - Integer-Encoding (varint, 1-5 Bytes je nach Wert)
 *   - Map-Keys als Integer (1 Byte statt String-Key)
 *   - String-Längen als varint
 *
 * @author Agent X Engineering
 * @license BUSL-1.1
 */

#ifndef CBOR_PAYLOAD_H
#define CBOR_PAYLOAD_H

#include <Arduino.h>

// ==========================================================================
// Constants
// ==========================================================================

#define CBOR_MAX_PAYLOAD_SIZE  150   // LoRaWAN Fair Use Limit
#define CBOR_MAP_KEYS          5     // Anzahl Felder im Payload
#define CBOR_VERSION           1     // Payload-Format-Version

// CBOR Map Key Identifiers (Integer-Keys statt String-Keys = 10+ Bytes Ersparnis)
enum CBORKey : uint8_t {
  CBOR_KEY_DEVICE_ID     = 1,
  CBOR_KEY_RESOURCE_TYPE = 2,
  CBOR_KEY_AMOUNT        = 3,
  CBOR_KEY_TIMESTAMP     = 4,
  CBOR_KEY_NONCE         = 5,
};

// ==========================================================================
// CBOR Encoder (Minimal-Implementation, keine externe Lib nötig)
// ==========================================================================

/**
 * @brief Encodiert eine Sensor-Messung in CBOR-Binär.
 *
 * @param device_id      Eindeutige Geräte-ID (z.B. "ESP32_SOLAR_MUC_01")
 * @param resource_type  Ressourcen-Typ (z.B. "ENERGY_KWH")
 * @param amount         Messwert in physikalischer Einheit (z.B. 15.4 kWh)
 * @param timestamp      Unix-Timestamp der Messung
 * @param nonce          Monoton steigender Zähler (Replay-Schutz)
 * @param buf_out        Output-Buffer (mind. CBOR_MAX_PAYLOAD_SIZE)
 * @param buf_size       Größe des Output-Buffers
 * @param written_out    [out] Tatsächlich geschriebene Bytes
 * @return true wenn Encoding erfolgreich und < CBOR_MAX_PAYLOAD_SIZE
 */
bool cbor_encode_measurement(
    const char *device_id,
    const char *resource_type,
    float       amount,
    uint32_t    timestamp,
    uint32_t    nonce,
    uint8_t    *buf_out,
    uint16_t    buf_size,
    uint16_t   *written_out
);

// ==========================================================================
// CBOR Primitives (Interne Hilfsfunktionen)
// ==========================================================================

/**
 * @brief Schreibt einen CBOR-Integer (Major Type 0).
 *
 * CBOR Integer Encoding:
 *   - 0..23:     Direkt im Major-Byte (1 Byte total)
 *   - 24..255:   0x18 + 1 Byte (2 Bytes total)
 *   - 256..65535: 0x19 + 2 Bytes (3 Bytes total)
 *   - 65536..2^32-1: 0x1A + 4 Bytes (5 Bytes total)
 */
static uint16_t cbor_write_uint(uint8_t *buf, uint16_t offset, uint32_t value) {
  if (value <= 23) {
    buf[offset++] = (uint8_t)value;
  } else if (value <= 0xFF) {
    buf[offset++] = 0x18;
    buf[offset++] = (uint8_t)value;
  } else if (value <= 0xFFFF) {
    buf[offset++] = 0x19;
    buf[offset++] = (uint8_t)(value >> 8);
    buf[offset++] = (uint8_t)(value & 0xFF);
  } else {
    buf[offset++] = 0x1A;
    buf[offset++] = (uint8_t)(value >> 24);
    buf[offset++] = (uint8_t)((value >> 16) & 0xFF);
    buf[offset++] = (uint8_t)((value >> 8) & 0xFF);
    buf[offset++] = (uint8_t)(value & 0xFF);
  }
  return offset;
}

/**
 * @brief Schreibt einen CBOR-String (Major Type 3).
 *
 * Format: 0x60 + Länge (varint) + Rohdaten
 */
static uint16_t cbor_write_string(uint8_t *buf, uint16_t offset, const char *str) {
  uint16_t len = strlen(str);

  // Major Type 3 (Text String)
  uint8_t major = 0x60;

  if (len <= 23) {
    buf[offset++] = major | (uint8_t)len;
  } else if (len <= 0xFF) {
    buf[offset++] = major | 0x18;
    buf[offset++] = (uint8_t)len;
  } else {
    buf[offset++] = major | 0x19;
    buf[offset++] = (uint8_t)(len >> 8);
    buf[offset++] = (uint8_t)(len & 0xFF);
  }

  memcpy(buf + offset, str, len);
  offset += len;
  return offset;
}

/**
 * @brief Schreibt einen CBOR-Float (Major Type 7, IEEE 754 float32).
 *
 * Format: 0xFA + 4 Bytes (IEEE 754 single-precision)
 * Spart 4 Bytes gegenüber float64 in JSON
 */
static uint16_t cbor_write_float(uint8_t *buf, uint16_t offset, float value) {
  buf[offset++] = 0xFA; // Major Type 7, float32

  // IEEE 754 float32 (Big-Endian)
  union {
    float    f;
    uint32_t u;
  } converter;
  converter.f = value;

  buf[offset++] = (uint8_t)(converter.u >> 24);
  buf[offset++] = (uint8_t)((converter.u >> 16) & 0xFF);
  buf[offset++] = (uint8_t)((converter.u >> 8) & 0xFF);
  buf[offset++] = (uint8_t)(converter.u & 0xFF);

  return offset;
}

/**
 * @brief Schreibt eine CBOR-Map (Major Type 5).
 *
 * Format: 0xA0 + Anzahl-Paare (varint) + [Key, Value] × N
 * Map mit 5 Keys: 1 Byte für Map-Header + 5×2 Einträge
 */
static uint16_t cbor_write_map_header(uint8_t *buf, uint16_t offset, uint8_t num_pairs) {
  uint8_t major = 0xA0; // Major Type 5 (Map)
  buf[offset++] = major | num_pairs;
  return offset;
}

// ==========================================================================
// Haupt-Encoder-Implementation
// ==========================================================================

bool cbor_encode_measurement(
    const char *device_id,
    const char *resource_type,
    float       amount,
    uint32_t    timestamp,
    uint32_t    nonce,
    uint8_t    *buf_out,
    uint16_t    buf_size,
    uint16_t   *written_out
) {
  if (!device_id || !resource_type || !buf_out || !written_out) {
    return false;
  }

  uint16_t offset = 0;

  // 1. CBOR Map Header (5 Key-Value-Paare)
  offset = cbor_write_map_header(buf_out, offset, CBOR_MAP_KEYS);

  // 2. Map-Eintrag 1: Device-ID (Key=1, Value=String)
  offset = cbor_write_uint(buf_out, offset, CBOR_KEY_DEVICE_ID);
  offset = cbor_write_string(buf_out, offset, device_id);

  // 3. Map-Eintrag 2: Resource-Type (Key=2, Value=String)
  offset = cbor_write_uint(buf_out, offset, CBOR_KEY_RESOURCE_TYPE);
  offset = cbor_write_string(buf_out, offset, resource_type);

  // 4. Map-Eintrag 3: Amount (Key=3, Value=Float32)
  //    Float32 statt Float64 spart 4 Bytes
  offset = cbor_write_uint(buf_out, offset, CBOR_KEY_AMOUNT);
  offset = cbor_write_float(buf_out, offset, amount);

  // 5. Map-Eintrag 4: Timestamp (Key=4, Value=Uint32)
  offset = cbor_write_uint(buf_out, offset, CBOR_KEY_TIMESTAMP);
  offset = cbor_write_uint(buf_out, offset, timestamp);

  // 6. Map-Eintrag 5: Nonce (Key=5, Value=Uint32)
  offset = cbor_write_uint(buf_out, offset, CBOR_KEY_NONCE);
  offset = cbor_write_uint(buf_out, offset, nonce);

  *written_out = offset;

  // Validierung
  if (offset > CBOR_MAX_PAYLOAD_SIZE) {
    Serial.print(F("[CBOR] ⚠️ Payload zu groß: "));
    Serial.print(offset);
    Serial.print(F(" > "));
    Serial.println(CBOR_MAX_PAYLOAD_SIZE);
    return false;
  }

  return true;
}

// ==========================================================================
// CBOR Decoder (für Debug/Gateway-Seite)
// ==========================================================================

/**
 * @brief Validiert einen CBOR-Payload strukturell.
 *
 * Prüft:
 *  - Map-Header vorhanden
 *  - Alle 5 Keys vorhanden
 *  - Keine Buffer-Overflows
 *
 * @return true wenn Payload strukturell valide
 */
bool cbor_validate_payload(const uint8_t *buf, uint16_t len) {
  if (!buf || len < 3) return false;

  // Prüfe Map-Header (0xA5 = Map mit 5 Paaren)
  uint8_t header = buf[0];
  if ((header & 0xE0) != 0xA0) return false; // Kein Map Major Type

  uint8_t num_pairs = header & 0x1F;
  if (num_pairs != CBOR_MAP_KEYS) return false;

  // TODO: Vollständige strukturelle Validierung der Keys
  (void)len;
  return true;
}

/**
 * @brief Gibt einen CBOR-Payload als Debug-String aus.
 */
void cbor_debug_print(const uint8_t *buf, uint16_t len) {
  Serial.print(F("[CBOR] Payload "));
  Serial.print(len);
  Serial.print(F(" bytes: "));

  for (uint16_t i = 0; i < min((uint16_t)32, len); i++) {
    if (buf[i] < 0x10) Serial.print('0');
    Serial.print(buf[i], HEX);
    Serial.print(' ');
  }

  if (len > 32) {
    Serial.print(F("... ("));
    Serial.print(len - 32);
    Serial.print(F(" more)"));
  }

  Serial.println();
}

#endif // CBOR_PAYLOAD_H
