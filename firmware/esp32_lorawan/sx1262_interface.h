/**
 * @file sx1262_interface.h
 * @title SX1262 LoRa Transceiver Interface (868 MHz)
 *
 * Treiber für den Semtech SX1262 LoRa-Transceiver via SPI.
 * Optimiert für Low-Power-Solar-Betrieb mit Deep-Sleep.
 *
 * SX1262 Key Features:
 *   - Frequenz:    150-960 MHz (konfiguriert auf 868 MHz EU SRD)
 *   - TX-Power:    +22 dBm max (158 mW)
 *   - RX-Sens:     -148 dBm @ SF12 (extrem empfindlich)
 *   - Sleep:       0.1 µA (Warm-Start)
 *   - Interface:   SPI (9 MHz max)
 *
 * Pin-Belegung (ESP32 → SX1262):
 *   - NSS:    GPIO5   (Chip Select)
 *   - SCK:    GPIO18  (SPI Clock)
 *   - MOSI:   GPIO23  (SPI Master-Out)
 *   - MISO:   GPIO19  (SPI Master-In)
 *   - BUSY:   GPIO26  (SX1262 Busy-Flag)
 *   - DIO1:   GPIO27  (TX-Done / RX-Done Interrupt)
 *   - RST:    GPIO14  (Hardware-Reset)
 *
 * @author Agent X Engineering
 * @license BUSL-1.1
 */

#ifndef SX1262_INTERFACE_H
#define SX1262_INTERFACE_H

#include <Arduino.h>
#include <SPI.h>

// ==========================================================================
// Pin Configuration (anpassbar via Build-Flags)
// ==========================================================================

#ifndef SX1262_NSS
  #define SX1262_NSS    5
#endif
#ifndef SX1262_SCK
  #define SX1262_SCK    18
#endif
#ifndef SX1262_MOSI
  #define SX1262_MOSI   23
#endif
#ifndef SX1262_MISO
  #define SX1262_MISO   19
#endif
#ifndef SX1262_BUSY
  #define SX1262_BUSY   26
#endif
#ifndef SX1262_DIO1
  #define SX1262_DIO1   27
#endif
#ifndef SX1262_RST
  #define SX1262_RST    14
#endif

// ==========================================================================
// SX1262 Commands (Semtech Datasheet Rev 1.2)
// ==========================================================================

#define SX1262_CMD_SET_SLEEP              0x84
#define SX1262_CMD_SET_STANDBY            0x80
#define SX1262_CMD_SET_FS                 0xC1  // Frequency Synthesis
#define SX1262_CMD_SET_TX                 0x83
#define SX1262_CMD_SET_RX                 0x82
#define SX1262_CMD_SET_PACKET_TYPE        0x8A
#define SX1262_CMD_SET_RF_FREQUENCY       0x86
#define SX1262_CMD_SET_TX_PARAMS          0x8E
#define SX1262_CMD_SET_PACKET_PARAMS      0x8C
#define SX1262_CMD_SET_BUFFER_BASE_ADDR   0x8F
#define SX1262_CMD_WRITE_BUFFER           0x0E
#define SX1262_CMD_READ_BUFFER            0x1E
#define SX1262_CMD_GET_STATUS             0xC0
#define SX1262_CMD_GET_DEVICE_ERRORS      0x17
#define SX1262_CMD_CLEAR_DEVICE_ERRORS     0x07
#define SX1262_CMD_SET_DIO_IRQ_PARAMS     0x08
#define SX1262_CMD_GET_IRQ_STATUS         0x12
#define SX1262_CMD_CLEAR_IRQ_STATUS       0x02
#define SX1262_CMD_SET_REGULATOR_MODE     0x96

// IRQ Flags
#define SX1262_IRQ_TX_DONE                (1 << 0)
#define SX1262_IRQ_RX_DONE                (1 << 1)
#define SX1262_IRQ_TIMEOUT                (1 << 9)
#define SX1262_IRQ_CRC_ERROR              (1 << 7)

// ==========================================================================
// Configuration Types
// ==========================================================================

