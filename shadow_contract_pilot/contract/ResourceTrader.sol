// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./CommodityToken.sol";

/// @title ResourceTrader — Atomarer P2P-Tausch von Commodity-Token
/// @notice Ermöglicht direkten Ressourcen-Tausch (kWh ↔ Liter ↔ kg) ohne Banken.
/// @dev Atomar: Entweder beide Seiten des Tauschs werden ausgeführt oder keine.
contract ResourceTrader is ReentrancyGuard {
    // =========================================================================
    // Events
    // =========================================================================

    event TradeExecuted(
        bytes32 indexed tradeId,
        address indexed partyA,
        address indexed partyB,
        uint256 tokenIdA,
        uint256 amountA,
        uint256 tokenIdB,
        uint256 amountB
    );
    event TradeProposed(
        bytes32 indexed tradeId,
        address indexed proposer,
        address indexed counterparty,
        uint256 offerTokenId,
        uint256 offerAmount,
        uint256 askTokenId,
        uint256 askAmount,
        uint256 expiresAt
    );
    event TradeCancelled(bytes32 indexed tradeId);
    event TradeFilled(bytes32 indexed tradeId, address indexed filler);

    // =========================================================================
    // Types
    // =========================================================================

    struct TradeProposal {
        address proposer;
        address counterparty;    // address(0) = öffentliches Angebot
        uint256 offerTokenId;    // Was der Proposer anbietet
        uint256 offerAmount;     // Wie viel davon
        uint256 askTokenId;      // Was der Proposer haben will
        uint256 askAmount;       // Wie viel davon
        uint256 expiresAt;       // Unix-Timestamp
        bool active;
        bool filled;
    }

    // =========================================================================
    // State
    // =========================================================================

    CommodityToken public commodityToken;
    mapping(bytes32 => TradeProposal) public proposals;
    bytes32[] public proposalIds;
    uint256 public tradeCount;

    // =========================================================================
    // Constructor
    // =========================================================================

    constructor(address _commodityToken) {
        require(_commodityToken != address(0), "Invalid commodity token address");
        commodityToken = CommodityToken(_commodityToken);
    }

    // =========================================================================
    // Trade Proposal (Offer)
    // =========================================================================

    /// @notice Erstellt ein Tauschangebot: "Ich biete X kWh und will Y Liter".
    /// @param counterparty address(0) = öffentliches Angebot für jeden
    /// @param expiresAt 0 = kein Ablauf (bis cancelled)
    /// @return tradeId Eindeutige ID des Angebots
    function proposeTrade(
        address counterparty,
        uint256 offerTokenId,
        uint256 offerAmount,
        uint256 askTokenId,
        uint256 askAmount,
        uint256 expiresAt
    ) external returns (bytes32 tradeId) {
        require(offerTokenId != askTokenId, "Cannot trade same resource");
        require(offerAmount > 0 && askAmount > 0, "Amounts must be positive");
        require(expiresAt == 0 || expiresAt > block.timestamp, "Already expired");

        // Prüfe dass Proposer genügend Tokens hat
        require(
            commodityToken.balanceOf(msg.sender, offerTokenId) >= offerAmount,
            "Insufficient offer balance"
        );

        // Genehmigung für ResourceTrader
        commodityToken.setApprovalForAll(address(this), true);

        tradeId = keccak256(
            abi.encodePacked(msg.sender, counterparty, offerTokenId, offerAmount, askTokenId, askAmount, block.timestamp)
        );

        proposals[tradeId] = TradeProposal({
            proposer: msg.sender,
            counterparty: counterparty,
            offerTokenId: offerTokenId,
            offerAmount: offerAmount,
            askTokenId: askTokenId,
            askAmount: askAmount,
            expiresAt: expiresAt,
            active: true,
            filled: false
        });
        proposalIds.push(tradeId);

        emit TradeProposed(tradeId, msg.sender, counterparty, offerTokenId, offerAmount, askTokenId, askAmount, expiresAt);
    }

    // =========================================================================
    // Trade Execution (Atomic Swap)
    // =========================================================================

    /// @notice Nimmt ein Tauschangebot an (atomarer Swap).
    /// @dev Beide Transfers in einer Transaktion — entweder beide oder keine.
    function fillTrade(bytes32 tradeId) external nonReentrant {
        TradeProposal storage proposal = proposals[tradeId];
        require(proposal.active, "Proposal not active");
        require(!proposal.filled, "Proposal already filled");
        require(proposal.expiresAt == 0 || proposal.expiresAt > block.timestamp, "Proposal expired");

        // Öffentlich oder spezifischer Counterparty
        require(
            proposal.counterparty == address(0) || proposal.counterparty == msg.sender,
            "Not authorized counterparty"
        );

        // Prüfe dass Filler genügend Tokens hat
        require(
            commodityToken.balanceOf(msg.sender, proposal.askTokenId) >= proposal.askAmount,
            "Insufficient ask balance"
        );

        // Genehmigung für ResourceTrader
        commodityToken.setApprovalForAll(address(this), true);

        // =====================================================================
        // ATOMARER SWAP (SafeTransferFrom × 2 in einer TX)
        // =====================================================================

        // Transfer A: Proposer → Filler (Offer)
        commodityToken.safeTransferFrom(
            proposal.proposer,
            msg.sender,
            proposal.offerTokenId,
            proposal.offerAmount,
            ""
        );

        // Transfer B: Filler → Proposer (Ask)
        commodityToken.safeTransferFrom(
            msg.sender,
            proposal.proposer,
            proposal.askTokenId,
            proposal.askAmount,
            ""
        );

        // =====================================================================

        proposal.filled = true;
        proposal.active = false;
        tradeCount++;

        emit TradeFilled(tradeId, msg.sender);
        emit TradeExecuted(
            tradeId,
            proposal.proposer,
            msg.sender,
            proposal.offerTokenId,
            proposal.offerAmount,
            proposal.askTokenId,
            proposal.askAmount
        );
    }

    /// @notice Führt einen direkten atomaren Tausch ohne Proposal aus.
    /// @dev Beide Parteien müssen vorab genehmigt haben.
    function atomicSwap(
        address counterparty,
        uint256 myTokenId,
        uint256 myAmount,
        uint256 theirTokenId,
        uint256 theirAmount
    ) external nonReentrant {
        require(counterparty != address(0), "Invalid counterparty");
        require(myTokenId != theirTokenId, "Cannot swap same resource");
        require(myAmount > 0 && theirAmount > 0, "Amounts must be positive");

        require(
            commodityToken.balanceOf(msg.sender, myTokenId) >= myAmount,
            "Insufficient your balance"
        );
        require(
            commodityToken.balanceOf(counterparty, theirTokenId) >= theirAmount,
            "Insufficient counterparty balance"
        );

        commodityToken.setApprovalForAll(address(this), true);

        // Transfer A: msg.sender → counterparty
        commodityToken.safeTransferFrom(msg.sender, counterparty, myTokenId, myAmount, "");

        // Transfer B: counterparty → msg.sender
        commodityToken.safeTransferFrom(counterparty, msg.sender, theirTokenId, theirAmount, "");

        tradeCount++;

        bytes32 tradeId = keccak256(abi.encodePacked(msg.sender, counterparty, block.timestamp, tradeCount));
        emit TradeExecuted(tradeId, msg.sender, counterparty, myTokenId, myAmount, theirTokenId, theirAmount);
    }

    // =========================================================================
    // Proposal Management
    // =========================================================================

    /// @notice Storniert ein eigenes Angebot.
    function cancelProposal(bytes32 tradeId) external {
        TradeProposal storage proposal = proposals[tradeId];
        require(proposal.proposer == msg.sender, "Not your proposal");
        require(proposal.active, "Proposal not active");
        require(!proposal.filled, "Already filled");

        proposal.active = false;
        emit TradeCancelled(tradeId);
    }

    /// @notice Gibt alle aktiven öffentlichen Angebote zurück.
    function getActivePublicProposals() external view returns (bytes32[] memory) {
        uint256 count;
        for (uint256 i = 0; i < proposalIds.length; i++) {
            TradeProposal storage p = proposals[proposalIds[i]];
            if (p.active && !p.filled && p.counterparty == address(0)) {
                if (p.expiresAt == 0 || p.expiresAt > block.timestamp) {
                    count++;
                }
            }
        }

        bytes32[] memory active = new bytes32[](count);
        uint256 index;
        for (uint256 i = 0; i < proposalIds.length; i++) {
            TradeProposal storage p = proposals[proposalIds[i]];
            if (p.active && !p.filled && p.counterparty == address(0)) {
                if (p.expiresAt == 0 || p.expiresAt > block.timestamp) {
                    active[index] = proposalIds[i];
                    index++;
                }
            }
        }
        return active;
    }

    /// @notice Gibt Details eines Angebots zurück.
    function getProposal(bytes32 tradeId) external view returns (TradeProposal memory) {
        return proposals[tradeId];
    }
}
