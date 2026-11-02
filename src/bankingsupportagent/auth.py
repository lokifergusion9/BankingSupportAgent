import time
from contextlib import closing
from functools import lru_cache

import bcrypt
import jwt


from bankingsupportagent.config import (ACCESS_TOKEN_MINUTES, JWT_ALGORITHM, JWT_PRIVATE_KEY_PATH ,JWT_PUBLIC_KEY_PATH)
from bankingsupportagent.tools.account_tools import get_connection


# Passwords
def hash_password(password: str) -> str:
    """Turn a password into a one way bcrypt hash (with a random salt) for storage"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash:str) -> bool:
    """True if the password matches the stored hash"""
    return bcrypt.checkpw(password.encode(),password_hash.encode())

def authenticate(customer_id: str, password:str) -> bool:
    """True only if the customer exist and the password is correct"""
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT password_hash FROM credentials WHERE customer_id=?",(customer_id,)).fetchone()
    if row is None:
        return False
    return verify_password(password,row["password_hash"])



# Tokens

@lru_cache
def private_key() -> str:
    return JWT_PRIVATE_KEY_PATH.read_text()

@lru_cache
def public_key() -> str:
    return JWT_PUBLIC_KEY_PATH.read_text()

def create_access_token(customer_id: str) -> str:
    """Make a signed JWT that says 'this is a customer X' and expires after ACCESS_TOKEN_MINUTES"""
    now = int(time.time())
    payload = {
        "sub": customer_id,                             # Who this token is about
        "iat": now,                                     # issued at
        "exp": now+ACCESS_TOKEN_MINUTES*60,             # expires at
    }
    return jwt.encode(payload,private_key(),algorithm=JWT_ALGORITHM)


def decode_access_token(token:str) -> str:
    """Check the token's signature and expiry, and return the customer ID inside it"""
    payload = jwt.decode(
        token,
        public_key(),
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub","exp"]}
    )
    return payload["sub"]