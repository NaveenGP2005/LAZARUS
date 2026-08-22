"""
LAZARUS — core/chargeback.py
Automated Dispute/Chargeback Defense Agent
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

try:
    import google.generativeai as genai
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False

class ChargebackAgent:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if _GEMINI_AVAILABLE and self.api_key and self.api_key != "YOUR_GEMINI_API_KEY_HERE":
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(model_name="gemini-3.5-flash-lite")
        else:
            self.model = None

    def _mock_db_lookup(self, customer_id: str) -> dict:
        """Simulates fetching proof-of-delivery and access logs from merchant DB."""
        return {
            "shipping_status": "DELIVERED",
            "tracking_id": "AWB_882910293",
            "ip_address": "103.170.245.230 (Match with billing location)",
            "digital_signature_present": True,
            "prior_successful_orders": 4
        }

    def generate_defense(self, dispute_data: dict) -> dict:
        """Generates a structured chargeback defense document."""
        if not self.model:
            return {"status": "error", "message": "Gemini API key missing. Cannot generate defense."}

        customer_id = dispute_data.get("customer_id", "CUST_UNKNOWN")
        merchant_evidence = self._mock_db_lookup(customer_id)

        prompt = f"""You are the LAZARUS Chargeback Defense Agent representing a merchant.
A customer has filed a chargeback dispute. You must review the transaction details and the merchant's internal evidence logs to generate a professional, compelling, and legally sound dispute response file to submit to the bank/payment gateway.

DISPUTE DETAILS:
- Dispute ID: {dispute_data.get('dispute_id')}
- Reason Code: {dispute_data.get('reason_code', 'Product not delivered')}
- Amount: ₹{dispute_data.get('amount_inr', 0)}

MERCHANT INTERNAL EVIDENCE LOGS:
- Shipping Status: {merchant_evidence['shipping_status']} (Tracking: {merchant_evidence['tracking_id']})
- Auth IP Address: {merchant_evidence['ip_address']}
- Digital Signature: {merchant_evidence['digital_signature_present']}
- Prior History: {merchant_evidence['prior_successful_orders']} successful orders from this IP.

Generate a comprehensive defense letter. Format the output as a clean, professional string (no markdown blocks like ```).
"""
        try:
            response = self.model.generate_content(prompt)
            defense_text = response.text.strip()
            return {
                "status": "success",
                "evidence_gathered": merchant_evidence,
                "defense_document": defense_text
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
