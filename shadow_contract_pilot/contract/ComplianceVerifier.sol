// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/cryptography/ECDSAUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/cryptography/EIP712Upgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/NoncesUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";

/**
 * @title ComplianceVerifier
 * @dev On-Chain Gate für Off-Chain generierte Compliance-Passports (Welle 24).
 *
 * Integration: Wave 20 (CertiK), Wave 23 (Token Launch), Wave 24 (Trading).
 *
 * Prüft EIP-712-signierte Compliance-Passports, die vom Off-Chain-Orchestrator
 * (token_trading_orchestrator.py) nach erfolgreicher MiCAR/Sanktionen/Circuit-Breaker-
 * Prüfung ausgestellt werden. Nur Transaktionen mit gültigem Passport erreichen
 * die DEX-Routing-Ebene.
 *
 * UUPS-upgradefähig für regulatorische Anpassungen ohne Migrationsaufwand.
 */
contract ComplianceVerifier is
    Initializable,
    AccessControlUpgradeable,
    UUPSUpgradeable,
    EIP712Upgradeable,
    NoncesUpgradeable,
    ReentrancyGuardUpgradeable
{
    using ECDSAUpgradeable for bytes32;

    bytes32 public constant UPGRADER_ROLE = keccak256("UPGRADER_ROLE");
    bytes32 public constant SIGNER_ROLE = keccak256("SIGNER_ROLE");
    bytes32 public constant ADMIN_ROLE = keccak256("ADMIN_ROLE");

    bytes32 public constant COMPLIANCE_DATA_TYPEHASH =
        keccak256(
            "ComplianceData(address trader,address token,uint256 amount,uint256 price,uint256 nonce,uint256 deadline)"
        );

    mapping(uint256 => bool) public usedNonces;
    bool public isTradingPaused;

    event CompliancePassportUsed(
        address indexed trader, address indexed token,
        uint256 amount, uint256 price, uint256 nonce,
        address indexed signer, uint256 timestamp
    );
    event TradingPaused(bool paused, address indexed admin);
    event SignerAdded(address indexed signer, address indexed admin);
    event SignerRemoved(address indexed signer, address indexed admin);

    modifier whenNotPaused() {
        require(!isTradingPaused, "ComplianceVerifier: Trading is globally paused");
        _;
    }

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() { _disableInitializers(); }

    function initialize(address initialAdmin) public initializer {
        __AccessControl_init();
        __UUPSUpgradeable_init();
        __EIP712_init("AGX Protocol Compliance Verifier", "1.0.0");
        __Nonces_init();
        _grantRole(DEFAULT_ADMIN_ROLE, initialAdmin);
        _grantRole(ADMIN_ROLE, initialAdmin);
        _grantRole(UPGRADER_ROLE, initialAdmin);
        _grantRole(SIGNER_ROLE, initialAdmin);
        isTradingPaused = false;
    }

    function verifyAndConsumeCompliance(
        address trader, address token, uint256 amount, uint256 price,
        uint256 nonce, uint256 deadline, bytes calldata signature
    ) external whenNotPaused nonReentrant returns (bool) {
        require(block.timestamp <= deadline, "ComplianceVerifier: Deadline expired");
        require(!usedNonces[nonce], "ComplianceVerifier: Nonce already used");
        require(trader != address(0), "ComplianceVerifier: Invalid trader");
        require(token != address(0), "ComplianceVerifier: Invalid token");

        bytes32 digest = _hashTypedDataV4(keccak256(abi.encode(
            COMPLIANCE_DATA_TYPEHASH, trader, token, amount, price, nonce, deadline
        )));

        address recoveredSigner = digest.recover(signature);
        require(hasRole(SIGNER_ROLE, recoveredSigner),
                "ComplianceVerifier: Invalid signature or signer");

        usedNonces[nonce] = true;
        emit CompliancePassportUsed(trader, token, amount, price, nonce,
                                     recoveredSigner, block.timestamp);
        return true;
    }

    modifier withCompliance(
        address trader, address token, uint256 amount, uint256 price,
        uint256 nonce, uint256 deadline, bytes calldata signature
    ) {
        verifyAndConsumeCompliance(trader, token, amount, price, nonce, deadline, signature);
        _;
    }

    function addSigner(address signer) external onlyRole(ADMIN_ROLE) {
        grantRole(SIGNER_ROLE, signer);
        emit SignerAdded(signer, msg.sender);
    }

    function removeSigner(address signer) external onlyRole(ADMIN_ROLE) {
        revokeRole(SIGNER_ROLE, signer);
        emit SignerRemoved(signer, msg.sender);
    }

    function setTradingPaused(bool _paused) external onlyRole(ADMIN_ROLE) {
        isTradingPaused = _paused;
        emit TradingPaused(_paused, msg.sender);
    }

    function _authorizeUpgrade(address newImplementation)
        internal override onlyRole(UPGRADER_ROLE) {}

    function getDomainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }
}
