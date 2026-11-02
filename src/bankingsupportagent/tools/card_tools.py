from contextlib import closing
from langchain.tools import tool,ToolRuntime
from langgraph.types import interrupt

from bankingsupportagent.tools.account_tools import (
    get_connection,NOT_VERIFIED,format_inr,get_recent_transactions
)
from bankingsupportagent.tools.policy_tools import search_policies

# Which status changes are allowed: action -> (required current status, new status)
TRANSITIONS = {
    "freeze": ("active","frozen"),
    "unfreeze": ("frozen","active"),
}


# Helpers
def is_valid_last4(last4:str) -> bool:
    return len(last4) == 4 and last4.isdigit()


# Data functions

def fetch_cards(customer_id: str) -> str:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "Select card_type, last4, status, international FROM cards where customer_id=?",(customer_id,),
        ).fetchall()

    if not rows:
        return "No card found for this customer"
    return "\n".join(
        f"{r['card_type']} ending {r['last4']} | status: {r['status']} | "
        f"international usage: {'on' if r['international'] else 'off'}"
        for r in rows
    )


def fetch_card_status(customer_id: str, last4: str):
    """Return the card's status and None if this customer has no such card"""
    with closing(get_connection()) as conn:
        row = conn.execute(
            "Select status FROM cards WHERE customer_id=? AND last4=?",(customer_id,last4)
        ).fetchone()

    return row['status'] if row else None


def change_card_status(customer_id:str, last4:str, action:str)->str:
    if not is_valid_last4(last4):
        return "Please give only the last 4 digits of your card. Never share the full card number"

    current = fetch_card_status(customer_id,last4)
    if current is None:
        return f"No card ending {last4} was found on this customer's profile"

    from_status,to_status = TRANSITIONS[action]
    if current!=from_status:
        return f"Cannot {action} the card ending {last4}: it's current status is {current}"

    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE cards SET status=? WHERE customer_id=? AND last4=?",(to_status,customer_id,last4),
        )
        conn.commit()
    return f"Done. The card ending {last4} is now {to_status}."


def block_card_in_db(customer_id: str, last4: str) -> str:
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE cards SET status='blocked' WHERE customer_id=? AND last4=?",
            (customer_id,last4),
        )
        conn.commit()
    return f"The card ending {last4} has been permanantly blocked. A replacement can be requested in the app."


def file_dispute(customer_id: str, txn_date:str, merchant:str, reason:str) -> str:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            SELECT t.txn_id, t.description, t.amount_paise
            FROM transactions t
            JOIN accounts a on a.account_number = t.account_number
            WHERE a.customer_id = ? AND txn_date = ? AND t.description LIKE ? AND t.amount_paise < 0
            """,
            (customer_id,txn_date, f"%{merchant}%")
        ).fetchall()

        if len(rows)==0:
            return f"No debit from '{merchant}' on {txn_date} was found on this customer's accounts."
        if len(rows)>1:
            return f"More than one matching transactions was found. Ask the customer for the exact amount"

        txn = rows[0]
        existing = conn.execute(
            "Select dispute_id from disputes WHERE txn_id=?",(txn['txn_id'],)
        ).fetchone()

        if existing:
            return f"This transaction is already under dispute (reference {existing['dispute_id']})."

        dispute_id = f"DSP-{txn['txn_id']:06d}"
        conn.execute(
            "INSERT INTO disputes (dispute_id, txn_id, customer_id, reason) VALUES (?,?,?,?)",
            (dispute_id,txn['txn_id'],customer_id,reason)
        )
        conn.commit()

        return (
            f"Dispute raised for {txn['description']} ({format_inr(-txn['amount_paise'])}) on {txn_date}. "
            f"Reference number: {dispute_id}. Disputes are resolved within 30 working days."
        )



# Tools

@tool
def list_cards(runtime:ToolRuntime) -> str:
    """List the logged in customer's card with their last 4 digits and status"""
    customer_id = runtime.state.get("customer_id")
    if not customer_id:
        return NOT_VERIFIED
    return fetch_cards(customer_id)


@tool
def freeze_card(runtime:ToolRuntime, last4:str) -> str:
    """Temporarily freeze one of the customer's cards. A frozen card can be unfrozen later.
    
    Args:
        last4: The last 4 digits of the card to be freeze
    """

    customer_id = runtime.state.get("customer_id")
    if not customer_id:
        return NOT_VERIFIED
    return change_card_status(customer_id,last4,"freeze")


@tool
def unfreeze_card(runtime:ToolRuntime, last4:str) -> str:
    """Unfreeze a card that the customer froze earlier
    
    Args:
        last4: The last 4 digits of the card to unfreeze
    """

    customer_id = runtime.state.get("customer_id")
    if not customer_id:
        return NOT_VERIFIED
    return change_card_status(customer_id,last4,"unfreeze")



@tool
def block_card(runtime:ToolRuntime, last4:str) -> str:
    """Permanently block a card that is lost, stolen or compromised. This cannot be undone.
    The customer will be asked to confirm before the card is blocked.

    Args:
        last4: The last 4 digits of the card to block.
    """

    customer_id = runtime.state.get("customer_id")
    if not customer_id:
        return NOT_VERIFIED
    if not is_valid_last4(last4):
        return "Please give only the last 4 digits of the card. Never share the full card number."

    current = fetch_card_status(customer_id,last4)
    if current is None:
        return f"No card ending {last4} was found on this customer's profile."
    if current == "blocked":
        return f"The card ending {last4} is already blocked."

    decision = interrupt({
        "action":"block_card",
        "last4":last4,
        "message": f"Blocking the card ending {last4} is permanant and cannot be undone. Do you want to continue?"
    })

    if not decision.get("approved"):
        return (
            f"The customer declined. The card ending {last4} was NOT blocked. "
            "Do not try to block it again unless the customer asks again. "
            "Offer to freeze the card instead."
        )
    return block_card_in_db(customer_id,last4)


@tool
def raise_dispute(runtime:ToolRuntime, txn_date:str, merchant: str, reason: str) -> str:
    """Raise a dispute for a debit transaction the customer does not recognise or did not authorise.

    Args:
        txn_date: Transaction date in YYYY-MM-DD format, as shown in the transaction list.
        merchant: The merchant name (or part of it) from the transaction description.
        reason: A short reason from the customer, e.g. 'I did not make this payment'.
    """
    customer_id = runtime.state.get("customer_id")
    if not customer_id:
        return NOT_VERIFIED
    return file_dispute(customer_id,txn_date,merchant,reason)


CARD_TOOLS = [
    list_cards, freeze_card, unfreeze_card, block_card, raise_dispute, get_recent_transactions, search_policies,
]