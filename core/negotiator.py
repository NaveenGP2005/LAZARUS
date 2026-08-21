"""
LAZARUS — core/negotiator.py
Conversational sub-agent for interactive recovery.
Helps overcome buyer hesitation and liquidity issues through dialogue.
"""
import os
from dotenv import load_dotenv
load_dotenv()

try:
    import google.generativeai as genai
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False

class NegotiatorAgent:
    def __init__(self, api_key: str | None = None, context: dict | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.context = context or {}
        
        if not _GEMINI_AVAILABLE or not self.api_key or self.api_key == "YOUR_GEMINI_API_KEY_HERE":
            self.chat = None
            return

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-3.5-flash-lite",
            system_instruction=self._build_system_prompt()
        )
        self.chat = self.model.start_chat(history=[])
        
    def _build_system_prompt(self) -> str:
        amt = self.context.get("amount_inr", 5000)
        arch = self.context.get("archetype", "hesitant_hand")
        return f"""You are the LAZARUS Negotiator, a helpful, empathetic payment recovery assistant for a merchant.
Your goal is to help the customer complete their failed payment of ₹{amt}.
The failure cause was: {arch}.

RULES:
1. Be polite, concise, and empathetic. Do not sound like a robot.
2. If the user cites a liquidity issue (e.g., "I don't have money until Friday"), offer to generate a new payment link that is valid until Saturday.
3. If the user cites a price issue, you may offer a one-time 10% discount to complete the purchase now.
4. Keep responses under 3 sentences.
5. If you reach an agreement, end your message with the exact string: [LINK_GENERATED]
"""

    def send_message(self, message: str):
        """Yields streaming response chunks."""
        if not self.chat:
            yield "Gemini API key not configured. Negotiator offline."
            return
            
        try:
            response = self.chat.send_message(message, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"System error: {e}"
