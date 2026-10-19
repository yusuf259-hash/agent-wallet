import json
from pathlib import Path

log_file = Path("logs/audit.jsonl")
if not log_file.exists():
    print("No audit log found at logs/audit.jsonl")
    raise SystemExit(1)

txs = []
for line in log_file.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    record = json.loads(line)
    if record.get("event") == "tool_result" and record.get("tool") == "send_eth":
        res = record.get("result", {})
        tx_hash = str(res.get("tx", ""))
        if res.get("status") == "sent" and tx_hash.startswith("0x"):
            txs.append(
                {
                    "time": record.get("time"),
                    "amount_eth": res.get("amount_eth"),
                    "to": res.get("to"),
                    "risk_score": res.get("risk_score", 0),
                    "tx": tx_hash,
                    "url": f"https://sepolia.etherscan.io/tx/{tx_hash}",
                }
            )

print(f"Total Confirmed Sepolia Transactions Logged: {len(txs)}\n")
for i, item in enumerate(txs, 1):
    print(f"#{i} | Time: {item['time']} | Amount: {item['amount_eth']} ETH | Risk: {item['risk_score']}/100")
    print(f"   To:   {item['to']}")
    print(f"   Hash: {item['tx']}")
    print(f"   Link: {item['url']}\n")