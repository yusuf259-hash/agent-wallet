import os
from dotenv import load_dotenv
from adapters.chain import ChainAdapter
from executor import AuditLog, ToolExecutor
from policy import LIMITED_AUTO, PolicyEngine

load_dotenv()

recipient = os.environ["RECIPIENT"]
stranger = "0x" + "c3" * 20

adapter = ChainAdapter()
policy = PolicyEngine.from_env(tier=LIMITED_AUTO)
audit = AuditLog("logs/audit.jsonl")
executor = ToolExecutor(adapter, policy, audit=audit)

print("=== 1. PORTFOLIO & GAS HEALTH CHECK (SEPOLIA) ===")
portfolio = executor.run("get_portfolio_status", {})
print(portfolio)

print("\n=== 2. PREFLIGHT DRY RUN SIMULATION ===")
sim = executor.run("simulate_transfer", {"to": recipient, "amount_eth": 0.0005})
print(sim)

print("\n=== 3. AUTO APPROVED SMALL PAYMENT (0.0005 ETH) ===")
tx1 = executor.run("send_eth", {"to": recipient, "amount_eth": 0.0005})
print(tx1)
if tx1.get("tx"):
    print("Etherscan:", "https://sepolia.etherscan.io/tx/" + tx1["tx"])

print("\n=== 4. HUMAN APPROVED MEDIUM PAYMENT (0.0022 ETH) ===")
print("When prompted below, type: yes")
tx2 = executor.run("send_eth", {"to": recipient, "amount_eth": 0.0022})
print(tx2)
if tx2.get("tx"):
    print("Etherscan:", "https://sepolia.etherscan.io/tx/" + tx2["tx"])

print("\n=== 5. BLOCKED OVER LIMIT ATTACK (0.5 ETH) ===")
denied1 = executor.run("send_eth", {"to": recipient, "amount_eth": 0.5})
print(denied1)

print("\n=== 6. BLOCKED UNAPPROVED RECIPIENT ATTACK ===")
denied2 = executor.run("send_eth", {"to": stranger, "amount_eth": 0.0005})
print(denied2)

print("\n=== 7. FINAL PORTFOLIO STATUS ===")
print(executor.run("get_portfolio_status", {}))