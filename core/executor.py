"""
LAZARUS — core/executor.py
Razorpay test-mode API wrapper.
Executes ONLY after the compliance gate returns ALLOW.
Enforces all Razorpay API constraints: paise formatting, notes limits, test-mode link cap.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    RAZORPAY_CURRENCY,
    RAZORPAY_MIN_AMOUNT_PAISE,
    RAZORPAY_NOTES_MAX_KEYS,
    RAZORPAY_NOTES_MAX_VALUE_LEN,
    RAZORPAY_PAYMENT_LINK_EXPIRE_SECONDS,
    POLICY_VERSION,
)

try:
    import razorpay
    _RAZORPAY_AVAILABLE = True
except ImportError:
    _RAZORPAY_AVAILABLE = False


class Executor:
    """
    Executes recovery actions via Razorpay test-mode API.
    Falls back to dry-run simulation if credentials are not set.
    All amounts validated as integers in paise before any API call.
    """

    def __init__(self, key_id: str | None = None, key_secret: str | None = None):
        self.key_id = key_id or os.getenv("RAZORPAY_KEY_ID", "")
        self.key_secret = key_secret or os.getenv("RAZORPAY_KEY_SECRET", "")
        self._client = None
        self._dry_run = True

        is_test_key = self.key_id.startswith("rzp_test_")
        has_real_creds = (
            _RAZORPAY_AVAILABLE
            and self.key_id
            and self.key_secret
            and is_test_key
            and "YOUR_KEY_ID_HERE" not in self.key_id
        )

        if has_real_creds:
            self._client = razorpay.Client(auth=(self.key_id, self.key_secret))
            self._dry_run = False

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def execute(
        self,
        transaction: dict,
        archetype: str,
        action: str,
        audit_id: int,
    ) -> dict:
        """
        Execute the approved recovery action.
        Returns execution result dict for the audit trail.
        """
        amount_paise = transaction.get("amount_paise", 0)

        # ── Validate amount
        assert isinstance(amount_paise, int), "Amount must be integer paise"
        assert amount_paise >= RAZORPAY_MIN_AMOUNT_PAISE, f"Amount {amount_paise} below minimum"

        # ── Route to correct action handler
        handlers = {
            "defer_to_payday_window":           self._defer,
            "offer_alternative_payment_method": self._create_payment_link,
            "silent_auto_retry":                self._silent_defer,
            "gentle_friction_reducer":          self._create_payment_link,
            "defer_to_limit_reset_or_split":    self._defer,
            "trigger_re_consent_flow":          self._create_payment_link,
            "reconstruct_and_warm_reengage":    self._create_payment_link,
            "hold_and_escalate":                self._escalate,
            "manual_review":                    self._escalate,
        }

        handler = handlers.get(action, self._escalate)
        return handler(transaction, archetype, action, audit_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Action Handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _create_payment_link(self, txn: dict, archetype: str, action: str, audit_id: int) -> dict:
        """Create a Razorpay Payment Link and return the short URL."""
        amount_paise = txn["amount_paise"]
        customer = txn.get("buyer", {})
        notes = self._build_notes(txn, archetype, action, audit_id)

        payload = {
            "amount": amount_paise,
            "currency": RAZORPAY_CURRENCY,
            "description": f"LAZARUS Recovery — {archetype.replace('_', ' ').title()}",
            "customer": {
                "name": customer.get("customer_id", "Customer"),
                "email": f"{customer.get('customer_id', 'cust').lower()}@example.com",
            },
            "notes": notes,
            "expire_by": int((datetime.now() + timedelta(seconds=RAZORPAY_PAYMENT_LINK_EXPIRE_SECONDS)).timestamp()),
            "reminder_enable": False,  # LAZARUS controls its own reminders
        }

        if self._dry_run:
            return {
                "resource_id": f"plink_DRY_{audit_id:04d}",
                "resource_type": "payment_link",
                "short_url": f"https://rzp.io/dry/{audit_id:04d}",
                "executed_at": datetime.now().isoformat(),
                "notes": notes,
                "dry_run": True,
            }

        try:
            response = self._client.payment_link.create(payload)
            return {
                "resource_id": response["id"],
                "resource_type": "payment_link",
                "short_url": response.get("short_url"),
                "executed_at": datetime.now().isoformat(),
                "notes": notes,
                "dry_run": False,
            }
        except Exception as e:
            return {
                "resource_id": None,
                "resource_type": "payment_link",
                "error": str(e),
                "executed_at": datetime.now().isoformat(),
                "notes": notes,
                "dry_run": False,
            }

    def _defer(self, txn: dict, archetype: str, action: str, audit_id: int) -> dict:
        """Log a deferred action — no API call, scheduled for later."""
        from config import ARCHETYPES
        cfg = ARCHETYPES.get(archetype, {})
        defer_days = cfg.get("defer_days", 0)
        defer_hours = cfg.get("defer_hours", 0)
        defer_until = (datetime.now() + timedelta(days=defer_days, hours=defer_hours)).isoformat()
        notes = self._build_notes(txn, archetype, action, audit_id)
        return {
            "resource_id": f"DEFER_{audit_id:04d}",
            "resource_type": "deferred_action",
            "defer_until": defer_until,
            "executed_at": datetime.now().isoformat(),
            "notes": notes,
            "dry_run": self._dry_run,
        }

    def _silent_defer(self, txn: dict, archetype: str, action: str, audit_id: int) -> dict:
        """Silent 15-minute retry — no customer contact."""
        from config import COMPLIANCE_RULES
        defer_until = (datetime.now() + timedelta(
            minutes=COMPLIANCE_RULES["dropped_signal_retry_minutes"]
        )).isoformat()
        notes = self._build_notes(txn, archetype, action, audit_id)
        return {
            "resource_id": f"SILENT_{audit_id:04d}",
            "resource_type": "silent_retry",
            "defer_until": defer_until,
            "executed_at": datetime.now().isoformat(),
            "notes": notes,
            "dry_run": self._dry_run,
        }

    def _escalate(self, txn: dict, archetype: str, action: str, audit_id: int) -> dict:
        """Escalate to merchant — no customer contact, no retry."""
        notes = self._build_notes(txn, archetype, action, audit_id)
        return {
            "resource_id": f"ESC_{audit_id:04d}",
            "resource_type": "merchant_escalation",
            "escalation_reason": archetype,
            "executed_at": datetime.now().isoformat(),
            "notes": notes,
            "dry_run": self._dry_run,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Notes Builder — strictly within Razorpay API limits
    # ─────────────────────────────────────────────────────────────────────────

    def _build_notes(self, txn: dict, archetype: str, action: str, audit_id: int) -> dict:
        """
        Build Razorpay-compliant notes object.
        Max 15 key-value pairs. Max 256 chars per value.
        """
        def trim(val: str) -> str:
            return str(val)[:RAZORPAY_NOTES_MAX_VALUE_LEN]

        notes = {
            "lazarus_audit_id":   trim(str(audit_id)),
            "archetype":          trim(archetype),
            "action":             trim(action),
            "policy_version":     trim(POLICY_VERSION),
            "original_txn_id":    trim(txn.get("txn_id", "")),
            "failure_code":       trim(txn.get("failure_code", "")),
        }
        assert len(notes) <= RAZORPAY_NOTES_MAX_KEYS, "Notes exceed Razorpay 15-key limit"
        return notes
