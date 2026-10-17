import os

from dotenv import load_dotenv

from adapters.chain import ChainAdapter

load_dotenv()
adapter = ChainAdapter()
recipient = os.environ["RECIPIENT"]

print("Balance before:", adapter.get_balance())
tx = adapter.transfer(recipient, 0.0005)
print("Transaction hash:", tx)
print("Balance after: ", adapter.get_balance())
print("View it here: https://sepolia.etherscan.io/tx/" + tx)