# Steward Review — Requests and Fixes (Theory + On-Chain Methods)

**Date:** 2026-11-13  
**Network:** GenLayer studionet (chain `61999`)  
**Wallet (deployer/verifier):** `0x646454E139609564ae2bbDA7762bB4ADaA01B467`  
**Scope:** ConditionalReleaseEscrow, ServiceLevelBreachEscrow (SealedGrantRound unchanged; portal submission handled by user)

---

## 1) ConditionalReleaseEscrow

- **Repo (pushed, matching source):** `dhozil/conditional-release-escrow` @ `8845db6` (`main`)
- **Deployed contract:** [`0x1F25Fd52468091e5a3b410669Ae33867634739F8`](https://explorer-studio.genlayer.com/address/0x1F25Fd52468091e5a3b410669Ae33867634739F8)
- **Deploy tx:** `0x7b6b13e3db45269e3eae0a1715c72f3127d1383aee747dea12cc90d5883c8350` (exec SUCCESS, stderr `''`)

### 1.1 Steward request (verbatim intent)

> Please correct the refund lifecycle and provide matching source and deployment. As written, any caller can refund an open escrow immediately: an LLM escrow starts with `judgment_approved = false`, while a time escrow is refundable before its release deadline. Require an explicit recorded denial or expiry before refund, keep funds locked through the agreed decision window, and apply the intended caller authorization. Please include tests showing that premature and unauthorized refunds fail and that eligible refunds still succeed.

### 1.2 Problem (theory)

- **Premature LLM refund:** refund eligibility depended on `not judgment_approved` while status was `open`. Since `judgment_approved` starts `false`, any caller could refund immediately—even before any judgment attempt—bypassing the agreed decision/judgment window.
- **Premature time refund:** refund was allowed before `release_deadline`, letting the depositor claw back funds during the agreed release window instead of waiting for expiry.
- **No recorded denial:** a failed/denied LLM judgment previously reverted, leaving no explicit on-chain denial record; refund eligibility was ambiguous/implicit rather than auditable.
- **Missing caller authorization:** `refund_escrow` did not bind the caller, so unauthorized parties could trigger refunds.

### 1.3 Fix — theory and design

| Concern | Design fix | Rationale |
|---|---|---|
| Explicit recorded denial (LLM) | `release_escrow` runs AI consensus; on **deny** it records `judgment_denied=True`, `judgment_score`, `reasoning`, keeps `status=open`, and returns `{released:false, denied:true,...}` (no revert). On **approve** it releases funds. | Denial becomes an explicit, auditable on-chain fact (not lost to revert) that gates refund eligibility. |
| Expiry before refund (time) | `refund_escrow` (time) requires `now >= release_deadline`. | Funds remain locked through the agreed decision/release window; refund only after expiry. |
| No premature refund (LLM) | `refund_escrow` (LLM) requires `judgment_denied == true` (and rejects if `judgment_approved`). | Refund impossible before an explicit recorded denial (i.e. before/without a concluded adverse judgment). |
| Caller authorization | `refund_escrow` requires `gl.message.sender_address == depositor` → `Only depositor can refund`. | Only the intended party (depositor) can reclaim escrowed funds. |
| Decision window locked | Premature paths revert for both modes; release remains permissionless crank after window/approval. | Escrow cannot be drained early by depositor or strangers. |
| Consensus safety | Validator requires leader `score` and `reasoning` (types/range/quantization) with exact-agreement tolerance; `reasoning` stored audit-only. | Every consumed consensus field is required/handled safely. |
| State fields (appended) | `Escrow`: `judgment_denied: bool`, `judgment_score: u256`, `reasoning: str`. | Persists explicit judgment outcome for eligibility and audit. |

**Relevant on-chain methods (final):**
- `create_escrow(escrow_id, depositor, recipient, amount, condition, release_after_seconds, condition_text, evidence_url)` — payable; depositor-bound; binds explicit condition + hash-bound evidence URL.
- `release_escrow(escrow_id)` — permissionless. `time`: releases after `release_deadline`. `llm`: consensus fetches evidence, scores satisfaction (>=50 release, else **records explicit denial** on-chain).
- `refund_escrow(escrow_id)` — **depositor-only**. `time`: only after expiry. `llm`: only after explicit recorded denial.
- `get_escrow`, `get_all_escrows` — views.

### 1.4 Tests (direct-mode)

`conditional-release-escrow/tests/test_conditional_release_escrow.py` — **8/8 passed** (`gltest tests/ -q`)

| Test | What it proves |
|---|---|
| `test_create_escrow_validates` | Funding/field/address guards; evidence hash binding |
| `test_release_by_time` | Time-gate release only after window |
| `test_release_by_llm_consensus` | LLM approve on fetched evidence releases funds |
| `test_release_llm_denied_records_denial_then_refund` | Deny **recorded** on-chain (not reverted) → depositor refund succeeds |
| `test_release_llm_unreachable_evidence_records_denial` | Unreachable evidence → recorded denial (score 0) |
| `test_refund_premature_and_unauthorized_fail` | Premature (time before expiry, LLM before recorded denial) **fail**; stranger **fails**; depositor eligible refunds (time after expiry, LLM after recorded denial) **succeed** |
| `test_refund_after_release_not_open` | No refund after release |
| `test_create_escrow_auth_address_and_duplicate_guards` | Sender/address/duplicate guards |

`genvm-lint check` — **passed** (5 methods: 2 view, 3 write).

### 1.5 On-chain verification (deterministic, `leader_only=True`)

Script: `scripts/verify_conditional_release_escrow_onchain.py` — **PASSED**

| Step | Result |
|---|---|
| A) `create_escrow` (time, payable 1000, 120s window) | accepted, status open |
| B) funding mismatch | reverted (expected) |
| C) invalid condition | reverted (expected) |
| D) `release_escrow` before window | reverted (expected) |
| E) **premature** `refund_escrow` (not expired) | **reverted (expected)** |
| F) **unauthorized** `refund_escrow` (stranger) | **reverted (expected)** |
| G) short-window escrow → expiry → `refund_escrow` by **depositor** | **succeeded** (refunded) |
| H) `release_escrow` after refund | reverted (not open, expected) |

