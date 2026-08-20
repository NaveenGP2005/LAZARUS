"""
LAZARUS — core/audit.py
Immutable append-only SQLite audit trail.
Every decision, action, and outcome is permanently recorded.
No UPDATE or DELETE operations — ever.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH, POLICY_VERSION


class AuditTrail:
    """
    Append-only SQLite ledger. Schema is fixed at creation time.
    All writes go through log_decision() — the only write method.
    """

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS lazarus_audit (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        policy_version          TEXT    NOT NULL,
        logged_at               TEXT    NOT NULL,

        -- Transaction identity
        txn_id                  TEXT    NOT NULL,
        merchant_id             TEXT,
        amount_paise            INTEGER,
        payment_method          TEXT,
        failure_code            TEXT,
        failure_time            TEXT,

        -- Coroner output
        archetype               TEXT    NOT NULL,
        archetype_confidence    REAL    NOT NULL,
        classification_method   TEXT,
        causal_factors          TEXT,   -- JSON array

        -- Strategist output
        prescribed_action       TEXT,
        strategist_reasoning    TEXT,

        -- Compliance gate output
        gate_verdict            TEXT    NOT NULL,
        gate_reason             TEXT    NOT NULL,
        gate_defer_until        TEXT,

        -- Execution output
        razorpay_resource_id    TEXT,
        razorpay_resource_type  TEXT,
        action_executed_at      TEXT,

        -- Outcome (filled in after recovery attempt)
        outcome                 TEXT,   -- SUCCESS / FAILURE / PENDING / DEFERRED / BLOCKED
        recovered_amount_paise  INTEGER DEFAULT 0,
        recovery_notes          TEXT,   -- JSON — compact Razorpay notes payload

        -- Counterfactual (filled in during batch evaluation)
        cf_baseline_action      TEXT,
        cf_baseline_outcome_prob REAL,
        cf_lazarus_outcome_prob  REAL,
        cf_estimated_lift        REAL
    );
    """

    # Prevent any UPDATE or DELETE by using a check trigger
    GUARD_TRIGGER_SQL = """
    CREATE TRIGGER IF NOT EXISTS prevent_audit_tampering
    BEFORE UPDATE ON lazarus_audit
    BEGIN
        SELECT RAISE(ABORT, 'LAZARUS: audit trail is append-only. UPDATE is forbidden.');
    END;
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(self.CREATE_TABLE_SQL)
            conn.execute(self.GUARD_TRIGGER_SQL)
            conn.commit()

    def log_decision(
        self,
        transaction: dict,
        coroner_result: dict,
        strategist_result: dict | None,
        gate_decision,          # ComplianceDecision object
        execution_result: dict | None = None,
        outcome: str = "PENDING",
        recovered_amount_paise: int = 0,
        counterfactual: dict | None = None,
    ) -> int:
        """
        Write one immutable record to the audit trail.
        Returns the row ID.
        """
        now = datetime.now().isoformat()
        buyer = transaction.get("buyer", {})
        execution_result = execution_result or {}
        counterfactual = counterfactual or {}

        record = {
            "policy_version":           POLICY_VERSION,
            "logged_at":                now,
            "txn_id":                   transaction.get("txn_id"),
            "merchant_id":              transaction.get("merchant_id"),
            "amount_paise":             transaction.get("amount_paise"),
            "payment_method":           transaction.get("payment_method"),
            "failure_code":             transaction.get("failure_code"),
            "failure_time":             transaction.get("failure_time"),
            "archetype":                coroner_result["archetype"],
            "archetype_confidence":     coroner_result["confidence"],
            "classification_method":    coroner_result.get("method"),
            "causal_factors":           json.dumps(coroner_result.get("causal_factors", [])),
            "prescribed_action":        (strategist_result or {}).get("chosen_action"),
            "strategist_reasoning":     (strategist_result or {}).get("reasoning"),
            "gate_verdict":             gate_decision.verdict,
            "gate_reason":              gate_decision.reason,
            "gate_defer_until":         gate_decision.defer_until,
            "razorpay_resource_id":     execution_result.get("resource_id"),
            "razorpay_resource_type":   execution_result.get("resource_type"),
            "action_executed_at":       execution_result.get("executed_at"),
            "outcome":                  outcome,
            "recovered_amount_paise":   recovered_amount_paise,
            "recovery_notes":           json.dumps(execution_result.get("notes", {})),
            "cf_baseline_action":       counterfactual.get("baseline_action"),
            "cf_baseline_outcome_prob": counterfactual.get("baseline_prob"),
            "cf_lazarus_outcome_prob":  counterfactual.get("lazarus_prob"),
            "cf_estimated_lift":        counterfactual.get("estimated_lift"),
        }

        cols = ", ".join(record.keys())
        placeholders = ", ".join("?" for _ in record)
        sql = f"INSERT INTO lazarus_audit ({cols}) VALUES ({placeholders})"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(sql, list(record.values()))
            conn.commit()
            return cursor.lastrowid

    def get_all(self) -> list[dict]:
        """Fetch all audit records as a list of dicts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM lazarus_audit ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def get_summary(self) -> dict:
        """Return aggregate statistics for the dashboard."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END) as recovered,
                    SUM(CASE WHEN outcome = 'BLOCKED' THEN 1 ELSE 0 END) as blocked,
                    SUM(CASE WHEN outcome = 'DEFERRED' THEN 1 ELSE 0 END) as deferred,
                    SUM(recovered_amount_paise) as total_recovered_paise,
                    AVG(archetype_confidence) as avg_confidence,
                    SUM(CASE WHEN gate_verdict = 'ALLOW' THEN 1 ELSE 0 END) as gate_allowed,
                    SUM(CASE WHEN gate_verdict = 'BLOCK' THEN 1 ELSE 0 END) as gate_blocked,
                    SUM(CASE WHEN gate_verdict = 'DEFER' THEN 1 ELSE 0 END) as gate_deferred
                FROM lazarus_audit
            """).fetchone()
            return dict(rows)
