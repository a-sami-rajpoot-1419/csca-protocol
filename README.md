# CSCA — Checkpointed State Compaction Architecture

> A protocol proposal for dramatically reduced and predictable validator storage growth in finality-based blockchains, through cryptographically verifiable checkpoint commitments.

Elevator pitch: a protocol-level coordination mechanism that makes history compaction verifiable, accountable, and economically sustainable.

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

Most validators only need to do the first. A smaller dedicated set of archive validators handles the second. Finalized history is periodically compacted into cryptographic checkpoints. Validators prune old block bodies. Storage growth becomes dramatically slower and more predictable — not zero, but no longer dominated by full historical block data. The chain keeps running.

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

This removes the largest and fastest-growing component of validator storage — full block bodies — from the long-term footprint. Headers and world state still grow over time; what changes is that full block bodies no longer accumulate across the entire chain history.

## What CSCA adds

CSCA converts informal, unverifiable maintenance practices into a protocol-level coordination mechanism with explicit guarantees:

- **Verifiable pruning:** checkpoints cryptographically commit to the data being pruned, so anyone can later prove what was present before deletion.
- **Accountable archival:** archive nodes become a protocol role with economic incentives and slashing rules, reducing single‑point failures in historical storage.
- **Trustless sync:** new validators verify checkpoint commitments against the header chain instead of blindly trusting snapshot providers.
- **Storage as a protocol property:** checkpoint intervals are derived from storage budgets, making validator storage capacity a first-class protocol parameter.

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
Every block already contains a state root in its header — a cryptographic hash of the entire world state after that block was executed. The checkpoint takes the state root from the final block in its window. This commits to the complete state of the chain at the checkpoint boundary. Because this value was already finalized by consensus, verifying that the checkpoint's state root matches the header does not require re-execution — only access to the finalized header itself.

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

All five checks pass — checkpoint is valid. No full block bodies or chain history required for these checks — only the previous checkpoint, headers for the current window, and committee signatures. Standard hash functions only.

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

Using conservative Ethereum-scale numbers for the **block body component** — the primary target of CSCA pruning:

```
Full block body (avg):          ~100kb to 2mb
10,000 blocks full data:        ~10gb to 200gb
10,000 block headers only:      ~5mb to 10mb
Checkpoint commitment:          ~2kb to 10kb

Reduction ratio (bodies only):  ~1,000x to 20,000x
```

For block bodies specifically, this is not marginal improvement. It is orders of magnitude.

### Storage Model — What Grows and What Is Bounded

CSCA affects different storage components differently. The honest breakdown:

```
Component              After CSCA                         Growth profile
─────────────────────────────────────────────────────────────────────────
Block bodies           Contained within the working window  Reusable; pruned after
                       (recent blocks + current window)   checkpoint finalization

Block headers          Kept permanently                   Linear, but ~500 bytes
                                                          each — orders of magnitude
                                                          smaller than full blocks

Checkpoint commitments Kept permanently                   Tiny (~2kb–10kb each);
                                                          negligible relative to bodies

World state            Kept (required for execution)    Grows with accounts,
                                                          contracts, and storage;
                                                          not addressed by CSCA alone
```

**What CSCA delivers:** predictable and dramatically reduced storage growth for consensus validators, by eliminating the unbounded accumulation of full block bodies across the entire chain history.

**What CSCA does not deliver:** fixed storage forever. Headers grow linearly with chain length. World state grows with network activity. Long-term state size depends on state expiry or statelessness mechanisms outside CSCA's scope. CSCA removes the dominant storage cost; it does not eliminate all growth.

---

## Participant Roles

### Consensus Validators

Responsible for block production and state transition validation. After CSCA, they maintain:

- Current world state
- Recent blocks (current checkpoint window)
- All checkpoint commitments (tiny)
- Block headers for all windows (small)

They do not maintain full block bodies for pruned history. Their storage growth is dramatically reduced and more predictable — dominated by headers and current state rather than the full historical block data that drives growth today. Checkpoint interval calibration keeps the working window (recent blocks + bodies not yet checkpointed) within a defined budget.

### Archive Validators

A smaller dedicated subset that maintains complete chain history. They are responsible for:

