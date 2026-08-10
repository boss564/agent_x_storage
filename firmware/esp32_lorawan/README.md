# Agent X — ESP32 LoRaWAN IoT Resource Oracle Firmware

Signiert physische Ressourcen-Messungen via ECDSA und sendet sie als CBOR-komprimierte LoRa-Pakete (<150 Bytes) an den Agent X CommodityToken Smart Contract.

## Hardware

| Komponente | Typ | Funktion |
|-----------|------|----------|
| MCU | ESP32-WROOM-32E | Dual-Core Xtensa LX6, 240 MHz, WiFi/BLE |
| LoRa | SX1262 (Semtech) | 868 MHz, +22 dBm, -148 dBm sensitivity |
| Secure Element | ATECC608A (Microchip) | ECDSA Signing, CC EAL6+, BSI TR-03162 |
| Stromsensor | SCT-013-030 (YHDC) | CT-Clamp 30A/1V, non-invasive |
| Solar | 2.4W Panel + 18650 Li-Ion | Autark, Deep-Sleep optimiert |

## Pin-Belegung (ESP32 → Peripherie)

| ESP32 GPIO | Funktion | Komponente |
|-----------|----------|------------|
| GPIO21/22 | I2C (SDA/SCL) | ATECC608A |
| GPIO5/18/23/19 | SPI (NSS/SCK/MOSI/MISO) | SX1262 |
| GPIO26 | BUSY Input | SX1262 |
| GPIO27 | DIO1 Interrupt | SX1262 TX-Done |
| GPIO14 | Reset Output | SX1262 |
| GPIO34 | ADC1_CH6 | CT-Clamp Stromsensor |
| GPIO35 | ADC1_CH7 | Batterie-Spannungsteiler |

## Build & Flash

### Arduino IDE

1. ESP32 Board Support installieren: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
2. Board: `ESP32-WROOM-32E`
3. `esp32_lorawan.ino` öffnen
4. In `config.h` (optional): `DEVICE_ID`, `RESOURCE_TYPE`, `LORA_FREQUENCY` anpassen
5. Kompilieren & Flashen

### PlatformIO (empfohlen für Produktion)

```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200

lib_deps =
    cbor2

build_flags =
    -D DEVICE_ID=\"ESP32_SOLAR_MUC_01\"
    -D RESOURCE_TYPE=\"ENERGY_KWH\"
    -D TX_INTERVAL_S=300
    -D LORA_FREQUENCY=868100000
```

## Konfiguration

Via Build-Flags in `platformio.ini` oder `config.h`:

| Flag | Default | Beschreibung |
|------|---------|-------------|
| `DEVICE_ID` | `ESP32_SOLAR_MUC_01` | Eindeutige Geräte-ID (max. 32 Zeichen) |
| `RESOURCE_TYPE` | `ENERGY_KWH` | Ressourcen-Typ (ENERGY_KWH/WATER_LITERS/...) |
| `TX_INTERVAL_S` | `300` | Sendeintervall in Sekunden |
| `LORA_FREQUENCY` | `868100000` | LoRa-Frequenz in Hz |
| `LORA_SPREADING_FACTOR` | `10` | SF7-SF12 |
| `DEEP_SLEEP_ENABLED` | `true` | Solar-Optimierung via Deep-Sleep |

## Datenfluss

```
┌─────────────────────────────────────────────────────────────┐
│ ESP32 Boot                                                  │
│   ├── ATECC608A Init (I2C)                                  │
│   ├── SX1262 Init (SPI)         868.1 MHz, SF10             │
│   ├── Sensor Init (ADC)         50-Sample Moving Average     │
│   └── READY                                                  │
│                                                              │
│ Loop (alle TX_INTERVAL_S):                                   │
│   ├── ADC-Read (CT-Clamp)       kWh Messung                  │
│   ├── CBOR-Encode               ~50 Bytes (cbor_payload.h)   │
│   ├── ECDSA-Sign                +65 Bytes (sig_engine.h)     │
│   ├── SX1262 TX                 ~115 Bytes total              │
│   ├── TX-Done IRQ               ~200ms Time-on-Air           │
│   ├── Nonce++                   Replay-Schutz                │
│   └── Deep-Sleep                300s (Duty-Cycle < 1%)       │
└─────────────────────────────────────────────────────────────┘
```

## LoRa-Paket-Format

```
[CBOR Payload (48-70 Bytes)] [ECDSA Signature (65 Bytes)]
├─ Map Header (1B)
├─ Device-ID (1 + 18 = 19B)
├─ Resource-Type (1 + 11 = 12B)
├─ Amount Float32 (1 + 4 = 5B)
├─ Timestamp uint32 (1 + 4 = 5B)
└─ Nonce uint32 (1-5B)
                            ├─ r (32B)
                            ├─ s (32B)
                            └─ v (1B)
Total: ~113-135 Bytes (< 150B Limit ✅)
```

## Betriebsmodi

### Normal-Mode (WiFi verfügbar)
- TX-Intervall: 5 Minuten (288 TX/Tag)
- Duty-Cycle: ~6% @ SF7, ~0.2% @ SF10 mit 30min
- Deep-Sleep zwischen TX
- Solar + 18650 → unbegrenzte Laufzeit

### Off-Grid-Mode (nur LoRa)
- Mesh-Routing via `MeshRouterAgent` (Wave 33)
- Store-and-Forward bei Relays
- Reduziertes TX-Intervall (15-30min)

## Security

- **Key Storage:** Private Key verlässt NIE den ATECC608A Chip
- **Signaturen:** ECDSA secp256k1 (Ethereum-kompatibel)
- **Replay-Schutz:** Monoton steigende Nonce im CBOR-Payload
- **Physisch:** ATECC608A Common Criteria EAL6+ zertifiziert
- **Audit:** Jede Messung on-chain verifizierbar via IoTVerifier.sol

## Test-Suite

```bash
# Alle 15 Tests (CBOR + ECDSA + LoRa + Pipeline)
python3 scripts/test_esp32_firmware.py

# Nur Payload-Analyse
python3 scripts/test_esp32_firmware.py --payload-analysis
```
