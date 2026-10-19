import json
import os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from adapters import get_adapter
from agent import chat_turn
from executor import AuditLog, ToolExecutor
from policy import APPROVE_ALL, LIMITED_AUTO, READ_ONLY, PolicyEngine

load_dotenv()

st.set_page_config(page_title="Agent Wallet Control Center", layout="wide")
st.title("Autonomous Agent Wallet & Risk Control Plane")
st.caption("2026 Shenzhen International FinTech Competition (Topic F: Agent Wallet)")

# Sidebar controls
st.sidebar.header("Security & Network Controls")
adapter_mode = st.sidebar.selectbox(
    "Execution Environment",
    options=["mock", "chain"],
    index=0 if os.getenv("ADAPTER", "mock") == "mock" else 1,
    help="Use 'mock' for instant sandbox testing and 'chain' for real Ethereum Sepolia execution.",
)

tier_label = st.sidebar.radio(
    "Permission Tier (Policy Engine)",
    options=[
        "Tier 2: Limited Auto (Default)",
        "Tier 1: Approve Everything",
        "Tier 0: Read-Only Lock",
    ],
    index=0,
)
tier_map = {
    "Tier 2: Limited Auto (Default)": LIMITED_AUTO,
    "Tier 1: Approve Everything": APPROVE_ALL,
    "Tier 0: Read-Only Lock": READ_ONLY,
}
active_tier = tier_map[tier_label]

# Initialize session objects
if "adapter_mode" not in st.session_state or st.session_state.adapter_mode != adapter_mode:
    st.session_state.adapter_mode = adapter_mode
    st.session_state.adapter = get_adapter(adapter_mode)

adapter = st.session_state.adapter
policy = PolicyEngine.from_env(tier=active_tier)
audit = AuditLog("logs/audit.jsonl")

if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None
if "messages" not in st.session_state:
    st.session_state.messages = []


def ui_approver(args, reason):
    """Queue medium payments for visual human approval in the web UI."""
    st.session_state.pending_approval = {"args": dict(args), "reason": reason}
    return False


executor = ToolExecutor(adapter, policy, approver=ui_approver, audit=audit)
status = executor.run("get_portfolio_status", {})

# Top KPI Cards
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Network", status["network"].upper())
col2.metric("Total Balance", f"{status['balance_eth']:.4f} ETH")
col3.metric("Spendable (Above Reserve)", f"{status['spendable_balance_eth']:.4f} ETH")
col4.metric("Remaining 24h Cap", f"{status['remaining_daily_budget_eth']:.4f} ETH")
col5.metric("Network Gas", f"{status['current_gas_gwei']} Gwei", status["gas_status"])

st.divider()

# Human-in-the-loop Approval Banner
if st.session_state.pending_approval:
    req = st.session_state.pending_approval
    st.warning(
        f"**HUMAN APPROVAL REQUIRED:** Request to send **{req['args'].get('amount_eth')} ETH** "
        f"to `{req['args'].get('to')}` ({req['reason']})"
    )
    b1, b2 = st.columns(2)
    if b1.button("Approve & Execute Transaction", type="primary", use_container_width=True):
        approved_exec = ToolExecutor(adapter, policy, approver=lambda a, r: True, audit=audit)
        res = approved_exec.run("send_eth", req["args"])
        st.session_state.pending_approval = None
        msg = f"Human Operator APPROVED payment: Status={res['status']}, TX={res.get('tx', 'N/A')}"
        st.session_state.messages.append({"role": "assistant", "content": msg})
        st.rerun()
    if b2.button("Reject Payment", use_container_width=True):
        audit.write("human_approval", approved=False, args=req["args"], source="web_ui")
        st.session_state.pending_approval = None
        st.session_state.messages.append(
            {"role": "assistant", "content": "Human Operator REJECTED the pending payment."}
        )
        st.rerun()

left_col, right_col = st.columns([3, 2])

with left_col:
    st.subheader("Autonomous Agent Chat")
    recipient_default = os.getenv("RECIPIENT", "0x" + "a1" * 20)
    st.caption(f"Approved Recipient in `.env`: `{recipient_default}`")

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    user_prompt = st.chat_input("Ask the agent to check portfolio, simulate a transfer, or send ETH...")
    if user_prompt:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        client = None
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
            except Exception:
                client = None
        reply, _ = chat_turn(client, executor, user_prompt)
        if st.session_state.pending_approval:
            reply += "\n\n*(Paused for human supervisor approval. Use the approval buttons above.)*"
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()

with right_col:
    st.subheader("Preflight Risk Simulator")
    sim_to = st.text_input("Recipient Address", value=os.getenv("RECIPIENT", ""))
    sim_amt = st.number_input("Amount (ETH)", min_value=0.0, value=0.001, step=0.001, format="%.4f")
    if st.button("Run Dry-Run Simulation", use_container_width=True):
        sim_res = executor.run("simulate_transfer", {"to": sim_to, "amount_eth": sim_amt})
        st.json(sim_res)

    st.subheader("Live Security Audit Log (`logs/audit.jsonl`)")
    log_path = Path("logs/audit.jsonl")
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").splitlines()[-10:]
        records = [json.loads(line) for line in reversed(lines) if line.strip()]
        st.dataframe(records, use_container_width=True)
    else:
        st.info("No audit events recorded yet.")