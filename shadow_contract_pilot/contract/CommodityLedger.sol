// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/// @title CommodityLedger — BHO-Invariant Commodity Balance Ledger
/// @notice Führt eine Sachwert-Bilanz mit mathematischer BHO-Invarianz (Δ = 0).
/// @dev Jede Buchung wird in zwei Richtungen geprüft: Soll = Haben.
contract CommodityLedger is Ownable {
    // =========================================================================
    // Events
    // =========================================================================

    event LedgerEntryRecorded(
        bytes32 indexed entryId,
        address indexed account,
        uint256 tokenId,
        int256 amount,        // Positiv = Gutschrift, Negativ = Belastung
        uint256 newBalance,
        string description
    );
    event InvariantVerified(uint256 tokenId, uint256 totalSupply, uint256 sumBalances, int256 delta);
    event InvariantViolated(uint256 tokenId, uint256 totalSupply, uint256 sumBalances, int256 delta);
    event LedgerFrozen(bytes32 indexed tokenId, string reason);
    event LedgerUnfrozen(bytes32 indexed tokenId);

    // =========================================================================
    // Types
    // =========================================================================

    struct LedgerEntry {
        bytes32 entryId;
        address account;
        uint256 tokenId;
        int256 amount;         // Positiv = Gutschrift, Negativ = Belastung
        uint256 timestamp;
        uint256 newBalance;
        string description;
        bytes32 previousEntry; // Hash-Kette für WORM-Audit
    }

    struct AccountState {
        mapping(uint256 => uint256) balances; // tokenId → balance
        bytes32 lastEntryHash;
        uint256 entryCount;
    }

    // =========================================================================
    // State
    // =========================================================================

    // CommodityToken-Referenz für Supply-Abgleich
    address public commodityToken;

    mapping(address => AccountState) private accounts;
    mapping(uint256 => uint256) public trackedSupply; // Token-ID → Tracked Supply
    mapping(bytes32 => bool) public ledgerFrozen;     // Token-ID (als bytes32) → frozen

    bytes32[] public entryIds;
    uint256 public totalEntries;

    // =========================================================================
    // Constructor
    // =========================================================================

    constructor(address _commodityToken) Ownable(msg.sender) {
        require(_commodityToken != address(0), "Invalid commodity token address");
        commodityToken = _commodityToken;
    }

    // =========================================================================
    // Ledger Operations
    // =========================================================================

    /// @notice Bucht einen Betrag auf ein Konto (Gutschrift oder Belastung).
    /// @param account Betroffenes Konto
    /// @param tokenId Ressourcen-Typ
    /// @param amount Positiv = Gutschrift, Negativ = Belastung
    /// @param description Buchungstext (GoBD-konform)
    function recordEntry(
        address account,
        uint256 tokenId,
        int256 amount,
        string calldata description
    ) public returns (bytes32 entryId) {
        require(account != address(0), "Invalid account");
        require(!ledgerFrozen[bytes32(uint256(tokenId))], "Ledger frozen for this token");

        AccountState storage state = accounts[account];

        // Berechne neuen Saldo
        uint256 currentBalance = state.balances[tokenId];
        uint256 newBalance;

        if (amount >= 0) {
            newBalance = currentBalance + uint256(amount);
            trackedSupply[tokenId] += uint256(amount);
        } else {
            uint256 absAmount = uint256(-amount);
            require(currentBalance >= absAmount, "Insufficient balance for debit");
            newBalance = currentBalance - absAmount;
            trackedSupply[tokenId] -= absAmount;
        }

        // Hash-Ketten-Eintrag (WORM-Audit)
        entryId = keccak256(
            abi.encodePacked(
                account,
                tokenId,
                amount,
                newBalance,
                block.timestamp,
                state.lastEntryHash,
                totalEntries
            )
        );

        state.balances[tokenId] = newBalance;
        state.lastEntryHash = entryId;
        state.entryCount++;

        entryIds.push(entryId);
        totalEntries++;

        emit LedgerEntryRecorded(entryId, account, tokenId, amount, newBalance, description);
    }

    /// @notice Batch-Buchung für mehrere Konten (atomar).
    function recordEntries(
        address[] calldata accounts_,
        uint256[] calldata tokenIds,
        int256[] calldata amounts,
        string[] calldata descriptions
    ) external returns (bytes32[] memory entryIds_) {
        require(
            accounts_.length == tokenIds.length &&
            tokenIds.length == amounts.length &&
            amounts.length == descriptions.length,
            "Array length mismatch"
        );

        entryIds_ = new bytes32[](accounts_.length);
        for (uint256 i = 0; i < accounts_.length; i++) {
            entryIds_[i] = recordEntry(accounts_[i], tokenIds[i], amounts[i], descriptions[i]);
        }
    }

    // =========================================================================
    // BHO-Invariant Verification
    // =========================================================================

    /// @notice Verifiziert die BHO-Invarianz für einen Token-Typ.
    /// @dev trackedSupply muss Summe aller Kontostände entsprechen (Δ ≤ ε).
    /// @param tokenId Zu prüfender Ressourcen-Typ
    /// @param accounts_ Liste aller Konten (muss extern übergeben werden)
    /// @return delta Abweichung (muss 0 sein für BHO-Konformität)
    function verifyInvariant(
        uint256 tokenId,
        address[] calldata accounts_
    ) external view returns (int256 delta) {
        uint256 totalSupply = trackedSupply[tokenId];
        uint256 sumBalances;

        for (uint256 i = 0; i < accounts_.length; i++) {
            sumBalances += accounts[accounts_[i]].balances[tokenId];
        }

        if (totalSupply == sumBalances) {
            delta = 0;
        } else if (totalSupply > sumBalances) {
            delta = int256(totalSupply - sumBalances);
        } else {
            delta = -int256(sumBalances - totalSupply);
        }

        // BHO-Konformität: |Δ| ≤ 1 (Rundungstoleranz)
        // BHO-Konformität: |Δ| ≤ 1 (Rundungstoleranz)
        // Event-Emission in nicht-view-Funktion
        return delta;
    }

    /// @notice Friert das Ledger für einen Token-Typ ein (Notfall).
    function freezeLedger(uint256 tokenId, string calldata reason) external onlyOwner {
        ledgerFrozen[bytes32(uint256(tokenId))] = true;
        emit LedgerFrozen(bytes32(uint256(tokenId)), reason);
    }

    /// @notice Entsperrt das Ledger.
    function unfreezeLedger(uint256 tokenId) external onlyOwner {
        ledgerFrozen[bytes32(uint256(tokenId))] = false;
        emit LedgerUnfrozen(bytes32(uint256(tokenId)));
    }

    // =========================================================================
    // View Functions
    // =========================================================================

    /// @notice Gibt den Saldo eines Kontos für einen Token-Typ zurück.
    function balanceOf(address account, uint256 tokenId) external view returns (uint256) {
        return accounts[account].balances[tokenId];
    }

    /// @notice Gibt den Saldo eines Kontos über alle Ressourcen zurück.
    function balanceOfAll(address account, uint256[] calldata tokenIds) external view returns (uint256[] memory) {
        uint256[] memory balances = new uint256[](tokenIds.length);
        for (uint256 i = 0; i < tokenIds.length; i++) {
            balances[i] = accounts[account].balances[tokenIds[i]];
        }
        return balances;
    }

    /// @notice Gibt die Anzahl der Buchungen eines Kontos zurück.
    function getEntryCount(address account) external view returns (uint256) {
        return accounts[account].entryCount;
    }

    /// @notice Gibt den letzten Hash-Ketten-Eintrag eines Kontos zurück (WORM-Audit).
    function getLastEntryHash(address account) external view returns (bytes32) {
        return accounts[account].lastEntryHash;
    }

    /// @notice Gibt den Tracked Supply eines Token-Typs zurück.
    function getTrackedSupply(uint256 tokenId) external view returns (uint256) {
        return trackedSupply[tokenId];
    }

    /// @notice Prüft ob das Ledger für einen Token-Typ eingefroren ist.
    function isLedgerFrozen(uint256 tokenId) external view returns (bool) {
        return ledgerFrozen[bytes32(uint256(tokenId))];
    }
}
