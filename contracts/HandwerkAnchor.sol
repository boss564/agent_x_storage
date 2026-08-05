// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title HandwerksNotar — Unveränderbare Bauabnahme-Protokolle auf Base L2
/// @notice Verankert Dokument-Hashes einzeln oder als Merkle-Batch.
///         Einzelankerung: ~28.000 Gas (~$0.008 auf Base)
///         Batch (50 Stück): ~45.000 Gas (~$0.012 → $0.00024/Dokument)
contract HandwerksNotar {

    /// @dev Einzel-Hash → Block-Timestamp (0 = nicht verankert)
    mapping(bytes32 => uint256) public anchoredHashes;

    /// @dev Merkle-Root → Block-Timestamp (für Batch-Verankerung)
    mapping(bytes32 => uint256) public anchoredBatches;

    /// @dev Betriebsnummer → Anzahl verankerter Dokumente (Statistik)
    mapping(bytes32 => uint256) public documentsByCompany;

    /// @dev Anzahl aller Verankerungen (Einzel + Batches)
    uint256 public totalSingleAnchored;
    uint256 public totalBatchesAnchored;

    // ─── Events ─────────────────────────────────────────────────────

    event HashAnchored(
        bytes32 indexed hash,
        bytes32 indexed companyId,
        address indexed submitter,
        uint256 timestamp
    );

    event BatchAnchored(
        bytes32 indexed merkleRoot,
        address indexed submitter,
        uint256 timestamp,
        uint256 batchSize
    );

    // ─── Einzelankerung (~28.000 Gas, ~$0.008) ─────────────────────

    /// @notice Verankert einen einzelnen Dokument-Hash (für Eilige).
    /// @param _hash SHA-256 Hash des Dokuments (32 Bytes)
    /// @param _companyId Betriebsnummer als bytes32 (z.B. "HWK-MUC-001")
    function anchorSingle(bytes32 _hash, bytes32 _companyId) external {
        require(_hash != bytes32(0), "Hash cannot be zero");
        require(anchoredHashes[_hash] == 0, "Already anchored");

        anchoredHashes[_hash] = block.timestamp;
        documentsByCompany[_companyId] += 1;
        totalSingleAnchored += 1;

        emit HashAnchored(_hash, _companyId, msg.sender, block.timestamp);
    }

    /// @notice Batch-Variante: Mehrere Hashes auf einmal (bis 50).
    /// @param _hashes Array von Dokument-Hashes
    /// @param _companyId Betriebsnummer
    function anchorSingleBatch(
        bytes32[] calldata _hashes,
        bytes32 _companyId
    ) external {
        uint256 count = _hashes.length;
        require(count > 0 && count <= 50, "Batch size 1-50");

        for (uint256 i = 0; i < count; i++) {
            require(_hashes[i] != bytes32(0), "Hash cannot be zero");
            require(anchoredHashes[_hashes[i]] == 0, "Already anchored");
            anchoredHashes[_hashes[i]] = block.timestamp;
            emit HashAnchored(_hashes[i], _companyId, msg.sender, block.timestamp);
        }

        documentsByCompany[_companyId] += count;
        totalSingleAnchored += count;
    }

    // ─── Batch-Ankerung via Merkle-Root (~45.000 Gas für 50 Docs) ───

    /// @notice Verankert einen Merkle-Root (bis zu 100 Dokumente in einer TX).
    /// @param _merkleRoot Merkle-Root des Batches
    /// @param _batchSize Anzahl der Dokumente im Batch
    /// @param _companyId Betriebsnummer
    function anchorBatch(
        bytes32 _merkleRoot,
        uint256 _batchSize,
        bytes32 _companyId
    ) external {
        require(_merkleRoot != bytes32(0), "Root cannot be zero");
        require(anchoredBatches[_merkleRoot] == 0, "Already anchored");
        require(_batchSize > 0 && _batchSize <= 100, "Batch size 1-100");

        anchoredBatches[_merkleRoot] = block.timestamp;
        documentsByCompany[_companyId] += _batchSize;
        totalBatchesAnchored += 1;

        emit BatchAnchored(_merkleRoot, msg.sender, block.timestamp, _batchSize);
    }

    // ─── Verifikation (View-Funktionen, kostenlos) ──────────────────

    /// @notice Prüft ob ein Einzel-Hash verankert wurde.
    function verifySingle(bytes32 _hash) external view returns (bool exists, uint256 timestamp) {
        uint256 ts = anchoredHashes[_hash];
        return (ts > 0, ts);
    }

    /// @notice Prüft ob ein Merkle-Root verankert wurde.
    function verifyBatch(bytes32 _merkleRoot) external view returns (bool exists, uint256 timestamp) {
        uint256 ts = anchoredBatches[_merkleRoot];
        return (ts > 0, ts);
    }

    /// @notice Batch-Verifikation mehrerer Hashes.
    function verifyMultiple(bytes32[] calldata _hashes)
        external
        view
        returns (bool[] memory exists, uint256[] memory timestamps)
    {
        uint256 len = _hashes.length;
        exists = new bool[](len);
        timestamps = new uint256[](len);
        for (uint256 i = 0; i < len; i++) {
            uint256 ts = anchoredHashes[_hashes[i]];
            exists[i] = ts > 0;
            timestamps[i] = ts;
        }
    }

    /// @notice Betriebsstatistik.
    function getCompanyStats(bytes32 _companyId)
        external
        view
        returns (uint256 totalDocs, uint256 singleAnchored, uint256 batchesAnchored)
    {
        return (documentsByCompany[_companyId], totalSingleAnchored, totalBatchesAnchored);
    }
}