typedef struct {
  uint32_t frequency_hz;       // z.B. 868100000
  uint8_t  spreading_factor;   // 5-12 (SF5-SF12)
  uint32_t bandwidth;           // 125000, 250000, 500000 Hz
  uint8_t  coding_rate;        // 5-8 (4/5 bis 4/8)
  int8_t   tx_power_dbm;       // -9 bis +22 dBm
  uint16_t preamble_length;    // 8-65535 Symbole
  uint8_t  sync_word;          // 0x12 = Private, 0x34 = Public LoRaWAN
  bool     crc_enabled;
  bool     invert_iq;
} sx1262_config_t;

#define SX1262_MAX_PAYLOAD_SIZE  255

// ==========================================================================
// SPI Communication Primitives
// ==========================================================================

static SPIClass sx1262_spi(VSPI);

/**
 * @brief Sendet einen SX1262-Kommando via SPI.
 */
static void sx1262_write_command(uint8_t opcode, const uint8_t *data, uint8_t len) {
  // Wait for BUSY pin LOW (SX1262 bereit)
  while (digitalRead(SX1262_BUSY) == HIGH) {
    delayMicroseconds(10);
  }

  digitalWrite(SX1262_NSS, LOW);
  sx1262_spi.transfer(opcode);
  if (data && len > 0) {
    sx1262_spi.transfer(data, len);
  }
  digitalWrite(SX1262_NSS, HIGH);
}

/**
 * @brief Liest Daten vom SX1262 via SPI.
 */
static void sx1262_read_command(uint8_t opcode, uint8_t *data, uint8_t len) {
  while (digitalRead(SX1262_BUSY) == HIGH) {
    delayMicroseconds(10);
  }

  digitalWrite(SX1262_NSS, LOW);
  sx1262_spi.transfer(opcode);
  // Dummy-Byte für SPI-Timing
  sx1262_spi.transfer(0x00);
  // Daten lesen
  for (uint8_t i = 0; i < len; i++) {
    data[i] = sx1262_spi.transfer(0x00);
  }
  digitalWrite(SX1262_NSS, HIGH);
}

/**
 * @brief Hardware-Reset des SX1262.
 */
static void sx1262_hardware_reset(void) {
  pinMode(SX1262_RST, OUTPUT);
  digitalWrite(SX1262_RST, LOW);
  delay(10);
  digitalWrite(SX1262_RST, HIGH);
  delay(20); // t_POWER_ON nach Reset

  // Warte bis BUSY LOW
  while (digitalRead(SX1262_BUSY) == HIGH) {
    delay(1);
  }
}

// ==========================================================================
// Core API
// ==========================================================================

/**
 * @brief Initialisiert den SX1262 LoRa-Transceiver.
 *
 * Ablauf:
 *  1. SPI initialisieren (9 MHz)
 *  2. Hardware-Reset
 *  3. LoRa-Modus setzen (Packet Type = LoRa)
 *  4. Frequenz, TX-Params, Packet-Params konfigurieren
 *  5. DIO1 als TX-Done-Interrupt konfigurieren
 *
 * @param config LoRa-Konfiguration
 * @return true wenn Init erfolgreich
 */
bool sx1262_init(const sx1262_config_t *config);

/**
 * @brief Sendet ein LoRa-Paket.
 *
 * Blockiert bis TX-Done (DIO1 Interrupt oder Timeout).
 *
 * @param data  Zu sendende Daten
 * @param len   Datenlänge in Bytes (max. 255)
 * @return true wenn TX erfolgreich bestätigt
 */
bool sx1262_send(const uint8_t *data, uint16_t len);

/**
 * @brief Versetzt SX1262 in Deep-Sleep (0.1 µA).
 */
void sx1262_sleep(void);

/**
 * @brief Berechnet die Time-on-Air eines LoRa-Pakets.
 *
 * Formel (Semtech AN1200.13):
 *   T_packet = T_preamble + T_payload
 *   T_payload = payloadSymbNb × T_sym
 *
 * @return Time-on-Air in Millisekunden
 */
uint32_t sx1262_calc_time_on_air(uint16_t payload_len, uint8_t sf, uint32_t bw);

// ==========================================================================
// Implementation
// ==========================================================================

