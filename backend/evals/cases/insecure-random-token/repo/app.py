import random
import string

ALPHABET = string.ascii_letters + string.digits


def session_token(length: int = 32) -> str:
    return "".join(random.choice(ALPHABET) for _ in range(length))
