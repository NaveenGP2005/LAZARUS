"""
LAZARUS — core/coroner.py
The Coroner: classifies a failed transaction into one of 8 archetypes.

Two-layer approach:
  Layer 1 — Deterministic rule engine: maps known error codes to archetypes (fast, ~100% accuracy on known codes)
  Layer 2 — Bayesian Network (pgmpy): handles unknown/ambiguous codes and outputs a confidence distribution

The output is always: {archetype, confidence, causal_factors, all_scores}
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ARCHETYPES
from pgmpy.models import BayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination
import warnings
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# Build the reverse lookup: error_code → archetype
# ─────────────────────────────────────────────────────────────────────────────
ERROR_CODE_MAP: dict[str, str] = {}
for arch_name, arch_cfg in ARCHETYPES.items():
    for code in arch_cfg["error_codes"]:
        ERROR_CODE_MAP[code.upper()] = arch_name


# ─────────────────────────────────────────────────────────────────────────────
# Bayesian Network — models ambiguous / unknown failure signals
#
# Structure:
#   PaymentMethod → Archetype
#   RiskScore     → Archetype
#   TimeOfDay     → Archetype
#   RetryCount    → Archetype
#
# Archetype has 8 states (one per archetype, in order of ARCHETYPES dict)
# ─────────────────────────────────────────────────────────────────────────────

ARCHETYPE_LIST = list(ARCHETYPES.keys())  # fixed ordering for CPD indexing
N_ARCHETYPES = len(ARCHETYPE_LIST)        # 8


def _build_bayesian_network() -> tuple[BayesianNetwork, VariableElimination]:
    """
    Build and return the Bayesian Network and its inference engine.
    Called once at module load. All CPDs are domain-knowledge-informed.
    """
    model = BayesianNetwork([
        ("PaymentMethod", "Archetype"),
        ("RiskScore",     "Archetype"),
        ("TimeOfDay",     "Archetype"),
        ("RetryCount",    "Archetype"),
    ])

    PM_STATES  = ["upi", "card", "netbanking", "emandate", "wallet"]
    RS_STATES  = ["low", "medium", "high"]
    TOD_STATES = ["night", "morning", "afternoon", "evening"]
    RC_STATES  = ["first", "second", "third_plus"]

    # ── PaymentMethod
    cpd_method = TabularCPD(
        variable="PaymentMethod", variable_card=5,
        values=[[0.35], [0.30], [0.15], [0.15], [0.05]],
        state_names={"PaymentMethod": PM_STATES},
    )

    # ── RiskScore
    cpd_risk = TabularCPD(
        variable="RiskScore", variable_card=3,
        values=[[0.75], [0.15], [0.10]],
        state_names={"RiskScore": RS_STATES},
    )

    # ── TimeOfDay
    cpd_tod = TabularCPD(
        variable="TimeOfDay", variable_card=4,
        values=[[0.20], [0.25], [0.30], [0.25]],
        state_names={"TimeOfDay": TOD_STATES},
    )

    # ── RetryCount
    cpd_retry = TabularCPD(
        variable="RetryCount", variable_card=3,
        values=[[0.70], [0.20], [0.10]],
        state_names={"RetryCount": RC_STATES},
    )

    # ── Archetype CPD — P(Archetype | PaymentMethod, RiskScore, TimeOfDay, RetryCount)
    # Shape: (8, 5*3*4*3) = (8, 180)
    # We define prior weights per archetype and modulate by parents
    # This is a simplified expert-defined CPD — honest about its construction
    import numpy as np

    n_parent_states = 5 * 3 * 4 * 3  # 180 combinations
    cpd_values = np.zeros((N_ARCHETYPES, n_parent_states))

    arch_idx = {a: i for i, a in enumerate(ARCHETYPE_LIST)}

    combo_idx = 0
    for pm in range(5):      # PaymentMethod
        for rs in range(3):  # RiskScore
            for tod in range(4):  # TimeOfDay
                for rc in range(3):  # RetryCount
                    weights = np.array([0.125] * 8)  # start uniform

                    # velocity_trap strongly indicated by high risk score
                    if rs == 2:
                        weights[arch_idx["velocity_trap"]] *= 8.0
                        weights[arch_idx["dropped_signal"]] *= 0.3

                    # emandate → expired_mandate likely
                    if pm == 3:
                        weights[arch_idx["expired_mandate"]] *= 5.0

                    # night + first attempt + low risk → empty_vault or ghost_checkout
                    if tod == 0 and rc == 0 and rs == 0:
                        weights[arch_idx["empty_vault"]] *= 3.0
                        weights[arch_idx["ghost_checkout"]] *= 2.0

                    # morning/afternoon, low risk, multiple retries → dropped_signal
                    if tod in (1, 2) and rs == 0 and rc >= 1:
                        weights[arch_idx["dropped_signal"]] *= 4.0

                    # high amount (proxied by retry count) → limit_breaker
                    if rc == 0 and rs == 0 and tod in (1, 2, 3):
                        weights[arch_idx["limit_breaker"]] *= 1.5

                    # normalize to probability distribution
                    weights /= weights.sum()
                    cpd_values[:, combo_idx] = weights
                    combo_idx += 1

    cpd_archetype = TabularCPD(
        variable="Archetype", variable_card=N_ARCHETYPES,
        values=cpd_values,
        evidence=["PaymentMethod", "RiskScore", "TimeOfDay", "RetryCount"],
        evidence_card=[5, 3, 4, 3],
        state_names={
            "Archetype": ARCHETYPE_LIST,
            "PaymentMethod": ["upi", "card", "netbanking", "emandate", "wallet"],
            "RiskScore": ["low", "medium", "high"],
            "TimeOfDay": ["night", "morning", "afternoon", "evening"],
            "RetryCount": ["first", "second", "third_plus"],
        },
    )

    model.add_cpds(cpd_method, cpd_risk, cpd_tod, cpd_archetype, cpd_retry)
    assert model.check_model(), "Bayesian Network CPDs are inconsistent!"
    inference = VariableElimination(model)
    return model, inference


# Module-level singleton — build once
_bn_model, _bn_inference = _build_bayesian_network()


# ─────────────────────────────────────────────────────────────────────────────
# Coroner: Public API
# ─────────────────────────────────────────────────────────────────────────────

class Coroner:
    """
    Classifies a failed payment into one of 8 archetypes.
    Returns a CoronerReport with archetype, confidence, and causal factors.
    """

    def classify(self, transaction: dict) -> dict:
        """
        Main classification method.
        Returns:
            {
                "archetype": str,
                "confidence": float,
                "causal_factors": list[str],
                "all_scores": dict[str, float],
                "method": str   # "rule_engine" or "bayesian_network"
            }
        """
        failure_code = transaction.get("failure_code", "").upper()

        # ── Layer 1: Deterministic rule engine (fast path)
        if failure_code in ERROR_CODE_MAP:
            archetype = ERROR_CODE_MAP[failure_code]
            causal_factors = self._extract_causal_factors(transaction, archetype)
            return {
                "archetype": archetype,
                "confidence": 0.95,  # high confidence for known codes
                "causal_factors": causal_factors,
                "all_scores": {a: (0.95 if a == archetype else 0.007) for a in ARCHETYPE_LIST},
                "method": "rule_engine",
            }

        # ── Layer 2: Bayesian Network (ambiguous/unknown codes)
        evidence = self._build_evidence(transaction)
        query = _bn_inference.query(
            variables=["Archetype"],
            evidence=evidence,
            show_progress=False,
        )

        scores = {state: float(query.values[i]) for i, state in enumerate(ARCHETYPE_LIST)}
        best_archetype = max(scores, key=scores.get)
        confidence = scores[best_archetype]
        causal_factors = self._extract_causal_factors(transaction, best_archetype)

        return {
            "archetype": best_archetype,
            "confidence": round(confidence, 4),
            "causal_factors": causal_factors,
            "all_scores": {k: round(v, 4) for k, v in scores.items()},
            "method": "bayesian_network",
        }

    def _build_evidence(self, txn: dict) -> dict:
        """Convert raw transaction fields to BN evidence states."""
        # PaymentMethod
        pm = txn.get("payment_method", "upi")
        pm_map = {"upi": "upi", "card": "card", "netbanking": "netbanking",
                  "emandate": "emandate", "wallet": "wallet"}
        pm_state = pm_map.get(pm, "upi")

        # RiskScore
        rs = txn.get("risk_score", 0.0)
        rs_state = "high" if rs > 0.7 else ("medium" if rs > 0.3 else "low")

        # TimeOfDay
        from datetime import datetime
        try:
            hour = datetime.fromisoformat(txn.get("failure_time", "2026-08-01T12:00:00")).hour
        except Exception:
            hour = 12
        if hour >= 22 or hour < 6:
            tod_state = "night"
        elif 6 <= hour < 12:
            tod_state = "morning"
        elif 12 <= hour < 18:
            tod_state = "afternoon"
        else:
            tod_state = "evening"

        # RetryCount
        rc = txn.get("retry_count", 0)
        rc_state = "first" if rc == 0 else ("second" if rc == 1 else "third_plus")

        return {
            "PaymentMethod": pm_state,
            "RiskScore": rs_state,
            "TimeOfDay": tod_state,
            "RetryCount": rc_state,
        }

    def _extract_causal_factors(self, txn: dict, archetype: str) -> list:
        """Human-readable list of factors that led to this classification."""
        factors = [f"error_code:{txn.get('failure_code', 'UNKNOWN')}"]

        if txn.get("risk_score", 0) > 0.7:
            factors.append(f"high_risk_score:{txn['risk_score']}")

        if txn.get("payment_method") == "emandate":
            factors.append("payment_method:emandate")

        buyer = txn.get("buyer", {})
        if buyer.get("is_first_time_buyer"):
            factors.append("first_time_buyer")

        if buyer.get("prior_failures_7d", 0) > 0:
            factors.append(f"prior_failures_7d:{buyer['prior_failures_7d']}")

        try:
            from datetime import datetime
            hour = datetime.fromisoformat(txn.get("failure_time", "")).hour
            if hour >= 22 or hour < 6:
                factors.append("late_night_timing")
        except Exception:
            pass

        return factors