- Verifying checkpoint correctness at full depth (re-execution and replay require full block bodies)
- Signing checkpoint commitments as committee members
- Serving historical data and inclusion proofs on request
- Preserving full replay capability for auditing and forensics

Header-level checkpoint verification can be performed by any participant holding the relevant headers. Full historical verification — re-executing transactions, serving pruned block bodies, and building inclusion proofs — requires archive nodes.

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

During this window, participants can verify the checkpoint independently and submit a challenge with a specific proof of incorrectness if they find a discrepancy. If the challenge is accepted, the checkpoint is rejected, the committee is penalized (slashing), and the challenger receives a significant reward.

The reward for a successful challenge must be large enough to justify the cost of verification. This creates an economic incentive for independent scrutiny without requiring every participant to run full verification on every checkpoint.

This is an optimistic model — the network proceeds on the assumption the committee is honest, with a punishment and reward mechanism that makes dishonesty irrational.

**Named parameter: `challenge_window`**

The length of the challenge window (`challenge_window`) is a named protocol parameter that must be tuned deliberately. It should be long enough to allow independent verifiers to:

- fetch headers and the lightweight boundary snapshot for `end_block`,
- run the necessary integrity checks (Merkle root, state_root continuity, signature verification), and
- submit an on‑chain challenge if they detect a discrepancy.

Key dimensions that determine an appropriate `challenge_window` value include: network bandwidth and latency (time to fetch headers/snapshots), archive node response time (RTT and backlog), monitoring and verification complexity (CPU/time required to recompute roots or re-run checks), and the economic monitoring model (who is expected to watch and at what cost).

Choice of `challenge_window` is empirical — it should be derived from operational measurements and simulation in the whitepaper. The implementation should expose `challenge_window` as a protocol parameter (or governance-updatable value) and document recommended defaults together with their assumptions.

### Challenge Types

Not all challenges require the same data or the same participants. Three distinct types must be specified separately:

**Type 1 — Incorrect Merkle root over headers**

```
What is disputed:  checkpoint.merkle_root does not match
                   MerkleRoot(headers in window)

Required data:     block headers for the checkpoint window

Who can challenge: any participant holding those headers
```

This is the lightweight case. Headers are kept permanently by consensus validators, so any validator can recompute the Merkle root and challenge a mismatch without access to pruned block bodies.

**Type 2 — Incorrect state root commitment**

```
What is disputed:  checkpoint.state_root does not match the
                   finalized state at the window boundary

Required data:     block header of the last block in the window
                   (for the standard case — see below)

Who can challenge: any participant holding that header
```

For the standard checkpoint fraud case — a committee signing a state root that does not match what consensus already finalized — no re-execution is required. The checkpoint's `state_root` must equal `header[end_block].state_root`, and that header field was agreed upon by consensus when the block was finalized. Any participant with the header can verify this directly.

Re-execution of full transaction data is only required if the dispute targets the correctness of execution itself — i.e., whether the block header's state root was correctly computed from the transactions. That is a consensus-layer dispute, not a checkpoint-layer dispute, and falls outside CSCA's scope. CSCA assumes consensus finality is already correct; it governs what happens to data after that finality is established.

**Type 3 — Full execution replay (archive-only)**

```
What is disputed:  whether transactions in a window were
                   executed correctly to produce the claimed state

Required data:     full block bodies for the window

Who can challenge: archive validators only
```

This is not a checkpoint integrity check. It is an independent audit of consensus execution. Archive validators are the only participants who retain the data needed to re-execute and verify. CSCA does not replace consensus validation; it provides a separate archival audit path for participants who choose to verify execution independently.

**State snapshot requirement for Type 2 challenges (fields + TTL example)**

To make Type 2 challenges practical and auditable, validators must capture and retain a lightweight boundary snapshot at checkpoint proposal time. A minimal snapshot SHOULD contain at least:

- `end_block` header (block number, parent hash, timestamp),
- `state_root` (from the `end_block` header),
- `checkpoint_hash` (the checkpoint that references the boundary),
- provenance metadata (checkpoint proposal time, committee id, and any committee signatures or signature references), and
- an optional short witness (small proof pointers or hashes to expedite verification).