### 1.6 On-chain proof — full AI consensus (`leader_only=False`)

Script: `scripts/test_full_consensus_conditional.py` — **DONE** (all txs exec SUCCESS, stderr `''` unless noted revert)

| Tx | Method / scenario | Exec | Stderr |
|---|---|---|---|
| `0xcf0507ef18aec1d0758f495cdce0e71a5e625bfb6c7fd6f98a13cf56b5c8da99` | `create_escrow` (LLM) | SUCCESS | `''` |
| `0x52e969941e6f1802b0087e1c0c828ef6d6b4142acb9162e48a9530fc5f689cd5` | `release_escrow` (LLM) — **explicit denial recorded** by AI consensus (evidence fetched from example.com, does not satisfy condition) | SUCCESS | `''` |
| `0xee768ef9e5f77575e89cd5274214edea8c1319d94bb8529c8917f0ed8bb511f5` | `refund_escrow` — **depositor refund after recorded denial** | SUCCESS | `''` |
| `0x85409b9894c0b53bd30aa2c9df2ac2fb2c6be21e3b374a9d9649f44ba98d3c18` | `create_escrow` (time) | SUCCESS | `''` |
| `0xf2299d088eb14926e68e6afe9b61ad521beb733e5bbc6f0d9a8aaca81089dde2` | `release_escrow` (time, after window) | SUCCESS | `''` |
| `0x97b62ce9fe1d17555d2eccc8950c9c2d3d244b11c038b7c836f112ef03a058d3` | `release_escrow` double (guard) | ERROR (expected revert) | `''` |

**Live on-chain state (read from contract):**

- `get_escrow("full-cond-llm-1794576242")`:
  - `status="refunded"`, `condition="llm"`, `amount=1000`
  - `judgment_approved=false`, **`judgment_denied=true`**, `judgment_score=0`
  - `reasoning`: "The fetched evidence is a generic 'Example Domain' placeholder page. It does not contain any project deliverables, code, or a coverage report as required by the explicit release condition."
  - `evidence_hash` bound to `(url|condition_text)`; depositor `0x646454...`, recipient `0x19E7...`
- `get_escrow("full-cond-time-1794576242")`:
  - `status="released"`, `judgment_approved=true`, `judgment_denied=false`, `judgment_score=100`, `reasoning="Time gate satisfied."`

**Conclusion (ConditionalReleaseEscrow):** refund lifecycle corrected — no premature/unauthorized refunds; LLM denial explicitly recorded on-chain; time refundable only after expiry; depositor-only; funds locked through decision window. Matching source deployed and pushed; proven by unit tests, deterministic on-chain verify, and real consensus txs + live state.

---

## 2) ServiceLevelBreachEscrow

