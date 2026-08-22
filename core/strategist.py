"""
LAZARUS — core/strategist.py
The Strategist: Gemini Flash generates a cause-specific recovery playbook.
LLM has ZERO authority to execute. Output is advisory only.
The compliance gate and executor own all financial actions.
"""

import os
import json
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ARCHETYPES

try:
    from pydantic import BaseModel, field_validator
    _PYDANTIC_AVAILABLE = True
except ImportError:
    _PYDANTIC_AVAILABLE = False

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


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schema — validates Gemini output before it enters the pipeline
# ─────────────────────────────────────────────────────────────────────────────

if _PYDANTIC_AVAILABLE:
    class StrategyPlaybook(BaseModel):
        chosen_action: str
        reasoning: str
        customer_message_hint: str | None = None
        risk: str = "medium"
        source: str = "gemini"
        strategy_variant: str = "standard"

        @field_validator("risk")
        @classmethod
        def validate_risk(cls, v: str) -> str:
            allowed = {"none", "low", "medium", "high", "high — do not contact customer"}
            return v if v in allowed else "medium"

        @field_validator("chosen_action")
        @classmethod
        def validate_action(cls, v: str) -> str:
            # Strip any LLM hallucination whitespace
            return v.strip().lower().replace(" ", "_")


# Archetypes where action is 100% deterministic — calling Gemini wastes 4s per txn
# dropped_signal: always silent_auto_retry. velocity_trap: always hold_and_escalate.
GEMINI_SKIP_ARCHETYPES = {"dropped_signal", "velocity_trap"}


class Strategist:
    """
    Generates a cause-specific recovery playbook for a classified archetype.
    Uses Gemini Flash if available; falls back to deterministic expert playbooks.
    Gemini is skipped for deterministic archetypes to save API quota and time.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = None
        if _GEMINI_AVAILABLE and self.api_key and self.api_key != "YOUR_GEMINI_API_KEY_HERE":
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-3.5-flash-lite")

    def _select_strategy_variant(self, archetype: str, risk_score: float) -> str:
        """
        Contextual UCB (Upper Confidence Bound) Bandit:
        Finds the mathematically optimal prompt variant by balancing 
        exploitation (what has worked) with exploration (what hasn't been tried),
        contextualized by the specific buyer's risk tier.
        """
        import random
        import sqlite3
        import math
        from config import DB_PATH
        
        VARIANTS = ["assertive_reminder", "empathetic_discount", "urgency_deadline", "neutral_informational"]
        risk_tier = "LOW" if risk_score < 0.5 else "HIGH"
        
        try:
            with sqlite3.connect(DB_PATH) as conn:
                rows = conn.execute("""
                    SELECT strategy_variant, COUNT(*) as tries, 
                           SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END) as successes
                    FROM lazarus_audit
                    WHERE archetype = ? AND (CASE WHEN buyer_risk_score < 0.5 THEN 'LOW' ELSE 'HIGH' END) = ? 
                          AND strategy_variant IS NOT NULL
                    GROUP BY strategy_variant
                """, (archetype, risk_tier)).fetchall()
                
                if not rows:
                    return random.choice(VARIANTS)
                    
                total_tries = sum(r[1] for r in rows)
                tested_variants = {r[0]: (r[1], r[2]) for r in rows}
                
                # Pure Exploration: Force test any variant that hasn't been tested yet for this context
                for v in VARIANTS:
                    if v not in tested_variants:
                        return v
                        
                # UCB Calculation
                best_variant, best_ucb = None, -1
                for v, (tries, successes) in tested_variants.items():
                    if v not in VARIANTS: continue # Ignore legacy variants
                    avg_success = successes / tries
                    exploration_factor = math.sqrt(2 * math.log(total_tries) / tries)
                    ucb = avg_success + exploration_factor
                    if ucb > best_ucb:
                        best_ucb = ucb
                        best_variant = v
                        
                return best_variant or random.choice(VARIANTS)
        except Exception:
            return random.choice(VARIANTS)

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

        # Skip Gemini for deterministic archetypes — action is always the same
        if not self.model or archetype in GEMINI_SKIP_ARCHETYPES:
            return self._fallback(archetype, transaction)

        return self._call_gemini(transaction, coroner_result, archetype)

    def generate_playbook_stream(self, transaction: dict, coroner_result: dict):
        """
        Streaming generator version for sandbox live demo.
        Yields (chunk_text: str, final_playbook: dict | None) tuples.
        chunk_text is a raw Gemini token; final_playbook is set on the last yield.
        """
        archetype = coroner_result["archetype"]

        if not self.model or archetype in GEMINI_SKIP_ARCHETYPES:
            playbook = self._fallback(archetype, transaction)
            yield "", playbook
            return

        arch_cfg = ARCHETYPES[archetype]
        variant = self._select_strategy_variant(archetype, transaction.get('risk_score', 0.0))
        
        safe_txn = self._mask_pii(transaction)
        
        prompt = f"""You are LAZARUS, a payment recovery AI. Analyze this failed payment and respond ONLY with valid JSON.

TRANSACTION: ₹{safe_txn.get('amount_paise',0)/100:.2f} | {safe_txn.get('payment_method')} | {safe_txn.get('failure_code')}
ARCHETYPE: {archetype} — {arch_cfg['description']}
CAUSAL FACTORS: {', '.join(coroner_result.get('causal_factors', []))}
STRATEGY VARIANT: Adopt a "{variant}" tone/approach for the customer_message_hint.

