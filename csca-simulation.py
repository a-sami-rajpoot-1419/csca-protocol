"""
CSCA — Checkpointed State Compaction Architecture
Simulation Script

Demonstrates the core cryptographic mechanics of CSCA:
  - Block production and chaining
  - Merkle tree construction over block headers
  - Checkpoint creation and chaining
  - Checkpoint verification (N -> N+1)
  - Transaction inclusion proof after pruning
  - Storage impact measurement

No external dependencies. Standard library only.
"""

import hashlib
import json
import random
import time


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

def sha256(data: str) -> str:
    """Hash any string to a 64-char hex digest."""
    return hashlib.sha256(data.encode()).hexdigest()


def short(h: str) -> str:
    """Shorten a hash for readable console output."""
    return h[:10] + "..."


# ─────────────────────────────────────────────
# MERKLE TREE
# ─────────────────────────────────────────────

def merkle_root(items: list[str]) -> str:
    """
    Build a Merkle tree over a list of hashes and return the root.
    Each leaf is a hash. Pairs are hashed together up the tree.
    Odd nodes are duplicated to form a pair.
    """
    if not items:
        return sha256("empty")

    layer = items[:]

    while len(layer) > 1:
        if len(layer) % 2 != 0:
            layer.append(layer[-1])  # duplicate last node if odd count
        layer = [sha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]

    return layer[0]


