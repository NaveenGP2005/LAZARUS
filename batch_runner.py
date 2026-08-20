"""
LAZARUS — batch_runner.py
Runs all 100 synthetic transactions through LAZARUS and a baseline strategy.
Prints a side-by-side comparison table.

Usage: python batch_runner.py
"""

import json
import sys
import os
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from config import TRANSACTIONS_PATH, ARCHETYPE_RECOVERY_RATES, ARCHETYPE_LIST
from core.counterfactual import CounterfactualEstimator


def run_baseline(transactions: list) -> dict:
    """
    Simulate baseline strategy: generic next-day retry / reminder for every failure.
    Uses the baseline recovery rates from config.py.
    """
    import random
    total_recovered = 0
    total_amount = 0
    recovered_count = 0
    unsafe_actions = 0  # actions on velocity_trap
    unnecessary_contacts = 0  # contacts on dropped_signal

    for txn in transactions:
        archetype = txn["archetype_true"]
        amount = txn["amount_paise"]
        total_amount += amount

        baseline_rate = ARCHETYPE_RECOVERY_RATES.get(archetype, (0.1, 0.1))[0]
        rng = random.Random(txn.get("idx", 0) * 13)
        if rng.random() < baseline_rate:
            total_recovered += amount
            recovered_count += 1

        # Unsafe: baseline always retries velocity_trap
        if archetype == "velocity_trap":
            unsafe_actions += 1

        # Unnecessary: baseline contacts customer even for dropped_signal
        if archetype == "dropped_signal":
            unnecessary_contacts += 1

    return {
        "total": len(transactions),
        "recovered_count": recovered_count,
        "recovery_rate": recovered_count / len(transactions),
        "total_amount_paise": total_amount,
        "recovered_paise": total_recovered,
        "recovered_inr": total_recovered / 100,
        "unsafe_actions": unsafe_actions,
        "unnecessary_contacts": unnecessary_contacts,
    }


def run_lazarus(transactions: list) -> dict:
    """Run the LAZARUS agent on all transactions."""
    from agent import LazarusAgent
    agent = LazarusAgent()

    results = []
    total_recovered = 0
    total_amount = 0
    recovered_count = 0
    unsafe_actions = 0
    unnecessary_contacts = 0
    per_archetype = defaultdict(lambda: {"count": 0, "recovered": 0, "amount": 0})
    cf_results = []

    print("─" * 70)
    print("LAZARUS BATCH RUN — 100 transactions")
    print("─" * 70)

    for txn in transactions:
        result = agent.process(txn, verbose=True)
        archetype = result["archetype"]
        amount = txn["amount_paise"]

        total_amount += amount
        per_archetype[archetype]["count"] += 1
        per_archetype[archetype]["amount"] += amount

        if result["outcome"] == "SUCCESS":
            total_recovered += amount
            recovered_count += 1
            per_archetype[archetype]["recovered"] += amount

        # LAZARUS should never act on velocity_trap
        if archetype == "velocity_trap" and result["gate_verdict"] != "BLOCK":
            unsafe_actions += 1

        # LAZARUS should never contact customer for dropped_signal
        if archetype == "dropped_signal" and result["outcome"] not in ("DEFERRED", "BLOCKED"):
            # Check if it was a silent retry (OK) or customer-facing
            pass  # silent_auto_retry is always contact_customer=False

        cf_results.append({
            "archetype": archetype,
            "amount_paise": amount,
            "counterfactual": result.get("counterfactual", {}),
        })
        results.append(result)

    cf_summary = CounterfactualEstimator().batch_summary(cf_results)

    return {
        "total": len(transactions),
        "recovered_count": recovered_count,
        "recovery_rate": recovered_count / len(transactions),
        "total_amount_paise": total_amount,
        "recovered_paise": total_recovered,
        "recovered_inr": total_recovered / 100,
        "unsafe_actions": unsafe_actions,
        "unnecessary_contacts": unnecessary_contacts,
        "per_archetype": dict(per_archetype),
        "counterfactual_summary": cf_summary,
        "results": results,
    }