- **Repo (pushed, matching source):** `dhozil/service-level-breach-escrow` @ `9576e28` (`main`)
- **Deployed contract:** [`0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1`](https://explorer-studio.genlayer.com/address/0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1)
- **Deploy tx:** `0x6c244d15151d605566221af625073abf2d0f2e1b5279fee19cea70d72328706b` (exec SUCCESS, stderr `''`)

### 2.1 Steward request (verbatim intent)

> Please provide matching submitted and deployed source that (1) fixes the evidence authority and immutability boundary—for example, by committing the cover to an agreed authoritative source policy and binding the exact evidence content before payout—and (2) requires every field consumed after consensus, including reasoning, or handles a missing field safely. Please include tests showing that evidence content cannot be substituted at the same URL before settlement and that any validator-accepted result completes settlement without a missing-field failure.

### 2.2 Problem (theory)

- **Evidence authority/immutability gap:** claim bound `evidence_url` and `incident_summary` (`sha256(url|summary)`) but **not the actual fetched content**. Because settlement fetches the URL at settle time, the content at the same URL could be substituted between claim and payout, breaking the immutability boundary.
- **Consensus field safety:** validator did not require `reasoning`, and settlement consumed it unsafely; a missing/ill-typed consensus field could cause settlement failure or unsafe handling.

### 2.3 Fix — theory and design

| Concern | Design fix | Rationale |
|---|---|---|
| Agreed authoritative source policy | `file_claim` commits `evidence_url` (authoritative http(s) source) and binds `evidence_hash = sha256(url|incident_summary)`. | Establishes the agreed source and claim context. |
| Exact evidence content bound before payout (immutability) | Claimant supplies `evidence_content_hash = sha256(exact fetched content)` at `file_claim` (validated 64-hex); stored as `SlaCover.evidence_content_hash`. During `settle_claim`, validators independently fetch content and enforce `sha256(fetched_content) == evidence_content_hash`. On mismatch → deterministic `score 0`, reasoning indicates substitution; payout favors provider (no claimant payout on substituted/invalid evidence). | Exact content is committed pre-payout; substitution at the same URL cannot produce a favorable settlement. |
| Require consumed consensus fields | `validator_fn` requires leader `score` (int, 0–100, quantized) **and** `reasoning` (str). Disagreement or missing/invalid fields → reject. | Every field consumed after consensus is required and validated. |
| Safe handling / no missing-field failure | `breach_fn` always returns `reasoning` string (fallbacks on invalid/missing LLM output). Settlement consumes via safe access/defaults (`result.get("score",0)`, `result.get("reasoning","")`, clamped). | Any validator-accepted/produced result settles without missing-field crash. |
| State field (appended) | `SlaCover.evidence_content_hash: str`. | Persists the committed content hash for enforcement. |

**Relevant on-chain methods (final):**
- `create_cover(cover_id, provider, claimant, service_name, sla_terms, escrow_amount, claim_window_seconds)` — payable, provider-bound, funded.
- `file_claim(cover_id, evidence_url, incident_summary, evidence_content_hash)` — **claimant-only**, before deadline; commits authoritative source + incident hash + **exact content hash**.
- `settle_claim(cover_id)` — permissionless; consensus fetches evidence, enforces committed content hash (substitution/unreachable → score 0), scores breach, splits escrow proportionally; requires/handles `score` & `reasoning`.
- `expire_cover(cover_id)` — bounded anti-lock (open after window, or claimed after settle grace).
- `get_cover`, `get_all_covers` — views.

### 2.4 Tests (direct-mode)

`service-level-breach-escrow/tests/test_service_level_breach_escrow.py` — **10/10 passed** (`gltest tests/ -q`)

| Test | What it proves |
|---|---|
| `test_create_cover_validates` | Funding/bounds/field guards |
| `test_file_claim_only_claimant_and_binds_evidence` | Claimant-only; binds `evidence_hash` **and** `evidence_content_hash`; validates 64-hex content hash |
| `test_settle_claim_proportional_payout` | Consensus score → proportional split; reasoning stored |
| `test_settle_claim_unreachable_evidence_scores_zero` | Unreachable evidence → deterministic score 0 |
| `test_evidence_content_cannot_be_substituted_before_settlement` | Same URL, substituted content (hash mismatch vs committed) → **score 0, no claimant payout, full provider return** (settled) |
| `test_validator_accepted_result_handles_missing_fields_safely` | LLM omits `reasoning` → settlement completes safely (defaulted), no missing-field failure |
| `test_expire_cover_after_window_releases_to_provider` | Expiry after window |
| `test_expire_before_window_and_settle_without_claim_revert` | Guards |
| `test_create_cover_auth_address_and_duplicate_guards` | Sender/address/duplicate guards |
| `test_claimed_cover_expires_after_settle_grace` | Claimed-cover anti-lock |

`genvm-lint check` — **passed** (6 methods: 2 view, 4 write).

### 2.5 On-chain verification (deterministic, `leader_only=True`)

Script: `scripts/verify_service_level_breach_onchain.py` — **PASSED**

| Step | Result |
|---|---|
| A) `create_cover` (payable 1000) | accepted |
| B) funding mismatch | reverted (expected) |
| C) duplicate id | reverted (expected) |
| D) `settle_claim` without claim | reverted (expected) |
| E) `expire_cover` before window | reverted (expected) |
| F) `file_claim` (claimant) binds evidence + **content hash** | accepted; `evidence_hash` match **and** `evidence_content_hash` match |

