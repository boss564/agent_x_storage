// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title IoTVerifier — On-Chain Hardware-Signatur-Verifikation
/// @notice Verifiziert ECDSA-Signaturen von ESP32-Sensoren bevor Commodity-Tokens geprägt werden.
/// @dev Zero-Trust: Jede Messung muss kryptografisch von einem registrierten Gerät signiert sein.
contract IoTVerifier is Ownable {
    // =========================================================================
    // Constructor
    // =========================================================================

    constructor(address initialOwner) Ownable(initialOwner) {}
    using ECDSA for bytes32;
    using MessageHashUtils for bytes32;

    // =========================================================================
    // Events
    // =========================================================================

    event DeviceRegistered(bytes32 indexed deviceId, address signer, string resourceType, string location);
    event DeviceRevoked(bytes32 indexed deviceId);
    event MeasurementVerified(bytes32 indexed deviceId, string resourceType, uint256 amount, uint256 timestamp);
    event MeasurementRejected(bytes32 indexed deviceId, string reason);

    // =========================================================================
    // Types
    // =========================================================================

    struct Device {
        address signer;        // Ethereum-Adresse des ESP32 Secure Elements
        string resourceType;   // "ENERGY_KWH" | "WATER_LITERS" | "WHEAT_KG" | "DIESEL_LITERS"
        string location;       // Physischer Standort (z.B. "München, Solarpark 1")
        bool active;           // false wenn Gerät deaktiviert/kompromittiert
        uint256 registeredAt;  // Unix-Timestamp der Registrierung
        uint256 lastMeasurement; // Letzte verifizierte Messung
        uint256 totalMeasured;   // Kumulierte Messungen (Wei/Gwei/Einheiten)
    }

    struct Measurement {
        bytes32 deviceId;
        string resourceType;
        uint256 amount;        // In Basiseinheiten (Wei-Äquivalent: kWh × 10^18)
        uint256 timestamp;
        bytes signature;       // ECDSA-Signatur des ESP32
    }

    // =========================================================================
    // State
    // =========================================================================

    mapping(bytes32 => Device) public devices;
    bytes32[] public deviceIds;
    mapping(bytes32 => uint256) public nonces; // Replay-Schutz pro Device

    // =========================================================================
    // Registration
    // =========================================================================

    /// @notice Registriert ein neues ESP32-Gerät mit seinem Public Key.
    /// @param deviceId Eindeutige Geräte-ID (keccak256 der ESP32-MAC + Seriennummer)
    /// @param signer Ethereum-Adresse abgeleitet vom ESP32 Secure Element Public Key
    /// @param resourceType Typ der gemessenen Ressource
    /// @param location Physischer Standort
    function registerDevice(
        bytes32 deviceId,
        address signer,
        string calldata resourceType,
        string calldata location
    ) external onlyOwner {
        require(!devices[deviceId].active, "Device already registered");
        require(signer != address(0), "Invalid signer address");
        require(bytes(resourceType).length > 0, "Resource type required");

        devices[deviceId] = Device({
            signer: signer,
            resourceType: resourceType,
            location: location,
            active: true,
            registeredAt: block.timestamp,
            lastMeasurement: 0,
            totalMeasured: 0
        });
        deviceIds.push(deviceId);

        emit DeviceRegistered(deviceId, signer, resourceType, location);
    }

    /// @notice Deaktiviert ein Gerät (Kompromittierung, Diebstahl, Wartung).
    function revokeDevice(bytes32 deviceId) external onlyOwner {
        require(devices[deviceId].active, "Device not active");
        devices[deviceId].active = false;
        emit DeviceRevoked(deviceId);
    }

    /// @notice Reaktiviert ein Gerät nach Wartung/Austausch mit neuem Signer.
    function reactivateDevice(bytes32 deviceId, address newSigner) external onlyOwner {
        require(!devices[deviceId].active, "Device still active");
        require(newSigner != address(0), "Invalid signer");
        devices[deviceId].active = true;
        devices[deviceId].signer = newSigner;
        emit DeviceRegistered(deviceId, newSigner, devices[deviceId].resourceType, devices[deviceId].location);
    }

    // =========================================================================
    // Zero-Trust Signature Verification
    // =========================================================================

    /// @notice Verifiziert eine ESP32-Messung (Zero-Trust: nur signierte Daten akzeptiert).
    /// @param measurement Die zu verifizierende Messung
    /// @return valid true wenn Signatur von registriertem, aktivem Gerät stammt
    function verifyMeasurement(Measurement calldata measurement) external returns (bool) {
        Device storage device = devices[measurement.deviceId];

        // 1. Gerät muss registriert und aktiv sein
        if (!device.active) {
            emit MeasurementRejected(measurement.deviceId, "DEVICE_NOT_ACTIVE");
            return false;
        }

        // 2. Resource-Type muss zum registrierten Typ passen
        if (keccak256(bytes(device.resourceType)) != keccak256(bytes(measurement.resourceType))) {
            emit MeasurementRejected(measurement.deviceId, "RESOURCE_TYPE_MISMATCH");
            return false;
        }

        // 3. Replay-Schutz: Nonce muss aktuell sein
        require(measurement.timestamp > device.lastMeasurement, "Timestamp must be newer than last measurement");

        // 4. ECDSA-Signatur prüfen (Zero-Trust Kern)
        bytes32 messageHash = keccak256(
            abi.encodePacked(
                measurement.deviceId,
                measurement.resourceType,
                measurement.amount,
                measurement.timestamp,
                nonces[measurement.deviceId]
            )
        );

        bytes32 ethSignedMessageHash = messageHash.toEthSignedMessageHash();
        address recoveredSigner = ethSignedMessageHash.recover(measurement.signature);

        if (recoveredSigner != device.signer) {
            emit MeasurementRejected(measurement.deviceId, "INVALID_SIGNATURE");
            return false;
        }

        // 5. Nonce inkrementieren (Replay-Schutz)
        nonces[measurement.deviceId]++;

        // 6. Device-Status aktualisieren
        device.lastMeasurement = measurement.timestamp;
        device.totalMeasured += measurement.amount;

        emit MeasurementVerified(
            measurement.deviceId,
            measurement.resourceType,
            measurement.amount,
            measurement.timestamp
        );

        return true;
    }

    // =========================================================================
    // View Functions
    // =========================================================================

    /// @notice Prüft ob ein Gerät registriert und aktiv ist.
    function isDeviceActive(bytes32 deviceId) external view returns (bool) {
        return devices[deviceId].active;
    }

    /// @notice Gibt die Signer-Adresse eines Geräts zurück.
    function getDeviceSigner(bytes32 deviceId) external view returns (address) {
        return devices[deviceId].signer;
    }

    /// @notice Gibt alle registrierten Geräte-IDs zurück.
    function getDeviceCount() external view returns (uint256) {
        return deviceIds.length;
    }

    /// @notice Gibt Statistiken eines Geräts zurück.
    function getDeviceStats(bytes32 deviceId) external view returns (
        string memory resourceType,
        string memory location,
        bool active,
        uint256 totalMeasured,
        uint256 lastMeasurement
    ) {
        Device storage d = devices[deviceId];
        return (d.resourceType, d.location, d.active, d.totalMeasured, d.lastMeasurement);
    }
}
