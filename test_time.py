from datetime import datetime
now = datetime.now()
print(f"Current time: {now.strftime('%H:%M')}")
is_quiet = now.hour >= 22 or now.hour < 8
print(f"Quiet hours active (10 PM - 8 AM): {is_quiet}")
if is_quiet:
    print("=> Compliance gate will DEFER all customer-contact actions until 8 AM.")
    print("=> Only dropped_signal (silent retry) executes right now.")
    print("=> This is CORRECT -- the agent respects quiet hours.")
else:
    print("=> All actions can execute normally.")
