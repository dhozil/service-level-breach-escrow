# Submission: ServiceLevelBreachEscrow

## Category
Intelligent Contracts

## Contract Name
ServiceLevelBreachEscrow

## Summary
A reusable GenLayer primitive for SLA breach claims: a provider posts an SLA bond in escrow, the claimant files a claim with hash-bound public evidence, GenLayer validators fetch the evidence on-chain and score the breach, and the escrow splits proportionally between claimant and provider.

## What Makes This Unique
- **Proportional SLA payout**: claimant payout = escrow_amount * breach_score // 100; provider keeps the remainder — partial breaches pay partial compensation
- **Hash-bound evidence**: evidence URL + incident summary are bound with `sha256(url|summary)` at claim time, so evidence cannot be swapped after filing
- **On-chain evidence fetch**: validators fetch the evidence URL from the contract; unreachable evidence deterministically scores 0
- **Bounded claim window**: after the claim window with no claim, `expire_cover` returns the full escrow to the provider (no fund locks)

## How Consensus Is Used
The contract uses `gl.vm.run_nondet_unsafe()` with a custom validator for `settle_claim`: each validator independently fetches the evidence URL and re-scores the breach. Consensus requires exact agreement with the leader (`SCORE_TOLERANCE = 5`). Unreachable evidence deterministically scores 0.

## Technical Details
- Python-based GenLayer Intelligent Contract
- Integer-only domain (wei amounts; `u256`/`bool`/`str`); time gates via `datetime` against consensus time
- Funding invariant: actual payable value must equal the recorded amount (`Escrow funding must equal the cover total`)
- Payout split sums exactly to the escrow total (floor + remainder; no dust remaining)
- Storage: `SlaCover` dataclass under `TreeMap` with `u256`/`bool`/`str` fields
- Constants: `MAX_COVERS = 100`, `MAX_CLAIM_WINDOW_SECONDS = 2592000`, `SCORE_TOLERANCE = 5`

## Use Case
Service-level agreements (uptime, latency, availability) where a provider posts an SLA bond and a claimant needs neutral, evidence-backed adjudication of an alleged breach with proportional compensation.

## Verification
- 8/8 direct-mode unit tests (create validation, claimant-only claim + hash binding, proportional payout 70→700/300, unreachable evidence → score 0, expiry after window, expiry/settle guards, auth/address/duplicate guards, claimed-cover expiry after settle grace)
- `genvm-lint check` + validation pass (6 methods: 2 view, 4 write)
- On-chain verified on studionet: payable creation, funding/duplicate guards, settle-without-claim revert, expire-before-window revert, claim filing with evidence-hash match
- Full AI-consensus integration test (leader_only=False, all methods): settle_claim tx `0x3162ed65976fdd30c0ffcbad2be18b70828e2c61ad2677dbc655e9b90318ed98` settled via validators (score 0, proportional split sums to 1000); double settle reverted; expire after window released to provider

## Live Deployment
Deployed on GenLayer studionet (chain `61999`):
[`0x99A67997df00046A681b235dBD0A4b0Cf9d8434E`](https://explorer-studio.genlayer.com/address/0x99A67997df00046A681b235dBD0A4b0Cf9d8434E)

## Source Code
See `contracts/service_level_breach_escrow.py`
