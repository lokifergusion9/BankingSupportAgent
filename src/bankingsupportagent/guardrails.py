# Say a user types his full account number or card number in the query, that is straight going to the LLM, so we gonna modify that

import re
from langchain.messages import HumanMessage
from bankingsupportagent.state import SupportState

# 9 to 19 digits, optionally separated by spaces or hyphens: card numbers, account numbers, phone numbers
LONG_NUMBER = re.compile(r"\b\d(?:[ -]?\d){8,18}\b")

# A secret keyword followed by a value that contains a digit: "OTP is 482913", "pin: 4821"
SECRET = re.compile(r"(?i)\b(otp|pin|cvv|password|passcode)\b(\s*(?:is|:|=)?\s*)(\S*\d\S*)")

def _mask_number(match) -> str:
    digits = re.sub(r"\D", "", match.group())
    return f"[number ending {digits[-4:]}]"

def mask_sensitive(text: str) -> str:
    """Hide secrets and long numbers before the text reaches any LLM or storage."""
    text = SECRET.sub(r"\1\2[REDACTED]", text)
    text = LONG_NUMBER.sub(_mask_number, text)
    return text


# Look-alike characters the LLM sometimes writes: they break copy-paste and exact matching of IDs like DSP-000011
LOOKALIKES = str.maketrans({
    "‐": "-",      # hyphen
    "‑": "-",      # non-breaking hyphen
    " ": " ",      # non-breaking space
    " ": " ",      # narrow non-breaking space
})

def normalize_reply(text: str) -> str:
    """Replace look-alike hyphens and spaces in a reply with plain ones."""
    return text.translate(LOOKALIKES)


def guardrail_node(state: SupportState):
    last = state["messages"][-1]
    masked = mask_sensitive(last.content)
    if masked == last.content:
        return {}
    return {"messages": [HumanMessage(content=masked, id=last.id)]}