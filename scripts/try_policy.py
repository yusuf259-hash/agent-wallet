import os

from dotenv import load_dotenv

from policy import PolicyEngine

load_dotenv()
RECIPIENT = os.environ["RECIPIENT"]
STRANGER = "0x" + "c3" * 20

policy = PolicyEngine([RECIPIENT])

cases = [
    ("Small payment to approved address", RECIPIENT, 0.001),
    ("Medium payment", RECIPIENT, 0.005),
    ("Over the per-transaction limit", RECIPIENT, 0.02),
    ("Unknown address", STRANGER, 0.001),
    ("Not a real address", "hello", 0.001),
    ("Negative amount", RECIPIENT, -1),
]

for label, to, amount in cases:
    d = policy.check({"to": to, "amount_eth": amount})
    print(f"{label:36} -> {d.status:15} {d.reason}")