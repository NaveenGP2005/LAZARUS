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

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _VADER_AVAILABLE = True
except ImportError:
    _VADER_AVAILABLE = False

class NegotiatorAgent:
    def __init__(self, api_key: str | None = None, context: dict | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.context = context or {}
        
        if not _GEMINI_AVAILABLE or not self.api_key or self.api_key == "YOUR_GEMINI_API_KEY_HERE":
            self.chat = None
            return

        self.analyzer = SentimentIntensityAnalyzer() if _VADER_AVAILABLE else None

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-3.5-flash-lite",
            system_instruction=self._build_system_prompt()
        )
        self.chat = self.model.start_chat(history=[])
        
    def _build_system_prompt(self) -> str:
        amt = self.context.get("amount_inr", 5000)
        arch = self.context.get("archetype", "hesitant_hand")
        mode = self.context.get("mode", "chat")
        
        base_prompt = f"""You are the LAZARUS Negotiator, a helpful, empathetic payment recovery assistant for a merchant.
Your goal is to help the customer complete their failed payment of ₹{amt}.
The failure cause was: {arch}.

RULES:
1. Be polite, concise, and empathetic. Do not sound like a robot.
2. If the user cites a liquidity issue (e.g., "I don't have money until Friday"), you have authorization to offer an Autonomous Liquidity Bridge: "Pay 25% today to keep your service active, and the rest next week".
3. If the user cites a price issue, you may offer a one-time 10% discount to complete the purchase now.
4. Keep responses under 3 sentences.
5. If you reach an agreement on the Liquidity Bridge (25% today), end your message with the exact string: [BRIDGE_CREATED_25_75]
6. If you reach a standard agreement (full amount), end your message with: [LINK_GENERATED]
"""
        if mode == "voice":
            base_prompt += """
7. [VOICE MODE]: You are simulating a live phone call via Vapi.ai. Format your response exactly like a phone call transcript. 
Start your response with: `📞 [LAZARUS Voice AI]: ` 
Speak conversationally, with natural pauses, as if you are on the phone.
"""
        return base_prompt

    def send_message(self, message: str):
        """Yields streaming response chunks."""
        if not self.chat:
            yield "Gemini API key not configured. Negotiator offline."
            return
            
        # Sentiment-Aware Routing (Neuro-Symbolic Hybrid)
        internal_message = message
        if self.analyzer:
            scores = self.analyzer.polarity_scores(message)
            compound = scores['compound']
            
            if compound <= -0.3:
                directive = "[SYSTEM DIRECTIVE: User sentiment is NEGATIVE. Apologize profusely, do not argue, and immediately authorize a 20% discount to salvage the relationship.]"
            elif compound >= 0.3:
                directive = "[SYSTEM DIRECTIVE: User sentiment is POSITIVE. Be warm, enthusiastic, and quickly finalize the payment link without offering unnecessary discounts.]"
            else:
                directive = "[SYSTEM DIRECTIVE: User sentiment is NEUTRAL. Proceed with standard negotiation.]"
                
            internal_message = f"{directive}\n\nUSER MESSAGE: {message}"
            
        try:
            response = self.chat.send_message(internal_message, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"System error: {e}"