Retention policy (example): retain the snapshot until `challenge_window` expires plus a small safety margin (for example: `snapshot_ttl = challenge_window + one_block_interval`). After that TTL, validators may discard the snapshot under normal pruning policies. The exact `snapshot_ttl` and safety margin should be set by protocol parameter or governance and justified in the whitepaper with empirical data.

---

## Checkpoint Interval Design

The interval between checkpoints should not be time-based. It should be storage-based — calibrated to keep the **working window** (recent block bodies not yet covered by a checkpoint) within a defined budget.

The interval should be derived from:

```
window_size_in_blocks = (target_storage - current_state_size - header_overhead) / average_block_body_size
```

Where:
- `target_storage` is the total storage budget allocated to the validator's CSCA footprint
- `current_state_size` is the current world state (grows independently of CSCA)
- `header_overhead` accounts for permanently retained headers and checkpoint commitments
- `average_block_body_size` is the rolling average size of full block bodies

This means:
- The interval floats with network activity
- High throughput periods produce larger block bodies, shortening the window
- Low throughput periods produce less, lengthening the window
- The working window footprint stays within a defined bound

This is meaningfully different from existing pruning approaches, which slow body accumulation but do not formalize a storage budget as a protocol property. CSCA targets **predictable and dramatically reduced growth** — not fixed storage forever. Header and state growth remain; the checkpoint interval formula accounts for state size explicitly so the working window budget is honest about what is and is not controlled.

---

## Trust Assumptions

CSCA does not alter consensus rules, finality mechanisms, or execution validation. It operates on data that consensus has already finalized. However, CSCA introduces its own assumptions that are distinct from — though related to — core consensus trust:

**Archive committee honesty**
A randomly selected committee of archive validators computes and signs each checkpoint. The protocol assumes a quorum of this committee is honest. Collusion by a majority of the committee could produce a checkpoint that misrepresents finalized history. The challenge window and slashing mechanism are designed to make this irrational, but the assumption is real.

**Challenge window economics**
The security of the optimistic checkpoint model depends on challenges being submitted when fraud occurs. This requires that challenge rewards exceed verification costs and that at least one honest participant is watching each checkpoint window. If economics are miscalibrated or no one monitors, a fraudulent checkpoint could pass unchallenged.

**Historical data availability**
Once consensus validators prune block bodies, they depend on archive validators to retain and serve historical data. If the archive set is too small, too centralized, or goes offline, pruned history becomes unavailable even though checkpoint commitments remain verifiable. See the Data Availability section below.

**Consensus finality as ground truth**
CSCA treats finalized block headers — including their state roots — as authoritative. Checkpoint verification checks that the checkpoint matches what consensus already agreed upon; it does not re-validate execution. Trust in execution correctness remains where it always was: in the consensus layer.

These assumptions should be evaluated independently from consensus security. Acknowledging them directly is a strength, not a weakness — it allows implementers to reason about the full security model rather than assuming CSCA adds zero new trust surface.

---

## Data Availability

Pruning block bodies from consensus validators creates a data availability dependency on archive nodes. This is the same fundamental problem addressed — but not fully resolved — by Ethereum's [EIP-4444](https://eips.ethereum.org/EIPS/eip-4444) (history expiry) and the [Portal Network](https://www.ethportal.net/) (distributed historical data).

CSCA does not solve data availability from scratch. It formalizes the split between validators who prune and validators who retain, and makes that split a protocol-level responsibility with economic accountability. But the dependency is real:

- If too few archive validators exist, historical block bodies may become unavailable
- If archive validators are geographically or economically concentrated, historical data has a single point of failure
- Receipts, logs, and other body-derived data become inaccessible to pruned nodes without archive cooperation

Mitigations that CSCA should specify or integrate with:

- **Minimum archive redundancy** — protocol-enforced floor on the number and distribution of archive validators
- **Economic incentives** — elevated staking returns and challenge rewards that make archival participation sustainable at scale
- **External DA layers** — integration with dedicated data availability systems (e.g., Celestia, EigenDA) for historical body data, reducing sole dependence on in-protocol archive nodes
- **Portal-style distribution** — decentralized serving of historical data across a wider node set, not just archive validators

