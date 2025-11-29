# balances_file.py
import json
import os

DATA_DIR = "/opt/render/project/src/data"
os.makedirs(DATA_DIR, exist_ok=True)
BALANCES_FILE = os.path.join(DATA_DIR, "balances.json")



def _load_balances():
    """Load balances from JSON file. Returns dict {key: cents_int}."""
    if not os.path.exists(BALANCES_FILE):
        return {}
    try:
        with open(BALANCES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            clean = {}
            for k, v in data.items():
                try:
                    clean[str(k)] = int(v)
                except Exception:
                    clean[str(k)] = 0
            return clean
    except Exception:
        return {}


def _save_balances(balances: dict) -> None:
    with open(BALANCES_FILE, "w", encoding="utf-8") as f:
        json.dump(balances, f, indent=2)


def get_balance(user_key) -> int:
    """
    Return the user's balance in cents (int).
    user_key can be username or ID – we store as string.
    """
    balances = _load_balances()
    return int(balances.get(str(user_key), 0))


def add_balance(user_key, delta_cents: int) -> None:
    """
    Add (or subtract) cents to the user's balance.
    Can be negative (for purchases).
    """
    balances = _load_balances()
    uid = str(user_key)
    current = int(balances.get(uid, 0))
    new_balance = current + int(delta_cents)
    if new_balance < 0:
        new_balance = 0  # safety: no negative balances
    balances[uid] = new_balance
    _save_balances(balances)

