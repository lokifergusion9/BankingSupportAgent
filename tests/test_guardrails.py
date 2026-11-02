import pytest

from bankingsupportagent.guardrails import mask_sensitive


@pytest.mark.parametrize("text, expected", [
    ("My card is 4111 1111 1111 1111", "My card is [number ending 1111]"),
    ("card 4111-1111-1111-4821 stolen", "card [number ending 4821] stolen"),
    ("account 50100012345678", "account [number ending 5678]"),
    ("my otp is 482913", "my otp is [REDACTED]"),
    ("PIN: 4821", "PIN: [REDACTED]"),
])
def test_sensitive_data_is_masked(text, expected):
    assert mask_sensitive(text) == expected


@pytest.mark.parametrize("text", [
    "Rs 20,000 was debited on 2026-09-18",
    "Block my card ending 4821",
    "Can I reset my password?",
    "What is the FD rate for 1 year?",
])
def test_normal_text_is_unchanged(text):
    assert mask_sensitive(text) == text