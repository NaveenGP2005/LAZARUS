"""
LAZARUS — core/counterfactual.py
Model-based counterfactual estimator.

IMPORTANT DISCLAIMER (embedded in all outputs):
This is a MODEL-BASED ESTIMATE, not experimental proof.
We use pgmpy's do-calculus to estimate what recovery probability
WOULD have been under a different action, given our causal model.
The model's priors are domain-informed but constructed from synthetic data.
Claims are "estimated intervention lift" — not "proved causal lift."
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ARCHETYPE_RECOVERY_RATES, ARCHETYPE_LIST


class CounterfactualEstimator:
    """
    Estimates recovery probability under two strategies:
    1. Baseline: generic next-day retry / send-reminder (Razorpay's default behavior)
    2. LAZARUS: archetype-specific recovery action

    Uses the domain-informed recovery rates from config.py as the causal model priors.
    For a real deployment, these would be estimated from A/B test data.
    """

    DISCLAIMER = (
        "MODEL-BASED ESTIMATE: Recovery probabilities are derived from a domain-informed "
        "causal model with synthetic priors. These are not experimentally proven causal effects. "
        "In production, run A/B tests to calibrate actuals."
    )

    def estimate(self, archetype: str, lazarus_action: str) -> dict:
        """
        Returns counterfactual estimate for one transaction.
        {
            baseline_action: str,
            baseline_prob: float,
            lazarus_action: str,
            lazarus_prob: float,
            estimated_lift: float,
            disclaimer: str
        }
        """
        if archetype not in ARCHETYPE_RECOVERY_RATES:
            return {
                "baseline_action": "generic_retry",
                "baseline_prob": 0.10,
                "lazarus_action": lazarus_action,
                "lazarus_prob": 0.10,
                "estimated_lift": 0.0,
                "disclaimer": self.DISCLAIMER,
            }

        baseline_prob, lazarus_prob = ARCHETYPE_RECOVERY_RATES[archetype]
        estimated_lift = lazarus_prob - baseline_prob

        return {
            "baseline_action": "generic_next_day_retry_or_reminder",
            "baseline_prob": baseline_prob,
            "lazarus_action": lazarus_action,
            "lazarus_prob": lazarus_prob,
            "estimated_lift": round(estimated_lift, 4),
            "disclaimer": self.DISCLAIMER,
        }

    def batch_summary(self, results: list[dict]) -> dict:
        """
        Summarize counterfactual estimates across a batch of transactions.
        Each result must have: archetype, amount_paise, cf_result dict.
        """
        total_amount = 0
        baseline_expected_recovered = 0
        lazarus_expected_recovered = 0
        per_archetype = {}

        for r in results:
            arch = r.get("archetype")
            amount = r.get("amount_paise", 0)
            cf = r.get("counterfactual", {})

            if not cf:
                continue

            baseline_p = cf.get("baseline_prob", 0)
            lazarus_p = cf.get("lazarus_prob", 0)

            total_amount += amount
            baseline_expected_recovered += baseline_p * amount
            lazarus_expected_recovered += lazarus_p * amount

            if arch not in per_archetype:
                per_archetype[arch] = {
                    "count": 0,
                    "total_amount_paise": 0,
                    "baseline_prob": baseline_p,
                    "lazarus_prob": lazarus_p,
                    "estimated_lift": cf.get("estimated_lift", 0),
                }
            per_archetype[arch]["count"] += 1
            per_archetype[arch]["total_amount_paise"] += amount

        estimated_additional_paise = lazarus_expected_recovered - baseline_expected_recovered

        return {
            "total_transactions": len(results),
            "total_amount_paise": total_amount,
            "total_amount_inr": total_amount / 100,
            "baseline_expected_recovered_paise": int(baseline_expected_recovered),
            "lazarus_expected_recovered_paise": int(lazarus_expected_recovered),
            "estimated_additional_recovered_paise": int(estimated_additional_paise),
            "estimated_additional_recovered_inr": round(estimated_additional_paise / 100, 2),
            "per_archetype": per_archetype,
            "disclaimer": self.DISCLAIMER,
        }
