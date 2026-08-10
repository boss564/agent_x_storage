// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title ValhallaVerifier — On-chain Groth16 proof verification for anonymous honor stamps.
/// @notice Anchors ZK settlement proofs from the subsurface D01 enclave onto a public L1.
///         No cleartext ever touches the chain — only hashes, proofs, and Valhalla pseudonyms.
/// @dev    Groth16 verification over BN254. The verification key is immutable after construction.
///         Gas cost: ~230k for a single proof verification (dominated by pairing checks).
///
/// Architecture:
///   D01 (SGX Enclave) → ZK Proof → C09 (off-chain Merkle-DAG) → ValhallaVerifier (L1 anchor)
///
/// Each settled proof is stored with:
///   - nullifier hash (prevents double-anchoring)
///   - commitment hash (binds proof to specific invoice, DSGVO-compliant)
///   - state root (the Merkle-DAG tip after settlement)
///   - Valhalla stamp (anonymous reputation pseudonym)
contract ValhallaVerifier {
    // ── Verification Key Components (BN254, Groth16) ──────────────────────
    // These are derived from the Circom circuit compilation.
    // Immutable after deployment — a new circuit requires a new deployment.

    struct G1Point {
        uint256 x;
        uint256 y;
    }

    struct G2Point {
        uint256[2] x;
        uint256[2] y;
    }

    struct VerifyingKey {
        G1Point alpha;
        G2Point beta;
        G2Point gamma;
        G2Point delta;
        G1Point[] ic; // Input commitments (one per public input)
    }

    struct Proof {
        G1Point pi_a;
        G2Point pi_b;
        G1Point pi_c;
    }

    // ── Immutable Verification Key ────────────────────────────────────────

    VerifyingKey public immutable vk;

    // ── Storage ───────────────────────────────────────────────────────────

    /// @notice Spent nullifiers — prevents double-anchoring of the same settlement.
    mapping(bytes32 => bool) public nullifierSpent;

    /// @notice Anchored proofs: commitmentHash → (stateRoot, valhallaStamp, blockNumber)
    struct AnchorEntry {
        bytes32 stateRoot;
        bytes32 valhallaStamp;
        uint64 blockNumber;
        uint64 timestamp;
    }
    mapping(bytes32 => AnchorEntry) public anchors;
    bytes32[] public anchorIndex; // Chronological list of all anchored commitments

    /// @notice Honor ledger: valhallaStamp → total honor points (anonymous reputation)
    mapping(bytes32 => uint256) public honorLedger;

    // ── Events ────────────────────────────────────────────────────────────

    event ProofAnchored(
        bytes32 indexed commitmentHash,
        bytes32 indexed nullifierHash,
        bytes32 stateRoot,
        bytes32 valhallaStamp,
        uint256 honorEarned,
        uint256 blockNumber
    );

    event HonorUpdated(
        bytes32 indexed valhallaStamp,
        uint256 totalHonor
    );

    // ── Constructor ───────────────────────────────────────────────────────

    /// @param _alpha  G1 point for alpha in verification key
    /// @param _beta   G2 point for beta
    /// @param _gamma  G2 point for gamma
    /// @param _delta  G2 point for delta
    /// @param _ic     Array of G1 points for input commitments
    constructor(
        G1Point memory _alpha,
        G2Point memory _beta,
        G2Point memory _gamma,
        G2Point memory _delta,
        G1Point[] memory _ic
    ) {
        vk = VerifyingKey(_alpha, _beta, _gamma, _delta, _ic);
    }

    // ── Core Verification ─────────────────────────────────────────────────

    /// @notice Verify a Groth16 proof and anchor it on-chain.
    /// @param pi_a       G1 point from proof
    /// @param pi_b       G2 point from proof
    /// @param pi_c       G1 point from proof
    /// @param publicInputs  Array of public inputs (must match Circom circuit order:
    ///                       [tickLower, tickUpper, commitmentHash, nullifierHash, amount])
    /// @param stateRoot      Merkle-DAG tip after settlement (from C09)
    /// @param valhallaStamp  Anonymous reputation pseudonym
    /// @return anchored  True if the proof was verified and anchored
    function verifyAndAnchor(
        G1Point calldata pi_a,
        G2Point calldata pi_b,
        G1Point calldata pi_c,
        uint256[] calldata publicInputs,
        bytes32 stateRoot,
        bytes32 valhallaStamp
    ) external returns (bool anchored) {
        require(publicInputs.length >= 5, "Need 5 public inputs");

        bytes32 commitmentHash = bytes32(publicInputs[2]);
        bytes32 nullifierHash = bytes32(publicInputs[3]);

        // 1. Replay protection: nullifier must not be spent
        require(!nullifierSpent[nullifierHash], "Nullifier already spent");

        // 2. Verify the Groth16 proof
        Proof memory proof = Proof(pi_a, pi_b, pi_c);
        bool valid = _verify(vk, proof, publicInputs);
        require(valid, "Groth16 proof verification failed");

        // 3. Mark nullifier spent
        nullifierSpent[nullifierHash] = true;

        // 4. Anchor the proof
        anchors[commitmentHash] = AnchorEntry({
            stateRoot: stateRoot,
            valhallaStamp: valhallaStamp,
            blockNumber: uint64(block.number),
            timestamp: uint64(block.timestamp)
        });
        anchorIndex.push(commitmentHash);

        // 5. Credit Valhalla honor (50 points per valid proof)
        honorLedger[valhallaStamp] += 50;

        emit ProofAnchored(commitmentHash, nullifierHash, stateRoot, valhallaStamp, 50, block.number);
        emit HonorUpdated(valhallaStamp, honorLedger[valhallaStamp]);

        return true;
    }

    // ── Queries ───────────────────────────────────────────────────────────

    /// @notice Get the total number of anchored proofs.
    function anchorCount() external view returns (uint256) {
        return anchorIndex.length;
    }

    /// @notice Get honor for a Valhalla stamp (public, anonymous).
    function getHonor(bytes32 stamp) external view returns (uint256) {
        return honorLedger[stamp];
    }

    /// @notice Check if a commitment has been anchored.
    function isAnchored(bytes32 commitmentHash) external view returns (bool) {
        return anchors[commitmentHash].blockNumber > 0;
    }

    // ── Groth16 Pairing Check ─────────────────────────────────────────────

    /// @dev Internal Groth16 verification. Gas-heavy (~230k).
    function _verify(
        VerifyingKey memory vk_,
        Proof memory proof,
        uint256[] memory input
    ) internal view returns (bool) {
        require(input.length + 1 == vk_.ic.length, "Input count mismatch");

        // Compute the linear combination of IC points with public inputs
        G1Point memory vk_x = vk_.ic[0];
        for (uint256 i = 0; i < input.length; i++) {
            vk_x = _g1Add(vk_x, _g1Mul(vk_.ic[i + 1], input[i]));
        }

        // The pairing check: e(pi_a, pi_b) == e(vk_x, gamma) * e(pi_c, delta) * e(alpha, beta)^(-1)
        // In practice: e(pi_a, pi_b) * e(vk_x, gamma)^(-1) * e(pi_c, delta)^(-1) * e(alpha, beta) == 1
        // We implement this via the precompile at address 0x08 (BN254 pairing).

        uint256[24] memory pairingInput;

        // e(pi_a, pi_b)  — positive
        _writeG1(pairingInput, 0, proof.pi_a);
        _writeG2(pairingInput, 2, proof.pi_b);

        // e(vk_x, gamma) — negative (flip y coordinate)
        G1Point memory negVkX = _g1Neg(vk_x);
        _writeG1(pairingInput, 6, negVkX);
        _writeG2(pairingInput, 8, vk_.gamma);

        // e(pi_c, delta) — negative
        G1Point memory negPiC = _g1Neg(proof.pi_c);
        _writeG1(pairingInput, 12, negPiC);
        _writeG2(pairingInput, 14, vk_.delta);

        // e(alpha, beta) — positive
        _writeG1(pairingInput, 18, vk_.alpha);
        _writeG2(pairingInput, 20, vk_.beta);

        // Call the BN254 pairing precompile (address 0x08)
        (bool success, bytes memory output) = address(0x08).staticcall(
            abi.encodePacked(pairingInput)
        );
        require(success, "Pairing precompile call failed");
        require(output.length == 32, "Invalid pairing output");

        // The precompile returns 1 at the last byte if pairing holds
        return output[31] == 0x01;
    }

    // ── Elliptic Curve Helpers (BN254 / alt_bn128) ────────────────────────

    uint256 private constant FIELD_MODULUS = 21888242871839275222246405745257275088696311157297823662689037894645226208583;
    uint256 private constant P = FIELD_MODULUS;

    function _g1Add(G1Point memory a, G1Point memory b) internal view returns (G1Point memory) {
        uint256[4] memory input = [a.x, a.y, b.x, b.y];
        (bool success, bytes memory output) = address(0x06).staticcall(
            abi.encodePacked(input)
        );
        require(success, "G1 add precompile failed");
        return G1Point(
            _uint256FromBytes(output, 0),
            _uint256FromBytes(output, 32)
        );
    }

    function _g1Mul(G1Point memory p, uint256 scalar) internal view returns (G1Point memory) {
        uint256[3] memory input = [p.x, p.y, scalar % P];
        (bool success, bytes memory output) = address(0x07).staticcall(
            abi.encodePacked(input)
        );
        require(success, "G1 mul precompile failed");
        return G1Point(
            _uint256FromBytes(output, 0),
            _uint256FromBytes(output, 32)
        );
    }

    function _g1Neg(G1Point memory p) internal pure returns (G1Point memory) {
        return G1Point(p.x, p.y == 0 ? 0 : P - (p.y % P));
    }

    function _writeG1(uint256[24] memory buf, uint256 offset, G1Point memory p) internal pure {
        buf[offset] = p.x;
        buf[offset + 1] = p.y;
    }

    function _writeG2(uint256[24] memory buf, uint256 offset, G2Point memory p) internal pure {
        buf[offset]     = p.x[0];
        buf[offset + 1] = p.x[1];
        buf[offset + 2] = p.y[0];
        buf[offset + 3] = p.y[1];
    }

    function _uint256FromBytes(bytes memory data, uint256 offset) internal pure returns (uint256 result) {
        require(data.length >= offset + 32, "Out of bounds");
        assembly {
            result := mload(add(add(data, 0x20), offset))
        }
    }
}
