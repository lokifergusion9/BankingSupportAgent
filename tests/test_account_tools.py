import pytest

from bankingsupportagent.tools.account_tools import (
    fetch_balances, fetch_transactions, format_inr, mask_account,
)

@pytest.mark.parametrize("paise, expected", [
    (8542050, "Rs. 85,420.50"),
    (5, "Rs. 0.05"),
    (-249900, "-Rs. 2,499.00"),
    (0, "Rs. 0.00"),
])
def test_format_inr(paise, expected):
    assert format_inr(paise) == expected


def test_mask_account_keeps_only_last_four():
    assert mask_account("50100012345678") == "XXXX5678"


def test_balance_is_masked_and_formatted():
    result = fetch_balances("C1001")
    assert "Rs. 85,420.50" in result
    assert "XXXX5678" in result
    assert "50100012345678" not in result



def test_unknown_customer_gets_no_data():
    assert "No account" in fetch_balances("C9999")



def test_transactions_are_capped_and_newest_first():
    lines = fetch_transactions("C1001", 999).splitlines()
    assert len(lines) == 7
    assert lines[0].startswith("2026-09-28")


def test_customer_never_sees_another_customers_transactions():
    rahul = fetch_transactions("C1001", 20)
    assert "XYZ DIGITAL" not in rahul
    assert "XXXX4321" not in rahul