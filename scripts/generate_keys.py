"""Create the RSA key pair used to sign(private) and verify(public) login tokens."""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEYS_DIR = Path(__file__).resolve().parents[1] / "keys"

def main():
    KEYS_DIR.mkdir(exist_ok=True)
    private_path = KEYS_DIR / "private.pem"
    public_path = KEYS_DIR / "public.pem"

    if private_path.exists():
        print(f"Keys already exist in {KEYS_DIR}. Delete them first if you really want new ones.")
        return

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
    print(f"Created {private_path.name} (keep secret) and {public_path.name} in {KEYS_DIR}")


if __name__ == "__main__":
    main()