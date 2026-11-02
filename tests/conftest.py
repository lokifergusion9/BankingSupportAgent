import pytest

from bankingsupportagent.db.seed import seed


@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    """Give every test its own fresh copy of the bank database in a temporary folder."""
    db_file = tmp_path / "test_bank.db"
    monkeypatch.setattr("bankingsupportagent.db.seed.DB_PATH", db_file)
    monkeypatch.setattr("bankingsupportagent.tools.account_tools.DB_PATH", db_file)
    seed()