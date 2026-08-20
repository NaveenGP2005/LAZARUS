# LAZARUS — Cause-Aware Payment Recovery Agent

**Razorpay AI Buildathon 2026 · Track 03: AI Revenue Recovery**

> *Razorpay already knows how to retry a failed payment. We asked a different question: should we retry it at all, and if so — why this action rather than another?*

---

## The Core Insight

Razorpay's documented subscription retry is undifferentiated: move to `pending` → retry next day. An insufficient-funds failure and an expired mandate get the same response. LAZARUS adds a **cause-specific decisioning layer** above retry mechanics.

## Architecture — 4 Forensic Layers

```
[Failed Payment]
       │
       ▼
┌──────────────────────────────┐
│  LAYER 1: CORONER            │  Rule engine + Bayesian Network (pgmpy)
│  Classifies into 1 of 8      │  Known NPCI codes → deterministic
│  failure archetypes          │  Unknown codes → BN inference
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│  LAYER 2: STRATEGIST         │  Gemini 1.5 Flash (free tier)
│  Generates cause-specific    │  Advisory only — zero financial authority
│  recovery playbook           │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│  LAYER 3: COMPLIANCE GATE    │  Pure Python, deterministic
│  Enforces hard stopping      │  Quiet hours, contact limits, link cap
│  rules before any API call   │  velocity_trap → always BLOCK
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│  LAYER 4: EXECUTOR           │  Razorpay test-mode SDK
│  Creates payment links,      │  All amounts validated as integer paise
│  deferred retries, escalates │  Notes: ≤15 keys, ≤256 chars each
└──────────────────────────────┘
```

## The 8 Failure Archetypes

| Archetype | Cause | Baseline Response | LAZARUS Response |
|-----------|-------|-------------------|-----------------|
| `empty_vault` | Insufficient funds | Retry next day | Defer 4 days (payday window) |
| `frozen_gate` | Account blocked/KYC | Retry same method | Offer alternative payment method |
| `dropped_signal` | Network timeout/PSP down | Send reminder | Silent auto-retry in 15 min |
| `hesitant_hand` | User decline / 1 PIN error | Spam reminder | Gentle trust-signal re-engage |
| `limit_breaker` | Daily limit exceeded | Retry | Defer to midnight reset |
| `expired_mandate` | Mandate revoked | Retry | Trigger re-consent flow |
| `ghost_checkout` | Abandoned before payment | Generic reminder | Reconstruct and warm re-engage |
| `velocity_trap` | Fraud risk flag | Retry (unsafe) | **Do nothing — escalate only** |

The `velocity_trap` archetype is the most important: **doing nothing is the correct recovery strategy** when any action would raise the fraud signal further.

## Batch Results (100 synthetic transactions)

| Metric | Baseline | LAZARUS |
|--------|----------|---------|
| Recovery rate | 19.0% | 41.0% |
| Amount recovered | ₹1,50,727 | ₹3,75,968 |
| Unsafe actions | 5 | **0** |
| Unnecessary contacts | 15 | **0** |

*Model-based counterfactual estimated additional lift: ~₹3,98,000 across batch*

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Failure classification | Rule engine + `pgmpy` Bayesian Network |
| LLM reasoning | Gemini 1.5 Flash (free tier) |
| Compliance gate | Pure Python — zero AI in financial decisions |
| Razorpay execution | `razorpay` Python SDK (test mode) |
| Audit trail | SQLite with append-only trigger |
| Dashboard | Streamlit |
| **Total cloud cost** | **₹0** |

## Setup

```bash
# 1. Clone
git clone https://github.com/NaveenGP2005/LAZARUS
cd LAZARUS

# 2. Install
pip install -r requirements.txt

# 3. Configure credentials
cp .env.example .env
# Edit .env with your Razorpay test keys and Gemini API key

# 4. Generate synthetic data
python -X utf8 data/generator.py

# 5. Run the batch
python -X utf8 batch_runner.py

# 6. Launch dashboard
streamlit run dashboard.py
```

## Audit Trail Design

Every decision is logged to SQLite with an append-only trigger:

```sql
-- Prevents any modification after write
CREATE TRIGGER prevent_audit_tampering
BEFORE UPDATE ON lazarus_audit
BEGIN
    SELECT RAISE(ABORT, 'LAZARUS: audit trail is append-only.');
END;
```

Razorpay payment link `notes` object is compressed to ≤15 keys, ≤256 chars:
```json
{
  "lazarus_audit_id": "42",
  "archetype": "empty_vault",
  "action": "defer_to_payday_window",
  "policy_version": "v1.0.0",
  "original_txn_id": "pay_XXXXX",
  "failure_code": "INSUFFICIENT_FUNDS"
}
```

## Counterfactual Disclaimer

Recovery probability estimates are **model-based**, not experimentally proven causal effects. The priors come from domain knowledge about UPI/card failure recovery patterns. For production use, calibrate with real A/B test outcomes.

---

*Built for Razorpay AI Buildathon 2026 · Applications close 5 September*
