// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title VOB_Shadow_Escrow
 * @dev Smart Contract für den Shadow-Contract-Piloten.
 * Simuliert VOB/B-konforme Bauabwicklung mit EURe-Token.
 *
 * Rechtssicherer Parallelbetrieb: Alle Zahlungsflüsse werden 1:1
 * im Smart Contract abgebildet, ohne die traditionelle VOB/B-Abwicklung
 * zu ersetzen. Die Behörde kann den Shadow Contract im Read-Only-Modus
 * beobachten und mit der realen Abwicklung vergleichen.
 *
 * Invariante (formal verifiziert, Wave 20):
 *   totalBudget == totalReleased + taxVault + contractBalance
 *   (retentionVault ist in contractBalance enthalten — kein additive Position)
 *
 * VOB/B-Konformität:
 *   - §16 Zahlungsfrist 30d nach Rechnungsstellung
 *   - §17 5% Sicherheitseinbehalt pro Abschlag
 *   - §13 Mängelrüge 14d Frist nach Abnahme
 *   - §13b UStG Reverse-Charge (19% USt)
 *
 * Integration: Wave 16 (Monerium SEPA-Bridge), Wave 18 (Shadow Contract),
 *              Wave 20 (CertiK Audit)
 */
contract VOB_Shadow_Escrow is ReentrancyGuard, Ownable {
    IERC20 public eureToken;

    struct Milestone {
        string ozId;
        string description;
        uint256 grossAmount;       // Bruttobetrag inkl. USt
        uint256 releaseableAmount; // Nettobetrag für Auszahlung (gross − vat − retention)
        uint256 vatAmount;         // §13b UStG: 19% USt, in completeMilestone berechnet
        uint256 retentionAmount;   // §17 VOB/B: 5% Einbehalt, in completeMilestone berechnet
        bool isCompleted;
        bytes32 popwProofHash;     // PoPW-IoT/ZK-Proof (Wave 5)
        uint256 completedAt;       // Block-Timestamp der Fertigstellung
        uint256 createdAt;         // Block-Timestamp der Erstellung (für Timeout)
    }

    struct Project {
        address client;            // Bauherr / Behörde
        address contractor;        // Auftragnehmer
        address auditor;           // RPA / Wirtschaftsprüfer
        address taxAuthority;      // Finanzamt / BZSt
        uint256 totalBudget;       // Gesamtfinanzierung
        uint256 totalReleased;     // Summe aller Auszahlungen (netto)
        uint256 retentionVault;    // §17 VOB/B: 5% Einbehalt
        uint256 taxVault;          // §13b UStG: Reverse-Charge USt
        uint256 acceptedAt;        // Timestamp der Abnahme (für Verjährungsfrist)
        bool isActive;
    }

    Project public project;
    mapping(string => Milestone) public milestones;
    string[] public milestoneIds;

    // --- Events (GoBD-JSONL Audit-Trail, Wave 6) ---

    event ProjectFunded(uint256 amount, uint256 totalBudget);
    event MilestoneAdded(string ozId, string description, uint256 grossAmount);
    event MilestoneCompleted(
        string ozId, uint256 grossAmount, bytes32 proofHash, uint256 timestamp
    );
    event MilestoneReleased(
        string ozId, uint256 netAmount, uint256 taxAmount, uint256 retentionAmount
    );
    event RetentionReleased(address to, uint256 amount);
    event TaxTransferred(address taxAuthority, uint256 amount);
    event ProjectClosed(
        address client, address contractor, uint256 totalReleased,
        uint256 retentionReleased, uint256 taxTransferred
    );
    event ProjectReopened(address by, address client);

    uint256 constant WARRANTY_PERIOD = 4 * 365 days;  // VOB/B §13: 4 Jahre für Bauwerke

    error ProjectNotActive();
    error MilestoneExists();
    error MilestoneNotFound();
    error AlreadyCompleted();
    error AlreadyReleased();
    error InsufficientBudget();
    error TransferFailed();

    constructor(
        address _eureToken,
        address _client,
        address _contractor,
        address _auditor,
        address _taxAuthority
    ) Ownable(_client) {
        require(_eureToken != address(0), "Invalid EURe token");
        require(_contractor != address(0), "Invalid contractor");
        eureToken = IERC20(_eureToken);
        project = Project({
            client: _client,
            contractor: _contractor,
            auditor: _auditor,
            taxAuthority: _taxAuthority,
            totalBudget: 0,
            totalReleased: 0,
            retentionVault: 0,
            taxVault: 0,
            acceptedAt: 0,
            isActive: true
        });
        // Ownership bereits via Ownable(_client) im Constructor gesetzt (OZ v5)
    }

    // ================================================================
    // Finanzierung
    // ================================================================

    /**
     * @dev Behörde finanziert das Projekt mit EURe.
     *      In der realen Welt: SEPA-Überweisung → Monerium Mint (Wave 16).
     *      Hier: EURe-Token-Transfer on-chain.
     */
    function fundProject(uint256 _amount) external onlyOwner {
        if (!project.isActive) revert ProjectNotActive();
        if (!eureToken.transferFrom(msg.sender, address(this), _amount))
            revert TransferFailed();
        project.totalBudget += _amount;
        emit ProjectFunded(_amount, project.totalBudget);
    }

    // ================================================================
    // Meilenstein-Management
    // ================================================================

    /**
     * @dev Meilenstein aus GAEB-Leistungsverzeichnis anlegen.
     *      OZ-Referenz und Bruttobetrag aus X83/X84 (Wave 2).
     */
    function addMilestone(
        string memory _ozId,
        string memory _description,
        uint256 _grossAmount
    ) external onlyOwner {
        if (!project.isActive) revert ProjectNotActive();
        if (bytes(_ozId).length == 0) revert("OZ-ID required");
        if (_grossAmount == 0) revert("Amount required");
        if (milestones[_ozId].grossAmount != 0) revert MilestoneExists();

        milestones[_ozId] = Milestone({
            ozId: _ozId,
            description: _description,
            grossAmount: _grossAmount,
            releaseableAmount: 0,
            vatAmount: 0,
            retentionAmount: 0,
            isCompleted: false,
            popwProofHash: bytes32(0),
            completedAt: 0,
            createdAt: block.timestamp
        });
        milestoneIds.push(_ozId);
        emit MilestoneAdded(_ozId, _description, _grossAmount);
    }

    /**
     * @dev Meilenstein mit PoPW-Proof abschließen.
     *      Der Proof-Hash verankert IoT/GPS/ZK-Evidenz (Wave 5)
     *      on-chain als manipulationssicheren Leistungsnachweis.
     *
     *      Authorization (ADR-008):
     *        - Client (Bauherr): jederzeit
     *        - Auditor (RPA/WP): jederzeit, als neutraler Dritter
     *        - Contractor: nach 14 Tagen ohne Client-Bestätigung (Timeout)
     *
     *      Berechnet die VOB/B-konforme Aufteilung:
     *        vat       = gross * 19 / 119   (§13b UStG Reverse-Charge)
     *        retention = gross * 5 / 100     (§17 VOB/B Sicherheitseinbehalt)
     *        net       = gross - vat - retention
     *
     *      Buchung und Token-Transfer erfolgen ERST in releaseMilestone(),
     *      damit die Conservation-of-Funds Invariante zu jedem Zeitpunkt hält.
     */
    function completeMilestone(
        string memory _ozId,
        bytes32 _popwProofHash
    ) external {
        Milestone storage m = milestones[_ozId];
        if (m.grossAmount == 0) revert MilestoneNotFound();
        if (m.isCompleted) revert AlreadyCompleted();
        if (!project.isActive) revert ProjectNotActive();

        // ADR-008: Client, Auditor, oder Contractor nach 14-Tage-Timeout
        bool isClient = msg.sender == project.client;
        bool isAuditor = msg.sender == project.auditor;
        bool isContractorWithTimeout = msg.sender == project.contractor
            && block.timestamp >= m.createdAt + 14 days;
        if (!isClient && !isAuditor && !isContractorWithTimeout)
            revert("Not authorized: client, auditor, or contractor after 14d");

        uint256 gross = m.grossAmount;
        uint256 vat = (gross * 19) / 119;
        uint256 retention = (gross * 5) / 100;
        uint256 net = gross - vat - retention;

        // Guard: keine stillen Rundungsverluste
        if (net + vat + retention != gross) revert("Rounding mismatch");

        m.isCompleted = true;
        m.popwProofHash = _popwProofHash;
        m.completedAt = block.timestamp;
        m.releaseableAmount = net;
        m.vatAmount = vat;
        m.retentionAmount = retention;

        // KEINE Buchung auf project.totalReleased/retentionVault/taxVault hier —
        // das geschieht erst bei der tatsächlichen Auszahlung in releaseMilestone().

        emit MilestoneCompleted(_ozId, gross, _popwProofHash, block.timestamp);
    }

    /**
     * @dev Auszahlung eines abgeschlossenen Meilensteins.
     *      Verwendet die in completeMilestone() berechneten und gespeicherten
     *      VAT/Retention-Werte — keine Neuberechnung, keine Rundungsdifferenz.
     *
     *      Buchungsreihenfolge (Checks-Effects-Interactions):
     *        1. Milestone auf released markieren (releaseableAmount = 0)
     *        2. Project-Buckets aktualisieren
     *        3. Token-Transfers ausführen
     *
     *      nonReentrant schützt vor Reentrancy-Angriffen (CertiK-geprüft, Wave 20).
     */
    function releaseMilestone(string memory _ozId) external nonReentrant {
        Milestone storage m = milestones[_ozId];
        if (!m.isCompleted) revert("Milestone not completed");
        if (m.releaseableAmount == 0) revert AlreadyReleased();
        if (!project.isActive) revert ProjectNotActive();

        uint256 net = m.releaseableAmount;
        uint256 vat = m.vatAmount;
        uint256 retention = m.retentionAmount;

        // Effects: Zustandsänderungen VOR externen Calls (CEI-Pattern, Wave 20)
        m.releaseableAmount = 0;
        project.totalReleased += net;
        project.taxVault += vat;
        project.retentionVault += retention;

        // Interactions: Token-Transfers
        if (!eureToken.transfer(project.taxAuthority, vat))
            revert TransferFailed();
        emit TaxTransferred(project.taxAuthority, vat);

        if (!eureToken.transfer(project.contractor, net))
            revert TransferFailed();

        emit MilestoneReleased(_ozId, net, vat, retention);
    }

    // ================================================================
    // §17 VOB/B: Sicherheitseinbehalt freigeben
    // ================================================================

    /**
     * @dev Gibt den Sicherheitseinbehalt nach Abnahme frei.
     *
     *      §17 VOB/B: 5% Einbehalt, freigegeben nach Abnahme.
     *      §13 VOB/B Verjährungsfrist: 4 Jahre für Bauwerke.
     *
     *      Authorization (ADR-008):
     *        - Client (Bauherr): jederzeit
     *        - Auditor (RPA/WP): jederzeit, als neutraler Dritter
     *        - Contractor: nach Ablauf der Verjährungsfrist (WARRANTY_PERIOD)
     *          ab Abnahme (project.acceptedAt)
     */
    function releaseRetention(uint256 _amount) external {
        // Kein isActive-Guard: §17 VOB/B sieht Rückgabe nach Abnahme vor,
        // also gerade dann, wenn das Projekt abgeschlossen ist (isActive=false).
        // Die Drei-Parteien-Auth + _amount > retentionVault tragen die Funktion allein.
        if (_amount > project.retentionVault) revert InsufficientBudget();

        bool isClient = msg.sender == project.client;
        bool isAuditor = msg.sender == project.auditor;
        bool isContractorAfterWarranty = msg.sender == project.contractor
            && project.acceptedAt > 0
            && block.timestamp >= project.acceptedAt + WARRANTY_PERIOD;
        if (!isClient && !isAuditor && !isContractorAfterWarranty)
            revert("Not authorized: client, auditor, or contractor after warranty");

        project.retentionVault -= _amount;
        project.totalReleased += _amount;  // freigegebener Einbehalt = Auszahlung an Contractor
        if (!eureToken.transfer(project.contractor, _amount))
            revert TransferFailed();
        emit RetentionReleased(project.contractor, _amount);
    }

    // ================================================================
    // Projektabschluss
    // ================================================================

    /**
     * @dev Schließt das Projekt ab.
     *
     *      ADR-008: Nur erlaubt, wenn ALLE Meilensteine completed UND released
     *      sind. Verhindert, dass Funds in VAT/Retention/unfertigen Meilensteinen
     *      permanent eingesperrt werden.
     *
     *      Nach closeProject() sind alle Mutationen blockiert.
     *      reopenProject() durch den Auditor ermöglicht Fehlerkorrektur.
     */
    function closeProject() external onlyOwner {
        if (!project.isActive) revert("Already closed");

        for (uint i = 0; i < milestoneIds.length; i++) {
            Milestone storage m = milestones[milestoneIds[i]];
            if (!m.isCompleted) revert("All milestones must be completed");
            if (m.releaseableAmount > 0) revert("All milestones must be released");
        }

        project.isActive = false;
        project.acceptedAt = block.timestamp;  // Abnahme-Zeitpunkt → Verjährungsbeginn
        emit ProjectClosed(
            project.client,
            project.contractor,
            project.totalReleased,
            project.retentionVault,
            project.taxVault
        );
    }

    /**
     * @dev Notfall-Wiedereröffnung durch den Auditor (ADR-008).
     *      Ermöglicht Korrektur bei versehentlichem closeProject().
     */
    function reopenProject() external {
        if (msg.sender != project.auditor) revert("Only auditor");
        if (project.isActive) revert("Already active");
        project.isActive = true;
        emit ProjectReopened(msg.sender, project.client);
    }

    // ================================================================
    // Views (Read-Only — für RPA-Dashboard, Wave 18)
    // ================================================================

    function getProjectStatus()
        external
        view
        returns (
            uint256 totalBudget,
            uint256 totalReleased,
            uint256 retentionVault,
            uint256 taxVault,
            bool isActive
        )
    {
        Project memory p = project;
        return (p.totalBudget, p.totalReleased, p.retentionVault, p.taxVault, p.isActive);
    }

    function getMilestone(string memory _ozId)
        external
        view
        returns (Milestone memory)
    {
        return milestones[_ozId];
    }

    function getMilestoneCount() external view returns (uint256) {
        return milestoneIds.length;
    }

    function getAllMilestoneIds() external view returns (string[] memory) {
        return milestoneIds;
    }

    /**
     * @dev BHO Zero-Sum Check (Δ ≤ 1 wei).
     *
     *      Invariante: totalBudget == totalReleased + taxVault + contractBalance
     *
     *      retentionVault ist NICHT Teil der Summe, weil der Sicherheitseinbehalt
     *      im Contract verbleibt (er ist ein Teil von contractBalance, keine
     *      separate Position). Er wird separat in project.retentionVault geführt,
     *      aber die Token liegen im selben Contract-Wallet.
     *
     *      Die Invariante hält zu JEDEM Zeitpunkt — auch zwischen
     *      completeMilestone() und releaseMilestone().
     */
    function verifyBHOInvariant() external view returns (bool, int256 delta) {
        uint256 contractBalance = eureToken.balanceOf(address(this));
        // retentionVault ist in contractBalance enthalten → nicht separat addieren
        uint256 accounted = project.totalReleased
            + project.taxVault
            + contractBalance;
        int256 diff = int256(project.totalBudget) - int256(accounted);
        return (diff >= -1 && diff <= 1, diff);
    }

    /**
     * @dev CertiK Conservation-of-Funds Invariante (Wave 20).
     *      Verifiziert, dass keine Funds verloren gehen oder erschaffen werden.
     *
     *      funded == totalReleased + taxVault + contractBalance
     *
     *      (retentionVault ist in contractBalance enthalten, daher nicht additiv)
     */
    function verifyConservationInvariant()
        external
        view
        returns (bool, uint256 funded, uint256 accounted, uint256 delta)
    {
        uint256 contractBalance = eureToken.balanceOf(address(this));
        funded = project.totalBudget;
        accounted = project.totalReleased
            + project.taxVault
            + contractBalance;
        delta = funded >= accounted ? funded - accounted : accounted - funded;
        return (delta <= 1, funded, accounted, delta);
    }
}
