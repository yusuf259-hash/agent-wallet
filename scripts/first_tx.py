import os
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

w3 = Web3(Web3.HTTPProvider(os.environ["RPC_URL"]))
acct = w3.eth.account.from_key(os.environ["PRIVATE_KEY"])
recipient = Web3.to_checksum_address(os.environ["RECIPIENT"])

print("From:          ", acct.address)
print("To:            ", recipient)
print("Balance before:", w3.from_wei(w3.eth.get_balance(acct.address), "ether"), "ETH")

max_fee = max(w3.eth.gas_price * 2, w3.to_wei(2, "gwei"))

tx = {
    "from": acct.address,
    "to": recipient,
    "value": w3.to_wei(0.001, "ether"),
    "nonce": w3.eth.get_transaction_count(acct.address),
    "maxFeePerGas": max_fee,
    "maxPriorityFeePerGas": w3.to_wei(1, "gwei"),
    "chainId": w3.eth.chain_id,
}
tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
print("Gas limit:     ", tx["gas"])

signed = acct.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print("Sent! Waiting for confirmation...")

receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
print("Status:        ", "SUCCESS" if receipt.status == 1 else "FAILED")
print("Transaction hash:", w3.to_hex(tx_hash))
print("View it here:  ", "https://sepolia.etherscan.io/tx/" + w3.to_hex(tx_hash))
print("Balance after: ", w3.from_wei(w3.eth.get_balance(acct.address), "ether"), "ETH")