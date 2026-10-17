import json
from pathlib import Path

LOG = Path("logs/audit.jsonl")
OUT = Path("evidence/tx_hashes.md")

rows = []
for line in LOG.read_text(encoding="utf-8").splitlines():
    rec = json.loads(line)
    if rec.get("event") != "tool_result" or rec.get("tool") != "send_eth":
        continue
    result = rec.get("result", {})
    tx = str(result.get("tx", ""))
    if result.get("status") == "sent" and tx.startswith("0x"):
        rows.append((rec["time"], result["amount_eth"], result["to"], tx))

out = [
    "# On-chain transactions (Sepolia testnet)",
    "",
    "| Time | Amount (ETH) | To | Transaction |",
    "|---|---|---|---|",
]
for t, amount, to, tx in rows:
    out.append(
        f"| {t} | {amount} | {to} | [{tx[:12]}...](https://sepolia.etherscan.io/tx/{tx}) |"
    )

OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
print(f"\n{len(rows)} on-chain transaction(s) saved to {OUT}")