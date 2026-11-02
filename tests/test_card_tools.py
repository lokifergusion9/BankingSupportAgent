from bankingsupportagent.tools.card_tools import (
    change_card_status, fetch_card_status, file_dispute,
)


def test_freeze_and_unfreeze():
    assert "now frozen" in change_card_status("C1001", "4821", "freeze")
    assert fetch_card_status("C1001", "4821") == "frozen"
    assert "now active" in change_card_status("C1001", "4821", "unfreeze")
    assert fetch_card_status("C1001", "4821") == "active"


def test_cannot_freeze_twice():
    change_card_status("C1001", "4821", "freeze")
    assert "Cannot freeze" in change_card_status("C1001", "4821", "freeze")


def test_cannot_touch_another_customers_card():
    result = change_card_status("C1001", "7710", "freeze")
    assert "No card ending 7710" in result
    assert fetch_card_status("C1002", "7710") == "active"


def test_full_card_number_is_rejected():
    result = change_card_status("C1001", "4111111111111111", "freeze")
    assert "only the last 4 digits" in result


def test_dispute_gets_reference_and_no_duplicates():
    first = file_dispute("C1002", "2026-09-18", "XYZ DIGITAL", "Not me")
    assert "DSP-" in first
    second = file_dispute("C1002", "2026-09-18", "XYZ DIGITAL", "Again")
    assert "already under dispute" in second


def test_cannot_dispute_another_customers_transaction():
    result = file_dispute("C1001", "2026-09-18", "XYZ DIGITAL", "Not mine")
    assert "No debit" in result


def test_cannot_dispute_a_credit():
    result = file_dispute("C1002", "2026-09-01", "SALARY", "Hmm")
    assert "No debit" in result