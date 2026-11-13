"""Direct-mode tests for the ServiceLevelBreachEscrow contract."""

import hashlib
import json
import re
from datetime import datetime, timedelta

from gltest.direct import create_address

COVER_ID = "c0"
PROVIDER_ADDR = create_address("provider")
CLAIMANT_ADDR = create_address("claimant")
PROVIDER = "0x" + PROVIDER_ADDR.hex()
CLAIMANT = "0x" + CLAIMANT_ADDR.hex()
AMOUNT = 1000
EVIDENCE_URL = "https://status.example.com/incident-42"
INCIDENT = "Uptime 85% during incident window; SLA requires 99.9%"
EVIDENCE_BODY = "Incident report: uptime 85%"
EVIDENCE_BODY_SUBSTITUTED = "Incident report: uptime 99.99% (edited)"
EVIDENCE_CONTENT_HASH = hashlib.sha256(EVIDENCE_BODY.encode()).hexdigest()

BREACH_70_JSON = json.dumps({"score": 70, "reasoning": "Clear breach of SLA terms."})
BREACH_0_JSON = json.dumps({"score": 0, "reasoning": "No breach."})


def _create_cover(
    contract,
    vm,
    provider=PROVIDER,
    claimant=CLAIMANT,
    amount=AMOUNT,
    claim_window_seconds=3600,
):
    vm.sender = PROVIDER_ADDR
    vm.value = amount
    return contract.create_cover(
        cover_id=COVER_ID,
        provider=provider,
        claimant=claimant,
        service_name="Status API",
        sla_terms="Uptime >= 99.9% per month",
        escrow_amount=amount,
        claim_window_seconds=claim_window_seconds,
    )


def _file_claim(contract, vm, evidence_content_hash=EVIDENCE_CONTENT_HASH):
    vm.sender = CLAIMANT_ADDR
    return contract.file_claim(
        cover_id=COVER_ID,
        evidence_url=EVIDENCE_URL,
        incident_summary=INCIDENT,
        evidence_content_hash=evidence_content_hash,
    )


