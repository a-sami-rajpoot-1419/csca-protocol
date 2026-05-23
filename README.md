# CSCA — Checkpointed State Compaction Architecture

> A protocol proposal for bounded validator storage in finality-based blockchains through cryptographically verifiable checkpoint commitments.

---

## Overview

Modern blockchains grow indefinitely. Every validator is required to store the entire history of the chain — blocks, transactions, state — from genesis to present. This was acceptable when chains were small. It is becoming a serious problem as chains scale.

The result is predictable:

- Validator hardware requirements increase every year
- New validators take longer and longer to synchronize
- Running a validator becomes progressively more expensive
- Decentralization suffers as fewer participants can afford the hardware

**CSCA proposes a different model.**

Once a block is finalized by consensus, it is immutable. It will never change. It will never be reorganized. Its correctness has already been agreed upon by the network. Yet every validator stores it forever, even though it plays no role in ongoing consensus.

CSCA separates two responsibilities that blockchains currently conflate:

- **Consensus participation** — producing blocks, validating state transitions, maintaining the network
- **Historical preservation** — storing and serving the complete chain history

Most validators only need to do the first. A smaller dedicated set of archive validators handles the second. Finalized history is periodically compacted into cryptographic checkpoints. Validators prune old block data. Storage becomes bounded. The chain keeps running.

---

## The Core Problem

### Validator Storage Growth Is Unbounded

Every block added to the chain adds permanently to the storage burden of every validator. There is no upper limit under the current model. A validator that joins today must either:

1. Download and store the entire chain history from genesis, or
2. Trust a snapshot and hope it is correct

Neither is satisfactory at scale. As throughput increases and chains grow older, the burden compounds.

### Finalized Data Is Stored But Rarely Used

Deep historical blocks are not used during normal consensus. Block production, state transition validation, and fork choice logic all operate on recent data. Historical blocks are useful for:

- Auditing
- Forensic investigation
- Historical state queries
- Independent archival verification

These are important use cases — but they do not require every validator to independently store everything. They require some validators to store everything.

### Synchronization Is Increasingly Slow

A new validator joining a mature network faces a synchronization problem that grows worse every day. Even with snapshots and state sync, the baseline cost of becoming a validator increases over time under the current model.

---

## The Proposal

### Checkpointed State Compaction Architecture

At fixed intervals — defined by block count rather than time — the network produces a **finalized checkpoint**.

A checkpoint is a compact cryptographic commitment that represents everything that happened before it. It is small, verifiable, and chains to the previous checkpoint exactly the way blocks chain to each other.

Once a checkpoint is finalized and accepted by the network, validators are free to prune the full block bodies that the checkpoint covers. They keep only:

- The checkpoint itself
- Block headers (small, needed for inclusion proofs)
- Current world state
- Recent blocks not yet covered by a checkpoint

Storage stops growing indefinitely. The same disk a validator bought on day one remains sufficient years later.

---

## How It Works Cryptographically

### What a Checkpoint Contains

```
Checkpoint_N {
  start_block:              first block in this window
  end_block:                last block in this window
  merkle_root:              MerkleRoot(all block headers in window)
  state_root:               header[end_block].state_root
  previous_checkpoint_hash: Hash(Checkpoint_N-1)
  committee_signatures:     k-of-m signatures from archive committee
}

checkpoint_hash = Hash(Checkpoint_N)
```

### What Each Field Does

**merkle_root**
A Merkle tree is built over all block headers in the checkpoint window. The root of this tree is a single 32-byte value that cryptographically commits to every block header in the range. If any single header is altered, the root changes. Any individual block header can be proven included using a small logarithmic proof path — you do not need all headers to verify one.

**state_root**
Every block already contains a state root in its header — a cryptographic hash of the entire world state after that block was executed. The checkpoint takes the state root from the final block in its window. This commits to the complete state of the chain at the checkpoint boundary.

