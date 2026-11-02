from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from bankingsupportagent.config import KEYS_DIR


def generate_keys(keys_dir: Path = KEYS_DIR) -> bool:
    """Create the RSA key pair used to sign (private) and verify (public) login tokens.

    Returns False and changes nothing if the keys already exist.
    """
    private_path = keys_dir / "private.pem"
    public_path = keys_dir / "public.pem"
    if private_path.exists() and public_path.exists():
        return False

    keys_dir.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.write_bytes(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    public_path.write_bytes(private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    return True
