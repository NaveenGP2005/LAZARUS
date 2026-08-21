<div align="center">

# 🔬 LAZARUS
### Cause-Aware Payment Recovery Agent
**Razorpay AI Buildathon 2026 · Track 03 — AI Revenue Recovery**

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-Flash-8B5CF6?style=flat-square&logo=google&logoColor=white)
![Razorpay](https://img.shields.io/badge/Razorpay-Test--Mode-02042B?style=flat-square&logo=razorpay&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-34d399?style=flat-square)

</div>

---

## What LAZARUS Does

Most payment recovery tools do **generic next-day retry**. LAZARUS does something different: it runs a **forensic diagnosis** on every failed transaction and picks a cause-specific recovery strategy.

A `TIMEOUT` failure is not the same as `INSUFFICIENT_FUNDS`. Retrying a timed-out UPI payment silently (no customer contact, 15 minutes later) recovers **93%** of those cases. Sending that same user a payment reminder for a true empty-vault failure is noise. LAZARUS knows the difference.

---

## Architecture

> **4 forensic layers. Each layer has one job. No layer overrides the next.**

```
Failed Payment ──► CORONER ──► STRATEGIST ──► COMPLIANCE GATE ──► EXECUTOR
                  (classify)   (plan)           (safe to run?)     (act)
```

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Coroner** | Rule Engine + `pgmpy` Bayesian Network | Classifies failure into 1 of 8 archetypes |
| **Strategist** | Gemini Flash + Expert Fallbacks | Generates cause-specific recovery playbook |
| **Compliance Gate** | Deterministic Python (zero LLM) | Enforces quiet hours, fraud blocks, rate limits |
| **Executor** | Razorpay SDK (test-mode) | Creates payment links, defers retries, escalates |

### The 8 Failure Archetypes

| Archetype | Root Cause | LAZARUS Action | Recovery Rate |
|-----------|-----------|----------------|---------------|
| 🟡 `empty_vault` | Insufficient funds | Defer to payday window | 31% (+22pp) |
| 🔵 `frozen_gate` | Account blocked / KYC | Offer alternative method | 52% (+48pp) |
| 🟢 `dropped_signal` | Network timeout / PSP offline | Silent auto-retry (15min) | 93% (+22pp) |
| 🟠 `hesitant_hand` | User cancelled / PIN error | Gentle friction reducer | 38% (+26pp) |
| 🟣 `limit_breaker` | Daily/txn limit exceeded | Defer to midnight reset | 61% (+43pp) |
| 🩷 `expired_mandate` | Recurring mandate revoked | Trigger re-consent flow | 45% (+39pp) |
| ⚫ `ghost_checkout` | Abandoned before payment | Warm re-engagement | 27% (+19pp) |
| 🔴 `velocity_trap` | Fraud signal / velocity flag | **Hold — do nothing** | 0% (intentional) |

> `velocity_trap` is the key insight: the baseline "recovers" 2% by retrying flagged transactions, creating chargeback exposure. LAZARUS blocks all action and escalates to the merchant. Revenue preservation sometimes means doing nothing.

---

## Results (100-transaction batch)

| Metric | Baseline | LAZARUS |
|--------|----------|---------|
| Recovery rate | 19% | **36%** |
| Amount recovered | ₹1,50,727 | **₹5,59,978** |
| Unsafe actions | 5 | **0** |
| Unnecessary contacts | 15 | **0** |
| Estimated lift | — | **+₹3,98,000** |

---

## Quick Start

**Prerequisites:** Python 3.10+, Razorpay test-mode keys, Gemini API key.

```bash
# 1. Clone and install
git clone https://github.com/NaveenGP2005/LAZARUS.git
cd LAZARUS
pip install -r requirements.txt

# 2. Set your credentials
cp .env.example .env
# Edit .env with your RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, GEMINI_API_KEY

# 3. Generate synthetic transactions
python -X utf8 data/generator.py

# 4. Run the full batch (takes ~4 min due to Gemini rate limits)
python -X utf8 batch_runner.py

# 5. Launch the dashboard
streamlit run dashboard.py
```

---

## Project Structure

```
LAZARUS/
├── core/
│   ├── coroner.py        # Archetype classification (Rule Engine + Bayesian Network)
│   ├── strategist.py     # Gemini Flash playbook generation + Pydantic validation
│   ├── compliance.py     # Deterministic safety gate (zero LLM)
│   ├── executor.py       # Razorpay API wrapper
│   ├── audit.py          # Immutable SQLite audit trail
│   └── counterfactual.py # Model-based lift estimation
├── data/
│   └── generator.py      # Synthetic failed transaction generator
├── agent.py              # Main orchestrator (4-layer pipeline)
├── batch_runner.py       # 100-transaction comparative simulation
├── dashboard.py          # Streamlit dashboard (5 tabs)
├── sandbox.py            # Interactive pipeline sandbox (no audit entry)
├── config.py             # All archetypes, compliance rules, recovery rates
└── requirements.txt
```

---

## Key Design Decisions

**Why no LLM in the Compliance Gate?**
The compliance gate enforces RBI quiet-hours rules and fraud velocity blocks. These are hard constraints — they must not hallucinate. Pure deterministic Python, tested independently.

**Why Pydantic for Strategist output?**
Gemini occasionally returns extra fields, wrong field types, or malformed JSON. Pydantic validates the schema before it enters the pipeline. If validation fails, expert fallbacks fire cleanly.

**Why is `velocity_trap` recovery 0%?**
Any contact or retry on a fraud-flagged transaction raises the risk signal further and risks a permanent bank block. The correct action is escalation, not recovery. LAZARUS prevents the 2% "recovery" that creates chargeback liability.

**Why Bayesian Network + Rule Engine (not just one)?**
For known NPCI error codes, the rule engine gives 95% confidence deterministically. For unknown or ambiguous codes, the Bayesian Network uses payment method, risk score, time of day, and retry count to infer the most likely archetype.

---

## Dashboard Tabs

| Tab | Contents |
|-----|----------|
| 🔬 Coroner's Report | Archetype distribution chart (Plotly), recovery rate table |
| 📊 Recovery Dashboard | Grouped bar chart + radar comparison vs baseline |
| 🧮 Counterfactual | Model-based lift estimates with honest disclaimers |
| 📋 Audit Trail | Filterable immutable log with expandable forensic rows |
| 🎮 Live Sandbox | Interactive single-transaction pipeline demo |

---

<div align="center">
Built for Razorpay AI Buildathon 2026 · Track 03: AI Revenue Recovery
</div>
