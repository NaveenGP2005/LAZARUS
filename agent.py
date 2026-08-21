"""
LAZARUS — agent.py
Main orchestrator. Processes one failed transaction end-to-end through all four layers.

Usage:
    from agent import LazarusAgent
    agent = LazarusAgent()
    result = agent.process(transaction)
"""

import sys
import os
import io

# Fix Windows cp1252 terminal encoding — force UTF-8
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from core.coroner import Coroner
from core.strategist import Strategist
from core.compliance import ComplianceGate, ComplianceDecision
from core.executor import Executor
from core.audit import AuditTrail
from core.counterfactual import CounterfactualEstimator
from config import ARCHETYPE_RECOVERY_RATES


class LazarusAgent:
    """
    The LAZARUS Agent.
    Processes one failed transaction through all four forensic layers.
    """

    def __init__(self):
        self.coroner = Coroner()
        self.strategist = Strategist()
        self.compliance = ComplianceGate()
        self.executor = Executor()
        self.audit = AuditTrail()
        self.cf_estimator = CounterfactualEstimator()

        # Rolling contact history: {customer_id: contacts_in_last_7_days}
        self._contact_history: dict[str, int] = {}

        print(f"[LAZARUS] Agent initialized")
        print(f"   Executor mode: {'DRY RUN (no real API calls)' if self.executor.dry_run else 'LIVE (Razorpay test-mode)'}")
        print(f"   Strategist: {'Gemini Flash' if self.strategist.model else 'Expert fallback playbooks'}")
        print()

    def process(self, transaction: dict, verbose: bool = True) -> dict:
        """
        Process one failed transaction through all four layers.
        Returns a complete result dict including audit trail ID.
        """
        txn_id = transaction.get("txn_id", "UNKNOWN")
        idx = transaction.get("idx", "?")

        if verbose:
            print(f"[{idx:>3}] {txn_id} | ₹{transaction.get('amount_paise', 0)/100:>8.2f} | {transaction.get('failure_code')}")

        # ── LAYER 1: Coroner
        coroner_result = self.coroner.classify(transaction)
        archetype = coroner_result["archetype"]

        if verbose:
            conf = coroner_result["confidence"]
            method = coroner_result.get("method", "?")
            print(f"       ↳ [{method[:4]}] Archetype: {archetype} ({conf:.0%})")

        # ── LAYER 2: Strategist
        strategist_result = self.strategist.generate_playbook(transaction, coroner_result)
        proposed_action = strategist_result.get("chosen_action", "manual_review")

        # ── LAYER 3: Compliance Gate
        customer_id = transaction.get("buyer", {}).get("customer_id", "UNKNOWN")
        gate_decision = self.compliance.evaluate(
            transaction=transaction,
            archetype=archetype,
            proposed_action=proposed_action,
            contact_history=self._contact_history,
        )

        if verbose:
            print(f"       ↳ Gate: {gate_decision.verdict} — {gate_decision.reason[:60]}")

        # ── LAYER 4: Execute (only if ALLOW)
        execution_result = {}
        outcome = "PENDING"
        recovered_paise = 0

        if gate_decision.verdict == ComplianceDecision.ALLOW:
            execution_result = self.executor.execute(
                transaction=transaction,
                archetype=archetype,
                action=proposed_action,
                audit_id=0,  # placeholder — real ID assigned after audit write
            )
            # Update contact history
            if self.compliance.allow_contact(archetype):
                self._contact_history[customer_id] = self._contact_history.get(customer_id, 0) + 1
                # Increment payment link counter
                if execution_result.get("resource_type") == "payment_link":
                    self.compliance.payment_links_created += 1

            # Simulate outcome using archetype recovery rates
            outcome, recovered_paise = self._simulate_outcome(archetype, transaction)

        elif gate_decision.verdict == ComplianceDecision.DEFER:
            outcome = "DEFERRED"
        elif gate_decision.verdict == ComplianceDecision.BLOCK:
            outcome = "BLOCKED"

        if verbose:
            emoji = {"SUCCESS": "[OK]", "FAILURE": "[FAIL]", "DEFERRED": "[DEFER]", "BLOCKED": "[BLOCK]", "PENDING": "[PEND]"}  .get(outcome, "?")
            print(f"       ↳ Outcome: {emoji} {outcome} | Recovered: ₹{recovered_paise/100:.2f}")

        # ── Counterfactual estimate
        cf = self.cf_estimator.estimate(archetype, proposed_action)

        # ── Audit Trail
        audit_id = self.audit.log_decision(
            transaction=transaction,
            coroner_result=coroner_result,
            strategist_result=strategist_result,
            gate_decision=gate_decision,
            execution_result=execution_result,
            outcome=outcome,
            recovered_amount_paise=recovered_paise,
            counterfactual=cf,
        )

        return {
            "txn_id": txn_id,
            "audit_id": audit_id,
            "archetype": archetype,
            "confidence": coroner_result["confidence"],
            "proposed_action": proposed_action,
            "gate_verdict": gate_decision.verdict,
            "outcome": outcome,
            "recovered_paise": recovered_paise,
            "recovered_inr": recovered_paise / 100,
            "amount_paise": transaction.get("amount_paise", 0),
            "counterfactual": cf,
        }

    def _simulate_outcome(self, archetype: str, txn: dict) -> tuple[str, int]:
        """
        Simulate recovery outcome using archetype recovery rates.
        In production this would be replaced by real webhook outcomes.
        """
        import random
        rates = ARCHETYPE_RECOVERY_RATES.get(archetype, (0.1, 0.1))
        lazarus_rate = rates[1]

        # Use transaction idx as seed for reproducible simulation
        rng = random.Random(txn.get("idx", 0) * 7 + hash(archetype) % 1000)
        recovered = rng.random() < lazarus_rate

        if recovered:
            return "SUCCESS", txn.get("amount_paise", 0)
        else:
            return "FAILURE", 0




if __name__ == "__main__":
    # Quick smoke test on one synthetic transaction
    import json
    from pathlib import Path
    from config import TRANSACTIONS_PATH

    txn_path = Path(TRANSACTIONS_PATH)
    if not txn_path.exists():
        print("[ERROR] No transactions found. Run: python data/generator.py")
        sys.exit(1)

    with open(txn_path) as f:
        transactions = json.load(f)

    agent = LazarusAgent()
    print("─" * 60)
    print("LAZARUS Smoke Test -- processing first 3 transactions")
    print("─" * 60)
    for txn in transactions[:3]:
        result = agent.process(txn)
        print()
