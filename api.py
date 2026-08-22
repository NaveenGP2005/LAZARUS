"""
LAZARUS — api.py
FastAPI Live Webhook Ingestion Engine
Run: uvicorn api:app --reload --port 8000
"""

from fastapi import FastAPI, Request
import datetime
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

from agent import LazarusAgent

app = FastAPI(
    title="LAZARUS Live Webhook Engine",
    description="Accepts real-time Razorpay webhooks and runs them through the cause-aware recovery pipeline."
)
agent = LazarusAgent()

@app.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, shadow_mode: bool = False):
    """
    Ingests live payment.failed webhooks.
    """
    payload = await request.json()
    
    event_type = payload.get("event")
    if event_type != "payment.failed":
        return {"status": "ignored", "reason": f"Event type {event_type} not supported"}
        
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
    error_code = payment.get("error_code", "INTERNAL_SERVER_ERROR")
    # Some Razorpay webhooks put the error reason in different fields, let's allow a fallback
    if not error_code or error_code == "null":
         error_code = payment.get("error_reason", "INTERNAL_SERVER_ERROR")

    # Map Razorpay entity to LAZARUS transaction schema
    # In a real environment, we would query the merchant's DB for buyer context.
    # Here we mock realistic contextual defaults.
    txn = {
        "txn_id": payment.get("id", f"pay_{uuid.uuid4().hex[:16]}"),
        "idx": 0,
        "merchant_id": payment.get("merchant_id", "MRC_LIVE"),
        "amount_paise": payment.get("amount", 0),
        "amount_inr": payment.get("amount", 0) / 100,
        "currency": payment.get("currency", "INR"),
        "payment_method": payment.get("method", "upi"),
        "failure_code": error_code,
        "failure_time": datetime.datetime.now().isoformat(),
        "buyer": {
            "customer_id": payment.get("customer_id", f"CUST_{uuid.uuid4().hex[:8]}"),
            "is_first_time_buyer": False,
            "historical_txn_count": 3,
            "days_since_last_txn": 15,
            "prior_failures_7d": 0,
        },
        "subscription_id": None,
        "session_data_available": True,
        "risk_score": 0.1,  # Default safe risk score for live testing
        "retry_count": 0,
        "status": "failed",
    }
    
    # Process through LAZARUS pipeline
    # This automatically writes to the immutable SQLite audit trail.
    result = agent.process(txn, verbose=True, shadow_mode=shadow_mode)
    
    return {
        "status": "processed",
        "txn_id": txn["txn_id"],
        "lazarus_verdict": result.get("gate_verdict"),
        "archetype": result.get("archetype"),
        "outcome": result.get("outcome")
    }

@app.post("/webhook/razorpay/dispute")
async def razorpay_dispute_webhook(request: Request):
    """
    Phase 6: Automated Chargeback Defense Agent Webhook.
    Listens for chargeback.created events, gathers merchant evidence, and generates a defense file.
    """
    payload = await request.json()
    
    # In a real scenario, we verify signature here.
    dispute = payload.get("payload", {}).get("dispute", {}).get("entity", {})
    if not dispute:
        # Mock payload for testing
        dispute = payload
        
    from core.chargeback import ChargebackAgent
    agent = ChargebackAgent()
    defense_result = agent.generate_defense(dispute)
    
    return {"status": "defense_generated", "data": defense_result}

@app.post("/webhook/razorpay/payment_link_paid")
async def razorpay_payment_paid_webhook(request: Request):
    """
    Phase 6: Reinforcement Learning Feedback Loop.
    Listens for payment link success and updates the audit trail to flag the strategy as successful.
    """
    payload = await request.json()
    link_entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    notes = link_entity.get("notes", {})
    audit_id = notes.get("lazarus_audit_id")
    
    if audit_id:
        try:
            import sqlite3
            from config import DB_PATH
            with sqlite3.connect(DB_PATH) as conn:
                # We update the outcome to SUCCESS_PAID so the RL loop can prioritize this prompt.
                # Since the audit trail is immutable, we simulate a "feedback_log" insertion in production.
                # For hackathon, updating outcome is fine.
                conn.execute("UPDATE lazarus_audit SET outcome = 'SUCCESS_PAID' WHERE id = ?", (audit_id,))
                conn.commit()
            print(f"✅ RL Feedback Loop: Audit {audit_id} marked as SUCCESS_PAID.")
        except Exception as e:
            print(f"RL Error: {e}")
            
    return {"status": "rl_feedback_recorded"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting LAZARUS Webhook Engine on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