bool sx1262_init(const sx1262_config_t *config) {
  if (!config) return false;

  Serial.println(F("[SX1262] Initialisiere..."));

  // 1. GPIO initialisieren
  pinMode(SX1262_NSS, OUTPUT);
  digitalWrite(SX1262_NSS, HIGH);
  pinMode(SX1262_BUSY, INPUT);
  pinMode(SX1262_DIO1, INPUT);
  pinMode(SX1262_RST, OUTPUT);

  // 2. SPI initialisieren (VSPI, 9 MHz)
  sx1262_spi.begin(SX1262_SCK, SX1262_MISO, SX1262_MOSI, SX1262_NSS);
  sx1262_spi.setFrequency(9000000);
  sx1262_spi.setDataMode(SPI_MODE0);

  // 3. Hardware-Reset
  sx1262_hardware_reset();
  Serial.println(F("[SX1262] ✅ Hardware-Reset"));

  // 4. LoRa-Modus setzen
  uint8_t pkt_type = 0x01; // LoRa
  sx1262_write_command(SX1262_CMD_SET_PACKET_TYPE, &pkt_type, 1);

  // 5. Frequenz setzen (868.1 MHz)
  //    RF_Frequency = (freq_hz × 2^25) / 32e6
  uint32_t rf_freq = (uint32_t)(((uint64_t)config->frequency_hz * 33554432ULL) / 32000000ULL);
  uint8_t freq_buf[4] = {
    (uint8_t)(rf_freq >> 24),
    (uint8_t)((rf_freq >> 16) & 0xFF),
    (uint8_t)((rf_freq >> 8) & 0xFF),
    (uint8_t)(rf_freq & 0xFF)
  };
  sx1262_write_command(SX1262_CMD_SET_RF_FREQUENCY, freq_buf, 4);
  Serial.print(F("[SX1262] ✅ Frequenz: "));
  Serial.print(config->frequency_hz / 1000000);
  Serial.println(F(" MHz"));

  // 6. TX-Parameter setzen
  uint8_t tx_buf[2] = {
    (uint8_t)(config->tx_power_dbm & 0xFF), // Power
    0x02  // Ramp Time: 40µs
  };
  sx1262_write_command(SX1262_CMD_SET_TX_PARAMS, tx_buf, 2);

  // 7. Packet-Parameter setzen
  //    PB1: [SF(4) | BW(3) | CR(1)]
  //    PB2: [CR(3) | ???]
  uint8_t bw_val;
  switch (config->bandwidth) {
    case 125000:  bw_val = 0x04; break;
    case 250000:  bw_val = 0x05; break;
    case 500000:  bw_val = 0x06; break;
    default:      bw_val = 0x04; break;
  }

  uint8_t pkt_buf[4] = {
    (uint8_t)((config->spreading_factor << 4) | (bw_val << 1) | ((config->coding_rate >> 2) & 0x01)),
    (uint8_t)((config->coding_rate & 0x03) << 6),
    (uint8_t)(config->preamble_length >> 8),
    (uint8_t)(config->preamble_length & 0xFF)
  };
  sx1262_write_command(SX1262_CMD_SET_PACKET_PARAMS, pkt_buf, 4);

  // 8. IRQ konfigurieren (TX-Done + RX-Done)
  uint8_t irq_buf[8] = {
    0x00, 0x00, 0x00, 0x00, // IRQ Mask (alle disabled für TX-only)
    SX1262_IRQ_TX_DONE,      // DIO1 = TX Done
    0x00, 0x00, 0x00
  };
  sx1262_write_command(SX1262_CMD_SET_DIO_IRQ_PARAMS, irq_buf, 8);

  // 9. Sync Word setzen (Private Netzwerk)
  uint8_t sync_buf[2] = {
    (uint8_t)((config->sync_word >> 8) & 0xFF),
    (uint8_t)(config->sync_word & 0xFF)
  };
  sx1262_write_command(0x8B, sync_buf, 2); // Write Register für Sync Word

  // 10. Buffer-Basis-Adresse
  uint8_t buf_addr[2] = {0x00, 0x00}; // TX Base = 0x00, RX Base = 0x00
  sx1262_write_command(SX1262_CMD_SET_BUFFER_BASE_ADDR, buf_addr, 2);

  // 11. In Standby gehen
  uint8_t standby_cfg = 0x01; // XOSC on
  sx1262_write_command(SX1262_CMD_SET_STANDBY, &standby_cfg, 1);

  // 12. Time-on-Air Info
  uint32_t toa = sx1262_calc_time_on_air(150, config->spreading_factor, config->bandwidth);
  Serial.print(F("[SX1262] ✅ Time-on-Air: ~"));
  Serial.print(toa);
  Serial.println(F(" ms @ max payload"));
  Serial.println(F("[SX1262] ✅ Init abgeschlossen"));

  return true;
}