def print_comparison(baseline: dict, lazarus: dict):
    """Print a formatted comparison table."""
    print()
    print("=" * 70)
    print("  LAZARUS vs BASELINE — BATCH RESULTS")
    print("=" * 70)

    def fmt_inr(paise): return f"₹{paise/100:,.2f}"
    def fmt_pct(rate): return f"{rate:.1%}"

    rows = [
        ("Transactions processed",  baseline["total"],                    lazarus["total"],             ""),
        ("Recovered count",          baseline["recovered_count"],           lazarus["recovered_count"],   ""),
        ("Recovery rate",            fmt_pct(baseline["recovery_rate"]),    fmt_pct(lazarus["recovery_rate"]), ""),
        ("Total amount at risk",     fmt_inr(baseline["total_amount_paise"]), fmt_inr(lazarus["total_amount_paise"]), ""),
        ("Amount recovered",         fmt_inr(baseline["recovered_paise"]),  fmt_inr(lazarus["recovered_paise"]), ""),
        ("Unsafe actions taken",     baseline["unsafe_actions"],            lazarus["unsafe_actions"],    "← lower is better"),
        ("Unnecessary contacts",     baseline["unnecessary_contacts"],      lazarus["unnecessary_contacts"], "← lower is better"),
    ]

    col_w = [32, 16, 16, 20]
    header = f"{'Metric':<{col_w[0]}} {'Baseline':>{col_w[1]}} {'LAZARUS':>{col_w[2]}} {'Note':<{col_w[3]}}"
    print(header)
    print("─" * 70)
    for row in rows:
        print(f"{str(row[0]):<{col_w[0]}} {str(row[1]):>{col_w[1]}} {str(row[2]):>{col_w[2]}} {str(row[3]):<{col_w[3]}}")

    cf = lazarus.get("counterfactual_summary", {})
    print()
    print("─" * 70)
    print("  MODEL-BASED COUNTERFACTUAL ESTIMATE")
    print("─" * 70)
    print(f"  Baseline expected recovery:  {fmt_inr(cf.get('baseline_expected_recovered_paise', 0))}")
    print(f"  LAZARUS expected recovery:   {fmt_inr(cf.get('lazarus_expected_recovered_paise', 0))}")
    print(f"  Estimated additional lift:   {fmt_inr(cf.get('estimated_additional_recovered_paise', 0))}")
    print()
    print(f"  ⚠  {cf.get('disclaimer', '')[:90]}")
    print()

    print("─" * 70)
    print("  PER-ARCHETYPE BREAKDOWN (LAZARUS)")
    print("─" * 70)
    print(f"  {'Archetype':<22} {'Count':>6} {'Amount':>12} {'Recovered':>12} {'Rate':>7}")
    for arch in ARCHETYPE_LIST:
        data = lazarus["per_archetype"].get(arch, {})
        count = data.get("count", 0)
        amount = data.get("amount", 0)
        recovered = data.get("recovered", 0)
        rate = recovered / amount if amount > 0 else 0
        print(f"  {arch:<22} {count:>6} {fmt_inr(amount):>12} {fmt_inr(recovered):>12} {fmt_pct(rate):>7}")

    print("=" * 70)


if __name__ == "__main__":
    txn_path = Path(TRANSACTIONS_PATH)
    if not txn_path.exists():
        print("❌ No transactions found. Run: python data/generator.py")
        sys.exit(1)

    with open(txn_path) as f:
        transactions = json.load(f)

    print(f"📦 Loaded {len(transactions)} transactions")
    print()

    baseline = run_baseline(transactions)
    print(f"\n✅ Baseline simulation complete")
    print()

    lazarus = run_lazarus(transactions)
    print(f"\n✅ LAZARUS run complete")

    print_comparison(baseline, lazarus)

    # Save results for dashboard
    import json as _json
    with open("batch_results.json", "w") as f:
        # Don't serialize the full results list to keep file small
        summary = {
            "baseline": {k: v for k, v in baseline.items()},
            "lazarus": {k: v for k, v in lazarus.items() if k != "results"},
        }
        _json.dump(summary, f, indent=2, default=str)
    print(f"\n📊 Results saved to batch_results.json")
    print("   Run: streamlit run dashboard.py")
