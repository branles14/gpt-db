import json
import random
from importlib import resources


def _load_messages() -> list[str]:
    with resources.files(__package__).joinpath("auth_errmsgs.json").open("r", encoding="utf-8") as f:
        return json.load(f)


auth_error_messages = _load_messages()


def get_random_auth_error() -> str:
    """Return a random authorization error message."""
    return random.choice(auth_error_messages)
