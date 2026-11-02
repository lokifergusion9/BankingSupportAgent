"""Create the RSA key pair used to sign(private) and verify(public) login tokens."""

from bankingsupportagent.config import KEYS_DIR
from bankingsupportagent.keys import generate_keys


def main():
    if generate_keys():
        print(f"Created private.pem (keep secret) and public.pem in {KEYS_DIR}")
    else:
        print(f"Keys already exist in {KEYS_DIR}. Delete them first if you really want new ones.")


if __name__ == "__main__":
    main()