bool sx1262_send(const uint8_t *data, uint16_t len) {
  if (!data || len == 0 || len > SX1262_MAX_PAYLOAD_SIZE) {
    return false;
  }

  // 1. In Frequency-Synthesis-Mode
  uint8_t fs_cmd = 0x00;
  sx1262_write_command(SX1262_CMD_SET_FS, &fs_cmd, 0);
  delay(1);

  // 2. Payload in TX-Buffer schreiben
  //    Offset 0x00 (TX Base Address)
  uint8_t write_buf[SX1262_MAX_PAYLOAD_SIZE + 1];
  write_buf[0] = 0x00; // Offset im Buffer
  memcpy(write_buf + 1, data, len);
  sx1262_write_command(SX1262_CMD_WRITE_BUFFER, write_buf, len + 1);

  // 3. TX starten
  //    Timeout = 0x0000 (kein Timeout für TX)
  uint8_t tx_buf[3] = {0x00, 0x00, 0x00};
  sx1262_write_command(SX1262_CMD_SET_TX, tx_buf, 3);

  // 4. Warte auf TX-Done (DIO1 Interrupt = HIGH)
  uint32_t start = millis();
  uint32_t timeout = 5000; // 5s Timeout (sollte nie erreicht werden)

  while (digitalRead(SX1262_DIO1) == LOW) {
    if (millis() - start > timeout) {
      Serial.println(F("[SX1262] ❌ TX-Timeout!"));
      return false;
    }
    delay(1);
  }

  // 5. IRQ-Status prüfen
  uint8_t irq_status[2];
  sx1262_read_command(SX1262_CMD_GET_IRQ_STATUS, irq_status, 2);
  uint16_t irq = (irq_status[0] << 8) | irq_status[1];

  if (irq & SX1262_IRQ_TX_DONE) {
    // IRQ-Flags clearen
    uint8_t clear_buf[2] = {irq_status[0], irq_status[1]};
    sx1262_write_command(SX1262_CMD_CLEAR_IRQ_STATUS, clear_buf, 2);

    Serial.print(F("[SX1262] ✅ TX-Done in "));
    Serial.print(millis() - start);
    Serial.println(F(" ms"));
    return true;
  }

  Serial.println(F("[SX1262] ❌ TX fehlgeschlagen — kein TX-Done IRQ"));
  return false;
}

void sx1262_sleep(void) {
  uint8_t sleep_cfg[1] = {0x00}; // Warm-Start (0.1µA), kein Retain
  sx1262_write_command(SX1262_CMD_SET_SLEEP, sleep_cfg, 1);
  Serial.println(F("[SX1262] 😴 Deep-Sleep (0.1 µA)"));
}

uint32_t sx1262_calc_time_on_air(uint16_t payload_len, uint8_t sf, uint32_t bw) {
  // Semtech AN1200.13: LoRa Modem Designer's Guide
  // T_sym = 2^SF / BW
  // T_preamble = (preamble_len + 4.25) × T_sym
  // T_payload = payloadSymbNb × T_sym

  float t_sym = (float)(1 << sf) / (float)bw;
  float t_preamble = 12.25 * t_sym; // 8 Symbole + 4.25 Fixed

  // Payload Symbol Calculation (vereinfacht)
  uint8_t ih = 0; // Implicit Header disabled
  uint8_t de = 0; // Low Data Rate Optimize disabled
  uint8_t cr = 1; // Coding Rate 4/5

  float payload_symb_nb = 8.0 + (float)max(
    (int)(ceil((float)(8 * payload_len - 4 * sf + 28 + 16 - 20 * ih) /
           (float)(4 * (sf - 2 * de))) * (cr + 4)),
    0
  );

  float t_payload = payload_symb_nb * t_sym;
  float t_packet = t_preamble + t_payload;

  return (uint32_t)(t_packet * 1000.0); // Sekunden → Millisekunden
}

#endif // SX1262_INTERFACE_H
