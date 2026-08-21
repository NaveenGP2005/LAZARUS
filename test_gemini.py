"""Test Gemini connection with gemini-2.0-flash-lite model."""
from dotenv import load_dotenv
import os
load_dotenv()

import google.generativeai as genai
key = os.getenv('GEMINI_API_KEY', '')
print(f'Key loaded: {key[:15]}...')
genai.configure(api_key=key)
model = genai.GenerativeModel('gemini-3.5-flash-lite')
try:
    r = model.generate_content('You are LAZARUS. Reply with exactly: LAZARUS online, model gemini-2.0-flash-lite ready.')
    print(f'[OK] Gemini: {r.text.strip()[:100]}')
except Exception as e:
    print(f'[FAIL] {e}')