**previous_checkpoint_hash**
This chains checkpoints together the same way blocks chain via parent hash. Checkpoint N+1 must reference the hash of Checkpoint N. This creates an unbroken cryptographic chain from genesis through every checkpoint to the present.

**committee_signatures**
A randomly selected committee of archive validators, who hold full chain history, independently verify the checkpoint before signing. The checkpoint is only finalized when a quorum of committee signatures is collected.

---

### Checkpoint Verification — N to N+1

To verify that Checkpoint N+1 is valid, any participant who holds:
- Checkpoint N (or its hash)
- Block headers from the N+1 window

Can run the following verification:

```
1. Hash(Checkpoint_N) == Checkpoint_N+1.previous_checkpoint_hash
   → confirms chain continuity between checkpoints

2. header[start_block].parent_hash == Hash(header[end_block of N])
   → confirms block continuity at the checkpoint boundary

3. MerkleRoot(headers[start_block..end_block]) == Checkpoint_N+1.merkle_root
   → confirms all headers in the window are correctly committed

4. header[end_block].state_root == Checkpoint_N+1.state_root
   → confirms state root at boundary matches what consensus finalized

5. verify k-of-m committee signatures over Hash(Checkpoint_N+1)
   → confirms archive committee approved this checkpoint
```

All five checks pass — checkpoint is valid. No full history required. No exotic cryptography. No GPU. Standard hash functions only.

---

### Transaction Verification After Pruning

Every block header already contains a transaction Merkle root:

```
Block header {
  tx_root: MerkleRoot([tx_1, tx_2, tx_3, ...])
  state_root: ...
  parent_hash: ...
  ...
}
```

After block bodies are pruned, a specific transaction can still be verified:

```
1. Requester provides: transaction data + Merkle proof path
2. Compute: MerkleProof(tx, proof_path) → should equal block_header.tx_root
3. Verify: block_header is committed in checkpoint via checkpoint.merkle_root
4. Result: transaction inclusion is proven without the full block body
```

Archive validators store full block bodies and serve them with attached proofs on request. The proof is verifiable by anyone using only data that is never pruned.

---

### What Is Pruned vs What Is Kept

```
PRUNED (after checkpoint finalization):
  Full block bodies — transactions, receipts, logs

KEPT PERMANENTLY:
  Block headers                 (~500 bytes to 1kb each, tiny)
  Checkpoint commitments        (~2kb to 10kb each)
  Current world state           (required for execution, never prunable)
  Recent blocks after latest    (current working window)
  checkpoint
```

### Storage Impact

Using conservative Ethereum-scale numbers:

```
Full block body (avg):          ~100kb to 2mb
10,000 blocks full data:        ~10gb to 200gb
10,000 block headers only:      ~5mb to 10mb
Checkpoint commitment:          ~2kb to 10kb

Reduction ratio:                ~1,000x to 20,000x
```

This is not marginal improvement. It is orders of magnitude.

---

## Participant Roles

### Consensus Validators

Responsible for block production and state transition validation. After CSCA, they maintain:

- Current world state
- Recent blocks (current checkpoint window)
- All checkpoint commitments (tiny)
- Block headers for all windows (small)

They do not maintain full block bodies for pruned history. Their storage is bounded. The same hardware remains sufficient indefinitely if the checkpoint interval is calibrated correctly.

### Archive Validators

A smaller dedicated subset that maintains complete chain history. They are responsible for:

- Verifying checkpoint correctness (they are the only participants who can do this fully)
- Signing checkpoint commitments as committee members
- Serving historical data and inclusion proofs on request
- Preserving full replay capability for auditing and forensics

Archive validators carry higher storage costs. Their incentive structure must reflect this — committee participation rewards, elevated staking returns, and challenge rewards should make this role economically attractive.

### The Archive Committee

At each checkpoint interval, a committee is randomly selected from the archive validator set. The committee:

1. Independently computes the checkpoint commitment over the window
2. Verifies state root continuity
3. Verifies Merkle root correctness
4. Signs the checkpoint if valid
5. Broadcasts the finalized checkpoint to the network

Randomness in committee selection prevents predictable collusion. Committee size is a parameter that balances verification cost against collusion resistance.

---

## The Challenge Window

After a checkpoint is proposed by the committee, a challenge window opens before the checkpoint is considered final.

During this window, any participant who holds block headers for the window can verify the checkpoint independently. If they find a discrepancy:

- They submit a challenge with a specific proof of incorrectness
- The network verifies the challenge
- If the challenge is accepted, the checkpoint is rejected, the committee is penalized (slashing), and the challenger receives a significant reward

The reward for a successful challenge must be large enough to justify the computational cost of running full verification. This creates an economic incentive for independent verification without requiring every participant to do it.

This is an optimistic model — the network proceeds on the assumption the committee is honest, with a punishment and reward mechanism that makes dishonesty irrational.

---

## Checkpoint Interval Design

The interval between checkpoints should not be time-based. It should be storage-based.

The target is **bounded validator storage** — a validator buys hardware once and that hardware remains sufficient indefinitely. The interval should be derived from:

```
window_size_in_blocks = (target_storage - current_state_size) / average_block_size
```

This means:
- The interval floats with network activity
- High throughput periods produce more data per block, shortening the window
- Low throughput periods produce less, lengthening the window
- The storage footprint for consensus validators stays within a defined bound

This is a meaningfully different promise from existing pruning approaches, which slow growth but do not bound it. CSCA targets genuinely fixed storage requirements as a first-class protocol property.

---

## What CSCA Does Not Change

- Consensus rules
- Finality mechanism
- Validator selection
- Block production logic
- Execution model
- Trust assumptions

CSCA operates entirely after consensus has already finalized correctness. It optimizes what is done with data that is already immutable and agreed upon. The underlying security assumptions of the chain are unchanged.

---

## Relationship to Existing Work

CSCA builds conceptually on directions the industry has explored:

| Concept | Relation to CSCA |
|---|---|
| Block pruning | CSCA formalizes aggressive pruning with cryptographic accountability |
| Weak subjectivity checkpoints | CSCA extends this into a full compaction protocol |
| Archive / full node separation | CSCA formalizes this as a protocol-level role distinction |
| State sync / snap sync | CSCA makes checkpoint-based sync the default, not the exception |
| Stateless validation research | CSCA is complementary — reduces state growth pressure |
| Modular blockchain architecture | CSCA aligns with separation of execution and data availability |

What CSCA specifically formalizes that does not exist as a unified proposal elsewhere:

> Aggressive finalized-history pruning for consensus validators, gated by archive committee consensus, with an open challenge window and explicit economic incentives for archival participation — as a first-class protocol architecture rather than an operational afterthought.

---

## Current Status

This repository contains the initial proposal and specification for CSCA.

```
v0  — Initial concept and problem framing
v1  — Cryptographic specification (this document)
```

Planned:

```
v2  — Python simulation demonstrating checkpoint math
v3  — Formal whitepaper (arxiv submission)
v4  — Reference implementation on a testable chain fork
```

---

## Author

Proposed and authored by **[Your Name]**
Initial commit and public record: **May 2026**

This document represents original work. All prior art referenced is acknowledged in the Relationship to Existing Work section above. The specific formalization, architecture, and combined protocol design represented here is the original contribution of the author.

---

## License

This proposal is published under **Creative Commons Attribution 4.0 International (CC BY 4.0)**.

You are free to share and build upon this work with appropriate credit to the original author.

---

## Contributing

This is an early stage research proposal. Feedback, formal critique, and technical discussion are welcome via GitHub Issues.

If you are a protocol researcher or core developer at a blockchain project and want to discuss implementation, open an issue or reach out directly.