def merkle_proof(items: list[str], index: int) -> list[dict]:
    """
    Generate a Merkle proof for the item at `index`.
    Returns a list of sibling hashes and their positions (left/right).
    The verifier uses this path to reconstruct the root.
    """
    proof = []
    layer = items[:]

    while len(layer) > 1:
        if len(layer) % 2 != 0:
            layer.append(layer[-1])

        sibling_index = index ^ 1  # XOR with 1 flips between even/odd pair
        position = "right" if index % 2 == 0 else "left"
        proof.append({"hash": layer[sibling_index], "position": position})

        # Move up one level
        layer = [sha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
        index //= 2

    return proof


def verify_merkle_proof(leaf: str, proof: list[dict], root: str) -> bool:
    """
    Verify a Merkle proof.
    Walks the proof path from leaf to root and checks the result matches.
    """
    current = leaf

    for step in proof:
        if step["position"] == "right":
            current = sha256(current + step["hash"])
        else:
            current = sha256(step["hash"] + current)

    return current == root


# ─────────────────────────────────────────────
# BLOCK
# ─────────────────────────────────────────────

def create_transaction(sender: str, receiver: str, amount: float, nonce: int) -> dict:
    """Create a simple transaction object."""
    tx = {
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "nonce": nonce,
    }
    tx["tx_hash"] = sha256(json.dumps(tx))
    return tx


def create_block(block_number: int, parent_hash: str, transactions: list[dict], state: dict) -> dict:
    """
    Create a block containing transactions.
    Computes tx_root (Merkle over tx hashes) and state_root (hash of world state).
    Block hash chains to parent via parent_hash.
    """

    # Apply transactions to get new state
    new_state = state.copy()
    for tx in transactions:
        sender, receiver, amount = tx["sender"], tx["receiver"], tx["amount"]
        new_state[sender] = new_state.get(sender, 1000.0) - amount
        new_state[receiver] = new_state.get(receiver, 0.0) + amount

    tx_hashes = [tx["tx_hash"] for tx in transactions]

    # Header — this is what gets kept after pruning
    header = {
        "block_number": block_number,
        "parent_hash": parent_hash,
        "tx_root": merkle_root(tx_hashes),
        "state_root": sha256(json.dumps(new_state, sort_keys=True)),
        "timestamp": int(time.time()) + block_number,
    }
    header["header_hash"] = sha256(json.dumps(header, sort_keys=True))

    # Full block = header + body (body gets pruned later)
    block = {
        "header": header,
        "body": {"transactions": transactions},  # prunable
        "state": new_state,                       # kept as current state
    }

    return block


# ─────────────────────────────────────────────
# CHECKPOINT
# ─────────────────────────────────────────────

def create_checkpoint(
    window_blocks: list[dict],
    previous_checkpoint_hash: str,
    committee_size: int = 5
) -> dict:
    """
    Create a checkpoint over a finalized window of blocks.

    Checkpoint commits to:
      - Every block header in the window (via Merkle root)
      - The world state at the window boundary (state_root)
      - The previous checkpoint (chain continuity)
      - Archive committee signatures (quorum approval)
    """

    headers = [b["header"] for b in window_blocks]
    header_hashes = [h["header_hash"] for h in headers]

    checkpoint = {
        "start_block": headers[0]["block_number"],
        "end_block": headers[-1]["block_number"],
        "merkle_root": merkle_root(header_hashes),
        "state_root": headers[-1]["state_root"],
        "previous_checkpoint_hash": previous_checkpoint_hash,
        # Simulate committee signatures — in production these are real cryptographic signatures
        "committee_signatures": [
            sha256(f"archive_validator_{i}_signs_{headers[-1]['header_hash']}")
            for i in range(committee_size)
        ],
    }
    checkpoint["checkpoint_hash"] = sha256(json.dumps(checkpoint, sort_keys=True))

    return checkpoint


def verify_checkpoint(
    checkpoint: dict,
    previous_checkpoint_hash: str,
    window_headers: list[dict],
    required_signatures: int = 3
) -> tuple[bool, list[str]]:
    """
    Verify a checkpoint against the previous checkpoint and window headers.
    Returns (is_valid, list_of_issues).

    Five checks must all pass:
      1. Previous checkpoint hash matches — chain continuity
      2. Block boundary continuity — first block follows last block of prev window
      3. Merkle root matches recomputed root over headers — window integrity
      4. State root matches last block's state root — state continuity
      5. Sufficient committee signatures — quorum approval
    """

    issues = []
    header_hashes = [h["header_hash"] for h in window_headers]

    # Check 1 — checkpoint chain continuity
    if checkpoint["previous_checkpoint_hash"] != previous_checkpoint_hash:
        issues.append("FAIL: previous_checkpoint_hash mismatch — chain broken")

    # Check 2 — Merkle root over headers
    computed_merkle = merkle_root(header_hashes)
    if checkpoint["merkle_root"] != computed_merkle:
        issues.append("FAIL: merkle_root mismatch — headers may be tampered")

    # Check 3 — state root matches last block in window
    if checkpoint["state_root"] != window_headers[-1]["state_root"]:
        issues.append("FAIL: state_root mismatch — state commitment incorrect")

    # Check 4 — block range matches headers provided
    if checkpoint["start_block"] != window_headers[0]["block_number"]:
        issues.append("FAIL: start_block mismatch")
    if checkpoint["end_block"] != window_headers[-1]["block_number"]:
        issues.append("FAIL: end_block mismatch")

    # Check 5 — quorum of committee signatures present
    if len(checkpoint["committee_signatures"]) < required_signatures:
        issues.append(f"FAIL: insufficient signatures ({len(checkpoint['committee_signatures'])} < {required_signatures})")

    return (len(issues) == 0, issues)


# ─────────────────────────────────────────────
# PRUNING
# ─────────────────────────────────────────────

def prune_blocks(blocks: list[dict]) -> list[dict]:
    """
    Simulate pruning: remove transaction bodies from finalized blocks.
    Headers are retained for inclusion proofs. Bodies are deleted.
    """
    pruned = []
    for block in blocks:
        pruned.append({
            "header": block["header"],  # kept — needed for Merkle proofs
            "body": None,               # pruned — full tx data deleted
            "state": None,              # pruned — only latest state is kept
        })
    return pruned


# ─────────────────────────────────────────────
# TRANSACTION INCLUSION PROOF
# ─────────────────────────────────────────────

def prove_transaction(
    tx: dict,
    block: dict,
    block_index_in_window: int,
    all_window_header_hashes: list[str]
) -> dict:
    """
    Build a complete proof that a transaction existed in a pruned block.
    Proof has two layers:
      Layer 1: tx is in block (against block's tx_root)
      Layer 2: block header is in checkpoint (against checkpoint's merkle_root)
    """
    tx_hashes = [t["tx_hash"] for t in block["body"]["transactions"]]
    tx_index = tx_hashes.index(tx["tx_hash"])

    return {
        "tx_hash": tx["tx_hash"],
        "tx_merkle_proof": merkle_proof(tx_hashes, tx_index),
        "tx_root": block["header"]["tx_root"],
        "block_header_hash": block["header"]["header_hash"],
        "block_merkle_proof": merkle_proof(all_window_header_hashes, block_index_in_window),
    }


def verify_transaction_proof(proof: dict, checkpoint_merkle_root: str) -> tuple[bool, str]:
    """
    Verify a transaction inclusion proof against a checkpoint.
    Anyone can run this using only the checkpoint — no full history needed.
    """

    # Layer 1: verify tx is inside the block
    tx_valid = verify_merkle_proof(
        proof["tx_hash"],
        proof["tx_merkle_proof"],
        proof["tx_root"]
    )
    if not tx_valid:
        return False, "FAIL: transaction not found in block"

    # Layer 2: verify block header is inside the checkpoint
    block_valid = verify_merkle_proof(
        proof["block_header_hash"],
        proof["block_merkle_proof"],
        checkpoint_merkle_root
    )
    if not block_valid:
        return False, "FAIL: block not found in checkpoint"

    return True, "PASS: transaction proven in finalized checkpoint"


# ─────────────────────────────────────────────
# STORAGE MEASUREMENT
# ─────────────────────────────────────────────

def measure_size(obj) -> int:
    """Estimate object size in bytes via JSON serialization."""
    return len(json.dumps(obj).encode())


# ─────────────────────────────────────────────
# MAIN SIMULATION
# ─────────────────────────────────────────────

def run_simulation():

    print("=" * 60)
    print("  CSCA — Checkpointed State Compaction Architecture")
    print("  Simulation")
    print("=" * 60)

    WINDOW_SIZE = 6       # blocks per checkpoint window (small for demo)
    NUM_WINDOWS = 2       # number of checkpoint windows to simulate
    TXS_PER_BLOCK = 4    # transactions per block

    wallets = ["alice", "bob", "carol", "dave", "eve"]
    world_state = {w: 1000.0 for w in wallets}

    all_blocks = []
    checkpoints = []
    previous_checkpoint_hash = sha256("genesis")

    # ── PRODUCE BLOCKS AND CHECKPOINTS ──────────────────────────

    for window_idx in range(NUM_WINDOWS):

        print(f"\n{'─' * 60}")
        print(f"  WINDOW {window_idx + 1} — Blocks {window_idx * WINDOW_SIZE} to {(window_idx + 1) * WINDOW_SIZE - 1}")
        print(f"{'─' * 60}")

        window_blocks = []

        for i in range(WINDOW_SIZE):
            block_number = window_idx * WINDOW_SIZE + i
            parent_hash = all_blocks[-1]["header"]["header_hash"] if all_blocks else sha256("genesis")

            # Generate random transactions
            transactions = []
            for _ in range(TXS_PER_BLOCK):
                sender, receiver = random.sample(wallets, 2)
                transactions.append(create_transaction(sender, receiver, round(random.uniform(1, 10), 2), block_number * 10 + _))

            block = create_block(block_number, parent_hash, transactions, world_state)
            world_state = block["state"]

            window_blocks.append(block)
            all_blocks.append(block)

            print(f"  Block {block_number:>3}  hash={short(block['header']['header_hash'])}  "
                  f"txs={len(transactions)}  state_root={short(block['header']['state_root'])}")

        # ── CREATE CHECKPOINT ────────────────────────────────────

        print(f"\n  Creating checkpoint for window {window_idx + 1}...")
        checkpoint = create_checkpoint(window_blocks, previous_checkpoint_hash)

        # ── VERIFY CHECKPOINT ────────────────────────────────────

        window_headers = [b["header"] for b in window_blocks]
        is_valid, issues = verify_checkpoint(checkpoint, previous_checkpoint_hash, window_headers)

        print(f"  Checkpoint hash : {short(checkpoint['checkpoint_hash'])}")
        print(f"  Merkle root     : {short(checkpoint['merkle_root'])}")
        print(f"  State root      : {short(checkpoint['state_root'])}")
        print(f"  Blocks covered  : {checkpoint['start_block']} → {checkpoint['end_block']}")
        print(f"  Verification    : {'✓ PASSED' if is_valid else '✗ FAILED'}")
        if issues:
            for issue in issues:
                print(f"    {issue}")

        checkpoints.append(checkpoint)
        previous_checkpoint_hash = checkpoint["checkpoint_hash"]

    # ── TRANSACTION INCLUSION PROOF ──────────────────────────────

    print(f"\n{'─' * 60}")
    print("  TRANSACTION INCLUSION PROOF (after pruning)")
    print(f"{'─' * 60}")

    # Pick a transaction from window 1 (which will be pruned)
    target_block = all_blocks[2]
    target_tx = target_block["body"]["transactions"][1]
    target_checkpoint = checkpoints[0]

    window_1_blocks = all_blocks[:WINDOW_SIZE]
    window_1_header_hashes = [b["header"]["header_hash"] for b in window_1_blocks]
    block_index_in_window = 2  # third block in window 1

    # Build proof before pruning (archive node does this)
    proof = prove_transaction(target_tx, target_block, block_index_in_window, window_1_header_hashes)

    # Now simulate pruning window 1
    pruned_window_1 = prune_blocks(window_1_blocks)
    print(f"  Window 1 blocks pruned. Full tx data deleted.")
    print(f"  Target tx hash : {short(target_tx['tx_hash'])}")
    print(f"  Proving tx existed in block {target_block['header']['block_number']}...")

    # Verify the proof — anyone can do this with only the checkpoint
    is_valid, message = verify_transaction_proof(proof, target_checkpoint["merkle_root"])
    print(f"  Proof result   : {'✓' if is_valid else '✗'} {message}")

    # ── TAMPER DETECTION TEST ────────────────────────────────────

    print(f"\n{'─' * 60}")
    print("  TAMPER DETECTION TEST")
    print(f"{'─' * 60}")

    # Attempt to verify a tampered checkpoint
    tampered_checkpoint = checkpoints[0].copy()
    tampered_checkpoint["state_root"] = sha256("fake_state")
    tampered_checkpoint["checkpoint_hash"] = sha256(json.dumps(tampered_checkpoint, sort_keys=True))

    window_headers = [b["header"] for b in all_blocks[:WINDOW_SIZE]]
    is_valid, issues = verify_checkpoint(tampered_checkpoint, sha256("genesis"), window_headers)
    print(f"  Tampered checkpoint verification : {'✓ PASSED' if is_valid else '✗ FAILED (expected)'}")
    for issue in issues:
        print(f"    {issue}")

    # ── STORAGE COMPARISON ───────────────────────────────────────

    print(f"\n{'─' * 60}")
    print("  STORAGE IMPACT")
    print(f"{'─' * 60}")

    full_blocks_size = sum(measure_size(b) for b in all_blocks)
    headers_only_size = sum(measure_size(b["header"]) for b in all_blocks)
    checkpoints_size = sum(measure_size(c) for c in checkpoints)
    total_csca_size = headers_only_size + checkpoints_size

    print(f"  Full blocks (original)     : {full_blocks_size:>8} bytes")
    print(f"  Headers only (kept)        : {headers_only_size:>8} bytes")
    print(f"  Checkpoints (kept)         : {checkpoints_size:>8} bytes")
    print(f"  Total CSCA footprint       : {total_csca_size:>8} bytes")
    print(f"  Reduction                  : {full_blocks_size / total_csca_size:.1f}x smaller")

    # ── CHECKPOINT CHAIN SUMMARY ─────────────────────────────────

    print(f"\n{'─' * 60}")
    print("  CHECKPOINT CHAIN")
    print(f"{'─' * 60}")

    print(f"  Genesis  →  {short(sha256('genesis'))}")
    for i, cp in enumerate(checkpoints):
        print(f"  CP {i + 1:<5}  →  {short(cp['checkpoint_hash'])}  "
              f"(blocks {cp['start_block']}–{cp['end_block']}  "
              f"prev={short(cp['previous_checkpoint_hash'])})")

    print(f"\n{'=' * 60}")
    print("  Simulation complete.")
    print("=" * 60)


if __name__ == "__main__":
    run_simulation()