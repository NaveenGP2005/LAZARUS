"""
LAZARUS — core/strategist.py
The Strategist: Gemini Flash generates a cause-specific recovery playbook.
LLM has ZERO authority to execute. Output is advisory only.
The compliance gate and executor own all financial actions.
"""

import os
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ARCHETYPES

try:
    import google.generativeai as genai
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False


# Fallback playbooks — used when Gemini is unavailable or API key not set
# These are deterministic, domain-expert-defined playbooks per archetype
FALLBACK_PLAYBOOKS = {
    "empty_vault": {
        "chosen_action": "defer_to_payday_window",
        "reasoning": "Insufficient funds indicates a temporary liquidity issue. Retrying immediately will fail again. The optimal window is 3–5 days after failure to align with typical Indian salary credit cycles (1st or last working day of month). A single, non-aggressive reminder 1 day before retry is the maximum contact.",
        "customer_message_hint": "Your payment of ₹{amount} didn't go through. We'll try again in a few days — no action needed from you.",
        "risk": "low",
    },
    "frozen_gate": {
        "chosen_action": "offer_alternative_payment_method",
        "reasoning": "Account block or KYC lock means the specific payment instrument is unusable — retrying it will always fail. The correct action is to offer a different payment method (UPI if card is blocked, or vice versa) via a fresh payment link.",
        "customer_message_hint": "There's an issue with your {method}. We've sent you a new payment link to complete your purchase using a different method.",
        "risk": "low",
    },
    "dropped_signal": {
        "chosen_action": "silent_auto_retry",
        "reasoning": "Network timeout or PSP unavailability is transient. The bank was never reached — the buyer has no awareness of failure. A silent retry in 15 minutes resolves ~90% of these cases. Customer contact is counterproductive and creates unnecessary alarm.",
        "customer_message_hint": None,
        "risk": "none",
    },
    "hesitant_hand": {
        "chosen_action": "gentle_friction_reducer",
        "reasoning": "One user cancellation or single PIN error suggests hesitation, not intent to abandon. Aggressive follow-up will complete the abandonment. A trust-building touchpoint (review highlights, clear return policy, 2-hour delay) recovers a meaningful fraction of these buyers.",
        "customer_message_hint": "Still thinking about your order? Here's what other customers say: {trust_signal}. Your cart is saved.",
        "risk": "low",
    },
    "limit_breaker": {
        "chosen_action": "defer_to_limit_reset_or_split",
        "reasoning": "Daily or per-transaction limit is a hard administrative constraint. Options: (1) defer to midnight when daily limits reset, or (2) offer payment splitting if the merchant supports it. The buyer has funds — the constraint is the bank's policy, not the buyer's intent.",
        "customer_message_hint": "Your bank's daily limit was reached. Your payment link will be automatically resent at midnight when your limit resets.",
        "risk": "none",
    },
    "expired_mandate": {
        "chosen_action": "trigger_re_consent_flow",
        "reasoning": "A revoked or expired mandate cannot be retried — it requires a new authorization from the buyer. The correct action is to trigger a re-consent flow with a clear explanation. Do not attempt to charge the old mandate.",
        "customer_message_hint": "Your {subscription_name} mandate needs to be renewed. Tap to re-authorize in 30 seconds.",
        "risk": "low",
    },
    "ghost_checkout": {
        "chosen_action": "reconstruct_and_warm_reengage",
        "reasoning": "No payment was initiated — the buyer abandoned the checkout flow. The session data (if available) allows us to reconstruct the cart. A warm, personalized re-engagement within 1 hour captures buyers who left due to distraction rather than intent change.",
        "customer_message_hint": "You left something behind! Your {item} is still in your cart. Complete your purchase:",
        "risk": "low",
    },
    "velocity_trap": {
        "chosen_action": "hold_and_escalate",
        "reasoning": "High fraud signal. Any further contact, retry, or payment link will raise the risk score further and risk a permanent block from the issuing bank. The correct action is to do nothing for 48 hours and escalate to the merchant for manual review. Revenue preservation here means avoiding a chargeback, not recovering the transaction.",
        "customer_message_hint": None,
        "risk": "high — do not contact customer",
    },
}


class Strategist:
    """
    Generates a cause-specific recovery playbook for a classified archetype.
    Uses Gemini Flash if available; falls back to deterministic expert playbooks.
    In both cases, output is advisory only — the compliance gate decides what executes.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = None
        if _GEMINI_AVAILABLE and self.api_key and self.api_key != "YOUR_GEMINI_API_KEY_HERE":
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-1.5-flash")

    def generate_playbook(self, transaction: dict, coroner_result: dict) -> dict:
        """
        Returns recovery playbook dict:
        {
            chosen_action: str,
            reasoning: str,
            customer_message_hint: str | None,
            risk: str,
            source: "gemini" | "fallback"
        }
        """
        archetype = coroner_result["archetype"]

        if self.model:
            return self._call_gemini(transaction, coroner_result, archetype)
        else:
            return self._fallback(archetype, transaction)

    def _call_gemini(self, txn: dict, coroner: dict, archetype: str) -> dict:
        """Call Gemini Flash with a structured prompt."""
        arch_cfg = ARCHETYPES[archetype]
        prompt = f"""You are LAZARUS, a payment recovery AI agent. A failed payment has been classified.

TRANSACTION:
- Amount: ₹{txn.get('amount_paise', 0) / 100:.2f}
- Payment method: {txn.get('payment_method')}
- Failure code: {txn.get('failure_code')}
- Failure time: {txn.get('failure_time')}
- First-time buyer: {txn.get('buyer', {}).get('is_first_time_buyer', False)}
- Prior failures (7d): {txn.get('buyer', {}).get('prior_failures_7d', 0)}

CORONER DIAGNOSIS:
- Archetype: {archetype} — {arch_cfg['description']}
- Confidence: {coroner['confidence']:.0%}
- Causal factors: {', '.join(coroner.get('causal_factors', []))}

ALLOWED RECOVERY ACTIONS FOR THIS ARCHETYPE:
- Primary: {arch_cfg['recovery_action']}
- Contact customer: {arch_cfg['contact_customer']}

Your task: Generate a precise recovery playbook. Be concise. The compliance gate will decide if this executes.

Respond ONLY with valid JSON in this exact format:
{{
  "chosen_action": "<action_slug>",
  "reasoning": "<2-3 sentences explaining why this specific action for this specific archetype>",
  "customer_message_hint": "<template message or null if no customer contact>",
  "risk": "<none|low|high>"
}}"""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            result["source"] = "gemini"
            return result
        except Exception as e:
            print(f"  ⚠ Gemini call failed ({e}), using fallback playbook")
            return self._fallback(archetype, txn)

    def _fallback(self, archetype: str, txn: dict) -> dict:
        """Return deterministic expert playbook."""
        playbook = dict(FALLBACK_PLAYBOOKS.get(archetype, {
            "chosen_action": "manual_review",
            "reasoning": "Unknown archetype — escalate to manual review.",
            "customer_message_hint": None,
            "risk": "unknown",
        }))
        playbook["source"] = "fallback"
        return playbook
