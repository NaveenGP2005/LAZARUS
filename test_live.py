"""Quick test: create one real Razorpay payment link in test mode"""
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
load_dotenv()

import razorpay
client = razorpay.Client(auth=(os.getenv('RAZORPAY_KEY_ID'), os.getenv('RAZORPAY_KEY_SECRET')))

payload = {
    'amount': 518700,
    'currency': 'INR',
    'description': 'LAZARUS Recovery Test -- ghost_checkout archetype',
    'customer': {'name': 'Test Buyer', 'email': 'test@example.com'},
    'notes': {
        'lazarus_audit_id': '1',
        'archetype': 'ghost_checkout',
        'action': 'reconstruct_and_warm_reengage',
        'policy_version': 'v1.0.0',
        'original_txn_id': 'pay_e0db52685e394c01',
        'failure_code': 'NO_PAYMENT_INITIATED',
    },
    'expire_by': int((datetime.now() + timedelta(hours=24)).timestamp()),
    'reminder_enable': False,
}

try:
    resp = client.payment_link.create(payload)
    link_id = resp['id']
    short_url = resp.get('short_url', 'N/A')
    amount = resp['amount'] / 100
    status = resp['status']
    print('[OK] Real Razorpay payment link created!')
    print(f'  ID:        {link_id}')
    print(f'  Short URL: {short_url}')
    print(f'  Amount:    Rs.{amount:.2f}')
    print(f'  Status:    {status}')
except Exception as e:
    print(f'[FAIL] {e}')
