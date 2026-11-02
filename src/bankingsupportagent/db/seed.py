import sqlite3

from bankingsupportagent.config import DB_PATH
from bankingsupportagent.auth import hash_password

SCHEMA = """

    DROP TABLE IF EXISTS disputes;
    DROP TABLE IF EXISTS transactions;
    DROP TABLE IF EXISTS cards;
    DROP TABLE IF EXISTS accounts;
    DROP TABLE IF EXISTS customers;
    DROP TABLE IF EXISTS tickets;
    DROP TABLE IF EXISTS credentials;

    
    CREATE TABLE disputes (
        dispute_id   TEXT PRIMARY KEY,
        txn_id       INTEGER NOT NULL UNIQUE REFERENCES transactions(txn_id),
        customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
        reason       TEXT NOT NULL,
        status       TEXT NOT NULL DEFAULT 'open',
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE customers (
        customer_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT NOT NULL
    );

    CREATE TABLE accounts (
        account_number  TEXT PRIMARY KEY,
        customer_id     TEXT NOT NULL REFERENCES customers(customer_id),
        account_type    TEXT NOT NULL,
        balance_paise   INTEGER NOT NULL
    );

    CREATE TABLE transactions (
        txn_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        account_number  TEXT NOT NULL REFERENCES accounts(account_number),
        txn_date        TEXT NOT NULL,
        description     TEXT NOT NULL,
        amount_paise    INTEGER NOT NULL,
        channel         TEXT NOT NULL
    );

    CREATE TABLE cards (
        card_id         TEXT PRIMARY KEY,
        customer_id     TEXT NOT NULL REFERENCES customers(customer_id),
        card_type       TEXT NOT NULL,
        last4           TEXT NOT NULL,
        status          TEXT NOT NULL CHECK (status IN ('active', 'frozen', 'blocked')),
        international   INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE tickets (
        ticket_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id  TEXT,
        category     TEXT NOT NULL,
        priority     TEXT NOT NULL,
        summary      TEXT NOT NULL,
        status       TEXT NOT NULL DEFAULT 'open',
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE credentials (
        customer_id    TEXT PRIMARY KEY REFERENCES customers(customer_id),
        password_hash  TEXT NOT NULL
    );
"""


CUSTOMERS = [
    ("C1001", "Rahul Sharma", "+91-98100-11111", "rahul.sharma@example.com"),
    ("C1002", "Priya Iyer",   "+91-98200-22222", "priya.iyer@example.com"),
]

ACCOUNTS = [
    ("50100012345678", "C1001", "Regular Savings", 8_542_050),
    ("50100087654321", "C1002", "Salary Savings",  21_390_000),
]

TRANSACTIONS = [
    ("50100012345678", "2026-09-01", "SALARY CREDIT - INFOTECH PVT LTD",      7_500_000, "NEFT"),
    ("50100012345678", "2026-09-03", "UPI - SWIGGY",                            -45_000, "UPI"),
    ("50100012345678", "2026-09-05", "ATM WITHDRAWAL - SECUREBANK ANDHERI",  -1_000_000, "ATM"),
    ("50100012345678", "2026-09-10", "ELECTRICITY BILL - ADANI POWER",         -235_000, "BILLPAY"),
    ("50100012345678", "2026-09-15", "UPI - ZOMATO",                            -62_050, "UPI"),
    ("50100012345678", "2026-09-22", "CARD POS - DMART",                       -318_000, "CARD"),
    ("50100012345678", "2026-09-28", "INTEREST CREDIT",                          64_100, "INTERNAL"),
    ("50100087654321", "2026-09-01", "SALARY CREDIT - FINSERV LTD",          15_000_000, "NEFT"),
    ("50100087654321", "2026-09-04", "RENT TRANSFER - IMPS",                 -3_500_000, "IMPS"),
    ("50100087654321", "2026-09-12", "CARD ONLINE - AMAZON",                   -249_900, "CARD"),
    ("50100087654321", "2026-09-18", "CARD ONLINE - XYZ DIGITAL SERVICES",     -500_000, "CARD"),
    ("50100087654321", "2026-09-25", "SIP - MUTUAL FUND",                    -1_000_000, "NACH"),
]

CARDS = [
    ("CARD-1", "C1001", "Classic Debit",         "4821", "active", 0),
    ("CARD-2", "C1002", "Platinum Debit",        "7710", "active", 1),
    ("CARD-3", "C1002", "Secure Rewards Credit", "3392", "active", 0),
]

DEMO_PASSWORDS = {
    "C1001": "rahul-demo-123",
    "C1002": "priya-demo-123",
}


def seed():
    """Create a fresh mock database with sample customers and data"""
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO customers VALUES (?,?,?,?)",CUSTOMERS)
        conn.executemany("INSERT INTO accounts VALUES (?,?,?,?)",ACCOUNTS)
        conn.executemany(
            "INSERT INTO transactions (account_number, txn_date, description, amount_paise, channel) "
            "VALUES (?, ?, ?, ?, ?)",
            TRANSACTIONS,
        )
        conn.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?)", CARDS)
        conn.executemany(
            "INSERT INTO credentials (customer_id, password_hash) VALUES (?, ?)",
            [(cid, hash_password(pw)) for cid, pw in DEMO_PASSWORDS.items()],
        )

    print(f"Seeded {len(CUSTOMERS)} customers, {len(TRANSACTIONS)} transactions, {len(CARDS)} cards into {DB_PATH}")


if __name__ == "__main__":
    seed()