"""
LAZARUS — data/generator.py
Generates 100 synthetic failed payment transactions across 8 archetypes.
Each record is realistic but entirely synthetic — no real customer data.
Run:  python data/generator.py
"""

import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ARCHETYPES, BATCH_DISTRIBUTION, TRANSACTIONS_PATH

# ─────────────────────────────────────────────────────────────────────────────
# Seed for reproducibility — same dataset every run
# ─────────────────────────────────────────────────────────────────────────────
SEED = 42
random.seed(SEED)

# ─────────────────────────────────────────────────────────────────────────────
# Realistic pools to draw from
# ─────────────────────────────────────────────────────────────────────────────

MERCHANT_IDS = [f"MRC_{i:04d}" for i in range(1, 11)]
PAYMENT_METHODS = ["upi", "card", "netbanking", "emandate", "wallet"]

# Amount ranges per archetype (in paise)
AMOUNT_RANGES = {
    "empty_vault":     (50000, 800000),    # ₹500 – ₹8,000  (real purchase, tight wallet)
    "frozen_gate":     (100000, 2000000),  # ₹1,000 – ₹20,000
    "dropped_signal":  (10000, 500000),    # any amount — pure network
    "hesitant_hand":   (30000, 300000),    # ₹300 – ₹3,000  (hesitation at smaller amounts)
    "limit_breaker":   (200000, 10000000), # ₹2,000 – ₹1,00,000 (high-value)
    "expired_mandate": (49900, 499900),    # ₹499 – ₹4,999  (subscription range)
    "ghost_checkout":  (20000, 600000),    # ₹200 – ₹6,000
    "velocity_trap":   (500000, 5000000),  # ₹5,000 – ₹50,000 (fraud usually targets high-value)
}

# Failure timestamps — mix of time-of-day patterns
def random_failure_time(archetype: str) -> str:
    """Generate a realistic failure timestamp for the archetype."""
    base = datetime(2026, 8, 1)
    day_offset = random.randint(0, 18)
    dt = base + timedelta(days=day_offset)

    if archetype == "empty_vault":
        # Month-end, late night — wallet is empty
        hour = random.choice([0, 1, 22, 23, 14, 15])
    elif archetype == "dropped_signal":
        # Peak hours — network congestion
        hour = random.choice([9, 10, 11, 13, 14, 20, 21])
    elif archetype == "velocity_trap":
        # Rapid sequence — fraud bots active at night
        hour = random.choice([1, 2, 3, 4])
    else:
        hour = random.randint(8, 22)

    minute = random.randint(0, 59)
    dt = dt.replace(hour=hour, minute=minute, second=random.randint(0, 59))
    return dt.isoformat()


def random_buyer(archetype: str) -> dict:
    """Generate realistic buyer context."""
    is_first_time = archetype in ("hesitant_hand", "ghost_checkout") and random.random() > 0.4
    txn_count = 0 if is_first_time else random.randint(1, 48)
    return {
        "customer_id": f"CUST_{uuid.uuid4().hex[:8].upper()}",
        "is_first_time_buyer": is_first_time,
        "historical_txn_count": txn_count,
        "days_since_last_txn": random.randint(0, 180) if txn_count > 0 else None,
        "prior_failures_7d": random.randint(0, 2) if archetype == "velocity_trap" else 0,
    }


def generate_transaction(archetype: str, idx: int) -> dict:
    """Generate a single synthetic failed transaction."""
    cfg = ARCHETYPES[archetype]
    error_code = random.choice(cfg["error_codes"])
    method_pool = (
        ["emandate", "upi"] if archetype == "expired_mandate"
        else (["upi", "card"] if archetype != "netbanking" else ["netbanking"])
    )
    amount_min, amount_max = AMOUNT_RANGES[archetype]
    amount_paise = random.randint(amount_min // 100, amount_max // 100) * 100  # round to rupee

    return {
        "txn_id": f"pay_{uuid.uuid4().hex[:16]}",
        "idx": idx,
        "archetype_true": archetype,          # ground truth for evaluation
        "merchant_id": random.choice(MERCHANT_IDS),
        "amount_paise": amount_paise,
        "amount_inr": amount_paise / 100,
        "currency": "INR",
        "payment_method": random.choice(method_pool),
        "failure_code": error_code,
        "failure_time": random_failure_time(archetype),
        "buyer": random_buyer(archetype),
        "subscription_id": f"sub_{uuid.uuid4().hex[:12]}" if archetype in ("expired_mandate",) else None,
        "session_data_available": archetype == "ghost_checkout",
        "risk_score": round(random.uniform(0.7, 0.98), 3) if archetype == "velocity_trap" else round(random.uniform(0.0, 0.3), 3),
        "retry_count": 0,
        "status": "failed",
    }


def generate_batch() -> list:
    transactions = []
    idx = 1
    for archetype, count in BATCH_DISTRIBUTION.items():
        for _ in range(count):
            transactions.append(generate_transaction(archetype, idx))
            idx += 1
    random.shuffle(transactions)  # shuffle so order isn't archetype-ordered
    # Re-assign idx after shuffle for cleaner display
    for i, t in enumerate(transactions):
        t["idx"] = i + 1
    return transactions


if __name__ == "__main__":
    Path("data").mkdir(exist_ok=True)
    batch = generate_batch()
    out_path = Path(TRANSACTIONS_PATH)
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(batch, f, indent=2)
    print(f"[OK] Generated {len(batch)} synthetic transactions -> {out_path}")
    # Archetype distribution check
    from collections import Counter
    dist = Counter(t["archetype_true"] for t in batch)
    for arch, cnt in sorted(dist.items()):
        print(f"   {arch:<20} {cnt:>3} records")
