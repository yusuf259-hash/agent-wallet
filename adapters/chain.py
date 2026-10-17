import os
from decimal import Decimal

from dotenv import load_dotenv
from web3 import Web3

from adapters.base import ExecutionAdapter


class ChainAdapter(ExecutionAdapter):
    name = "sepolia"

    def __init__(self):
        load_dotenv()
        self.w3 = Web3(Web3.HTTPProvider(os.environ["RPC_URL"]))
        self.account = self.w3.eth.account.from_key(os.environ["PRIVATE_KEY"])
        self.agent_address = self.account.address

    def get_balance(self, address=None):
        addr = Web3.to_checksum_address(address or self.agent_address)
        return float(self.w3.from_wei(self.w3.eth.get_balance(addr), "ether"))

    def transfer(self, to, amount_eth):
        w3 = self.w3
        to = Web3.to_checksum_address(to)
        max_fee = max(w3.eth.gas_price * 2, w3.to_wei(2, "gwei"))

        tx = {
            "from": self.agent_address,
            "to": to,
            "value": w3.to_wei(Decimal(str(amount_eth)), "ether"),
            "nonce": w3.eth.get_transaction_count(self.agent_address),
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": w3.to_wei(1, "gwei"),
            "chainId": w3.eth.chain_id,
        }
        # Ask the network how much gas it needs, then add a 20% safety margin.
        tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)

        signed = self.account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

        if receipt.status != 1:
            raise RuntimeError("Transaction failed on chain: " + w3.to_hex(tx_hash))
        return w3.to_hex(tx_hash)