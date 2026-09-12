
"""Shared economy data helpers (Mongo via load_stats/save_stats)."""
from functions import load_stats, save_stats

CREATOR_ID = 1465295674768883889


def get_cash(user_id: int):
    if int(user_id) == CREATOR_ID:
        return float("inf")
    stats = load_stats()
    eco = stats.get("economy") or {}
    u = eco.get(str(user_id)) or {}
    try:
        return int(u.get("cash", 0) or 0)
    except (TypeError, ValueError):
        return 0


def set_cash(user_id: int, amount: int) -> int:
    if int(user_id) == CREATOR_ID:
        return int(amount) if amount != float("inf") else 0
    stats = load_stats()
    if "economy" not in stats or not isinstance(stats["economy"], dict):
        stats["economy"] = {}
    uid = str(user_id)
    cur = stats["economy"].get(uid) or {}
    cur["cash"] = max(0, int(amount))
    stats["economy"][uid] = cur
    save_stats(stats)
    return cur["cash"]


def add_cash(user_id: int, amount: int):
    if int(user_id) == CREATOR_ID:
        return float("inf")
    cur = get_cash(user_id)
    if cur == float("inf"):
        return cur
    return set_cash(user_id, int(cur) + int(amount))


def format_money(amount) -> str:
    if amount == float("inf") or amount is None:
        return "∞"
    try:
        return f"{int(amount)}$"
    except Exception:
        return f"{amount}$"


def all_balances():
    """Return list of (user_id_str, cash) sorted desc."""
    stats = load_stats()
    eco = stats.get("economy") or {}
    out = []
    for uid, data in eco.items():
        if not str(uid).isdigit():
            continue
        try:
            cash = int((data or {}).get("cash", 0) or 0)
        except (TypeError, ValueError):
            cash = 0
        out.append((str(uid), cash))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out
