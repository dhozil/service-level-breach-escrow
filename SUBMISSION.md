# Submission: ServiceLevelBreachEscrow

## Category
Intelligent Contracts

## Contract Name
ServiceLevelBreachEscrow

## Summary
A reusable GenLayer primitive for SLA breach claims: a provider posts an SLA bond in escrow, the claimant files a claim committing an agreed authoritative evidence source and the **exact evidence content hash**, GenLayer validators fetch the evidence on-chain, reject substitution, and score the breach; the escrow splits proportionally between claimant and provider.

## What Makes This Unique
- **Immutability-bound evidence (steward fix)**: claimant commits `evidence_url` + `incident_summary` hash and the **exact `evidence_content_hash`** at claim time; settlement re-fetches and deterministically scores 0 if content is substituted at the same URL before payout
- **Proportional SLA payout**: claimant payout = `escrow_amount * breach_score // 100`; provider keeps the remainder — partial breaches pay partial compensation
- **On-chain evidence fetch**: validators fetch the evidence URL from the contract; unreachable/substituted evidence deterministically scores 0
- **Consensus field safety (steward fix)**: validators require every field consumed after consensus (`score`, `reasoning`); settlement handles consensus fields safely
- **Bounded windows / no fund locks**: bounded claim window with expiry and a claimed-cover settle grace (abort) escape path

## How Consensus Is Used
The contract uses `gl.vm.run_nondet_unsafe()` with a custom validator for `settle_claim`: each validator independently fetches the evidence URL, verifies it matches the committed content hash, and re-scores the breach. Consensus requires exact agreement with the leader (`SCORE_TOLERANCE = 5`) and requires `score` and `reasoning`. Unreachable or substituted evidence deterministically scores 0.

## Technical Details
- Python-based GenLayer Intelligent Contract
- `file_claim(cover_id, evidence_url, incident_summary, evidence_content_hash)` commits source policy + exact content hash (immutability boundary)
- Integer-only domain (wei amounts; `u256`/`bool`/`str`); time gates via `datetime` against consensus time
- Funding invariant: actual payable value must equal the recorded amount (`Escrow funding must equal the cover total`)
- Payout split sums exactly to the escrow total (floor + remainder; no dust remaining)
- Storage: `SlaCover` dataclass under `TreeMap` with `u256`/`bool`/`str` fields (includes `evidence_content_hash`)
- Constants: `MAX_COVERS = 100`, `MAX_CLAIM_WINDOW_SECONDS = 2592000`, `SETTLE_GRACE_SECONDS = 2592000`, `SCORE_TOLERANCE = 5`

## Use Case
Service-level agreements (uptime, latency, availability) where a provider posts an SLA bond and a claimant needs neutral, evidence-backed adjudication with proportional compensation and protection against evidence substitution before payout.

## Verification
- 10/10 direct-mode unit tests (create validation, claimant-only claim + evidence/content hash binding, proportional payout 70→700/300, unreachable evidence → score 0, **evidence substitution at same URL → score 0 (cannot be substituted before settlement)**, **validator-accepted result with missing reasoning field handled safely**, expiry after window, expiry/settle guards, auth/address/duplicate guards, claimed-cover expiry after settle grace)
- `genvm-lint check` + validation pass (6 methods: 2 view, 4 write)
- On-chain verified on studionet: payable creation, funding/duplicate guards, settle-without-claim revert, expire-before-window revert, claim filing with evidence + content hash match
- Full AI-consensus integration test (`leader_only=False`, all methods): `settle_claim` tx `0x05b9fe286fe1ff2318415a13f9a93162a23ec02df4086aaf9bc7bf7536f0de6b` settled via validators (score 0, proportional split sums to 1000) with committed content hash enforced; double settle reverted; expire after window released to provider; receipt stderr empty

## Live Deployment
Deployed on GenLayer studionet (chain `61999`):
[`0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1`](https://explorer-studio.genlayer.com/address/0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1)

## Source Code
See `contracts/service_level_breach_escrow.py`
