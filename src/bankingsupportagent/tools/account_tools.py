import sqlite3
from contextlib import closing

from langchain.tools import tool, ToolRuntime
from bankingsupportagent.config import DB_PATH

MAX_TRANSACTIONS = 20
NOT_VERIFIED = "Customer is not verified. Ask them to log in before sharing account details."

# HELPERS
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def format_inr(paise: int) -> str:
    """8542050 -> 'Rs. 85,420.50' (integer maths only, no floats)."""
    sign = "-" if paise < 0 else ""
    rupees, p = divmod(abs(paise), 100)
    return f"{sign}Rs. {rupees:,}.{p:02d}"

def mask_account(account_number: str) -> str:
    """50100012345678 -> 'XXXX5678'"""
    return "XXXX" + account_number[-4:]


# Data functions

def fetch_balances(customer_id: str) -> str:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT account_number, account_type, balance_paise FROM accounts WHERE customer_id = ?",  # ← changed
            (customer_id,),
        ).fetchall()

    if not rows:
        return "No account found for this customer"
    return "\n".join(
        f"{r['account_type']} account {mask_account(r['account_number'])}: "
        f"balance {format_inr(r['balance_paise'])}"                                                  # ← changed
        for r in rows
    )


def fetch_transactions(customer_id: str, limit: int = 5) -> str:
    limit = max(1, min(limit, MAX_TRANSACTIONS))

    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
                SELECT t.txn_date, t.description, t.amount_paise, a.account_number
                FROM transactions t
                JOIN accounts a ON t.account_number = a.account_number
                WHERE a.customer_id = ?
                ORDER BY t.txn_date DESC, t.txn_id DESC
                LIMIT ?
            """,                                                                                     # ← changed (amount_paise)
            (customer_id, limit),
        ).fetchall()

    if not rows:
        return "No transaction found"
    return "\n".join(
        f"{r['txn_date']} | {r['description']} | "
        f"{'Credit' if r['amount_paise'] > 0 else 'Debit'} {format_inr(abs(r['amount_paise']))} | "  # ← changed (2 places)
        f"{mask_account(r['account_number'])}"
        for r in rows
    )


# TOOLS (what the LLM can call)

@tool
def get_balance(runtime: ToolRuntime) -> str:
    """Get the current balance for the logged in customer's account"""
    customer_id = runtime.state.get('customer_id')
    if not customer_id:
        return NOT_VERIFIED
    return fetch_balances(customer_id)


@tool
def get_recent_transactions(runtime: ToolRuntime, limit: int = 5) -> str:
    """Get the logged in customer's most recent transactions, newest first.

    Args:
        limit: How many transactions to return (1 to 20). Defaults to 5.
    """
    customer_id = runtime.state.get('customer_id')
    if not customer_id:
        return NOT_VERIFIED
    return fetch_transactions(customer_id, limit)


ACCOUNT_TOOLS = [get_balance, get_recent_transactions]