### 2.6 On-chain proof — full AI consensus (`leader_only=False`)

Script: `scripts/test_full_consensus_sla.py` — **DONE** (claim committed exact content hash of fetched stable evidence; all txs exec SUCCESS, stderr `''` unless noted revert)

| Tx | Method / scenario | Exec | Stderr |
|---|---|---|---|
| `0x8f08a1a8e9b996879ed28636ca0a7ac3e2a309752cdb0cf9f97eb79a0acc4f9d` | `create_cover` | SUCCESS | `''` |
| `0x9578a6242d93de93030b87f3f2a3305a2fe1cb41f2271012729702ce81e103b8` | duplicate `create_cover` (guard) | ERROR (expected) | `''` |
| `0xc8b9c1ad5b7a8ace19c5c7ffe4350b1092f8f7400c49f32f0df2d591a00c18db` | `file_claim` by non-claimant (guard) | ERROR (expected) | `''` |
| `0xe138a52544ea75ce8c9ad5abbf594d8757f6934d8f3d291460323b0d8b835013` | `file_claim` (claimant) — **commits exact evidence content hash** | SUCCESS | `''` |
| `0x05b9fe286fe1ff2318415a13f9a93162a23ec02df4086aaf9bc7bf7536f0de6b` | `settle_claim` — **AI consensus, content-hash enforced** (score 0, split 0/1000 sums to total) | SUCCESS | `''` |
| `0x0c576d5f166f6b0666cd2daf1216e8c3121616b836c1a0c5db92e9014e54d6c2` | double `settle_claim` (guard) | ERROR (expected) | `''` |
| `0x78a50bb12c9ff762e699d8d19c22f08eca506cacbe3fffec665e6cedd8187e2c` | `expire_cover` after window | SUCCESS | `''` |

**Live on-chain state (read from contract, settled consensus case):**

- `get_cover("full-sla-1794576113")`:
  - `status="settled"`, `breach_score=0`, `claimant_payout=0`, `provider_return=1000`, `escrow_amount=1000`
  - `evidence_url="https://raw.githubusercontent.com/genlayerlabs/genvm/main/LICENSE"` (authoritative source)
  - `evidence_hash="85f2b723..."` (url|summary), **`evidence_content_hash="9db8336874ca896ae3e88efca8efaf6d058f32730ef0c9fc912de43ef27aed89"`** (exact content committed)
  - `reasoning`: "Fetched evidence is a software license agreement containing no data on uptime, availability, or any SLA metrics. No breach can be substantiated from the authoritative on-chain evidence."

**Conclusion (ServiceLevelBreachEscrow):** evidence authority established and exact content hash committed pre-payout (immutability boundary enforced on-chain; substitution at same URL deterministically rejected/scored 0 per tests & design). Consensus requires `score`+`reasoning` and settlement handles fields safely (no missing-field failure). Matching source deployed and pushed; proven by unit tests, deterministic on-chain verify, and real consensus txs + live state.

---

## 3) Evidence summary

| Contract | Address | Deploy tx | Tests | Lint | Deterministic on-chain | Full AI consensus (key txs, stderr `''`) | Pushed |
|---|---|---|---:|---|---|---|---|
| ConditionalReleaseEscrow | `0x1F25Fd52468091e5a3b410669Ae33867634739F8` | `0x7b6b13e3...8350` | 8/8 | pass | PASS | deny recorded `0x52e9...`, refund after denial `0xee76...`, time release `0xf229...` | `8845db6` |
| ServiceLevelBreachEscrow | `0x8eCB5f46A8c29C6456338e73BcDB9D5ae7fF16B1` | `0x6c244d151...706b` | 10/10 | pass | PASS | settle (content-hash enforced) `0x05b9...` | `9576e28` |

All cited consensus/deterministic transactions executed successfully on studionet with empty `stderr` on leader receipts (revert-guard txs show expected ERROR). Source repositories match deployed contracts. User handles portal submissions.
