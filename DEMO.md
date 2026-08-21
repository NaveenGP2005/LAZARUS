# LAZARUS — Quick Start for Judges

## Prerequisites
- Python 3.10+
- A Razorpay **test-mode** account (free at dashboard.razorpay.com)
- A Gemini API key (free at aistudio.google.com)

---

## Step 1 — Clone and install (2 min)

```bash
git clone https://github.com/NaveenGP2005/LAZARUS.git
cd LAZARUS
pip install -r requirements.txt
```

## Step 2 — Set credentials (1 min)

```bash
cp .env.example .env
```

Edit `.env` and fill in:
```
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
GEMINI_API_KEY=AIza...
```

## Step 3 — Run everything (1 command)

```powershell
.\run.ps1
```

This generates synthetic data, runs the 100-transaction batch, and launches the dashboard at **http://localhost:8501**.

> The batch takes ~4 minutes due to Gemini's free-tier rate limit (15 RPM). This is by design — the 4s inter-call delay prevents quota errors.

---

## What to look at in the dashboard

| Tab | What to show |
|-----|-------------|
| 🔬 Coroner's Report | Archetype distribution chart, self-calibrating prior table |
| 📊 Recovery Dashboard | Sankey flow diagram, radar chart |
| 🧮 Counterfactual | Lift estimate with honest disclaimers |
| 📋 Audit Trail | Expand any row to see Gemini reasoning + customer message |
| 🎮 Live Sandbox | Pick `SUSPECTED_FRAUD` at hour 23 → watch BLOCK. Then `INSUFFICIENT_FUNDS` at hour 14 → watch Gemini stream the playbook live |

---

## Key numbers to highlight

- **Recovery rate:** 36% vs 19% baseline
- **Revenue recovered:** ₹5,59,978 vs ₹1,50,727
- **Unsafe actions:** 0 (baseline: 5)
- **Unnecessary contacts:** 0 (baseline: 15)
- **`velocity_trap` recovery:** intentionally 0% — prevents chargeback liability

---

## Architecture in 30 seconds

```
Failed Payment → CORONER → STRATEGIST → COMPLIANCE GATE → EXECUTOR
                (classify) (Gemini plan)  (hard rules)    (Razorpay API)
```

The Compliance Gate has zero LLM involvement — it enforces RBI quiet hours and fraud velocity blocks deterministically. The LLM can only advise, never execute.
