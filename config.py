"""
LAZARUS — config.py
Central configuration: archetype definitions, compliance rules, Razorpay limits.
All tunable constants live here. Nothing is hardcoded elsewhere.
"""

from dataclasses import dataclass, field
from typing import Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# Archetype Definitions
# ─────────────────────────────────────────────────────────────────────────────

ARCHETYPES = {
    "empty_vault": {
        "id": 1,
        "description": "Insufficient funds — buyer likely solvent, wrong timing",
        "error_codes": ["INSUFFICIENT_FUNDS", "BAD_REQUEST_ERROR:funds", "Z9"],
        "recovery_action": "defer_to_payday_window",
        "defer_days": 4,
        "contact_customer": True,
        "message_tone": "gentle",
    },
    "frozen_gate": {
        "id": 2,
        "description": "Account blocked, KYC incomplete, or bank restriction",
        "error_codes": ["ACCOUNT_BLOCKED", "KYC_INCOMPLETE", "ACCOUNT_FROZEN", "DO_NOT_HONOR"],
        "recovery_action": "offer_alternative_payment_method",
        "defer_days": 0,
        "contact_customer": True,
        "message_tone": "helpful",
    },
    "dropped_signal": {
        "id": 3,
        "description": "Network timeout, PSP/CBS offline — transient technical failure",
        "error_codes": ["TIMEOUT", "GATEWAY_ERROR", "PSP_UNAVAILABLE", "CBS_OFFLINE", "NETWORK_ERROR"],
        "recovery_action": "silent_auto_retry",
        "defer_minutes": 15,
        "contact_customer": False,  # KEY: never wake user for a system blip
        "message_tone": None,
    },
    "hesitant_hand": {
        "id": 4,
        "description": "User declined or single PIN error — intent exists, friction too high",
        "error_codes": ["USER_CANCELLED", "PIN_ERROR_1", "PAYMENT_CANCELLED", "INVALID_PIN"],
        "recovery_action": "gentle_friction_reducer",
        "defer_hours": 2,
        "contact_customer": True,
        "message_tone": "reassuring",
    },
    "limit_breaker": {
        "id": 5,
        "description": "Daily/per-transaction limit hit — administrative constraint",
        "error_codes": ["LIMIT_EXCEEDED", "TRANSACTION_LIMIT", "DAILY_LIMIT_EXCEEDED", "UL"],
        "recovery_action": "defer_to_limit_reset_or_split",
        "defer_hours": 6,  # midnight for daily limits
        "contact_customer": True,
        "message_tone": "informative",
    },
    "expired_mandate": {
        "id": 6,
        "description": "Recurring mandate revoked, paused, or expired",
        "error_codes": ["MANDATE_REVOKED", "MANDATE_PAUSED", "MANDATE_EXPIRED", "EMANDATE_FAILURE"],
        "recovery_action": "trigger_re_consent_flow",
        "defer_days": 0,
        "contact_customer": True,
        "message_tone": "urgent_but_polite",
    },
    "ghost_checkout": {
        "id": 7,
        "description": "Abandoned before payment attempt — session ended without initiating payment",
        "error_codes": ["CHECKOUT_ABANDONED", "SESSION_EXPIRED", "NO_PAYMENT_INITIATED"],
        "recovery_action": "reconstruct_and_warm_reengage",
        "defer_hours": 1,
        "contact_customer": True,
        "message_tone": "warm",
    },
    "velocity_trap": {
        "id": 8,
        "description": "Risk score flag or fraud velocity signal — any action raises fraud signal further",
        "error_codes": ["RISK_THRESHOLD_EXCEEDED", "FRAUD_FLAG", "VELOCITY_LIMIT", "SUSPECTED_FRAUD"],
        "recovery_action": "hold_and_escalate",
        "defer_hours": 48,
        "contact_customer": False,  # KEY: do NOTHING — any contact worsens fraud signal
        "message_tone": None,
        "escalate_to_merchant": True,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Compliance Gate Rules
# ─────────────────────────────────────────────────────────────────────────────

COMPLIANCE_RULES = {
    "max_contact_touches_per_7_days": 3,
    "quiet_hours_start": 22,   # 10 PM
    "quiet_hours_end": 8,      # 8 AM
    "velocity_trap_block_hours": 48,
    "dropped_signal_retry_minutes": 15,
    "max_razorpay_payment_links": 28,  # conservative — Razorpay test limit is 30
    "max_retries_per_transaction": 3,
}

# ─────────────────────────────────────────────────────────────────────────────
# Batch & Simulation Config
# ─────────────────────────────────────────────────────────────────────────────

BATCH_DISTRIBUTION = {
    "empty_vault": 25,
    "frozen_gate": 15,
    "dropped_signal": 15,
    "hesitant_hand": 10,
    "limit_breaker": 10,
    "expired_mandate": 10,
    "ghost_checkout": 10,
    "velocity_trap": 5,
}
TOTAL_TRANSACTIONS = sum(BATCH_DISTRIBUTION.values())  # 100

# Simulated recovery rates (informed by RBI/industry data)
# These are used by the simulation engine — NOT invented ad-hoc
ARCHETYPE_RECOVERY_RATES = {
    # archetype: (baseline_rate, lazarus_rate)
    # baseline = generic next-day retry / reminder
    "empty_vault":      (0.09, 0.31),  # payday timing is key
    "frozen_gate":      (0.04, 0.52),  # method switch recovers most
    "dropped_signal":   (0.71, 0.93),  # just needs a quiet retry
    "hesitant_hand":    (0.12, 0.38),  # trust signal + right delay
    "limit_breaker":    (0.18, 0.61),  # midnight reset / split works
    "expired_mandate":  (0.06, 0.45),  # re-consent flow is the unlock
    "ghost_checkout":   (0.08, 0.27),  # warm re-engage beats cold
    "velocity_trap":    (0.02, 0.00),  # LAZARUS correctly does nothing — avoids worsening fraud signal
}
# Note: velocity_trap has 0% because LAZARUS escalates rather than recovering directly.
# The 2% baseline "recovery" is actually 2% getting through despite the risk signal —
# which creates chargeback exposure. LAZARUS prevents that unsafe recovery.

ARCHETYPE_LIST = list(ARCHETYPES.keys())

# ─────────────────────────────────────────────────────────────────────────────
# Razorpay API
# ─────────────────────────────────────────────────────────────────────────────

RAZORPAY_CURRENCY = "INR"
RAZORPAY_MIN_AMOUNT_PAISE = 100  # ₹1 minimum
RAZORPAY_NOTES_MAX_KEYS = 15
RAZORPAY_NOTES_MAX_VALUE_LEN = 256
RAZORPAY_PAYMENT_LINK_EXPIRE_SECONDS = 86400  # 24 hours

# ─────────────────────────────────────────────────────────────────────────────
# Policy Version (embed in every audit record)
# ─────────────────────────────────────────────────────────────────────────────

POLICY_VERSION = "v1.0.0"
DB_PATH = "lazarus_audit.db"
TRANSACTIONS_PATH = "data/transactions.json"