def test_create_cover_validates(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    direct_vm.sender = PROVIDER_ADDR
    direct_vm.value = AMOUNT

    with direct_vm.expect_revert("Cover id is required"):
        contract.create_cover(cover_id="", provider=PROVIDER, claimant=CLAIMANT, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=3600)
    with direct_vm.expect_revert("Provider and claimant are required"):
        contract.create_cover(cover_id="c0", provider="", claimant=CLAIMANT, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=3600)
    with direct_vm.expect_revert("Service name and SLA terms are required"):
        contract.create_cover(cover_id="c0", provider=PROVIDER, claimant=CLAIMANT, service_name="", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=3600)
    with direct_vm.expect_revert("Escrow amount must be > 0"):
        direct_vm.value = 0
        contract.create_cover(cover_id="c0", provider=PROVIDER, claimant=CLAIMANT, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=3600)
    direct_vm.value = 5
    with direct_vm.expect_revert("Escrow funding must equal the cover total"):
        contract.create_cover(cover_id="c0", provider=PROVIDER, claimant=CLAIMANT, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=3600)
    direct_vm.value = AMOUNT
    with direct_vm.expect_revert("Escrow funding must equal the cover total"):
        contract.create_cover(cover_id="c0", provider=PROVIDER, claimant=CLAIMANT, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=5, claim_window_seconds=3600)
    with direct_vm.expect_revert("Claim window must be at least 1 second"):
        contract.create_cover(cover_id="c0", provider=PROVIDER, claimant=CLAIMANT, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=0)
    with direct_vm.expect_revert("Claim window cannot exceed 30 days"):
        contract.create_cover(cover_id="c0", provider=PROVIDER, claimant=CLAIMANT, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=2592001)

    cid = _create_cover(contract, direct_vm)
    c = contract.get_cover(cid)
    assert c["status"] == "open"
    assert c["escrow_amount"] == AMOUNT
    assert c["provider"] == PROVIDER
    assert c["claimant"] == CLAIMANT


def test_file_claim_only_claimant_and_binds_evidence(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    cid = _create_cover(contract, direct_vm)

    direct_vm.sender = PROVIDER_ADDR
    with direct_vm.expect_revert("Only claimant can file a claim"):
        contract.file_claim(
            cover_id=cid, evidence_url=EVIDENCE_URL, incident_summary=INCIDENT,
            evidence_content_hash=EVIDENCE_CONTENT_HASH,
        )

    # Content hash must be valid 64-hex sha256.
    direct_vm.sender = CLAIMANT_ADDR
    with direct_vm.expect_revert("Evidence content hash is required"):
        contract.file_claim(cover_id=cid, evidence_url=EVIDENCE_URL, incident_summary=INCIDENT, evidence_content_hash="")
    with direct_vm.expect_revert("Evidence content hash must be a 64-hex sha256"):
        contract.file_claim(cover_id=cid, evidence_url=EVIDENCE_URL, incident_summary=INCIDENT, evidence_content_hash="bad")

    _file_claim(contract, direct_vm)
    c = contract.get_cover(cid)
    expected_hash = hashlib.sha256(f"{EVIDENCE_URL}|{INCIDENT}".encode()).hexdigest()
    assert c["status"] == "claimed"
    assert c["evidence_url"] == EVIDENCE_URL
    assert c["evidence_hash"] == expected_hash
    assert c["evidence_content_hash"] == EVIDENCE_CONTENT_HASH

    with direct_vm.expect_revert("Cover is not open"):
        _file_claim(contract, direct_vm)


def test_settle_claim_proportional_payout(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    cid = _create_cover(contract, direct_vm)
    _file_claim(contract, direct_vm)

    direct_vm.mock_web(re.escape(EVIDENCE_URL), {"status": 200, "body": EVIDENCE_BODY})
    direct_vm.mock_llm(re.escape("You are an SLA breach adjudicator"), BREACH_70_JSON)
    res = contract.settle_claim(cover_id=cid)
    assert int(res.get("breach_score")) == 70
    assert int(res.get("claimant_payout")) == 700
    assert int(res.get("provider_return")) == 300
    c = contract.get_cover(cid)
    assert c["status"] == "settled"
    assert c["claimant_payout"] == 700
    assert c["provider_return"] == 300
    assert c["reasoning"] == "Clear breach of SLA terms."


def test_settle_claim_unreachable_evidence_scores_zero(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    cid = _create_cover(contract, direct_vm)
    _file_claim(contract, direct_vm)

    direct_vm.mock_web(re.escape(EVIDENCE_URL), {"status": 404, "body": "not found"})
    direct_vm.mock_llm(re.escape("You are an SLA breach adjudicator"), BREACH_0_JSON)
    res = contract.settle_claim(cover_id=cid)
    assert int(res.get("breach_score")) == 0
    assert int(res.get("claimant_payout")) == 0
    assert int(res.get("provider_return")) == AMOUNT
    assert contract.get_cover(cid)["status"] == "settled"


def test_evidence_content_cannot_be_substituted_before_settlement(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    cid = _create_cover(contract, direct_vm)
    _file_claim(contract, direct_vm)  # commits hash of EVIDENCE_BODY

    # Same URL now serves substituted content -> must be rejected (score 0), not paid out.
    direct_vm.mock_web(re.escape(EVIDENCE_URL), {"status": 200, "body": EVIDENCE_BODY_SUBSTITUTED})
    direct_vm.mock_llm(re.escape("You are an SLA breach adjudicator"), BREACH_70_JSON)
    res = contract.settle_claim(cover_id=cid)
    assert int(res.get("breach_score")) == 0
    assert int(res.get("claimant_payout")) == 0
    assert int(res.get("provider_return")) == AMOUNT
    c = contract.get_cover(cid)
    assert c["status"] == "settled"
    assert "substituted" in c["reasoning"].lower()


def test_validator_accepted_result_handles_missing_fields_safely(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    cid = _create_cover(contract, direct_vm)
    _file_claim(contract, direct_vm)

    # LLM omits reasoning field; breach_fn must handle it safely and still
    # complete settlement without a missing-field failure.
    direct_vm.mock_web(re.escape(EVIDENCE_URL), {"status": 200, "body": EVIDENCE_BODY})
    direct_vm.mock_llm(re.escape("You are an SLA breach adjudicator"), json.dumps({"score": 40}))
    res = contract.settle_claim(cover_id=cid)
    assert int(res.get("breach_score")) == 40
    assert int(res.get("claimant_payout")) == 400
    assert int(res.get("provider_return")) == 600
    c = contract.get_cover(cid)
    assert c["status"] == "settled"
    assert c["reasoning"] == ""  # safely defaulted, no crash


def test_expire_cover_after_window_releases_to_provider(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    cid = _create_cover(contract, direct_vm)

    direct_vm.warp((datetime.now() + timedelta(seconds=7200)).isoformat())
    res = contract.expire_cover(cover_id=cid)
    assert bool(res.get("released")) is True
    c = contract.get_cover(cid)
    assert c["status"] == "released"
    assert c["provider_return"] == AMOUNT

    with direct_vm.expect_revert("Cover is not open"):
        contract.expire_cover(cover_id=cid)


def test_expire_before_window_and_settle_without_claim_revert(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    cid = _create_cover(contract, direct_vm)

    with direct_vm.expect_revert("Claim window has not passed"):
        contract.expire_cover(cover_id=cid)
    with direct_vm.expect_revert("Cover has no filed claim"):
        contract.settle_claim(cover_id=cid)


def test_create_cover_auth_address_and_duplicate_guards(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    stranger = create_address("stranger")

    direct_vm.sender = stranger
    direct_vm.value = AMOUNT
    with direct_vm.expect_revert("Only provider can create a cover"):
        contract.create_cover(cover_id="c9", provider=PROVIDER, claimant=CLAIMANT, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=3600)

    direct_vm.sender = PROVIDER_ADDR
    with direct_vm.expect_revert("Invalid Ethereum address"):
        contract.create_cover(cover_id="c9", provider="0x123", claimant=CLAIMANT, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=3600)
    with direct_vm.expect_revert("Provider and claimant must differ"):
        contract.create_cover(cover_id="c9", provider=PROVIDER, claimant=PROVIDER, service_name="Status API", sla_terms="Uptime >= 99.9%", escrow_amount=AMOUNT, claim_window_seconds=3600)

    cid = _create_cover(contract, direct_vm)
    assert cid == COVER_ID
    with direct_vm.expect_revert("Cover already exists"):
        _create_cover(contract, direct_vm)


def test_claimed_cover_expires_after_settle_grace(direct_vm, direct_deploy):
    contract = direct_deploy("contracts/service_level_breach_escrow.py")
    cid = _create_cover(contract, direct_vm)
    _file_claim(contract, direct_vm)

    # Before deadline + 30d grace: cannot expire a claimed cover.
    with direct_vm.expect_revert("Claim filed; settle grace has not passed"):
        contract.expire_cover(cover_id=cid)

    direct_vm.warp((datetime.now() + timedelta(seconds=3600 + 2592000 + 3600)).isoformat())
    res = contract.expire_cover(cover_id=cid)
    assert bool(res.get("released")) is True
    c = contract.get_cover(cid)
    assert c["status"] == "released"
    assert c["provider_return"] == AMOUNT