Respond ONLY with this JSON (no markdown fences):
{{"chosen_action":"{arch_cfg['recovery_action']}","reasoning":"<2-3 sentences>","customer_message_hint":"<template>","risk":"<low|medium>","strategy_variant":"{variant}"}}"""

        full_text = ""
        try:
            stream = self.model.generate_content_stream(prompt)
            for chunk in stream:
                if hasattr(chunk, "text") and chunk.text:
                    full_text += chunk.text
                    yield chunk.text, None

            text = full_text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            raw = json.loads(text)
            raw["source"] = "gemini_stream"
            if _PYDANTIC_AVAILABLE:
                playbook = StrategyPlaybook(**raw).model_dump()
            else:
                playbook = raw
            yield "", playbook

        except Exception as e:
            err_msg = str(e).encode('ascii', 'ignore').decode('ascii')
            print(f"  [!] Stream failed ({err_msg}), using fallback")
            yield "", self._fallback(archetype, transaction)
    def _mask_pii(self, txn: dict) -> dict:
        """SOC2 Compliance: Redacts sensitive PII before passing to LLM."""
        masked = txn.copy()
        if "buyer" in masked:
            buyer = masked["buyer"].copy()
            if "customer_id" in buyer:
                buyer["customer_id"] = "[REDACTED_USER_HASH]"
            if "email" in buyer:
                buyer["email"] = "[REDACTED_EMAIL]"
            masked["buyer"] = buyer
        return masked

    def _get_rl_success_examples(self, archetype: str) -> str:
        """Fetches past successful prompts for this archetype to simulate RL Few-Shot learning."""
        try:
            import sqlite3
            from config import DB_PATH
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT proposed_action FROM lazarus_audit WHERE archetype = ? AND outcome = 'SUCCESS_PAID' LIMIT 2", (archetype,))
                rows = cursor.fetchall()
                if not rows:
                    return "No prior RL data available."
                return "Past Successful Approaches (Use these as inspiration):\\n- " + "\\n- ".join([r[0] for r in rows])
        except Exception:
            return "No prior RL data available."

    def _call_gemini(self, txn: dict, coroner: dict, archetype: str) -> dict:
        """Call Gemini Flash with a structured prompt."""
        arch_cfg = ARCHETYPES[archetype]
        variant = self._select_strategy_variant(archetype, txn.get('risk_score', 0.0))
        
        # Security: Redact PII
        safe_txn = self._mask_pii(txn)
        print("       ↳ [SOC2] PII Redacted for LLM Inference")
        
        # RL Feedback loop
        rl_context = self._get_rl_success_examples(archetype)
        
        prompt = f"""You are LAZARUS, an expert payment recovery strategist.

TRANSACTION CONTEXT:
- Amount: ₹{safe_txn.get('amount_paise', 0) / 100:.2f}
- Method: {safe_txn.get('payment_method')}
- Error Code: {safe_txn.get('failure_code')}
- Failure time: {safe_txn.get('failure_time')}
- First-time buyer: {safe_txn.get('buyer', {}).get('is_first_time_buyer', False)}
- Prior failures (7d): {safe_txn.get('buyer', {}).get('prior_failures_7d', 0)}

CORONER DIAGNOSIS:
- Archetype: {archetype} — {arch_cfg['description']}
- Confidence: {coroner['confidence']:.0%}
- Causal factors: {', '.join(coroner.get('causal_factors', []))}

ALLOWED RECOVERY ACTIONS FOR THIS ARCHETYPE:
- Primary: {arch_cfg['recovery_action']}
{'- Autonomous Liquidity Bridge (offer_installment_bridge)' if archetype == 'empty_vault' and txn.get('risk_score', 0.0) < 0.6 else ''}
- Contact customer: {arch_cfg['contact_customer']}

STRATEGY INSTRUCTION:
Adopt a "{variant}" tone/approach for the customer_message_hint. If offering a Liquidity Bridge, suggest paying 25% today and 75% later.

RL FEEDBACK MEMORY:
{rl_context}

Your task: Generate a precise recovery playbook. Be concise. The compliance gate will decide if this executes.

Respond ONLY with valid JSON in this exact format:
{{
  "chosen_action": "<action_slug>",
  "reasoning": "<2-3 sentences explaining why this specific action for this specific archetype>",
  "customer_message_hint": "<template message or null if no customer contact>",
  "risk": "<none|low|high>",
  "strategy_variant": "{variant}"
}}"""

        try:
            time.sleep(4)  # respect free tier 15 RPM limit (60s / 15 = 4s per call)
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            raw = json.loads(text.strip())
            raw["source"] = "gemini"

            # Validate with Pydantic if available
            if _PYDANTIC_AVAILABLE:
                playbook = StrategyPlaybook(**raw)
                return playbook.model_dump()
            return raw

        except Exception as e:
            err_msg = str(e).encode('ascii', 'ignore').decode('ascii')
            print(f"  [!] Gemini call failed ({err_msg}), using fallback playbook")
            return self._fallback(archetype, txn)

    def _fallback(self, archetype: str, txn: dict) -> dict:
        """Return deterministic expert playbook."""
        playbook = dict(FALLBACK_PLAYBOOKS.get(archetype, {
            "chosen_action": "manual_review",
            "reasoning": "Unknown archetype — escalate to manual review.",
            "customer_message_hint": None,
            "risk": "medium",
        }))
        playbook["source"] = "fallback"
        playbook["strategy_variant"] = "standard"
        return playbook
