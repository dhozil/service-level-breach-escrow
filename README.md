<div align="center">

# ServiceLevelBreachEscrow

**SLA breach claims with proportional escrow payout: provider posts an SLA bond, claimant files a hash-bound evidence claim, validators fetch evidence and score the breach, payout is split proportionally.**

![GenLayer](https://img.shields.io/badge/GenLayer-Intelligent%20Contract-6a4cff)
![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![Status](https://img.shields.io/badge/status-live%20on%20studionet-2ea44f)
![Tests](https://img.shields.io/badge/tests-10%20passed-2ea44f)

[Live Contract](https://explorer-studio.genlayer.com/address/0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1)

[GenLayer Docs](https://docs.genlayer.com)

</div>

---

## Why

Service-level agreements (uptime, response time, availability) need a neutral way to decide whether a breach actually happened. A provider can promise 99.9% uptime and post an SLA bond; when the claimant alleges a breach, a neutral consensus must weigh the claimant's story against public evidence. ServiceLevelBreachEscrow does this: the claimant files a claim with an evidence URL that is hash-bound at claim time, validators fetch the evidence on-chain, score the breach, and the escrow splits proportionally.

Reference: [GenLayer Use Cases — Markets and claims](https://docs.genlayer.com/understand-genlayer-protocol/typical-use-cases) (SLA claims based on public sources, chargeback evidence).

## Live Deployment

| | |
|---|---|
| **Contract** | [ServiceLevelBreachEscrow](https://explorer-studio.genlayer.com/address/0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1) |
| **Address** | `0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1` |
| **Network** | GenLayer studionet (chain `61999`) |
| **Status** | Deployed + verified on-chain |

## Highlights

- **Proportional SLA payout**: claimant payout = `escrow_amount * breach_score // 100`; provider keeps the remainder — partial breaches pay partial compensation
- **Immutability-bound evidence (steward fix)**: evidence URL + incident summary are hash-bound, and the claimant commits the **exact evidence content hash** (`sha256` of fetched content) at claim time; settlement re-fetches and rejects substitution at the same URL (score 0) if content does not match
- **On-chain evidence fetch**: validators fetch the evidence URL from the contract, not from claimant-supplied text; unreachable evidence deterministically scores 0
- **Consensus field safety**: every field consumed after consensus (`score`, `reasoning`) is required by validators and handled safely on settlement
- **No fund locks**: bounded escape paths for open and claimed-but-unsettled covers

## How It Works

```
create_cover (payable; provider, claimant, service, SLA terms, claim_window)
      |
      v
file_claim (claimant only; evidence URL + summary + exact content hash → committed)
      |
      v
settle_claim (permissionless; consensus breach score 0-100 → proportional split)
      |
      v (no claim)
expire_cover (after window → provider reclaims full escrow)
```

## Methods

| Role | Method | Guard |
|---|---|---|
| Provider | `create_cover` | payable; funding == amount; bounded inputs; unique id |
| Claimant | `file_claim` | status open; claimant only; before deadline; commits evidence+content hashes |
| Any | `settle_claim` | status claimed; consensus breach score; atomic split |
| Any | `expire_cover` | status open; after claim window; no claim filed |
| Any | `get_cover`, `get_all_covers` | read-only |

## Security Model

- **Caller binding**: only the provider (`provider == sender`) can create a cover (addresses validated as `0x` + 40 hex; provider ≠ claimant)
- Funding invariant: actual payable value must equal the recorded amount (`Escrow funding must equal the cover total`)
- **Evidence authority & immutability boundary (steward fix)**: claim commits agreed authoritative source (URL) and binds exact evidence content via `sha256` at claim time; settlement re-fetches and deterministically scores 0 if content is substituted at the same URL before payout
- **Consensus field safety (steward fix)**: validators require every field consumed after consensus (`score`, `reasoning`); settlement safely handles consensus fields
- LLM scoring with exact agreement (`SCORE_TOLERANCE = 5`), unreachable/substituted evidence → deterministic deny (score 0)
- Payout split sums exactly to the escrow total (integer floor + remainder → no dust left behind)
- **Anti-lock**: claimed covers can be aborted by anyone after `claim_deadline + 30 days` (full return to provider); open covers expire after the claim window — funds can never lock forever
- `reasoning` is descriptive-only (audit note) and never reused in consequential computation

## Test

```bash
gltest tests/ -q   # 10 passed
```

## Lint

```bash
genvm-lint check contracts/service_level_breach_escrow.py
```

## Live Deployment

Deployed on GenLayer studionet (chain `61999`):
[`0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1`](https://explorer-studio.genlayer.com/address/0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1)