CSCA makes the DA dependency explicit and assigns protocol-level responsibility for it. Resolving the dependency fully may require coordination with existing DA infrastructure rather than a standalone CSCA solution.

Qualitatively, the minimum archive set should be determined by factors including geographic diversity, uptime targets, maximum acceptable recovery time for historical data requests, and economic incentives. A protocol parameter such as `min_archive_redundancy` (and rules for its update) can codify this floor; exact numeric values require simulation and incentives analysis in the formal design phase.

## Validator bootstrap and sync path

New validators cannot rely on replaying entire block bodies if history is aggressively pruned. A practical bootstrap path in CSCA is:

1. Obtain and verify the latest finalized checkpoint chain (start from a trusted checkpoint or genesis checkpoint).  
2. Download the corresponding state snapshot for the checkpoint's `end_block` from archive nodes or distributed DA layers and verify it against the checkpoint's `state_root`.  
3. Download and verify block headers back to genesis (headers are kept permanently).  
4. Download recent block bodies from the checkpoint's end forward (the active working window) to catch up to head and begin validation/participation.  

This path assumes archive availability for snapshots and a means to verify checkpoint provenance (committee signatures and checkpoint chain continuity). The bootstrap section should be expanded with protocol messages and trust bootstrapping details in the whitepaper and reference implementation.

---

## What CSCA Does Not Change

- Consensus rules
- Finality mechanism
- Validator selection
- Block production logic
- Execution model

CSCA operates entirely after consensus has already finalized correctness. It optimizes what is done with data that is already immutable and agreed upon. The underlying consensus security model is unchanged — but CSCA adds the additional trust assumptions described above, which must be evaluated as part of any deployment.

---

## Relationship to Existing Work

CSCA builds conceptually on directions the industry has already explored. Individual components are not novel on their own:

| Concept | Relation to CSCA |
|---|---|
| Block pruning | CSCA formalizes aggressive pruning with cryptographic accountability |
| Weak subjectivity checkpoints | CSCA extends this into a full compaction protocol |
| Archive / full node separation | CSCA formalizes this as a protocol-level role distinction |
| State sync / snap sync | CSCA makes checkpoint-based sync the default path, not the exception |
| Stateless validation research | CSCA is complementary — reduces state growth pressure but does not replace statelessness |
| Modular blockchain architecture | CSCA aligns with separation of execution and data availability |
| [EIP-4444](https://eips.ethereum.org/EIPS/eip-4444) (history expiry) | CSCA addresses the same history storage problem; EIP-4444 removes history from execution clients, CSCA adds checkpoint accountability and archive roles |
| [Portal Network](https://www.ethportal.net/) | Portal distributes historical data across a wider node set; CSCA could integrate with or complement Portal-style serving |

**What is synthesis versus what is new**

Most building blocks exist independently: pruning, checkpoint sync, archive node separation, Merkle proofs, and optimistic verification are all established concepts. CSCA's contribution is not inventing these primitives.

What does not exist as a unified protocol specification elsewhere is the combination of:

- Aggressive finalized-history pruning for consensus validators
- Gated by archive committee quorum with cryptographic checkpoint commitments
- An open challenge window with distinct challenge types and economic incentives
- Explicit protocol-level role distinction between consensus and archive validators
- Storage-budget-driven checkpoint intervals as a first-class protocol property

That combination — named, specified, and designed as a coherent architecture rather than an operational afterthought — is the original contribution. The README and eventual whitepaper should be precise about this distinction: CSCA synthesizes known ideas into a unified protocol; it does not claim to invent Merkle trees, pruning, or checkpoint sync.

---

## Current Status

This repository contains the initial proposal, specification, and a working simulation for CSCA.

```
v0  — Initial concept and problem framing
v1  — Cryptographic specification (this document)
v2  — Python simulation demonstrating checkpoint math (csca-simulation.py)
```

Planned:

```
v3  — Formal whitepaper (arxiv submission)
v4  — Reference implementation on a testable chain fork
```

---

## Author

Proposed and authored by **Abdul Sami**
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