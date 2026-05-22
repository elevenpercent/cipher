"""
Sound alert — plays a beep sequence to get the user's attention.
Usage: python scripts/alert.py [message]
       python scripts/alert.py "Done! Reinstall cipher."
"""
import sys
import time

message = sys.argv[1] if len(sys.argv) > 1 else "Cipher: action needed"

# Print to terminal in case they glance
print(f"\n{'='*60}")
print(f"  CIPHER ALERT: {message}")
print(f"{'='*60}\n")

# Play a distinctive alert pattern using winsound
try:
    import winsound
    # Three ascending beeps — hard to miss
    for freq, dur in [(600, 200), (800, 200), (1000, 400)]:
        winsound.Beep(freq, dur)
        time.sleep(0.05)
    time.sleep(0.3)
    # Repeat once more
    for freq, dur in [(600, 200), (800, 200), (1000, 400)]:
        winsound.Beep(freq, dur)
        time.sleep(0.05)
except Exception:
    # Fallback: system bell via print
    print("\a\a\a")
