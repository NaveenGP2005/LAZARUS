"""
LAZARUS — core/compliance.py
The Compliance Gate: deterministic, zero-LLM, zero-hallucination.
Every proposed recovery action passes through here before any API call.
Returns ALLOW, BLOCK, or DEFER with a mandatory reason string.
"""

import sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import COMPLIANCE_RULES, ARCHETYPES


class ComplianceDecision:
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    DEFER = "DEFER"

    def __init__(self, verdict: str, reason: str, defer_until: str | None = None):
        self.verdict = verdict
        self.reason = reason
        self.defer_until = defer_until  # ISO timestamp if DEFER

    def __repr__(self):
        base = f"ComplianceDecision({self.verdict}: {self.reason})"
        if self.defer_until:
            base += f" until {self.defer_until}"
        return base

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "defer_until": self.defer_until,
        }


class ComplianceGate:
    """
    Hard policy engine. All rules are deterministic Python — no AI involved.
    Order of evaluation matters: earlier rules take precedence.
    """

    def __init__(self, payment_links_created: int = 0):
        # Running counter of payment links created this session
        self.payment_links_created = payment_links_created

    def allow_contact(self, archetype: str) -> bool:
        """Returns True if this archetype permits customer contact."""
        return ARCHETYPES.get(archetype, {}).get("contact_customer", False)

    def evaluate(
        self,
        transaction: dict,
        archetype: str,
        proposed_action: str,
        contact_history: dict | None = None,
        _now: datetime | None = None,
    ) -> ComplianceDecision:
        """_now: override current time (used by sandbox for simulation)"""
        """
        Evaluate whether the proposed action is compliant.
        contact_history: {customer_id: number_of_contacts_last_7_days}
        """
        now = _now or datetime.now()
        contact_history = contact_history or {}
        customer_id = transaction.get("buyer", {}).get("customer_id", "UNKNOWN")
        contacts_7d = contact_history.get(customer_id, 0)

        # ── Rule 1: Velocity trap — ALWAYS block any contact/retry
        if archetype == "velocity_trap":
            return ComplianceDecision(
                ComplianceDecision.BLOCK,
                reason="velocity_trap: any contact or retry raises fraud signal. Escalate to merchant instead.",
            )

        # ── Rule 2: Quiet hours — no customer contact between 22:00–08:00
        if ARCHETYPES[archetype]["contact_customer"]:
            hour = now.hour
            quiet_start = COMPLIANCE_RULES["quiet_hours_start"]  # 22
            quiet_end = COMPLIANCE_RULES["quiet_hours_end"]      # 8
            if hour >= quiet_start or hour < quiet_end:
                # Calculate defer until 8 AM
                if hour >= quiet_start:
                    defer_hours = (24 - hour) + quiet_end
                else:
                    defer_hours = quiet_end - hour
                from datetime import timedelta
                defer_until = (now + timedelta(hours=defer_hours)).replace(minute=0, second=0).isoformat()
                return ComplianceDecision(
                    ComplianceDecision.DEFER,
                    reason=f"quiet_hours: no customer contact between {quiet_start}:00–{quiet_end}:00",
                    defer_until=defer_until,
                )

        # ── Rule 3: Contact frequency limit
        if ARCHETYPES[archetype]["contact_customer"]:
            max_contacts = COMPLIANCE_RULES["max_contact_touches_per_7_days"]
            if contacts_7d >= max_contacts:
                return ComplianceDecision(
                    ComplianceDecision.BLOCK,
                    reason=f"contact_limit: customer already contacted {contacts_7d} times in last 7 days (max {max_contacts})",
                )

        # ── Rule 4: Max retries per transaction
        retry_count = transaction.get("retry_count", 0)
        max_retries = COMPLIANCE_RULES["max_retries_per_transaction"]
        if retry_count >= max_retries:
            return ComplianceDecision(
                ComplianceDecision.BLOCK,
                reason=f"max_retries: transaction already attempted {retry_count} times (max {max_retries})",
            )

        # ── Rule 5: Razorpay payment link cap (test-mode)
        if proposed_action in ("create_payment_link", "trigger_re_consent_flow", "gentle_friction_reducer"):
            max_links = COMPLIANCE_RULES["max_razorpay_payment_links"]
            if self.payment_links_created >= max_links:
                return ComplianceDecision(
                    ComplianceDecision.BLOCK,
                    reason=f"razorpay_limit: payment link cap reached ({self.payment_links_created}/{max_links}). Use alternative action.",
                )

        # ── Rule 6: Dropped signal — silent retry, no contact
        if archetype == "dropped_signal":
            if ARCHETYPES[archetype]["contact_customer"] is False:
                return ComplianceDecision(
                    ComplianceDecision.ALLOW,
                    reason="dropped_signal: silent auto-retry approved — no customer contact",
                )

        # ── Rule 7: Minimum amount validation
        amount_paise = transaction.get("amount_paise", 0)
        if amount_paise < 100:  # below ₹1
            return ComplianceDecision(
                ComplianceDecision.BLOCK,
                reason=f"min_amount: amount {amount_paise} paise is below Razorpay minimum (100 paise = ₹1)",
            )

        # ── All checks passed
        return ComplianceDecision(
            ComplianceDecision.ALLOW,
            reason="all_checks_passed",
        )
