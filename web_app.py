# web_app.py



import os
from dotenv import load_dotenv
load_dotenv()
import re
import time
import json
import hmac
import hashlib
import base64
import datetime
import logging
import random
import secrets
import smtplib
import threading
from email.message import EmailMessage
from typing import List, Tuple, Optional, Set, Dict, Any
from zoneinfo import ZoneInfo

import requests
from flask import (
    Flask,
    request,
    jsonify,
    render_template,          # ✅ ADD
    render_template_string,
    redirect,
    url_for,
    session,
    send_from_directory,
    Response,
)


from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps


# ===================== FORTNITE ICON LOOKUP =====================

FORTNITE_COSMETICS_ALL_URL = "https://fortnite-api.com/v2/cosmetics/br"
COSMETIC_ICON_CACHE_FILE = "cosmetic_icon_cache.json"
COSMETIC_LOOKUP_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60
COSMETIC_TYPE_ALIASES = {
    "emote": "emote",
    "dance": "emote",
    "outfit": "outfit",
    "pickaxe": "pickaxe",
    "backpack": "backpack",
    "glider": "glider",
}

COSMETIC_LOOKUP: Dict[str, Optional[str]] = {}
COSMETIC_LOOKUP_BY_TYPE: Dict[str, Dict[str, Optional[str]]] = {}
COSMETIC_RARITY_LOOKUP: Dict[str, Optional[str]] = {}
COSMETIC_LOOKUP_LAST_REFRESH_TS = 0
COSMETIC_LOOKUP_LOCK = threading.Lock()
COSMETIC_LOOKUP_SCHEDULER_STARTED = False
COSMETIC_LOOKUP_SCHEDULER_LOCK = threading.Lock()
COSMETIC_LOOKUP_RUNTIME_INITIALIZED = False
COSMETIC_LOOKUP_RUNTIME_INIT_LOCK = threading.Lock()
COSMETIC_LOGGER = logging.getLogger("cosmetic_lookup")
COSMETIC_REFRESH_IN_PROGRESS = False
PURCHASE_DELAY_AFTER_CHECK_SECONDS = 5
FAST_BUY_MAX_ATTEMPTS = 100
# Sub-second pause between retries to avoid hammering the API.
FAST_BUY_RETRY_DELAY_SECONDS = 0.1
# Delay when the marketplace signals rate-limiting (429).
FAST_BUY_RATE_LIMIT_DELAY_SECONDS = 5.0
# Delay when the marketplace returns a 5xx server error.
FAST_BUY_SERVER_ERROR_DELAY_SECONDS = 2.0
PURCHASE_RECOVERY_MAX_ATTEMPTS = 5
PURCHASE_RECOVERY_DELAY_SECONDS = 1.0
ACCOUNT_UNAVAILABLE_MESSAGE = "Account is no longer available. Please choose another account."
ACCOUNT_UNAVAILABLE_KEYWORDS = ("sold", "not found", "unavailable", "deleted", "archived")
BALANCE_ERROR_KEYWORDS = (
    "balance_id",
    "insufficient balance",
    "not enough balance",
    "balance required",
    "insufficient_funds",
    "insufficient funds",
)
AUTH_ERROR_KEYWORDS = (
    "forbidden",
    "access denied",
    "permission",
    "scope",
    "unauthorized",
    "token",
)
MAX_MARKETPLACE_ERROR_LENGTH = 180
# Error text patterns that indicate a transient failure worth retrying.
FAST_BUY_RETRYABLE_KEYWORDS = (
    "too many requests",
    "rate_limit",
    "item_locked",
    "account_locked",
    "try again later",
    "try later",
)
PURCHASE_LOCK_SESSION_KEY = "purchase_lock"
DEFAULT_PURCHASE_ITEM_TITLE = "Fortnite Account"
MAX_PURCHASE_ITEM_TITLE_LENGTH = 160
DEFAULT_PURCHASE_PRODUCT_NAME = "Fortnite"
PURCHASE_LOCK_MAX_SECONDS = 600


class PurchaseFlowError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _build_marketplace_error_message(
    fallback_message: str,
    error_parts: List[str],
) -> str:
    if not error_parts:
        return fallback_message

    first_error = str(error_parts[0] or "").strip()
    if not first_error:
        return fallback_message

    if len(first_error) > MAX_MARKETPLACE_ERROR_LENGTH:
        first_error = f"{first_error[:MAX_MARKETPLACE_ERROR_LENGTH - 3]}..."

    return f"{fallback_message} ({first_error})"


def _find_nested_value(obj: Any, key_name: str) -> Any:
    """Recursively find a nested key and unwrap `{raw: ...}` marketplace fields."""
    if not isinstance(obj, dict):
        return None

    if key_name in obj:
        value = obj.get(key_name)
        if isinstance(value, dict) and "raw" in value:
            return value.get("raw")
        return value

    for child in obj.values():
        if isinstance(child, dict):
            found = _find_nested_value(child, key_name)
            if found not in (None, ""):
                return found
        elif isinstance(child, list):
            for item in child:
                found = _find_nested_value(item, key_name)
                if found not in (None, ""):
                    return found
    return None


def _purchase_result_has_credentials(purchase_result: Any) -> bool:
    """Return True when marketplace purchase data includes Epic or email login details."""
    return bool(
        _find_nested_value(purchase_result, "loginData")
        or _find_nested_value(purchase_result, "emailLoginData")
    )


def _extract_purchase_item_id(purchase_result: Any) -> Optional[int]:
    """Extract an item identifier from common marketplace purchase payload shapes."""
    raw_item_id = (
        _find_nested_value(purchase_result, "item_id")
        or _find_nested_value(purchase_result, "fortnite_item_id")
        or _find_nested_value(purchase_result, "itemId")
    )
    try:
        return int(raw_item_id)
    except (TypeError, ValueError):
        return None


def _normalize_purchase_result_payload(payload: Any) -> Any:
    """Preserve item fields while keeping full purchase-response metadata like login details."""
    if not isinstance(payload, dict):
        return payload

    item = payload.get("item")
    if not isinstance(item, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            item = data

    if not isinstance(item, dict):
        return payload

    normalized = dict(item)
    normalized["item"] = dict(item)
    for key, value in payload.items():
        if key not in ("item", "data"):
            normalized[key] = value
    return normalized


def _fetch_purchase_result_by_item_id(item_id: int) -> Optional[dict]:
    """Fetch the purchased item payload so delivery/login data is preserved."""
    url = f"https://prod-api.lzt.market/{item_id}"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {MARKET_API_TOKEN}",
    }

    resp = requests.get(url, headers=headers, timeout=20)

    if resp.status_code == 404:
        return None

    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch account {item_id}: "
            f"{resp.status_code} - {resp.text[:200]}"
        )

    return _normalize_purchase_result_payload(resp.json())


def _recover_purchase_result(
    item_id: int,
    reason: str,
    initial_result: Optional[dict] = None,
    initial_delay_seconds: float = 0.0,
) -> Optional[dict]:
    """Retry the item lookup after ambiguous purchase responses and return recovered credentials."""
    if isinstance(initial_result, dict) and _purchase_result_has_credentials(initial_result):
        return initial_result

    if initial_delay_seconds > 0:
        time.sleep(initial_delay_seconds)

    for attempt in range(PURCHASE_RECOVERY_MAX_ATTEMPTS):
        try:
            recovered_result = _fetch_purchase_result_by_item_id(item_id)
        except Exception as exc:
            app.logger.warning(
                "Purchase recovery lookup failed for item %s after %s (attempt %s/%s): %s",
                item_id,
                reason,
                attempt + 1,
                PURCHASE_RECOVERY_MAX_ATTEMPTS,
                exc,
            )
            recovered_result = None

        if isinstance(recovered_result, dict) and _purchase_result_has_credentials(recovered_result):
            app.logger.warning(
                "Recovered purchase credentials for item %s after %s on attempt %s/%s",
                item_id,
                reason,
                attempt + 1,
                PURCHASE_RECOVERY_MAX_ATTEMPTS,
            )
            return recovered_result

        if attempt < PURCHASE_RECOVERY_MAX_ATTEMPTS - 1:
            time.sleep(PURCHASE_RECOVERY_DELAY_SECONDS)

    return initial_result if isinstance(initial_result, dict) else None

def fortnite_api_get_outfit_icon_url_by_name(name: str):
    """
    Fetch outfit/skin icon URL by name. Wrapper around the generic function.
    """
    return fortnite_api_get_cosmetic_icon_url_by_name(name, 'outfit')


def _normalize_cosmetic_type(cosmetic_type: Optional[str]) -> Optional[str]:
    if cosmetic_type is None:
        return None
    value = str(cosmetic_type).strip().lower()
    if not value:
        return None
    return COSMETIC_TYPE_ALIASES.get(value, value)


def _extract_cosmetic_icon_url(item: dict) -> Optional[str]:
    images = item.get("images") or {}
    return images.get("icon") or images.get("smallIcon") or images.get("featured")


def _build_cosmetic_lookup(raw_items: list) -> Tuple[Dict[str, Optional[str]], Dict[str, Dict[str, Optional[str]]], Dict[str, Optional[str]]]:
    any_lookup: Dict[str, Optional[str]] = {}
    by_type_lookup: Dict[str, Dict[str, Optional[str]]] = {}
    rarity_lookup: Dict[str, Optional[str]] = {}

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        name = (item.get("name") or "").strip()
        if not name:
            continue
        name_key = name.lower()
        icon_url = _extract_cosmetic_icon_url(item)

        if name_key not in any_lookup:
            any_lookup[name_key] = icon_url

        rarity_info = item.get("rarity") or {}
        rarity_value = (rarity_info.get("value") or "").strip().lower()
        if name_key not in rarity_lookup:
            rarity_lookup[name_key] = rarity_value or None

        item_type = item.get("type") or {}
        item_type_value = (item_type.get("value") or item_type.get("backendValue") or "").strip().lower()
        normalized_type = _normalize_cosmetic_type(item_type_value)
        if normalized_type:
            type_lookup = by_type_lookup.setdefault(normalized_type, {})
            if name_key not in type_lookup:
                type_lookup[name_key] = icon_url

    return any_lookup, by_type_lookup, rarity_lookup


def _persist_cosmetic_lookup_to_disk() -> None:
    payload = {
        "updated_at": COSMETIC_LOOKUP_LAST_REFRESH_TS,
        "any": COSMETIC_LOOKUP,
        "by_type": COSMETIC_LOOKUP_BY_TYPE,
        "rarity": COSMETIC_RARITY_LOOKUP,
    }
    with open(COSMETIC_ICON_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _load_cosmetic_lookup_from_disk() -> bool:
    if not os.path.exists(COSMETIC_ICON_CACHE_FILE):
        return False
    try:
        with open(COSMETIC_ICON_CACHE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
        any_lookup = payload.get("any")
        by_type_lookup = payload.get("by_type")
        if not isinstance(any_lookup, dict):
            return False
        if not isinstance(by_type_lookup, dict):
            by_type_lookup = {}

        normalized_by_type: Dict[str, Dict[str, Optional[str]]] = {}
        for key, value in by_type_lookup.items():
            normalized_key = _normalize_cosmetic_type(key)
            if not normalized_key or not isinstance(value, dict):
                continue
            normalized_by_type[normalized_key] = value

        rarity_lookup = payload.get("rarity")
        if not isinstance(rarity_lookup, dict):
            rarity_lookup = {}

        with COSMETIC_LOOKUP_LOCK:
            global COSMETIC_LOOKUP, COSMETIC_LOOKUP_BY_TYPE, COSMETIC_RARITY_LOOKUP, COSMETIC_LOOKUP_LAST_REFRESH_TS
            COSMETIC_LOOKUP = any_lookup
            COSMETIC_LOOKUP_BY_TYPE = normalized_by_type
            COSMETIC_RARITY_LOOKUP = rarity_lookup
            raw_updated_at = int(payload.get("updated_at") or 0)
            now_ts = int(time.time())
            COSMETIC_LOOKUP_LAST_REFRESH_TS = min(max(raw_updated_at, 0), now_ts)
        return True
    except Exception:
        return False


def refresh_cosmetic_lookup_from_api() -> bool:
    started_at = time.time()
    with COSMETIC_LOOKUP_LOCK:
        global COSMETIC_REFRESH_IN_PROGRESS
        if COSMETIC_REFRESH_IN_PROGRESS:
            return False
        COSMETIC_REFRESH_IN_PROGRESS = True
    try:
        COSMETIC_LOGGER.info("Starting cosmetic lookup refresh from Fortnite API")
        response = requests.get(FORTNITE_COSMETICS_ALL_URL, timeout=20)
        if response.status_code != 200:
            COSMETIC_LOGGER.warning(
                "Cosmetic lookup refresh failed with status %s in %.2fs",
                response.status_code,
                time.time() - started_at,
            )
            return False

        data = (response.json() or {}).get("data") or []
        if not isinstance(data, list):
            COSMETIC_LOGGER.warning(
                "Cosmetic lookup refresh failed due to invalid payload in %.2fs",
                time.time() - started_at,
            )
            return False
        any_lookup, by_type_lookup, rarity_lookup = _build_cosmetic_lookup(data)
        if not any_lookup:
            COSMETIC_LOGGER.warning(
                "Cosmetic lookup refresh produced empty lookup in %.2fs",
                time.time() - started_at,
            )
            return False

        with COSMETIC_LOOKUP_LOCK:
            global COSMETIC_LOOKUP, COSMETIC_LOOKUP_BY_TYPE, COSMETIC_RARITY_LOOKUP, COSMETIC_LOOKUP_LAST_REFRESH_TS
            COSMETIC_LOOKUP = any_lookup
            COSMETIC_LOOKUP_BY_TYPE = by_type_lookup
            COSMETIC_RARITY_LOOKUP = rarity_lookup
            COSMETIC_LOOKUP_LAST_REFRESH_TS = int(time.time())

        _persist_cosmetic_lookup_to_disk()
        COSMETIC_LOGGER.info(
            "Cosmetic lookup refresh succeeded with %s entries in %.2fs",
            len(any_lookup),
            time.time() - started_at,
        )
        return True
    except Exception as exc:
        COSMETIC_LOGGER.warning(
            "Cosmetic lookup refresh failed with exception after %.2fs: %s",
            time.time() - started_at,
            exc,
        )
        return False
    finally:
        with COSMETIC_LOOKUP_LOCK:
            COSMETIC_REFRESH_IN_PROGRESS = False


def initialize_cosmetic_lookup() -> None:
    if refresh_cosmetic_lookup_from_api():
        return
    _load_cosmetic_lookup_from_disk()


def start_cosmetic_lookup_scheduler() -> None:
    global COSMETIC_LOOKUP_SCHEDULER_STARTED
    with COSMETIC_LOOKUP_SCHEDULER_LOCK:
        if COSMETIC_LOOKUP_SCHEDULER_STARTED:
            return
        COSMETIC_LOOKUP_SCHEDULER_STARTED = True

    def _scheduler_loop():
        while True:
            with COSMETIC_LOOKUP_LOCK:
                last_refresh_ts = COSMETIC_LOOKUP_LAST_REFRESH_TS

            now_ts = time.time()
            if last_refresh_ts <= 0:
                sleep_seconds = 60
            else:
                age_seconds = max(now_ts - last_refresh_ts, 0)
                sleep_seconds = max(COSMETIC_LOOKUP_REFRESH_INTERVAL_SECONDS - age_seconds, 0)

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

            with COSMETIC_LOOKUP_LOCK:
                latest_refresh_ts = COSMETIC_LOOKUP_LAST_REFRESH_TS
            if latest_refresh_ts > 0:
                latest_age_seconds = max(time.time() - latest_refresh_ts, 0)
                if latest_age_seconds < COSMETIC_LOOKUP_REFRESH_INTERVAL_SECONDS:
                    continue

            refresh_cosmetic_lookup_from_api()

    thread = threading.Thread(target=_scheduler_loop, daemon=True)
    thread.start()


def ensure_cosmetic_lookup_runtime_initialized() -> None:
    global COSMETIC_LOOKUP_RUNTIME_INITIALIZED
    with COSMETIC_LOOKUP_RUNTIME_INIT_LOCK:
        if COSMETIC_LOOKUP_RUNTIME_INITIALIZED:
            return
        initialize_cosmetic_lookup()
        start_cosmetic_lookup_scheduler()
        COSMETIC_LOOKUP_RUNTIME_INITIALIZED = True


def fortnite_api_get_cosmetic_icon_url_by_name(name: str, cosmetic_type: str = None):
    """
    Generic O(1) in-memory cosmetic icon lookup by name.
    cosmetic_type can be: 'outfit', 'pickaxe', 'emote', 'glider', or None (searches all types).
    Runtime initialization must run first via ensure_cosmetic_lookup_runtime_initialized().
    """
    name = (name or "").strip()
    if not name:
        return None

    name_key = name.lower()
    normalized_type = _normalize_cosmetic_type(cosmetic_type)
    with COSMETIC_LOOKUP_LOCK:
        if normalized_type:
            return (COSMETIC_LOOKUP_BY_TYPE.get(normalized_type) or {}).get(name_key)
        return COSMETIC_LOOKUP.get(name_key)




# <<< ADD THIS BLOCK >>>
DATA_DIR = "/opt/render/project/src/data"
os.makedirs(DATA_DIR, exist_ok=True)
# <<< END ADD >>>


# ===================== CONFIG =====================

# --- Marketplace / Fortnite API ---
MARKET_API_URL = "https://prod-api.lzt.market/fortnite"
MARKET_API_TOKEN = os.environ.get("MARKET_API_TOKEN")  # set in env

if not MARKET_API_TOKEN:
    raise SystemExit("MARKET_API_TOKEN is not set in environment.")

market_headers = {
    "accept": "application/json",
    "authorization": f"Bearer {MARKET_API_TOKEN}",
}

# LZT balance cache for owner account
_lzt_balance_cache = {"cents": 0, "time": 0}

def get_lzt_balance_cents(force: bool = False) -> int:
    """Fetch the LZT marketplace balance for the owner."""
    global _lzt_balance_cache
    now = int(time.time())
    if not force and now - _lzt_balance_cache["time"] < 300:
        return _lzt_balance_cache["cents"]
    try:
        resp = requests.get(
            "https://prod-api.lzt.market/balance/exchange",
            headers=market_headers,
            timeout=4,
        )
        if resp.status_code == 200:
            data = resp.json()
            balances = data.get("from", {})
            main_balance_obj = balances.get("balance", {})
            bal_float = main_balance_obj.get("convertedBalance", 0)
            try:
                cents = int(float(bal_float) * 100)
            except (TypeError, ValueError):
                cents = 0
            _lzt_balance_cache = {"cents": cents, "time": now}
            return cents
    except Exception:
        pass
    return _lzt_balance_cache["cents"]

# --- Shopify store (for topup link) ---
SHOPIFY_STORE_DOMAIN = os.environ.get(
    "SHOPIFY_STORE_DOMAIN", "0dgkay-n6.myshopify.com"
)
STORE_CREDIT_VARIANT_ID = os.environ.get(
    "STORE_CREDIT_VARIANT_ID", "46922856005885"
)

# --- Shopify Admin API (for /redeem) ---
SHOPIFY_ADMIN_DOMAIN = os.environ.get(
    "SHOPIFY_ADMIN_DOMAIN", "0dgkay-n6.myshopify.com"
)
SHOPIFY_ADMIN_TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN")  # set in env
SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2025-10")
SHOPIFY_API_TIMEOUT = int(os.environ.get("SHOPIFY_API_TIMEOUT", "30"))
SHOPIFY_ERROR_BODY_LIMIT = int(os.environ.get("SHOPIFY_ERROR_BODY_LIMIT", "200"))

if not SHOPIFY_ADMIN_TOKEN:
    print("WARNING: SHOPIFY_ADMIN_TOKEN not set â€“ /redeem will not work.")

# --- Email / SMTP ---
GMAIL_APP_PASSWORD_LENGTH = 16


def _normalize_smtp_password(raw_password: str) -> str:
    cleaned = (raw_password or "").strip()
    compact = cleaned.replace(" ", "")
    # Gmail app passwords are often copied as four 4-character groups with spaces.
    if " " in cleaned and len(compact) == GMAIL_APP_PASSWORD_LENGTH:
        return compact
    return cleaned


SMTP_HOST = (os.environ.get("SMTP_HOST") or "").strip()
SMTP_USER = (os.environ.get("SMTP_USER") or "").strip()
SMTP_PASS = _normalize_smtp_password(os.environ.get("SMTP_PASS") or "")
EMAIL_FROM = (os.environ.get("EMAIL_FROM") or SMTP_USER).strip()
EMAIL_CODE_TTL_SECONDS = int(os.environ.get("EMAIL_CODE_TTL_SECONDS", "900"))
try:
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "0").strip() or "0")
except ValueError:
    SMTP_PORT = 0

if any([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM]) and not all(
    [SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM]
):
    print("WARNING: SMTP config is incomplete â€“ email verification and password reset will not work.")

# --- Shopify Webhook (for auto top-up) ---
SHOPIFY_WEBHOOK_SECRET = os.environ.get("SHOPIFY_WEBHOOK_SECRET")  # set in env

if not SHOPIFY_WEBHOOK_SECRET:
    print("WARNING: SHOPIFY_WEBHOOK_SECRET not set – /webhooks/shopify/order-paid will reject all requests.")

# --- Discord purchase webhook ---
DISCORD_PURCHASE_WEBHOOK_URL = (
    os.environ.get("DISCORD_PURCHASE_WEBHOOK_URL")
    or "https://discord.com/api/webhooks/1505767232528191711/ymt9MXOVGKX2Eaz-h9oT8FxyCWesF9LW9WKFqmPggXciqvhx1Fht3Sp_fgKKcD8vGRFd"
).strip()
DISCORD_PURCHASE_WEBHOOK_TIMEOUT = int(os.environ.get("DISCORD_PURCHASE_WEBHOOK_TIMEOUT", "10"))
DISCORD_PURCHASE_BANNER_URL = (
    "https://cdn.discordapp.com/attachments/1505680543633772775/1505767457875296356/"
    "ChatGPT_Image_May_17_2026_09_59_53_PM.png"
)
DISCORD_PURCHASE_THUMBNAIL_URL = (
    "https://media.discordapp.net/attachments/1505680543633772775/1505767517589868545/"
    "itemztrans.png?format=webp&quality=lossless&width=648&height=648"
)

# --- Fortnite browse limits ---
MAX_ACCOUNTS = 50
MAX_PAGES = 10
MARKET_API_TIMEOUT = 10
MAX_PREVIEW_COSMETICS = 8

# --- Redeemed orders tracking ---
REDEEMED_FILE = os.path.join(DATA_DIR, "redeemed_orders.json")

# --- Purchased accounts tracking ---
PURCHASES_FILE = os.path.join(DATA_DIR, "purchased_accounts.json")

# --- Topup history tracking ---
TOPUP_HISTORY_FILE = os.path.join(DATA_DIR, "topup_history.json")

# --- Pending topups (awaiting admin verification) ---
PENDING_TOPUPS_FILE = os.path.join(DATA_DIR, "pending_topups.json")

# --- Topup notifications (approved topups shown to user) ---
TOPUP_NOTIFICATIONS_FILE = os.path.join(DATA_DIR, "topup_notifications.json")

# --- Customer news ---
CUSTOMER_NEWS_FILE = os.path.join(DATA_DIR, "customer_news.json")

# --- Messages / chat ---
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
CHAT_BAN_FILE = os.path.join(DATA_DIR, "chat_bans.json")

# --- Profile uploads ---
PROFILE_UPLOAD_DIR = os.path.join(DATA_DIR, "profile_pics")

# --- Fake reviews config ---
FAKE_REVIEWS_FILE = os.path.join(DATA_DIR, "fake_reviews_config.json")

def _load_fake_reviews_config() -> dict:
    if not os.path.exists(FAKE_REVIEWS_FILE):
        return {"enabled": False, "usernames": [], "per_hour": 5, "texts": []}
    try:
        with open(FAKE_REVIEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"enabled": False, "usernames": [], "per_hour": 5, "texts": []}

def _save_fake_reviews_config(cfg: dict) -> None:
    with open(FAKE_REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def _fake_review_scheduler():
    """Background thread that posts fake reviews periodically."""
    while True:
        try:
            cfg = _load_fake_reviews_config()
            if cfg.get("enabled") and cfg.get("usernames"):
                per_hour = max(1, min(int(cfg.get("per_hour", 5)), 60))
                # Spread reviews across the hour: sleep between each
                usernames = cfg["usernames"]
                texts = cfg.get("texts", [])
                for _ in range(per_hour):
                    username = random.choice(usernames)
                    text = random.choice(texts) if texts else ""
                    reviews = _load_reviews()
                    review = {
                        "id": f"rev_{secrets.token_hex(8)}",
                        "username": username,
                        "rating": 5,
                        "text": text,
                        "image": "",
                        "account_item_id": None,
                        "account_title": "",
                        "status": "approved",
                        "created_at": int(time.time()),
                    }
                    reviews.insert(0, review)
                    _save_reviews(reviews)
                    sleep_sec = 3600 / per_hour
                    time.sleep(sleep_sec)
            else:
                time.sleep(3600)
        except Exception:
            time.sleep(60)

# Start fake review scheduler in background
import threading as _thr
_thr.Thread(target=_fake_review_scheduler, daemon=True).start()

# --- Account view tracking ---
VIEWS_FILE = os.path.join(DATA_DIR, "account_views.json")

def _load_views() -> dict:
    if not os.path.exists(VIEWS_FILE):
        return {}
    try:
        with open(VIEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_views(views: dict) -> None:
    with open(VIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(views, f, indent=2)

def _get_view_count(item_id: int) -> int:
    views = _load_views()
    key = str(item_id)
    return views.get(key, 0)

def _increment_view_count(item_id: int) -> int:
    views = _load_views()
    key = str(item_id)
    views[key] = views.get(key, 0) + 1
    _save_views(views)
    return views[key]

# --- Activity feed ---
ACTIVITY_FILE = os.path.join(DATA_DIR, "activity.json")

def _load_activity() -> list:
    if not os.path.exists(ACTIVITY_FILE):
        return []
    try:
        with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []

def _save_activity(activity: list) -> None:
    with open(ACTIVITY_FILE, "w", encoding="utf-8") as f:
        json.dump(activity, f, indent=2)

MAX_ACTIVITY_ITEMS = 200

def _push_activity(activity_type: str, username: str, details: Optional[dict] = None) -> None:
    activity = _load_activity()
    activity.insert(0, {
        "type": activity_type,
        "username": username,
        "timestamp": int(time.time()),
        "details": details or {},
    })
    if len(activity) > MAX_ACTIVITY_ITEMS:
        activity[:] = activity[:MAX_ACTIVITY_ITEMS]
    _save_activity(activity)

# --- Reviews ---
REVIEWS_FILE = os.path.join(DATA_DIR, "reviews.json")
REVIEW_UPLOADS_DIR = os.path.join(DATA_DIR, "review_uploads")

def _load_reviews() -> list:
    if not os.path.exists(REVIEWS_FILE):
        return []
    try:
        with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []

def _save_reviews(reviews: list) -> None:
    with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(reviews, f, indent=2)

# --- Support tickets ---
SUPPORT_TICKETS_FILE = os.path.join(DATA_DIR, "support_tickets.json")
TICKET_UPLOADS_DIR = os.path.join(DATA_DIR, "ticket_uploads")

# --- Fake orders scheduler config ---
FAKE_ORDERS_FILE = os.path.join(DATA_DIR, "fake_orders_config.json")

# --- Support ticket webhook ---
DISCORD_SUPPORT_TICKET_WEBHOOK_URL = (
    os.environ.get("DISCORD_SUPPORT_TICKET_WEBHOOK_URL")
    or "https://discord.com/api/webhooks/1506143463207600189/MKRAh5Ni644fwlQV-IOdqZHJQHreboHNq8gubrU3Jm_KmNb6sSagBOGvPhFwvrKdgTKe"
).strip()

# --- Blacklist ---
BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist.json")

# --- Pricing ---
PRICING_CONFIG_FILE = os.path.join(DATA_DIR, "pricing_config.json")
DEFAULT_LZT_MULTIPLIER = float(os.environ.get("DEFAULT_LZT_MULTIPLIER", "2.0"))
MIN_LZT_MULTIPLIER = 0.01
MAX_LZT_MULTIPLIER = 100.0


def _load_pricing_config() -> dict:
    if not os.path.exists(PRICING_CONFIG_FILE):
        return {}
    try:
        with open(PRICING_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_pricing_config(config: dict) -> None:
    with open(PRICING_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_lzt_multiplier() -> float:
    config = _load_pricing_config()
    raw = config.get("lzt_multiplier", DEFAULT_LZT_MULTIPLIER)
    try:
        value = float(raw)
    except Exception:
        value = DEFAULT_LZT_MULTIPLIER
    return value if value >= MIN_LZT_MULTIPLIER else DEFAULT_LZT_MULTIPLIER


def set_lzt_multiplier(value: float) -> None:
    config = _load_pricing_config()
    config["lzt_multiplier"] = value
    _save_pricing_config(config)


def get_lzt_multiplier_for_pricing() -> float:
    """Get configured LZT multiplier used for customer pricing."""
    return get_lzt_multiplier()

DEFAULT_OG_MULTIPLIER = float(os.environ.get("DEFAULT_OG_MULTIPLIER", "2.0"))

def get_og_multiplier() -> float:
    config = _load_pricing_config()
    raw = config.get("og_multiplier", DEFAULT_OG_MULTIPLIER)
    try:
        value = float(raw)
    except Exception:
        value = DEFAULT_OG_MULTIPLIER
    return value if value >= MIN_LZT_MULTIPLIER else DEFAULT_OG_MULTIPLIER

def set_og_multiplier(value: float) -> None:
    config = _load_pricing_config()
    config["og_multiplier"] = value
    _save_pricing_config(config)

# --- Discount Config ---
DISCOUNT_CONFIG_FILE = os.path.join(DATA_DIR, "discount_config.json")

def _load_discount_config() -> dict:
    if not os.path.exists(DISCOUNT_CONFIG_FILE):
        return {"enabled": False, "percent": 0, "start": None, "end": None}
    try:
        with open(DISCOUNT_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {"enabled": False, "percent": 0, "start": None, "end": None}

def _save_discount_config(cfg: dict) -> None:
    with open(DISCOUNT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def get_active_discount() -> dict:
    cfg = _load_discount_config()
    if not cfg.get("enabled"):
        return {"active": False, "percent": 0}
    now = time.time()
    start = cfg.get("start")
    end = cfg.get("end")
    if start and now < start:
        return {"active": False, "percent": 0}
    if end and now > end:
        return {"active": False, "percent": 0}
    return {"active": True, "percent": int(cfg.get("percent", 0))}

def apply_discount(price_cents: int) -> int:
    disc = get_active_discount()
    if disc["active"] and disc["percent"] > 0:
        return max(1, int(price_cents * (100 - disc["percent"]) / 100))
    return price_cents

# --- Referral Config ---
REFERRAL_FILE = os.path.join(DATA_DIR, "referrals.json")

def _load_referrals() -> dict:
    if not os.path.exists(REFERRAL_FILE):
        return {"codes": {}, "referral_credit_cents": 500}
    try:
        with open(REFERRAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {"codes": {}, "referral_credit_cents": 500}

def _save_referrals(data: dict) -> None:
    with open(REFERRAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def generate_referral_code(username: str) -> str:
    refs = _load_referrals()
    if username in refs.get("codes", {}):
        return refs["codes"][username]
    code = username[:4].upper() + str(secrets.randbelow(9000) + 1000)
    refs.setdefault("codes", {})[username] = code
    _save_referrals(refs)
    return code

def apply_referral_credit(referrer: str, new_user: str) -> None:
    credit_cents = _load_referrals().get("referral_credit_cents", 500)
    add_balance(referrer, credit_cents)

# --- Loyalty Tiers ---
LOYALTY_FILE = os.path.join(DATA_DIR, "loyalty.json")

def _load_loyalty_config() -> dict:
    default = {"tiers": [
        {"name": "Bronze", "min_spend_cents": 0, "fee_discount": 0},
        {"name": "Silver", "min_spend_cents": 50000, "fee_discount": 5},
        {"name": "Gold", "min_spend_cents": 200000, "fee_discount": 10},
    ]}
    if not os.path.exists(LOYALTY_FILE):
        return default
    try:
        with open(LOYALTY_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or default
    except Exception:
        return default

def _save_loyalty_config(cfg: dict) -> None:
    with open(LOYALTY_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def get_user_tier(total_spent_cents: int) -> dict:
    cfg = _load_loyalty_config()
    tiers = cfg.get("tiers", [])
    best = tiers[0] if tiers else {"name": "Bronze", "min_spend_cents": 0, "fee_discount": 0}
    for t in tiers:
        if total_spent_cents >= t.get("min_spend_cents", 0):
            best = t
    return best

def get_user_total_spent(username: str) -> int:
    from balances_file import get_balance
    purchases = get_user_purchases(username)
    return sum(p.get("amount_cents", 0) for p in purchases)

def get_user_purchases(username: str) -> list:
    if not os.path.exists(PURCHASES_FILE):
        return []
    try:
        with open(PURCHASES_FILE, "r", encoding="utf-8") as f:
            all_purchases = json.load(f) or {}
        return all_purchases.get(username, [])
    except Exception:
        return []

# --- OG Config ---
OG_CONFIG_FILE = os.path.join(DATA_DIR, "og_config.json")

OG_SKINS = [
    {"id": "purple_skull", "name": "Purple Skull Trooper", "icon": "💀"},
    {"id": "pink_ghoul", "name": "Pink Ghoul Trooper", "icon": "👻"},
    {"id": "aerial_assault", "name": "Aerial Assault Trooper", "icon": "🪂"},
    {"id": "renegade_raider", "name": "Renegade Raider", "icon": "🏴‍☠️"},
]

OG_SKIN_KEYWORDS = ['og skull trooper', 'og aerial assault trooper', 'og renegade raider', 'og ghoul trooper']
OG_SKIN_IDS_LOWER = {
    '030_athena_commando_m_halloween_og',
    '017_athena_commando_m_og',
    '028_athena_commando_f_og',
    '029_athena_commando_f_halloween_og',
    'cid_030_athena_commando_m_halloween_og',
    'cid_017_athena_commando_m_og',
    'cid_028_athena_commando_f_og',
    'cid_029_athena_commando_f_halloween_og',
}

def account_has_og_skin(account: dict) -> bool:
    skins = account.get("fortniteSkins") or []
    if not isinstance(skins, list):
        return False
    for entry in skins:
        if isinstance(entry, dict):
            val = (entry.get("id") or entry.get("title") or entry.get("name") or "")
        else:
            val = str(entry)
        lowered = val.strip().lower()
        if lowered in OG_SKIN_IDS_LOWER:
            return True
        if any(kw in lowered for kw in OG_SKIN_KEYWORDS):
            return True
    return False

def get_multiplier_for_account(account: dict) -> float:
    if account_has_og_skin(account):
        return get_og_multiplier()
    return get_lzt_multiplier()

def _load_og_config() -> dict:
    if not os.path.exists(OG_CONFIG_FILE):
        return {"accounts": {s["id"]: [] for s in OG_SKINS}}
    try:
        with open(OG_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {"accounts": {s["id"]: [] for s in OG_SKINS}}

def _save_og_config(cfg: dict) -> None:
    with open(OG_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

OG_WEBHOOK_URL = "https://discord.com/api/webhooks/1518458916105621533/vS4p4vtNv-VoraA-6JNqRRln7CBT3MpPxgh4Saj99dzd8uvZg7lzdC4QM0wvItuA1rC5"

def _load_admins() -> list:
    if not os.path.exists(ADMINS_FILE):
        return []
    try:
        with open(ADMINS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []

def _save_admins(admins: list) -> None:
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        json.dump(admins, f, indent=2)

def is_admin_user(username: str) -> bool:
    if not username:
        return False
    users = _load_users()
    user_data = users.get(username, {})
    if (user_data.get("email") or "").lower() == "konvyvip@gmail.com":
        return True
    if user_data.get("role") == "support":
        return True
    admins = _load_admins()
    return username.lower() in [a.lower() for a in admins]

def _load_chat_bans() -> dict:
    if not os.path.exists(CHAT_BAN_FILE):
        return {"banned_ips": [], "timed_out_users": {}}
    try:
        with open(CHAT_BAN_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {"banned_ips": [], "timed_out_users": {}}
    except Exception:
        return {"banned_ips": [], "timed_out_users": {}}

def _save_chat_bans(bans: dict) -> None:
    with open(CHAT_BAN_FILE, "w", encoding="utf-8") as f:
        json.dump(bans, f, indent=2)

def _is_chat_banned(username: str, ip: str) -> Optional[str]:
    bans = _load_chat_bans()
    if ip in bans.get("banned_ips", []):
        return "You are banned from chat."
    timeout = bans.get("timed_out_users", {}).get(username.lower())
    if timeout and timeout > int(time.time()):
        remaining = timeout - int(time.time())
        return f"You are timed out for {remaining} more seconds."
    if timeout and timeout <= int(time.time()):
        timed_out = bans.get("timed_out_users", {})
        timed_out.pop(username.lower(), None)
        _save_chat_bans(bans)
    return None

def _send_og_restock_webhook(skin_name: str, item_id: int) -> None:
    try:
        import requests as req
        embed = {
            "embeds": [{
                "title": f"🔄 OG Restocked: {skin_name}",
                "description": f"Item ID: **#{item_id}**\nHead to the OGs page to purchase.",
                "color": 0x7C5CFF,
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
        req.post(OG_WEBHOOK_URL, json=embed, timeout=10)
    except Exception:
        pass

# --- User storage ---
USERS_FILE = os.path.join(DATA_DIR, "users.json")


# --- Balances (reuse your balances_file) ---
from balances_file import get_balance as _file_get_balance, add_balance  # uses balances.json

def get_balance(username: str) -> int:
    """Return balance for user."""
    return _file_get_balance(username)


# ===================== USER HELPERS =====================

def _load_users():
    """Load users from users.json: {username: {password_hash: ...}}"""
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_users(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _generate_one_time_code() -> str:
    return str(secrets.randbelow(900000) + 100000)


def _is_valid_email_address(email: str) -> bool:
    normalized = _normalize_email(email)
    if not normalized or normalized.count("@") != 1:
        return False

    local_part, domain_part = normalized.split("@", 1)
    if not local_part or not domain_part or domain_part.startswith(".") or domain_part.endswith("."):
        return False

    allowed_local_chars = set("abcdefghijklmnopqrstuvwxyz0123456789._+-")
    if any(ch not in allowed_local_chars for ch in local_part):
        return False

    domain_labels = domain_part.split(".")
    if len(domain_labels) < 2 or len(domain_labels[-1]) < 2:
        return False

    for label in domain_labels:
        if not label or label.startswith("-") or label.endswith("-"):
            return False
        if any(not (ch.isalnum() or ch == "-") for ch in label):
            return False

    return True


def _hash_one_time_code(code: str) -> str:
    return generate_password_hash(code or "")


def _is_email_configured() -> bool:
    return all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM])


def _send_email_message(recipient: str, subject: str, body: str, html_body: str = "") -> Tuple[bool, str]:
    if not _is_email_configured():
        return False, "Email is not configured yet. Add SMTP env values first."

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = EMAIL_FROM
    message["To"] = recipient
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(message)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(message)
    except Exception as exc:
        return False, f"Could not send email: {exc}"

    return True, "Email sent."


def _itemz_email_html(title: str, subtitle: str, code: str, expire_minutes: int, footer_note: str) -> str:
    """Render a branded Konvy Accounts HTML email."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title></head>
<body style="margin:0;padding:0;background:#0d0d0d;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d0d;min-height:100vh;">
<tr><td align="center" style="padding:40px 16px;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">

    <!-- Logo / Brand -->
    <tr><td align="center" style="padding-bottom:28px;">
      <span style="font-family:'Segoe UI',Arial,sans-serif;font-size:26px;font-weight:900;letter-spacing:-0.5px;">
        <span style="color:#00c8ff;">Konvy</span><span style="color:#ffffff;"> Accounts</span>
      </span>
    </td></tr>

    <!-- Card -->
    <tr><td style="background:#161616;border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:36px 32px;">

      <!-- Title -->
      <p style="margin:0 0 6px;font-size:22px;font-weight:700;color:#ffffff;">{title}</p>
      <p style="margin:0 0 28px;font-size:14px;color:#a1a1aa;line-height:1.55;">{subtitle}</p>

      <!-- Code box -->
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center" style="padding:22px 0;background:#0d0d0d;border:1px solid rgba(0,200,255,0.25);border-radius:14px;">
          <span style="font-size:38px;font-weight:900;letter-spacing:10px;color:#00c8ff;font-family:'Courier New',monospace;">{code}</span>
        </td></tr>
      </table>

      <p style="margin:20px 0 0;font-size:13px;color:#71717a;text-align:center;line-height:1.55;">
        This code expires in <strong style="color:#e4e4e7;">{expire_minutes} minutes</strong>.<br>
        {footer_note}
      </p>

    </td></tr>

    <!-- Footer -->
    <tr><td align="center" style="padding-top:24px;">
      <p style="margin:0;font-size:12px;color:#3f3f46;">
        &copy; 2026 Konvy Accounts &nbsp;&bull;&nbsp;
        <a href="mailto:support@konvyaccounts.com" style="color:#00c8ff;text-decoration:none;">support@konvyaccounts.com</a>
      </p>
    </td></tr>

  </table>
</td></tr>
</table>
</body>
</html>"""


def find_username_by_email(email: str, users: Optional[dict] = None) -> Optional[str]:
    normalized = _normalize_email(email)
    if not normalized:
        return None

    loaded_users = users if users is not None else _load_users()
    for username, info in loaded_users.items():
        if _normalize_email(info.get("email", "")) == normalized:
            return username
    return None


def get_user_email(username: str) -> str:
    users = _load_users()
    return _normalize_email(users.get(username, {}).get("email", ""))


def is_email_verified(username: str) -> bool:
    users = _load_users()
    info = users.get(username, {})
    if not info.get("email"):
        return True
    return bool(info.get("email_verified"))


def mark_email_verified(username: str) -> bool:
    users = _load_users()
    if username not in users:
        return False
    users[username]["email_verified"] = True
    users[username].pop("email_verification_code_hash", None)
    users[username].pop("email_verification_expires_at", None)
    _save_users(users)
    return True


def update_user_password(username: str, password: str) -> bool:
    users = _load_users()
    if username not in users:
        return False
    users[username]["password_hash"] = generate_password_hash(password)
    users[username].pop("password_reset_code_hash", None)
    users[username].pop("password_reset_expires_at", None)
    _save_users(users)
    return True


def _set_one_time_code(username: str, code_field: str, expiry_field: str, code: str) -> bool:
    users = _load_users()
    if username not in users:
        return False
    users[username][code_field] = _hash_one_time_code(code)
    users[username][expiry_field] = int(time.time()) + EMAIL_CODE_TTL_SECONDS
    _save_users(users)
    return True


def _verify_one_time_code(username: str, code_field: str, expiry_field: str, submitted_code: str) -> bool:
    users = _load_users()
    info = users.get(username)
    if not info:
        return False

    expires_at = int(info.get(expiry_field) or 0)
    stored_hash = info.get(code_field) or ""
    if not stored_hash or expires_at < int(time.time()):
        return False

    return check_password_hash(stored_hash, (submitted_code or "").strip())


def send_email_verification_code(username: str) -> Tuple[bool, str]:
    recipient = get_user_email(username)
    if not recipient:
        return False, "This account does not have an email address."

    code = _generate_one_time_code()
    if not _set_one_time_code(username, "email_verification_code_hash", "email_verification_expires_at", code):
        return False, "Could not prepare verification code."

    expire_minutes = EMAIL_CODE_TTL_SECONDS // 60
    subject = "Your Konvy Accounts verification code"
    body = (
        f"Hi {username},\n\n"
        f"Your Konvy Accounts email verification code is: {code}\n\n"
        f"This code expires in {expire_minutes} minutes.\n"
        "If you did not create this account, you can ignore this email.\n"
    )
    html_body = _itemz_email_html(
        title="Verify Your Email",
        subtitle=f"Hi {username}, enter the code below to verify your Konvy Accounts account.",
        code=code,
        expire_minutes=expire_minutes,
        footer_note="If you did not create a Konvy Accounts account, you can safely ignore this email.",
    )
    ok, msg = _send_email_message(recipient, subject, body, html_body)
    if not ok:
        return False, msg
    return True, "We sent a 6-digit verification code to your email."


def send_password_reset_code(username: str) -> Tuple[bool, str]:
    recipient = get_user_email(username)
    if not recipient:
        return False, "This account does not have an email address."

    code = _generate_one_time_code()
    if not _set_one_time_code(username, "password_reset_code_hash", "password_reset_expires_at", code):
        return False, "Could not prepare reset code."

    expire_minutes = EMAIL_CODE_TTL_SECONDS // 60
    subject = "Your Konvy Accounts password reset code"
    body = (
        f"Hi {username},\n\n"
        f"Your Konvy Accounts password reset code is: {code}\n\n"
        f"This code expires in {expire_minutes} minutes.\n"
        "If you did not request a password reset, you can ignore this email.\n"
    )
    html_body = _itemz_email_html(
        title="Reset Your Password",
        subtitle=f"Hi {username}, use the code below to reset your Konvy Accounts password.",
        code=code,
        expire_minutes=expire_minutes,
        footer_note="If you did not request a password reset, you can safely ignore this email.",
    )
    ok, msg = _send_email_message(recipient, subject, body, html_body)
    if not ok:
        return False, msg
    return True, "We sent a 6-digit reset code to your email."


def _username_exists_ci(username: str, users: Optional[dict] = None) -> bool:
    if users is None:
        users = _load_users()
    lowered = username.strip().lower()
    return any(k.lower() == lowered for k in users)

def _rename_user_in_all_stores(old: str, new: str) -> None:
    users = _load_users()
    if old in users:
        users[new] = users.pop(old)
        _save_users(users)
    try:
        from balances_file import _load_balances, _save_balances
        bals = _load_balances()
        if old in bals:
            bals[new] = bals.pop(old)
            _save_balances(bals)
    except Exception:
        pass
    try:
        pur = _load_purchases()
        if old in pur:
            pur[new] = pur.pop(old)
            _save_purchases(pur)
    except Exception:
        pass

def create_user(username: str, password: str, email: str) -> bool:
    if password == username:
        return False
    users = _load_users()
    if _username_exists_ci(username, users):
        return False

    normalized_email = _normalize_email(email)
    users[username] = {
        "password_hash": generate_password_hash(password),
        "email": normalized_email,
        "email_verified": False if normalized_email else True,
        "bio": "",
        "profile_pic": "",
        "last_online": 0,
        "online": False,
    }
    _save_users(users)
    return True


def verify_user(username: str, password: str) -> bool:
    users = _load_users()
    info = users.get(username)
    if not info:
        return False
    return check_password_hash(info["password_hash"], password)


# ===================== REDEEMED ORDERS HELPERS =====================


def _load_redeemed() -> Set[str]:
    if not os.path.exists(REDEEMED_FILE):
        return set()
    try:
        with open(REDEEMED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(str(x) for x in data)
    except Exception:
        return set()


def _save_redeemed(redeemed: Set[str]) -> None:
    with open(REDEEMED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(redeemed), f, indent=2)


def is_redeemed(order_id: str) -> bool:
    redeemed = _load_redeemed()
    return str(order_id) in redeemed


def mark_redeemed(order_id: str) -> None:
    redeemed = _load_redeemed()
    redeemed.add(str(order_id))
    _save_redeemed(redeemed)


# ===================== TOPUP HISTORY HELPERS =====================

def _load_topup_history() -> dict:
    if not os.path.exists(TOPUP_HISTORY_FILE):
        return {}
    try:
        with open(TOPUP_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_topup_history(history: dict) -> None:
    with open(TOPUP_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def add_topup_record(username: str, amount_cents: int, order_id: str, status: str = "completed") -> None:
    history = _load_topup_history()
    user_topups = history.get(username, [])
    user_topups.append({
        "timestamp": int(time.time()),
        "amount_cents": amount_cents,
        "order_id": order_id,
        "status": status,
    })
    history[username] = user_topups
    _save_topup_history(history)


def user_has_any_topup(username: str) -> bool:
    history = _load_topup_history()
    return len(history.get(username, [])) > 0


# ===================== PENDING TOPUPS HELPERS =====================

def _load_pending_topups() -> list:
    if not os.path.exists(PENDING_TOPUPS_FILE):
        return []
    try:
        with open(PENDING_TOPUPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []


def _save_pending_topups(pending: list) -> None:
    with open(PENDING_TOPUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2)


def add_pending_topup(username: str, amount_cents: int, order_id: str) -> None:
    pending = _load_pending_topups()
    pending.append({
        "id": f"{username}_{order_id}_{int(time.time())}",
        "username": username,
        "amount_cents": amount_cents,
        "order_id": order_id,
        "timestamp": int(time.time()),
        "status": "pending",
    })
    _save_pending_topups(pending)
    mark_redeemed(order_id)


# ===================== TOPUP NOTIFICATIONS HELPERS =====================

def _load_topup_notifications() -> dict:
    if not os.path.exists(TOPUP_NOTIFICATIONS_FILE):
        return {}
    try:
        with open(TOPUP_NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_topup_notifications(data: dict) -> None:
    with open(TOPUP_NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_topup_notification(username: str, amount_cents: int, notif_id: str) -> None:
    data = _load_topup_notifications()
    user_notifs = data.get(username, [])
    user_notifs.append({
        "id": notif_id,
        "amount_cents": amount_cents,
        "timestamp": int(time.time()),
        "seen": False,
    })
    data[username] = user_notifs
    _save_topup_notifications(data)


def get_user_notifications(username: str) -> list:
    data = _load_topup_notifications()
    return [n for n in data.get(username, []) if not n.get("seen", False)]


def dismiss_notification(username: str, notif_id: str) -> bool:
    data = _load_topup_notifications()
    user_notifs = data.get(username, [])
    found = False
    for n in user_notifs:
        if n["id"] == notif_id:
            n["seen"] = True
            found = True
            break
    if found:
        data[username] = user_notifs
        _save_topup_notifications(data)
    return found


# ===================== SUPPORT TICKETS HELPERS =====================

SUPPORT_TICKET_SUBJECT_MAX_LENGTH = 120
SUPPORT_TICKET_MESSAGE_MAX_LENGTH = 2000
TICKET_UPLOAD_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB per file
TICKET_UPLOAD_MAX_FILES_PER_MESSAGE = 5
TICKET_UPLOAD_ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp",
    "mp4", "mov", "avi", "webm",
    "zip",
    "pdf",
}


def _ticket_upload_allowed(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in TICKET_UPLOAD_ALLOWED_EXTENSIONS


def _save_ticket_attachments(ticket_id: str, files) -> Tuple[list, Optional[str]]:
    """Save uploaded files for a ticket message.

    Returns (attachments_list, error_message).
    attachments_list entries: {"stored_name": "...", "original_name": "..."}
    """
    if not files:
        return [], None
    file_list = files if isinstance(files, list) else [files]
    if len(file_list) > TICKET_UPLOAD_MAX_FILES_PER_MESSAGE:
        return [], f"Maximum {TICKET_UPLOAD_MAX_FILES_PER_MESSAGE} files per message."
    # Validate ticket_id to prevent path traversal
    if not re.fullmatch(r"tkt_[0-9a-f]{12}", ticket_id):
        return [], "Invalid ticket ID."
    ticket_dir = os.path.join(TICKET_UPLOADS_DIR, ticket_id)
    # Explicit canonicalization check as defense-in-depth against path traversal
    resolved = os.path.realpath(ticket_dir)
    safe_root = os.path.realpath(TICKET_UPLOADS_DIR)
    if not resolved.startswith(safe_root + os.sep):
        return [], "Invalid ticket ID."
    os.makedirs(resolved, exist_ok=True)
    attachments = []
    for f in file_list:
        original_name = f.filename or ""
        if not original_name:
            continue
        if not _ticket_upload_allowed(original_name):
            return [], f"File type not allowed: {original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else 'unknown'}"
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > TICKET_UPLOAD_MAX_SIZE_BYTES:
            return [], f"File too large (max {TICKET_UPLOAD_MAX_SIZE_BYTES // (1024 * 1024)} MB): {original_name}"
        safe = secure_filename(original_name) or "file"
        stored_name = f"{secrets.token_hex(8)}_{safe}"
        dest = os.path.join(resolved, stored_name)
        f.save(dest)
        attachments.append({"stored_name": stored_name, "original_name": original_name})
    return attachments, None


def _load_support_tickets() -> list:
    if not os.path.exists(SUPPORT_TICKETS_FILE):
        return []
    try:
        with open(SUPPORT_TICKETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or []
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_support_tickets(tickets: list) -> None:
    with open(SUPPORT_TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2)


def _format_ticket_text(value: Any, max_length: int) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        trim_limit = max(max_length - 3, 1)
        truncated = text[:trim_limit].rstrip()
        boundary = truncated.rfind(" ")
        if boundary >= max(trim_limit // 2, 1):
            truncated = truncated[:boundary].rstrip()
        if not truncated:
            truncated = (text[:trim_limit] or text[:1]).strip() or text[:1]
        text = f"{truncated}..."
    return text


def _sort_support_tickets(tickets: list) -> list:
    def _ts(value: Any) -> int:
        try:
            parsed = int(value or 0)
            return parsed if parsed > 0 else -1
        except Exception:
            return -1

    return sorted(
        tickets,
        key=lambda t: (_ts(t.get("updated_at")), _ts(t.get("created_at"))),
        reverse=True,
    )


def _serialize_ticket_for_user(ticket: dict, with_internal_notes: bool = False) -> dict:
    messages = ticket.get("messages") if isinstance(ticket.get("messages"), list) else []
    last_message = messages[-1] if messages else {}
    result = {
        "id": str(ticket.get("id") or ""),
        "username": str(ticket.get("username") or ""),
        "subject": str(ticket.get("subject") or "Support Request"),
        "status": str(ticket.get("status") or "open"),
        "priority": str(ticket.get("priority") or "medium"),
        "linked_item_id": ticket.get("linked_item_id"),
        "created_at": int(ticket.get("created_at") or 0),
        "updated_at": int(ticket.get("updated_at") or 0),
        "closed_at": int(ticket.get("closed_at") or 0),
        "closed_by": str(ticket.get("closed_by") or ""),
        "messages": messages,
        "last_message_from_admin": str(last_message.get("author_type") or "") == "admin",
        "last_message_author_type": str(last_message.get("author_type") or ""),
        "needs_admin_response": (
            str(ticket.get("status") or "") == "open"
            and str(last_message.get("author_type") or "") == "user"
        ),
        "last_message_preview": str(last_message.get("message") or "")[:140],
    }
    if with_internal_notes:
        result["internal_notes"] = ticket.get("internal_notes", [])
    return result


def _find_ticket(tickets: list, ticket_id: str) -> Optional[dict]:
    for ticket in tickets:
        if str(ticket.get("id")) == str(ticket_id):
            return ticket
    return None


def _new_ticket_message(author_type: str, author: str, message: str, attachments: Optional[list] = None) -> dict:
    return {
        "id": secrets.token_hex(8),
        "author_type": author_type,
        "author": author,
        "message": message,
        "attachments": attachments or [],
        "timestamp": int(time.time()),
    }



def _send_new_ticket_webhook(ticket: dict) -> None:
    try:
        embed = {
            "title": "🎫 New Support Ticket",
            "color": 0x00C8FF,
            "fields": [
                {"name": "Ticket ID", "value": str(ticket.get("id") or ""), "inline": True},
                {"name": "User", "value": str(ticket.get("username") or ""), "inline": True},
                {"name": "Subject", "value": str(ticket.get("subject") or "")[:256], "inline": False},
                {
                    "name": "Message",
                    "value": str((ticket.get("messages") or [{}])[0].get("message") or "")[:1024],
                    "inline": False,
                },
            ],
            "footer": {"text": "Konvy Accounts Support"},
            "timestamp": datetime.datetime.fromtimestamp(
                ticket.get("created_at") or time.time(), tz=datetime.timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        requests.post(DISCORD_SUPPORT_TICKET_WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
    except Exception as exc:
        app.logger.warning("Failed to send new-ticket Discord webhook: %s", exc)


def _send_ticket_reply_notification_email(username: str, ticket: dict, reply_message: str, site_url: str) -> None:
    """Send an email to the ticket owner notifying them of an admin reply."""
    if not _is_email_configured():
        return
    recipient = get_user_email(username)
    if not recipient:
        return
    ticket_id = ticket.get("id") or ""
    subject_text = ticket.get("subject") or "your support ticket"
    reply_url = f"{site_url.rstrip('/')}?ticket={ticket_id}"
    preview = (reply_message or "").strip()[:300]
    if len((reply_message or "")) > 300:
        preview += "…"
    subject = f"[Konvy Accounts Support] Admin replied to: {subject_text[:80]}"
    body = (
        f"Hi {username},\n\n"
        f"An admin has replied to your support ticket \"{subject_text}\".\n\n"
        f"Reply:\n{preview}\n\n"
        f"Visit your support page to reply back:\n{reply_url}\n\n"
        "— Konvy Accounts Support Team"
    )
    # Build a branded HTML version
    safe_username = username.replace("<", "&lt;").replace(">", "&gt;")
    safe_subject = subject_text.replace("<", "&lt;").replace(">", "&gt;")
    safe_preview = preview.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Admin replied to your ticket</title></head>
<body style="margin:0;padding:0;background:#0d0d0d;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d0d;min-height:100vh;">
<tr><td align="center" style="padding:40px 16px;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">
    <tr><td align="center" style="padding-bottom:28px;">
      <span style="font-family:'Segoe UI',Arial,sans-serif;font-size:26px;font-weight:900;letter-spacing:-0.5px;">
        <span style="color:#00c8ff;">Konvy</span><span style="color:#ffffff;"> Accounts</span>
      </span>
    </td></tr>
    <tr><td style="background:#161616;border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:36px 32px;">
      <p style="margin:0 0 6px;font-size:22px;font-weight:700;color:#ffffff;">Admin Replied to Your Ticket</p>
      <p style="margin:0 0 20px;font-size:14px;color:#a1a1aa;line-height:1.55;">Hi <strong style="color:#e4e4e7;">{safe_username}</strong>, an admin has responded to your support ticket <strong style="color:#e4e4e7;">"{safe_subject}"</strong>.</p>
      <div style="background:#0d0d0d;border:1px solid rgba(0,200,255,0.2);border-radius:12px;padding:18px 20px;margin-bottom:24px;">
        <p style="margin:0;font-size:14px;color:#d4d4d8;line-height:1.65;">{safe_preview}</p>
      </div>
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center">
          <a href="{reply_url}" style="display:inline-block;padding:13px 32px;background:linear-gradient(135deg,#00c8ff,#8b5cf6);color:#ffffff;font-weight:700;font-size:15px;border-radius:10px;text-decoration:none;letter-spacing:0.3px;">View &amp; Reply</a>
        </td></tr>
      </table>
      <p style="margin:20px 0 0;font-size:13px;color:#71717a;text-align:center;line-height:1.55;">
        If the button doesn't work, copy this link:<br>
        <a href="{reply_url}" style="color:#00c8ff;text-decoration:none;word-break:break-all;">{reply_url}</a>
      </p>
    </td></tr>
    <tr><td align="center" style="padding-top:24px;">
      <p style="margin:0;font-size:12px;color:#3f3f46;">
        &copy; 2026 Konvy Accounts &nbsp;&bull;&nbsp;
        <a href="mailto:support@konvyaccounts.com" style="color:#00c8ff;text-decoration:none;">support@konvyaccounts.com</a>
      </p>
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>"""
    try:
        _send_email_message(recipient, subject, body, html_body)
    except Exception as exc:
        app.logger.warning("Failed to send ticket reply notification email: %s", exc)


def create_support_ticket(username: str, subject: str, message: str, attachments: Optional[list] = None) -> Tuple[bool, str, Optional[dict]]:
    clean_subject = _format_ticket_text(subject, SUPPORT_TICKET_SUBJECT_MAX_LENGTH)
    clean_message = _format_ticket_text(message, SUPPORT_TICKET_MESSAGE_MAX_LENGTH)
    if not clean_subject:
        return False, "Subject is required.", None
    if not clean_message and not attachments:
        return False, "Message is required.", None

    tickets = _load_support_tickets()
    existing_open = any(
        str(t.get("username") or "") == username and str(t.get("status") or "") == "open"
        for t in tickets
    )
    if existing_open:
        return False, "You already have an open ticket. Please wait for it to be resolved or close it before opening a new one.", None

    # Extract linked account ID from subject or message
    linked_item_id = None
    combined = (clean_subject + " " + clean_message)
    m = re.search(r'account #(\d+)', combined, re.IGNORECASE)
    if m:
        try:
            linked_item_id = int(m.group(1))
        except ValueError:
            pass

    now = int(time.time())
    ticket = {
        "id": f"tkt_{secrets.token_hex(6)}",
        "username": username,
        "subject": clean_subject,
        "status": "open",
        "priority": "medium",
        "internal_notes": [],
        "linked_item_id": linked_item_id,
        "created_at": now,
        "updated_at": now,
        "closed_at": 0,
        "closed_by": "",
        "messages": [_new_ticket_message("user", username, clean_message, attachments)],
    }
    tickets.append(ticket)
    _save_support_tickets(_sort_support_tickets(tickets))
    threading.Thread(target=_send_new_ticket_webhook, args=(ticket,), daemon=True).start()
    return True, "Ticket created.", ticket


def _append_ticket_message(ticket: dict, author_type: str, author: str, message: str, attachments: Optional[list] = None) -> Tuple[bool, str]:
    if str(ticket.get("status") or "") != "open":
        return False, "This ticket is closed. Please open a new ticket if you need further assistance."
    clean_message = _format_ticket_text(message, SUPPORT_TICKET_MESSAGE_MAX_LENGTH)
    if not clean_message and not attachments:
        return False, "Message is required."
    messages = ticket.get("messages") if isinstance(ticket.get("messages"), list) else []
    messages.append(_new_ticket_message(author_type, author, clean_message, attachments))
    ticket["messages"] = messages
    ticket["updated_at"] = int(time.time())
    return True, "Reply sent."


def _close_ticket(ticket: dict, closed_by: str) -> Tuple[bool, str]:
    if str(ticket.get("status") or "") == "closed":
        return False, "Ticket is already closed."
    now = int(time.time())
    ticket["status"] = "closed"
    ticket["closed_at"] = now
    ticket["closed_by"] = closed_by
    ticket["updated_at"] = now
    return True, "Ticket closed."


# ===================== BLACKLIST HELPERS =====================

def _load_blacklist() -> set:
    if not os.path.exists(BLACKLIST_FILE):
        return set()
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_blacklist(bl: set) -> None:
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(list(bl), f, indent=2)


def is_blacklisted(username: str) -> bool:
    return username in _load_blacklist()


# ===================== VERIFICATION HELPERS =====================

def get_user_verification_status(username: str) -> str:
    """Returns: 'unverified', 'verified', 'verify_each', 'blacklisted'"""
    if is_blacklisted(username):
        return "blacklisted"
    users = _load_users()
    return users.get(username, {}).get("verification_status", "unverified")


def set_user_verification_status(username: str, status: str) -> None:
    users = _load_users()
    if username in users:
        users[username]["verification_status"] = status
        _save_users(users)


# ===================== PURCHASED ACCOUNTS HELPERS =====================


def _load_purchases() -> dict:
    if not os.path.exists(PURCHASES_FILE):
        return {}
    try:
        with open(PURCHASES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_purchases(purchases: dict) -> None:
    with open(PURCHASES_FILE, "w", encoding="utf-8") as f:
        json.dump(purchases, f, indent=2)


def add_purchase(username: str, purchase_result, latest_order, amount_cents: int = 0) -> dict:
    """
    Save a purchased account for this user and return the entry that was saved.
    We store the full purchase_result so credentials/details are kept.
    """
    purchases = _load_purchases()
    user_list = purchases.get(username, [])
    entry = {
        "timestamp": int(time.time()),
        "purchase_result": purchase_result,
        "latest_order": latest_order,
        "amount_cents": amount_cents,
    }
    user_list.append(entry)
    purchases[username] = user_list
    _save_purchases(purchases)
    return entry


def get_purchases(username: str):
    purchases = _load_purchases()
    return purchases.get(username, [])


def is_item_sold(item_id: int) -> bool:
    """Check if an item_id exists in any user's purchase records."""
    purchases = _load_purchases()
    for user_list in purchases.values():
        if not isinstance(user_list, list):
            continue
        for entry in user_list:
            if not isinstance(entry, dict):
                continue
            existing_id = _extract_purchase_item_id(entry.get("purchase_result"))
            if existing_id is not None and existing_id == item_id:
                return True
    return False


def save_purchase_record(
    username: str,
    purchase_result: Any,
    latest_order: Optional[dict],
    amount_cents: int = 0,
) -> Tuple[dict, list, int]:
    """Update an existing saved purchase for the same item or append a new purchase entry."""
    purchases = _load_purchases()
    user_list = purchases.get(username, [])
    item_id = _extract_purchase_item_id(purchase_result)

    if item_id is not None:
        for index in range(len(user_list) - 1, -1, -1):
            existing_entry = user_list[index] if isinstance(user_list[index], dict) else {}
            existing_result = existing_entry.get("purchase_result")
            if _extract_purchase_item_id(existing_result) != item_id:
                continue

            updated = False
            if latest_order and not existing_entry.get("latest_order"):
                existing_entry["latest_order"] = latest_order
                updated = True
            if (
                isinstance(purchase_result, dict)
                and _purchase_result_has_credentials(purchase_result)
                and not _purchase_result_has_credentials(existing_result)
            ):
                existing_entry["purchase_result"] = purchase_result
                updated = True
            if amount_cents and not existing_entry.get("amount_cents"):
                existing_entry["amount_cents"] = amount_cents
                updated = True

            if updated:
                user_list[index] = existing_entry
                purchases[username] = user_list
                _save_purchases(purchases)

            return existing_entry, user_list, index

    entry = add_purchase(username, purchase_result, latest_order, amount_cents)
    user_list = get_purchases(username)
    return entry, user_list, len(user_list) - 1


def _format_purchase_webhook_currency(amount: Any) -> str:
    try:
        numeric_amount = float(amount or 0)
    except (TypeError, ValueError):
        numeric_amount = 0.0
    return f"${numeric_amount:.2f}"


def _safe_webhook_display_username(username: Any) -> str:
    cleaned = str(username or "").strip()
    if not cleaned:
        return "Unknown"
    # Prevent Discord mass-mention formatting in webhook embeds by inserting U+200B.
    cleaned = cleaned.replace("@", "@\u200b")
    return cleaned[:64]


def _get_purchase_item_summary(item: dict) -> str:
    if not isinstance(item, dict):
        return "Fortnite Account"

    title = str(item.get("title_en") or item.get("title") or "").strip()
    if title:
        return title[:1024]

    try:
        skin_count = int(item.get("fortnite_skin_count") or 0)
    except (TypeError, ValueError):
        skin_count = 0

    if skin_count > 0:
        return f"{skin_count} Skins | Fortnite Account"
    return "Fortnite Account"


def _build_purchase_webhook_payload(
    purchase_result: dict,
    latest_order: Optional[dict],
    user_price: float,
    username: str,
) -> dict:
    item = (purchase_result or {}).get("item") or {}
    item_id = item.get("item_id") or item.get("fortnite_item_id") or "N/A"
    product_summary = _get_purchase_item_summary(item)
    order_ref = None
    if isinstance(latest_order, dict):
        order_ref = latest_order.get("order_id") or latest_order.get("id") or latest_order.get("order_number")

    fields = [
        {
            "name": "👤 User",
            "value": _safe_webhook_display_username(username),
            "inline": True,
        },
        {
            "name": "💳 Payment Method",
            "value": "Balance",
            "inline": True,
        },
        {
            "name": "Status",
            "value": "Purchased",
            "inline": True,
        },
        {
            "name": "💰 USD Spent",
            "value": _format_purchase_webhook_currency(user_price),
            "inline": True,
        },
        {
            "name": "⭐ Review",
            "value": "5/5",
            "inline": True,
        },
        {
            "name": "📦 Account",
            "value": product_summary,
            "inline": False,
        },
        {
            "name": "🆔 Item ID",
            "value": str(item_id),
            "inline": True,
        },
    ]

    if order_ref:
        fields.append(
            {
                "name": "🧾 Order Ref",
                "value": str(order_ref),
                "inline": True,
            }
        )

    return {
        "username": "Konvy Accounts",
        "avatar_url": DISCORD_PURCHASE_THUMBNAIL_URL,
        "embeds": [
            {
                "title": "✅ Order Confirmed - Thank You!",
                "description": "Your Konvy Accounts Fortnite purchase was completed successfully.",
                "color": 0x00c8ff,
                "author": {
                    "name": "Konvy Accounts Purchase Notification",
                    "icon_url": DISCORD_PURCHASE_THUMBNAIL_URL,
                },
                "thumbnail": {
                    "url": DISCORD_PURCHASE_THUMBNAIL_URL,
                },
                "image": {
                    "url": DISCORD_PURCHASE_BANNER_URL,
                },
                "fields": fields,
                "footer": {
                    "text": "Powered by Konvy Accounts",
                    "icon_url": DISCORD_PURCHASE_THUMBNAIL_URL,
                },
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        ],
    }


def send_purchase_discord_webhook(
    purchase_result: dict,
    latest_order: Optional[dict],
    user_price: float,
    username: str,
) -> None:
    if not DISCORD_PURCHASE_WEBHOOK_URL:
        return

    payload = _build_purchase_webhook_payload(purchase_result, latest_order, user_price, username)
    webhook_logger = logging.getLogger("purchase_webhook")

    try:
        response = requests.post(
            DISCORD_PURCHASE_WEBHOOK_URL,
            json=payload,
            timeout=DISCORD_PURCHASE_WEBHOOK_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        webhook_logger.warning("Purchase webhook send failed: %s", exc)


# ===================== FAKE ORDERS SCHEDULER =====================

_CHICAGO_TZ = ZoneInfo("America/Chicago")
_fake_orders_lock = threading.Lock()
_fake_orders_scheduler_started = False
_fake_orders_scheduler_lock = threading.Lock()
_FAKE_SCHEDULER_POLL_INTERVAL = 30       # seconds to sleep while disabled / no usernames
_FAKE_MIN_HOUR_REMAINING_SECONDS = 60    # minimum remaining window to attempt scheduling

# Account product names to randomly pick from for fake embeds
_FAKE_ACCOUNT_TITLES = [
    "Black Knight | 47 Skins",
    "Renegade Raider | 31 Skins",
    "Galaxy Scout | 22 Skins",
    "Aerial Assault Trooper | 18 Skins",
    "Skull Trooper | 39 Skins",
    "Ghoul Trooper | 27 Skins",
    "Season 2 OG | 14 Skins",
    "Wonder | 55 Skins",
    "Purple Skull Trooper | 33 Skins",
    "Ikonik | 11 Skins",
    "Recon Expert | 29 Skins",
    "Travis Scott | 8 Skins",
    "Merry Marauder | 43 Skins",
    "Eon | 16 Skins",
    "Dark Voyager | 52 Skins",
    "Double Helix | 7 Skins",
    "Minty Pickaxe | 19 Skins",
    "OG Account | 64 Skins",
    "John Wick | 38 Skins",
    "The Reaper | 24 Skins",
]


def _random_fake_price() -> float:
    """
    Returns a random fake USD price.
    ~10% cheap ($1.00-$4.99), ~70% mid ($10-$24.99), ~20% high ($60-$120)
    """
    roll = random.random()
    if roll < 0.10:
        # Cheap — include odd cents
        return round(random.uniform(1.00, 4.99), 2)
    elif roll < 0.80:
        # Mid range
        return round(random.uniform(10.00, 24.99), 2)
    else:
        # High
        return round(random.uniform(60.00, 120.00), 2)


def _random_fake_item_id() -> int:
    return random.randint(100000, 9999999)


def _build_fake_purchase_webhook_payload(username: str) -> dict:
    price = _random_fake_price()
    title = random.choice(_FAKE_ACCOUNT_TITLES)
    item_id = _random_fake_item_id()
    purchase_result = {
        "item": {
            "item_id": item_id,
            "title_en": title,
        }
    }
    return _build_purchase_webhook_payload(purchase_result, None, price, username)


def _send_one_fake_order(username: str) -> None:
    if not DISCORD_PURCHASE_WEBHOOK_URL:
        return
    payload = _build_fake_purchase_webhook_payload(username)
    try:
        r = requests.post(
            DISCORD_PURCHASE_WEBHOOK_URL,
            json=payload,
            timeout=DISCORD_PURCHASE_WEBHOOK_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException as exc:
        app.logger.warning("Fake order webhook failed: %s", exc)


def _load_fake_orders_config() -> dict:
    if not os.path.exists(FAKE_ORDERS_FILE):
        return {"enabled": False, "usernames": []}
    try:
        with open(FAKE_ORDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"enabled": False, "usernames": []}
            return data
    except Exception:
        return {"enabled": False, "usernames": []}


def _save_fake_orders_config(cfg: dict) -> None:
    with open(FAKE_ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _chicago_hour_now() -> int:
    """Return current hour (0-23) in Chicago time."""
    return datetime.datetime.now(tz=_CHICAGO_TZ).hour


def _orders_for_current_hour() -> int:
    """
    Return how many fake orders to send during the current Chicago hour.
    9am-11pm (hour 9..22): uniform 6-12
    11pm-9am (hour 23 or 0..8): 60% chance of 0, 40% chance of 1-2
    """
    hour = _chicago_hour_now()
    if 9 <= hour <= 22:
        return random.randint(6, 12)
    else:
        if random.random() < 0.60:
            return 0
        return random.randint(1, 2)


def _fake_orders_scheduler_loop() -> None:
    """
    Each iteration handles one full Chicago hour.
    Decides how many orders to send that hour, spaces them evenly with jitter.
    """
    while True:
        cfg = _load_fake_orders_config()
        if not cfg.get("enabled"):
            time.sleep(_FAKE_SCHEDULER_POLL_INTERVAL)
            continue

        usernames = [u for u in (cfg.get("usernames") or []) if u]
        if not usernames:
            time.sleep(_FAKE_SCHEDULER_POLL_INTERVAL)
            continue

        count = _orders_for_current_hour()

        if count == 0:
            # Sleep until the top of the next hour
            now = datetime.datetime.now(tz=_CHICAGO_TZ)
            next_hour = (now + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            sleep_secs = max((next_hour - now).total_seconds(), 1)
            time.sleep(sleep_secs)
            continue

        # Spread `count` orders across the hour (3600 seconds) with random spacing
        now_chicago = datetime.datetime.now(tz=_CHICAGO_TZ)
        hour_start = now_chicago.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + datetime.timedelta(hours=1)

        # Remaining seconds in the current hour
        remaining = max((hour_end - now_chicago).total_seconds(), _FAKE_MIN_HOUR_REMAINING_SECONDS)

        # Generate `count` uniformly-random offsets within [0, remaining)
        offsets = sorted(random.uniform(0, remaining) for _ in range(count))

        for offset in offsets:
            cfg = _load_fake_orders_config()
            if not cfg.get("enabled"):
                break
            usernames = [u for u in (cfg.get("usernames") or []) if u]
            if not usernames:
                break

            now_ts = datetime.datetime.now(tz=_CHICAGO_TZ)
            already_elapsed = (now_ts - now_chicago).total_seconds()
            wait = offset - already_elapsed
            if wait > 0:
                time.sleep(wait)

            username = random.choice(usernames)
            threading.Thread(target=_send_one_fake_order, args=(username,), daemon=True).start()

        # Sleep until the top of the next hour
        now = datetime.datetime.now(tz=_CHICAGO_TZ)
        next_hour = (now + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        sleep_secs = max((next_hour - now).total_seconds(), 1)
        time.sleep(sleep_secs)


def start_fake_orders_scheduler() -> None:
    global _fake_orders_scheduler_started
    with _fake_orders_scheduler_lock:
        if _fake_orders_scheduler_started:
            return
        _fake_orders_scheduler_started = True
    t = threading.Thread(target=_fake_orders_scheduler_loop, daemon=True)
    t.start()


def find_account_by_item_id(item_id: int):
    """
    Fetch a single Fortnite account from the marketplace by item_id
    """
    url = f"https://prod-api.lzt.market/{item_id}"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {MARKET_API_TOKEN}",
    }

    resp = requests.get(url, headers=headers, timeout=20)

    if resp.status_code == 404:
        return None

    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch account {item_id}: "
            f"{resp.status_code} - {resp.text[:200]}"
        )

    data = _normalize_purchase_result_payload(resp.json())
    item = data.get("item") or data
    item_state = (item.get("item_state") or "").strip().lower()
    if item_state not in ("", "active"):
        raise RuntimeError(
            f"Account {item_id} is not available (item_state={item_state})"
        )
    return item


def _extract_account_price(account: dict) -> float:
    if not isinstance(account, dict):
        raise PurchaseFlowError(
            "account_unavailable",
            ACCOUNT_UNAVAILABLE_MESSAGE,
            409,
        )

    try:
        price = float(account.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0

    if price <= 0:
        raise PurchaseFlowError(
            "account_unavailable",
            ACCOUNT_UNAVAILABLE_MESSAGE,
            409,
        )

    return price


def get_live_account_purchase_price(item_id: int) -> float:
    account = find_account_by_item_id(item_id)
    if not account:
        raise PurchaseFlowError(
            "account_unavailable",
            ACCOUNT_UNAVAILABLE_MESSAGE,
            409,
        )
    return _extract_account_price(account)


def get_live_purchase_costs(item_id: int) -> Tuple[float, float, int]:
    account = find_account_by_item_id(item_id)
    if not account:
        raise PurchaseFlowError("account_unavailable", ACCOUNT_UNAVAILABLE_MESSAGE, 409)
    live_price = _extract_account_price(account)
    user_price = live_price * get_multiplier_for_account(account)
    cost_cents = int(round(user_price * 100))
    return live_price, user_price, cost_cents


def _not_enough_balance_response(balance_cents: int, cost_cents: int):
    missing = (cost_cents - balance_cents) / 100
    return jsonify(
        {
            "error": "not_enough_balance",
            "message": f"Not enough balance. Missing ${missing:.2f}",
        }
    ), 400



# ===================== FORTNITE / MARKET HELPERS =====================


def norm(s: str) -> str:
    return " ".join(s.lower().split())


def extract_accounts(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            return data["data"]
        if isinstance(data.get("data"), dict) and isinstance(
            data["data"].get("items"), list
        ):
            return data["data"]["items"]
        if isinstance(data.get("items"), list):
            return data["items"]
    return []


def compute_days_ago(acc) -> Optional[int]:
    last_ts = acc.get("fortnite_last_activity") or acc.get("account_last_activity")
    if not isinstance(last_ts, (int, float)) or last_ts <= 0:
        return None
    now_ts = time.time()
    days = int((now_ts - last_ts) / 86400)
    return max(days, 0)


FORTNITE_MARKET_PARAM_KEYS = {
    "page", "pmin", "pmax", "title", "order_by", "tag_id[]", "not_tag_id[]",
    "public_tag_id[]", "not_public_tag_id[]", "origin[]", "not_origin[]", "user_id",
    "nsb", "sb", "nsb_by_me", "sb_by_me", "currency", "email_login_data",
    "email_provider[]", "email_type[]", "not_email_provider[]", "parse_same_item_ids",
    "temp_email", "item_domain", "eg", "smin", "smax", "vbmin", "vbmax", "skin[]",
    "pickaxe[]", "glider[]", "dance[]", "change_email", "platform[]",
    "skins_shop_min", "skins_shop_max", "pickaxes_shop_min", "pickaxes_shop_max",
    "dances_shop_min", "dances_shop_max", "gliders_shop_min", "gliders_shop_max",
    "skins_shop_vbmin", "skins_shop_vbmax", "pickaxes_shop_vbmin", "pickaxes_shop_vbmax",
    "dances_shop_vbmin", "dances_shop_vbmax", "gliders_shop_vbmin", "gliders_shop_vbmax",
    "bp", "lmin", "lmax", "bp_lmin", "bp_lmax", "last_trans_date",
    "last_trans_date_period", "no_trans", "xbox_linkable", "psn_linkable", "daybreak",
    "rl_purchases", "reg", "reg_period", "refund_credits_min", "refund_credits_max",
    "pickaxe_min", "pickaxe_max", "dmin", "dmax", "gmin", "gmax", "country[]",
    "not_country[]", "stw[]", "not_stw[]",
}


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_market_param_value(value: Any) -> Any:
    if isinstance(value, list):
        cleaned = []
        for v in value:
            if v is None:
                continue
            sv = str(v).strip() if isinstance(v, str) else v
            if sv == "":
                continue
            cleaned.append(sv)
        return cleaned or None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def build_market_search_params(payload: Dict[str, Any]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}

    for key in FORTNITE_MARKET_PARAM_KEYS:
        if key not in payload:
            continue
        cleaned = _clean_market_param_value(payload.get(key))
        if cleaned is not None:
            params[key] = cleaned

    # Backward-compatible aliases from current dashboard payload.
    days = _as_int(payload.get("days"))
    if "daybreak" not in params and days is not None and days >= 0:
        params["daybreak"] = days

    skins = _as_int(payload.get("skins"))
    if "smin" not in params and skins is not None and skins > 0:
        params["smin"] = skins

    budget = _as_float(payload.get("budget"))
    if "pmax" not in params and budget is not None and budget > 0:
        params["pmax"] = budget

    enum_filter_keys = {"change_email", "bp", "xbox_linkable", "psn_linkable", "temp_email"}
    for key in enum_filter_keys:
        if key not in params:
            continue
        value = str(params.get(key) or "").strip().lower()
        if value == "maybe":
            value = "yes"
        if value not in {"yes", "no", "nomatter"}:
            params.pop(key, None)
            continue
        params[key] = value

    if "email_login_data" in params:
        value = params["email_login_data"]
        if not isinstance(value, bool):
            lowered = str(value).strip().lower()
            if lowered in {"yes", "true", "1"}:
                params["email_login_data"] = True
            elif lowered in {"no", "false", "0"}:
                params["email_login_data"] = False
            else:
                params.pop("email_login_data", None)

    return params


# Replace the find_item_by_name function in web_app.py with this:

def find_item_by_name(item_name: str, max_pages: int = 20):
    """
    Scan Fortnite listings, match cosmetic by title.
    Returns (param_name, query_id, raw_id, matched_title, item_type).
    """
    target = norm(item_name)

    # Map field names to API parameter names and display types
    buckets = [
        ("skin[]", "fortniteSkins", "Skin"),
        ("pickaxe[]", "fortnitePickaxe", "Pickaxe"),
        ("dance[]", "fortniteDance", "Emote"),
        ("glider[]", "fortniteGliders", "Glider"),
    ]

    for page in range(1, max_pages + 1):
        params = {
            "order_by": "pdate_to_down",
            "page": page,
        }
        resp = requests.get(
            MARKET_API_URL,
            headers=market_headers,
            params=params,
            timeout=MARKET_API_TIMEOUT,
        )

        if resp.status_code == 401:
            raise RuntimeError("Marketplace API token invalid/expired (401).")

        if resp.status_code != 200:
            raise RuntimeError(
                f"Error scanning page {page}: {resp.status_code} - {resp.text[:300]}"
            )

        data = resp.json()
        accounts = extract_accounts(data)
        if not accounts:
            break

        for acc in accounts:
            for param_name, field_name, type_name in buckets:
                cosmetic_list = acc.get(field_name, [])
                
                if not isinstance(cosmetic_list, list):
                    continue
                
                for item in cosmetic_list:
                    if not isinstance(item, dict):
                        continue
                    
                    title = item.get("title") or ""
                    if norm(title) == target:
                        raw_id = item.get("id")
                        if not raw_id:
                            continue
                        
                        # Convert to string
                        query_id = str(raw_id)
                        
                        # Strip prefixes that work, keep full ID for ones that don't
                        if isinstance(raw_id, str):
                            # Skins: strip cid_ (WORKS)
                            if raw_id.startswith("cid_"):
                                query_id = raw_id[4:]
                            # Emotes: strip eid_ (WORKS) 
                            elif raw_id.startswith("eid_"):
                                query_id = raw_id[4:]
                            # Gliders: strip glider_id_ (WORKS)
                            elif raw_id.startswith("glider_id_"):
                                query_id = raw_id[10:]
                            # Pickaxes: DON'T strip anything, keep full ID
                            # (This is the key - pickaxes need the full ID including prefix)
                        
                        return param_name, query_id, raw_id, title, type_name

    return None

# Replace the fetch_cheapest_accounts function in web_app.py with this:

def fetch_cheapest_accounts(
    item_filters: List[Tuple[str, str]],
    min_days: Optional[int],
    min_skins: Optional[int] = None,
    extra_params: Optional[Dict[str, Any]] = None,
):
    """
    Get up to MAX_ACCOUNTS cheapest accounts that match filters.
    """
    base_params = {
        "order_by": "price_to_up",  # cheapest first
    }

    if extra_params:
        for key, value in extra_params.items():
            if key == "page":
                continue
            base_params[key] = value

    # Build the filter parameters correctly
    for param_name, query_id in item_filters:
        # The param_name is like "skin[]", "dance[]", etc.
        # API expects these as arrays, so we need to handle them properly
        
        if param_name in base_params:
            # If parameter already exists, convert to list or append
            existing = base_params[param_name]
            if isinstance(existing, list):
                existing.append(str(query_id))
            else:
                base_params[param_name] = [existing, str(query_id)]
        else:
            # First time seeing this parameter, just set it
            # For array parameters like dance[], pass as string (requests will handle it)
            base_params[param_name] = str(query_id)

    if "daybreak" not in base_params and min_days is not None and min_days >= 0:
        base_params["daybreak"] = min_days

    if "smin" not in base_params and min_skins is not None and min_skins >= 0:
        base_params["smin"] = min_skins

    all_accounts = []

    for page in range(1, MAX_PAGES + 1):
        params = dict(base_params)
        params["page"] = page

        resp = requests.get(
            MARKET_API_URL,
            headers=market_headers,
            params=params,
            timeout=MARKET_API_TIMEOUT,
        )

        if resp.status_code == 401:
            raise RuntimeError("Marketplace API token invalid/expired (401) on listing.")

        if resp.status_code != 200:
            raise RuntimeError(f"API error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        accounts = extract_accounts(data)
        if not accounts:
            break

        all_accounts.extend(accounts)
        if len(all_accounts) >= MAX_ACCOUNTS:
            break

    return all_accounts, base_params


def confirm_buy_account(item_id: int):
    """
    Initiate a marketplace fast-buy purchase for an account item.
    Sends optional balance_id when available.
    If no balance_id is configured, the request is sent without it.
    Returns parsed marketplace JSON on success.
    Raises PurchaseFlowError for known purchase failures, including unavailable accounts.
    """
    url = f"https://prod-api.lzt.market/{item_id}/fast-buy"
    headers_fb = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {MARKET_API_TOKEN}",
    }
    account = find_account_by_item_id(item_id)
    if not account:
        raise PurchaseFlowError(
            "account_unavailable",
            ACCOUNT_UNAVAILABLE_MESSAGE,
            409,
        )

    request_kwargs: Dict[str, Any] = {
        "headers": headers_fb,
        "timeout": 60,
    }
    balance_id = os.environ.get("LZT_BALANCE_ID")
    if balance_id:
        try:
            request_kwargs["json"] = {"balance_id": int(balance_id)}
        except (ValueError, TypeError):
            pass

    for attempt in range(FAST_BUY_MAX_ATTEMPTS):
        resp = requests.post(url, **request_kwargs)

        # Try to parse JSON response; retry on 5xx non-JSON (e.g. nginx error pages),
        # otherwise fall back to raising with raw text.
        try:
            data = resp.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            if resp.status_code >= 500 and attempt < FAST_BUY_MAX_ATTEMPTS - 1:
                app.logger.warning(
                    "Fast-buy got non-JSON 5xx (status=%s) for item %s, retrying (attempt %s/%s)",
                    resp.status_code, item_id, attempt + 1, FAST_BUY_MAX_ATTEMPTS,
                )
                time.sleep(FAST_BUY_SERVER_ERROR_DELAY_SECONDS)
                continue
            recovered_result = _recover_purchase_result(
                item_id,
                f"non_json_status_{resp.status_code}",
            )
            if recovered_result:
                return recovered_result
            raise RuntimeError(f"Fast-buy returned non-JSON: {resp.status_code} - {resp.text[:300]}")

        error_parts: List[str] = []
        error_code_raw = ""
        if isinstance(data, dict):
            raw_errors = data.get("errors", [])
            if isinstance(raw_errors, list):
                error_parts.extend(str(part) for part in raw_errors if part)
            elif raw_errors:
                error_parts.append(str(raw_errors))
            message = data.get("message")
            if message:
                error_parts.append(str(message))
            error_code = data.get("error")
            if error_code:
                error_code_raw = str(error_code)
                error_parts.append(str(error_code))
        # Deduplicate while preserving API-provided order.
        error_parts = list(dict.fromkeys(error_parts))
        error_text = " | ".join(error_parts).lower()

        # --- Retry on API-signaled transient conditions ---
        if "retry_request" in error_text:
            if attempt < FAST_BUY_MAX_ATTEMPTS - 1:
                time.sleep(FAST_BUY_RETRY_DELAY_SECONDS)
                continue
            recovered_result = _recover_purchase_result(item_id, "retry_request")
            if recovered_result:
                return recovered_result
            raise RuntimeError(
                f"Fast-buy exhausted all {FAST_BUY_MAX_ATTEMPTS} attempts due to retry_request responses"
            )

        if any(keyword in error_text for keyword in FAST_BUY_RETRYABLE_KEYWORDS):
            if attempt < FAST_BUY_MAX_ATTEMPTS - 1:
                app.logger.info(
                    "Fast-buy got retryable error for item %s (attempt %s/%s): %s",
                    item_id, attempt + 1, FAST_BUY_MAX_ATTEMPTS, error_text[:200],
                )
                time.sleep(FAST_BUY_RETRY_DELAY_SECONDS)
                continue
            recovered_result = _recover_purchase_result(item_id, "retryable_api_error", data)
            if recovered_result:
                return recovered_result
            raise PurchaseFlowError(
                "confirm_buy_failed",
                "Marketplace rejected the purchase request. Please try again.",
                400,
            )

        # --- Retry on HTTP-level transient conditions ---
        if resp.status_code == 429:
            if attempt < FAST_BUY_MAX_ATTEMPTS - 1:
                retry_after = FAST_BUY_RATE_LIMIT_DELAY_SECONDS
                try:
                    retry_after_header = resp.headers.get("Retry-After", "")
                    if retry_after_header:
                        retry_after = float(retry_after_header)
                except (ValueError, TypeError):
                    pass
                app.logger.info(
                    "Fast-buy rate-limited for item %s (attempt %s/%s), waiting %.1fs",
                    item_id, attempt + 1, FAST_BUY_MAX_ATTEMPTS, retry_after,
                )
                time.sleep(min(retry_after, 30))
                continue
            recovered_result = _recover_purchase_result(item_id, "rate_limited", data)
            if recovered_result:
                return recovered_result
            raise PurchaseFlowError(
                "rate_limited",
                "Marketplace is rate limiting purchases. Please wait a moment and try again.",
                429,
            )

        if resp.status_code >= 500:
            if attempt < FAST_BUY_MAX_ATTEMPTS - 1:
                app.logger.warning(
                    "Fast-buy got %s server error for item %s (attempt %s/%s): %s",
                    resp.status_code, item_id, attempt + 1, FAST_BUY_MAX_ATTEMPTS,
                    error_text[:200],
                )
                time.sleep(FAST_BUY_SERVER_ERROR_DELAY_SECONDS)
                continue
            recovered_result = _recover_purchase_result(item_id, f"http_{resp.status_code}", data)
            if recovered_result:
                return recovered_result
            raise PurchaseFlowError(
                "confirm_buy_failed",
                "Marketplace is experiencing issues. Please try again in a moment.",
                503,
            )

        normalized_error_text = str(error_text or "").lower()
        normalized_error_code = str(error_code_raw or "").lower()
        combined_error_signal = f"{normalized_error_text} {normalized_error_code}"
        has_balance_error = any(
            keyword in combined_error_signal
            for keyword in BALANCE_ERROR_KEYWORDS
        )
        has_auth_error = any(
            keyword in combined_error_signal
            for keyword in AUTH_ERROR_KEYWORDS
        )

        # --- Terminal error classification ---
        if resp.status_code == 404:
            recovered_result = _recover_purchase_result(
                item_id,
                "account_unavailable_404",
                data if isinstance(data, dict) else None,
                initial_delay_seconds=PURCHASE_DELAY_AFTER_CHECK_SECONDS,
            )
            if recovered_result:
                return recovered_result
            raise PurchaseFlowError(
                "account_unavailable",
                ACCOUNT_UNAVAILABLE_MESSAGE,
                409,
            )

        if resp.status_code == 403:
            if any(keyword in error_text for keyword in ACCOUNT_UNAVAILABLE_KEYWORDS):
                recovered_result = _recover_purchase_result(
                    item_id,
                    "account_unavailable_403",
                    data if isinstance(data, dict) else None,
                    initial_delay_seconds=PURCHASE_DELAY_AFTER_CHECK_SECONDS,
                )
                if recovered_result:
                    return recovered_result
                raise PurchaseFlowError(
                    "account_unavailable",
                    ACCOUNT_UNAVAILABLE_MESSAGE,
                    409,
                )
            if has_balance_error:
                raise PurchaseFlowError(
                    "market_balance_required",
                    "Marketplace balance is not configured correctly. Please contact support.",
                    422,
                )
            if has_auth_error:
                raise PurchaseFlowError(
                    "market_auth_failed",
                    "Marketplace API token does not have purchase access. Ensure the token includes required market/payment scopes.",
                    401,
                )
            raise PurchaseFlowError(
                "market_access_denied",
                _build_marketplace_error_message(
                    "Marketplace rejected the purchase request.",
                    error_parts,
                ),
                403,
            )

        if resp.status_code == 401:
            raise PurchaseFlowError(
                "market_auth_failed",
                "Marketplace API token is invalid or expired.",
                401,
            )

        if resp.status_code in (400, 422) and has_balance_error:
            raise PurchaseFlowError(
                "market_balance_required",
                "Marketplace balance is not configured correctly. Please contact support.",
                422,
            )

        if not resp.ok:
            app.logger.warning(
                "Fast-buy failed for item %s with status %s: %s",
                item_id,
                resp.status_code,
                error_text or resp.text[:300],
            )
            recovered_result = _recover_purchase_result(item_id, f"http_{resp.status_code}", data)
            if recovered_result:
                return recovered_result
            raise PurchaseFlowError(
                "confirm_buy_failed",
                "Marketplace rejected the purchase request. Please try again.",
                400,
            )

        normalized_data = _normalize_purchase_result_payload(data)
        delivery_result = _recover_purchase_result(
            item_id,
            "fast_buy_success",
            normalized_data if isinstance(normalized_data, dict) else None,
        )
        return delivery_result or normalized_data

def get_latest_order():
    """
    GET /user/orders, return latest order or None.
    """
    url = "https://prod-api.lzt.market/user/orders"
    headers_ord = {
        "accept": "application/json",
        "authorization": f"Bearer {MARKET_API_TOKEN}",
    }

    resp = requests.get(url, headers=headers_ord, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"/user/orders failed: {resp.status_code} - {resp.text[:300]}")

    data = resp.json()
    orders = extract_accounts(data)
    if not orders:
        return None
    return orders[0]


# ===================== SHOPIFY ADMIN HELPER =====================


def get_shopify_order_by_ref(order_ref: str):
    """
    Look up Shopify order by numeric ID or #number.
    Note format used: user:<username>
    """
    if not SHOPIFY_ADMIN_TOKEN:
        return None, None, None, None, "no_token", None

    order_ref = str(order_ref).strip()

    base_url = f"https://{SHOPIFY_ADMIN_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}"
    headers_shopify = {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
        "Content-Type": "application/json",
    }

    order = None

    by_id_url = f"{base_url}/orders/{order_ref}.json"
    try:
        resp_id = requests.get(by_id_url, headers=headers_shopify, timeout=SHOPIFY_API_TIMEOUT)
    except requests.RequestException as e:
        return (
            None,
            None,
            None,
            None,
            "api_error",
            {"status_code": None, "body": str(e)},
        )
    if resp_id.status_code == 200:
        order = (resp_id.json() or {}).get("order")
    elif resp_id.status_code in (400, 404):
        app.logger.info(
            "Shopify order-by-id lookup miss for ref %s (status=%s), falling back to order number",
            order_ref,
            resp_id.status_code,
        )
    else:
        return (
            None,
            None,
            None,
            None,
            "api_error",
            {
                "status_code": resp_id.status_code,
                "body": resp_id.text[:SHOPIFY_ERROR_BODY_LIMIT],
            },
        )

    if not order:
        order_name = f"#{order_ref}"
        by_number_url = f"{base_url}/orders.json"
        params = {
            "status": "any",
            "name": order_name,
            "limit": 1,
        }
        try:
            resp_number = requests.get(
                by_number_url, headers=headers_shopify, params=params, timeout=SHOPIFY_API_TIMEOUT
            )
        except requests.RequestException as e:
            return (
                None,
                None,
                None,
                None,
                "api_error",
                {"status_code": None, "body": str(e)},
            )
        if resp_number.status_code != 200:
            return (
                None,
                None,
                None,
                None,
                "api_error",
                {
                    "status_code": resp_number.status_code,
                    "body": resp_number.text[:SHOPIFY_ERROR_BODY_LIMIT],
                },
            )

        data = resp_number.json()
        orders = data.get("orders", [])
        if not orders:
            return None, None, None, None, "not_found", None
        order = orders[0]

    order_id_str = str(order.get("id"))
    note = order.get("note", "")
    financial_status = order.get("financial_status")

    if financial_status != "paid":
        return None, None, None, financial_status, "not_paid", None

    total_price_str = order.get("total_price") or "0.00"
    try:
        amount_dollars = float(total_price_str)
    except Exception:
        return None, None, None, None, "bad_price", None

    amount_cents = int(round(amount_dollars * 100))

    return amount_cents, order_id_str, note, financial_status, "ok", None


# ===================== FLASK APP =====================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-this")
KONVY_ADMIN_PASSWORD = os.environ.get("KONVY_ADMIN_PASSWORD", "Kelvilo40")
try:
    session_lifetime_days = int(os.environ.get("SESSION_LIFETIME_DAYS", "30"))
except (TypeError, ValueError):
    session_lifetime_days = 30
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=max(1, session_lifetime_days))
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
# Allow up to 5 files × 10 MB + some overhead for support ticket uploads
app.config["MAX_CONTENT_LENGTH"] = 55 * 1024 * 1024


ensure_cosmetic_lookup_runtime_initialized()
start_fake_orders_scheduler()


@app.template_filter("timestamp_to_ago")
def _timestamp_to_ago(ts: int) -> str:
    if not ts:
        return "never"
    diff = int(time.time()) - ts
    if diff < 60:
        return "just now"
    if diff < 3600:
        m = diff // 60
        return f"{m}m ago"
    if diff < 86400:
        h = diff // 3600
        return f"{h}h ago"
    d = diff // 86400
    return f"{d}d ago"


@app.template_filter("timestamp_to_date")
def _timestamp_to_date(ts: int) -> str:
    if not ts:
        return "N/A"
    return datetime.datetime.fromtimestamp(ts).strftime("%b %d, %Y %I:%M %p")


@app.template_filter("is_online")
def _is_online(ts) -> bool:
    return bool(ts) if isinstance(ts, bool) else (bool(ts) and (int(time.time()) - ts) < 300)


@app.template_filter("email_login_url")
def _email_login_url(email_login: str) -> str:
    return _get_email_login_url(email_login)


@app.template_filter("censor_username")
def _censor_username(name: str) -> str:
    s = name.strip()
    if len(s) <= 2:
        return s[0] + "*" * (len(s) - 1) if s else "***"
    return s[0] + "*" * (len(s) - 2) + s[-1]


@app.context_processor
def _inject_globals():
    username = session.get("username", "")
    nav_profile_pic = ""
    has_admin = bool(session.get("is_konvy_admin"))
    if username:
        users = _load_users()
        udata = users.get(username, {})
        nav_profile_pic = udata.get("profile_pic", "") or ""
        if not has_admin:
            has_admin = is_admin_user(username)
    return dict(is_konvy_admin=has_admin, nav_profile_pic=nav_profile_pic)


@app.before_request
def _track_last_online():
    username = session.get("username")
    if username:
        users = _load_users()
        if username in users:
            now = int(time.time())
            users[username]["last_online"] = now
            users[username]["online"] = True
            _save_users(users)


def login_required_page(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


def login_required_api(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return jsonify({"error": "not_logged_in"}), 401
        return f(*args, **kwargs)

    return wrapper


def _normalize_locked_purchase(session_value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(session_value, dict):
        return None
    try:
        item_id = int(session_value.get("item_id") or 0)
    except (TypeError, ValueError):
        return None
    if item_id <= 0:
        return None
    created_at = 0
    try:
        created_at = int(session_value.get("created_at") or 0)
    except (TypeError, ValueError):
        created_at = int(time.time())
    if created_at <= 0:
        created_at = int(time.time())
    if (time.time() - float(created_at)) > PURCHASE_LOCK_MAX_SECONDS:
        return None
    item_title = (
        str(session_value.get("item_title") or DEFAULT_PURCHASE_ITEM_TITLE).strip()
        or DEFAULT_PURCHASE_ITEM_TITLE
    )
    return {
        "item_id": item_id,
        "item_title": item_title[:MAX_PURCHASE_ITEM_TITLE_LENGTH],
        "created_at": created_at,
    }


def get_purchase_lock() -> Optional[Dict[str, Any]]:
    normalized = _normalize_locked_purchase(session.get(PURCHASE_LOCK_SESSION_KEY))
    if normalized is None and PURCHASE_LOCK_SESSION_KEY in session:
        session.pop(PURCHASE_LOCK_SESSION_KEY, None)
    return normalized


def set_purchase_lock(item_id: int, item_title: str) -> None:
    session[PURCHASE_LOCK_SESSION_KEY] = {
        "item_id": int(item_id),
        "item_title": (
            str(item_title or DEFAULT_PURCHASE_ITEM_TITLE).strip()
            or DEFAULT_PURCHASE_ITEM_TITLE
        )[:MAX_PURCHASE_ITEM_TITLE_LENGTH],
        "created_at": int(time.time()),
    }


def clear_purchase_lock() -> None:
    session.pop(PURCHASE_LOCK_SESSION_KEY, None)


def _purchase_in_progress_response(waiting_for_other_item: bool = False):
    message = "Purchase is processing. Please wait until it completes."
    if waiting_for_other_item:
        message = "Another purchase is processing. Please wait until it completes."
    return jsonify({"error": "purchase_in_progress", "message": message}), 423


def _build_fallback_purchase_title(item_id: int) -> str:
    return f"{DEFAULT_PURCHASE_ITEM_TITLE} #{item_id}"


@app.before_request
def enforce_purchase_lock():
    if "username" not in session:
        return None
    session.permanent = True

    locked_purchase = get_purchase_lock()
    if not locked_purchase:
        return None

    path = (request.path or "").strip()
    if path.startswith("/static/"):
        return None
    if path in {"/purchase-processing", "/logout"}:
        requested_item_id = 0
        try:
            requested_item_id_raw = request.args.get("item_id") or ""
            requested_item_id_text = str(requested_item_id_raw).strip()
            requested_item_id = int(requested_item_id_text or 0)
        except (TypeError, ValueError):
            requested_item_id = 0
        if (
            path == "/purchase-processing"
            and requested_item_id > 0
            and requested_item_id != locked_purchase["item_id"]
        ):
            return redirect(
                url_for(
                    "purchase_processing_page",
                    item_id=locked_purchase["item_id"],
                    title=locked_purchase["item_title"],
                )
            )
        return None

    if path == "/api/fortnite/purchase-lock/release":
        payload = request.get_json(silent=True) or {}
        release_item_id = 0
        try:
            release_item_id = int(payload.get("item_id") or 0)
        except (TypeError, ValueError):
            release_item_id = 0
        if release_item_id > 0 and release_item_id == locked_purchase["item_id"]:
            return None
        return _purchase_in_progress_response(waiting_for_other_item=True)

    if path == "/api/fortnite/buy":
        payload = request.get_json(silent=True) or {}
        incoming_item_id = 0
        try:
            incoming_item_id = int(payload.get("item_id") or 0)
        except (TypeError, ValueError):
            incoming_item_id = 0
        if incoming_item_id > 0 and incoming_item_id != locked_purchase["item_id"]:
            return _purchase_in_progress_response(waiting_for_other_item=True)
        return None

    if path.startswith("/api/"):
        return _purchase_in_progress_response()

    return redirect(
        url_for(
            "purchase_processing_page",
            item_id=locked_purchase["item_id"],
            title=locked_purchase["item_title"],
        )
    )


def admin_required_page(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_admin_user(session.get("username", "")):
            return redirect(url_for("admin123_page"))
        return f(*args, **kwargs)

    return wrapper


def user_has_purchases(username):
    purchases = get_purchases(username)
    return len(purchases) > 0


# ===================== AUTH ROUTES =====================


# ===================== AUTH ROUTES =====================

LOGIN_HTML = """
<!doctype html>
<html>
  <head>
    <title>Konvy Accounts – Login</title>
    <style>
      * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }

      body {
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #000;
        background-image: radial-gradient(circle at top, #222 0, #000 55%);
        background-attachment: fixed;
        color: #f6f6f6;
        min-height: 100vh;
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 40px 16px;
        position: relative;
        overflow: hidden;
      }

      #snow-canvas {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: -1;
        pointer-events: none;
      }

      .auth-shell {
        width: 100%;
        max-width: 420px;
        padding: 26px 22px 24px;
        border-radius: 18px;
        background: rgba(0, 0, 0, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow:
          0 24px 60px rgba(0, 0, 0, 0.9),
          0 0 0 1px rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(18px);
      }

      .auth-title {
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        font-size: 0.85rem;
        color: #fdfdfd;
        margin-bottom: 4px;
      }

      .auth-heading {
        font-size: 1.35rem;
        font-weight: 500;
        margin-bottom: 4px;
      }

      .auth-sub {
        font-size: 0.8rem;
        color: #a3a3a3;
        margin-bottom: 18px;
      }

      form {
        margin-top: 8px;
      }

      label {
        display: block;
        margin-top: 12px;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #bfbfbf;
      }

      input {
        margin-top: 6px;
        padding: 9px 12px;
        width: 100%;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.18);
        background: rgba(0, 0, 0, 0.85);
        color: #f9f9f9;
        outline: none;
        font-size: 0.9rem;
        transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
      }

      input::placeholder {
        color: #666;
      }

      input:focus {
        border-color: #ffffff;
        background: rgba(0, 0, 0, 0.96);
        box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.4);
      }

      button {
        margin-top: 16px;
        padding: 9px 20px;
        width: 100%;
        border-radius: 999px;
        border: 1px solid #ffffff;
        background: #ffffff;
        color: #000000;
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        cursor: pointer;
        transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease;
      }

      button:hover {
        background: #000000;
        color: #ffffff;
        box-shadow: 0 0 0 1px #ffffff, 0 8px 18px rgba(0, 0, 0, 0.9);
        transform: translateY(-1px);
      }

      button:active {
        transform: translateY(0);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.8);
      }

      .auth-footer {
        margin-top: 16px;
        font-size: 0.8rem;
        color: #b5b5b5;
        text-align: center;
      }

      .auth-footer a {
        color: #ffffff;
        text-decoration: none;
        border-bottom: 1px solid rgba(255, 255, 255, 0.3);
      }

      .auth-footer a:hover {
        border-color: #ffffff;
      }

      .error {
        margin-top: 10px;
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 0.8rem;
        background: rgba(255, 77, 77, 0.1);
        border: 1px solid rgba(255, 77, 77, 0.5);
        color: #ffb3b3;
      }

      @media (max-width: 480px) {
        .auth-shell {
          padding: 22px 18px 20px;
          border-radius: 14px;
        }
      }
    </style>
  </head>
  <body>
    <canvas id="snow-canvas"></canvas>

    <div class="auth-shell">
      <div class="auth-title">Konvy Accounts</div>
      <div class="auth-heading">Sign in</div>
      <div class="auth-sub">Access your Fortnite account panel.</div>

      {% if error %}
      <div class="error">{{ error }}</div>
      {% endif %}

      <form method="post">
        <label>Username
          <input name="username" placeholder="yourname" value="{{ username_prefill or '' }}">
        </label>
        <label>Password
          <input name="password" type="password" placeholder="••••••••">
        </label>
        <button type="submit">Login</button>
      </form>

      <div class="auth-footer">
        New here?
        <a href="{{ url_for('register') }}">Create an account</a>
      </div>
    </div>

    <script>
      (function () {
        const canvas = document.getElementById('snow-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        let width, height;
        let flakes = [];

        function resize() {
          width = canvas.width = window.innerWidth;
          height = canvas.height = window.innerHeight;
        }
        window.addEventListener('resize', resize);
        resize();

        const FLAKE_COUNT = 140;

        function initFlakes() {
          flakes = [];
          for (let i = 0; i < FLAKE_COUNT; i++) {
            flakes.push({
              x: Math.random() * width,
              y: Math.random() * height,
              r: Math.random() * 2 + 1,
              v: Math.random() * 0.5 + 0.3,
              drift: (Math.random() - 0.5) * 0.5
            });
          }
        }

        function draw() {
          ctx.clearRect(0, 0, width, height);
          ctx.beginPath();
          for (const f of flakes) {
            ctx.moveTo(f.x, f.y);
            ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2);

            f.y += f.v;
            f.x += f.drift + Math.sin(f.y * 0.01) * 0.2;

            if (f.y > height + 5) {
              f.y = -5;
              f.x = Math.random() * width;
            }
            if (f.x > width + 5) f.x = -5;
            if (f.x < -5) f.x = width + 5;
          }
          ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
          ctx.fill();
          requestAnimationFrame(draw);
        }

        initFlakes();
        draw();
      })();
    </script>
  </body>
</html>
"""



# ===== Actual route functions that use the above HTML =====

@app.route("/api/skins/icons", methods=["POST"])
def get_skin_icons():
    names = request.json.get("names", [])
    cosmetic_type = request.json.get("type", None)  # Optional: 'outfit', 'pickaxe', 'emote', 'glider'
    icons = []

    for name in names:
        # Use the generic function - it handles both with and without type
        url = fortnite_api_get_cosmetic_icon_url_by_name(name, cosmetic_type)
        rarity = None
        with COSMETIC_LOOKUP_LOCK:
            rarity = COSMETIC_RARITY_LOOKUP.get((name or "").strip().lower())

        icons.append({
            "name": name,
            "icon": url,
            "rarity": rarity,
        })

    return jsonify({"icons": icons})


@app.route("/api/account/<int:item_id>/cosmetics/<cosmetic_type>")
def get_account_cosmetics(item_id, cosmetic_type):
    account = find_account_by_item_id(item_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404

    # Map cosmetic types to API field names
    type_mapping = {
        "skins": "fortniteSkins",
        "pickaxes": "fortnitePickaxe",
        "emotes": "fortniteDance",
        "gliders": "fortniteGliders"
    }
    
    field_name = type_mapping.get(cosmetic_type)
    if not field_name:
        return jsonify({"error": "Invalid cosmetic type"}), 400
    
    cosmetics = account.get(field_name) or []
    names = []

    for item in cosmetics:
        if isinstance(item, dict):
            name = item.get("title") or item.get("name")
        else:
            name = str(item)

        if name:
            names.append(name)

    return jsonify({
        "item_id": item_id,
        "type": cosmetic_type,
        "cosmetics": names
    })

@app.route("/api/account/<int:item_id>/skins")
def get_account_skins(item_id):
    account = find_account_by_item_id(item_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404

    skins = account.get("fortniteSkins") or []
    names = []

    for s in skins:
        if isinstance(s, dict):
            name = s.get("title") or s.get("name")
        else:
            name = str(s)

        if name:
            names.append(name)

    return jsonify({
        "item_id": item_id,
        "skins": names
    })





@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        error = request.args.get("error", "")
        message = request.args.get("message", "")
        username_prefill = request.args.get("u", "")
        return render_template(
            "login.html",
            error=error,
            message=message,
            username_prefill=username_prefill,
            logged_in=False,
            balance="0.00",
            active_page="login",
        )

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if not verify_user(username, password):
        return redirect(
            url_for("login", error="Invalid username or password.", u=username)
        )

    if is_blacklisted(username):
        return redirect(
            url_for("login", error="Your account has been suspended.", u=username)
        )

    if not is_email_verified(username):
        ok, msg = send_email_verification_code(username)
        if ok:
            session["pending_verify_username"] = username
            return redirect(
                url_for(
                    "verify_email",
                    u=username,
                    message=msg,
                )
            )
        app.logger.warning("Email verification send failed for %s: %s", username, msg)
        return redirect(
            url_for(
                "login",
                u=username,
                error=f"Your account needs email verification, but the code could not be sent yet. {msg}",
            )
        )

    # Two-factor auth check
    users = _load_users()
    user_data = users.get(username, {})
    if user_data.get("twofa_enabled"):
        code = _generate_one_time_code()
        user_data["twofa_code"] = _hash_one_time_code(code)
        user_data["twofa_expires"] = int(time.time()) + 300
        _save_users(users)
        recipient = user_data.get("email", "")
        if recipient:
            _send_email_message(recipient, "Your login code — Konvy Accounts",
                f"Your login code is: {code}\nExpires in 5 minutes.",
                _itemz_email_html("Login Code", "Enter this code to complete your login.", code, 5, "If you did not request this, ignore this email."))
        session["pending_twofa_username"] = username
        return redirect(url_for("verify_twofa"))

    session["username"] = username
    session.permanent = True
    session.pop("pending_verify_username", None)
    _push_activity("online", username)
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        error = request.args.get("error", "")
        message = request.args.get("message", "")
        username_prefill = request.args.get("u", "")
        email_prefill = request.args.get("e", "")
        return render_template(
            "register.html",
            error=error,
            message=message,
            username_prefill=username_prefill,
            email_prefill=email_prefill,
            logged_in=False,
            balance="0.00",
            active_page="register",
        )

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    email = _normalize_email(request.form.get("email") or "")

    if not username or not password or not email:
        return redirect(
            url_for(
                "register",
                error="Username, email, and password are required.",
                u=username,
                e=email,
            )
        )

    if not _is_valid_email_address(email):
        return redirect(
            url_for(
                "register",
                error="Enter a valid email address.",
                u=username,
                e=email,
            )
        )

    if password == username:
        return redirect(
            url_for(
                "register",
                error="Password cannot be the same as username.",
                u=username,
                e=email,
            )
        )

    if find_username_by_email(email):
        return redirect(
            url_for(
                "register",
                error="That email is already in use.",
                u=username,
                e=email,
            )
        )

    created = create_user(username, password, email=email)
    if not created:
        return redirect(
            url_for(
                "register",
                error="That username is already taken.",
                u=username,
                e=email,
            )
        )

    _push_activity("signup", username)
    session["pending_verify_username"] = username
    ok, msg = send_email_verification_code(username)
    return redirect(
        url_for(
            "verify_email",
            u=username,
            message=(
                msg
                if ok
                else "Account created. Email verification will work once email "
                "is configured by the administrator."
            ),
            error="" if ok else msg,
        )
    )


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    if request.method == "GET":
        error = request.args.get("error", "")
        message = request.args.get("message", "")
        username_prefill = request.args.get("u", "") or session.get("pending_verify_username", "")
        return render_template(
            "verify_email.html",
            error=error,
            message=message,
            username_prefill=username_prefill,
            logged_in=False,
            balance="0.00",
            active_page="login",
        )

    username = (request.form.get("username") or session.get("pending_verify_username") or "").strip()
    action = (request.form.get("action") or "verify").strip().lower()

    if not username:
        return redirect(url_for("verify_email", error="Enter your username first."))

    if action == "resend":
        ok, msg = send_email_verification_code(username)
        session["pending_verify_username"] = username
        return redirect(
            url_for(
                "verify_email",
                u=username,
                message=msg if ok else "",
                error="" if ok else msg,
            )
        )

    code = (request.form.get("code") or "").strip()
    if not code:
        return redirect(url_for("verify_email", u=username, error="Enter the 6-digit code."))

    if not _verify_one_time_code(username, "email_verification_code_hash", "email_verification_expires_at", code):
        return redirect(url_for("verify_email", u=username, error="Invalid or expired verification code."))

    mark_email_verified(username)
    session["username"] = username
    session.permanent = True
    session.pop("pending_verify_username", None)
    return redirect(url_for("index"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        error = request.args.get("error", "")
        message = request.args.get("message", "")
        identifier_prefill = request.args.get("i", "")
        return render_template(
            "forgot_password.html",
            error=error,
            message=message,
            identifier_prefill=identifier_prefill,
            logged_in=False,
            balance="0.00",
            active_page="login",
        )

    identifier = (request.form.get("identifier") or "").strip()
    users = _load_users()
    username = identifier if identifier in users else find_username_by_email(identifier, users=users)
    if not username:
        return redirect(
            url_for(
                "forgot_password",
                error="We could not find that username or email.",
                i=identifier,
            )
        )

    ok, msg = send_password_reset_code(username)
    if not ok:
        return redirect(url_for("forgot_password", error=msg, i=identifier))

    return redirect(url_for("reset_password", u=username, message=msg))


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "GET":
        error = request.args.get("error", "")
        message = request.args.get("message", "")
        username_prefill = request.args.get("u", "")
        return render_template(
            "reset_password.html",
            error=error,
            message=message,
            username_prefill=username_prefill,
            logged_in=False,
            balance="0.00",
            active_page="login",
        )

    username = (request.form.get("username") or "").strip()
    code = (request.form.get("code") or "").strip()
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if not username or not code or not password:
        return redirect(
            url_for(
                "reset_password",
                u=username,
                error="Username, code, and new password are required.",
            )
        )

    if password != confirm_password:
        return redirect(
            url_for(
                "reset_password",
                u=username,
                error="Passwords do not match.",
            )
        )

    if not _verify_one_time_code(username, "password_reset_code_hash", "password_reset_expires_at", code):
        return redirect(
            url_for(
                "reset_password",
                u=username,
                error="Invalid or expired reset code.",
            )
        )

    if not update_user_password(username, password):
        return redirect(url_for("reset_password", u=username, error="Could not update that password."))

    return redirect(url_for("login", u=username, message="Password reset complete. Please sign in."))

@app.route("/secure")
@login_required_page
def secure_page():
    username = session["username"]
    if not user_has_purchases(username):
        return "Access denied", 403
    return render_template("secure.html")



@app.route("/logout")
def logout():
    _push_activity("offline", session.get("username", "unknown"))
    session.clear()
    return redirect(url_for("login"))

@app.route("/index")
@login_required_page
def index():
    return redirect(url_for("dashboard"))


# 1. Update the home redirect to allow guest access
@app.route("/")
def home_redirect():
    # Always redirect to dashboard (guests can browse)
    return redirect(url_for("dashboard"))


# ===================== MAIN HTML =====================

INDEX_HTML = """
<!doctype html>
<html>
  <head>
    <title>Konvy Accounts – Web Panel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
      * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }

      body {
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #000;
        background-image: radial-gradient(circle at top, #222 0, #000 55%);
        color: #f6f6f6;
        min-height: 100vh;
        display: flex;
        justify-content: center;
        align-items: flex-start;
        padding: 40px 16px;
        position: relative;
        overflow-x: hidden;
      }

      /* Snow canvas background */
      #snow-canvas {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: -1;
        pointer-events: none;
      }

      .app-shell {
        position: relative;
        width: 100%;
        max-width: 960px;
        padding: 24px 20px 28px;
        border-radius: 18px;
        background: rgba(0, 0, 0, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.06);
        box-shadow:
          0 24px 60px rgba(0, 0, 0, 0.9),
          0 0 0 1px rgba(255, 255, 255, 0.02);
        backdrop-filter: blur(16px);
      }

      .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
        padding-bottom: 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      }

      .topbar-title {
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        font-size: 0.8rem;
        color: #fdfdfd;
      }

      .topbar-user {
        font-size: 0.85rem;
        color: #d4d4d4;
      }

      .topbar a {
        color: #ffffff;
        text-decoration: none;
        border-bottom: 1px solid transparent;
        transition: border-color 0.15s ease, color 0.15s ease;
      }

      .topbar a:hover {
        border-color: #ffffff;
        color: #ffffff;
      }

      .small {
        font-size: 0.8rem;
        color: #a3a3a3;
        margin-bottom: 16px;
      }

      .row {
        margin-bottom: 18px;
      }

      .card {
        border-radius: 14px;
        padding: 16px 14px 14px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.7);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease;
      }

      .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.9);
        border-color: rgba(255, 255, 255, 0.18);
        background: rgba(255, 255, 255, 0.03);
      }

      h1, h2 {
        font-weight: 500;
        margin-bottom: 8px;
        color: #ffffff;
      }

      h2 {
        font-size: 1.05rem;
        letter-spacing: 0.03em;
        text-transform: uppercase;
      }

      form {
        margin-top: 8px;
      }

      label {
        display: block;
        margin-top: 10px;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #bfbfbf;
      }

      input {
        margin-top: 5px;
        padding: 8px 10px;
        width: 100%;
        max-width: 320px;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.16);
        background: rgba(0, 0, 0, 0.8);
        color: #f9f9f9;
        outline: none;
        font-size: 0.85rem;
        transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
      }

      input::placeholder {
        color: #666;
      }

      input:focus {
        border-color: #ffffff;
        background: rgba(0, 0, 0, 0.95);
        box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.4);
      }

      button {
        margin-top: 12px;
        padding: 7px 18px;
        border-radius: 999px;
        border: 1px solid #ffffff;
        background: #ffffff;
        color: #000000;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        cursor: pointer;
        transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease, border-color 0.15s ease;
      }

      button:hover {
        background: #000000;
        color: #ffffff;
        box-shadow: 0 0 0 1px #ffffff, 0 8px 18px rgba(0, 0, 0, 0.8);
        border-color: #ffffff;
        transform: translateY(-1px);
      }

      button:active {
        transform: translateY(0);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.8);
      }

      .price {
        font-weight: 600;
        margin-bottom: 6px;
        font-size: 0.95rem;
        color: #ffffff;
      }

      .account-meta {
        font-size: 0.85rem;
        line-height: 1.6;
        color: #dcdcdc;
      }

      .account-meta span {
        color: #ffffff;
        font-weight: 500;
      }

      .account-small {
        margin-top: 6px;
      }

      a {
        color: #ffffff;
      }

      #topup-result a {
        word-break: break-all;
        border-bottom: 1px solid rgba(255, 255, 255, 0.3);
      }

      #balance-result,
      #topup-result,
      #redeem-result {
        margin-top: 10px;
        font-size: 0.85rem;
      }

      /* ===== TABS ===== */
      .tab-bar {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 16px 0 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        padding-bottom: 8px;
      }

      .tab-btn {
        background: transparent;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.25);
        color: #f5f5f5;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        padding: 6px 14px;
        cursor: pointer;
        transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease, transform 0.1s ease;
      }

      .tab-btn:hover {
        transform: translateY(-1px);
        border-color: #ffffff;
      }

      .tab-btn.active {
        background: #ffffff;
        color: #000000;
        border-color: #ffffff;
        box-shadow: 0 0 0 1px #ffffff, 0 8px 18px rgba(0, 0, 0, 0.8);
      }

      .tab-panel {
        display: none;
        margin-top: 10px;
      }

      .tab-panel.active {
        display: block;
      }

      .results-card {
        min-height: 220px;
        max-height: 620px;
        overflow-y: auto;
        margin-top: 12px;
      }



      .yt-wrap {
        width: 100%;
        aspect-ratio: 16 / 9;
        border-radius: 12px;
        overflow: hidden;
        margin: 12px 0 10px;
        box-shadow: 0 0 20px rgba(0, 0, 0, 0.85);
      }

      .yt-wrap iframe {
        width: 100%;
        height: 100%;
        border: 0;
      }

      .tutorial-steps {
        margin-top: 10px;
        font-size: 0.85rem;
        line-height: 1.6;
        color: #d4d4d4;
      }

      .tutorial-steps li {
        margin-bottom: 4px;
      }









      #search-result {
        margin-top: 8px;
        font-size: 0.85rem;
      }

      #search-result > .card {
        margin-top: 10px;
      }

      /* Review stars */
      .star-row {
        display: flex;
        gap: 6px;
        margin-top: 10px;
        font-size: 1.6rem;
      }

      .star {
        cursor: pointer;
        opacity: 0.4;
        transition: opacity 0.15s ease, transform 0.1s ease;
        user-select: none;
      }

      .star:hover {
        transform: translateY(-1px);
        opacity: 1;
      }

      .star.active {
        opacity: 1;
      }

      @media (max-width: 640px) {
        .app-shell {
          padding: 18px 14px 22px;
          border-radius: 14px;
        }

        .topbar {
          flex-direction: column;
          align-items: flex-start;
          gap: 4px;
        }
      }
    </style>
  </head>
  <body>
    <canvas id="snow-canvas"></canvas>

    <div class="app-shell">
      <div class="topbar">
        <div class="topbar-title">Konvy Accounts – Web Panel</div>
        <div class="topbar-user">
          {% if logged_in %}
            Logged in as <strong>{{ username }}</strong> |
            <a href="{{ url_for('logout') }}">Logout</a>
          {% else %}
            <a href="{{ url_for('login') }}">Login</a> Â·
            <a href="{{ url_for('register') }}">Register</a>
          {% endif %}
        </div>
      </div>

      <p class="small">
        Search Fortnite accounts, then sign up to buy and manage them securely.
      </p>

      <!-- TAB BAR -->
      <div class="tab-bar">
        <button class="tab-btn" data-tab-target="#tab-tutorial">Tutorial</button>
        <button class="tab-btn active" data-tab-target="#tab-buy">Search Accounts</button>

        {% if logged_in %}
          <button class="tab-btn" data-tab-target="#tab-balance">Reload Balance</button>
          <button class="tab-btn" data-tab-target="#tab-my-accounts">My Account Info</button>
          <button class="tab-btn" data-tab-target="#tab-redeem">Redeem</button>
          {% if has_purchases %}
          <button class="tab-btn" data-tab-target="#tab-review">Review</button>
          {% endif %}
        {% endif %}
      </div>

      <!-- TAB: TUTORIAL -->
      <div id="tab-tutorial" class="tab-panel">
        <div class="card">
          <h2>How Konvy Accounts Works</h2>
          <p class="small">
            Watch this quick tutorial, then follow the steps below to use Konvy Accounts.
          </p>

          <div class="yt-wrap">
            <iframe
              src="https://www.youtube.com/embed/uhL9-_EyKvM"
              title="Konvy Accounts Tutorial"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowfullscreen>
            </iframe>
          </div>

          <ol class="tutorial-steps">
            <li>Search any Fortnite item (ex: <strong>Black Knight</strong>) on the <strong>Search Accounts</strong> tab.</li>
            <li>When you find an account you like, hit <strong>Buy</strong> â€“ you'll be asked to sign up or log in.</li>
            <li>After you login, your balance, purchases, and redeem options unlock in the other tabs.</li>
            <li>Once bought, your account login info shows under <strong>My Account Info</strong>.</li>
          </ol>
        </div>
      </div>


      <!-- TAB: BUY / SEARCH -->
      <div id="tab-buy" class="tab-panel active">
        <div class="row card">
          <h2>Fortnite Search</h2>
          <form id="search-form">
            <label>Item(s)
              <input name="item" placeholder="Black Knight, Orange Justice" required />
            </label>
            <label>Min days offline (0 = any)
              <input name="days" type="number" value="0" />
            </label>
            <label>Min skins (0 = any)
              <input name="skins" type="number" value="0" />
            </label>
            <button type="submit">Search</button>
          </form>
        </div>

        <div class="card results-card">
          <h2>Results</h2>
          <p class="small" id="search-description">
            Matching Fortnite accounts will show here after you search.
          </p>
          <div id="search-result"></div>
        </div>
      </div>  <!-- close #tab-buy -->

      {% if logged_in %}
      <!-- TAB: BALANCE / RELOAD -->
      <div id="tab-balance" class="tab-panel">
        <div class="row card">
          <h2>Balance</h2>
          <form id="balance-form">
            <button type="submit">Check Balance</button>
          </form>
          <div id="balance-result"></div>
        </div>

        <div class="row card">
          <h2>Top Up</h2>
          <form id="topup-form">
            <label>Amount in USD
              <input name="amount" type="number" step="0.01" value="10" />
            </label>
            <button type="submit">Generate Shopify Link</button>
          </form>
          <div id="topup-result"></div>
        </div>
      </div>

      <!-- TAB: MY ACCOUNT INFO -->
      <div id="tab-my-accounts" class="tab-panel">
        <div class="card">
          <h2>My Accounts</h2>
          <p class="small">Browse Fortnite accounts you've already purchased.</p>
          <div id="my-accounts-view"></div>
          <div style="margin-top:10px; display:flex; gap:8px;">
            <button id="prev-account-btn" type="button">Previous</button>
            <button id="next-account-btn" type="button">Next</button>
          </div>
          <div class="small" id="my-accounts-indicator" style="margin-top:6px;"></div>
        </div>
      </div>

      <!-- TAB: REDEEM -->
      <div id="tab-redeem" class="tab-panel">
        <div class="row card">
          <h2>Top Up Balance</h2>
          <p>Your balance is credited <strong>automatically</strong> when your Shopify order is paid &mdash; no manual redemption needed.</p>
          <p class="small">Make sure you enter <code>user:{{ username }}</code> in the <strong>Order Notes</strong> field at Shopify checkout so we know which account to credit.</p>
          <hr />
          <p class="small">If your balance has not appeared within a few minutes after payment, use the manual form below as a fallback.</p>
          <form id="redeem-form">
            <label>Order number (without #)
              <input name="order_number" type="number" />
            </label>
            <button type="submit">Redeem Manually</button>
          </form>
          <div id="redeem-result"></div>
        </div>
      </div>

      {% if has_purchases %}
      <!-- TAB: REVIEW -->
      <div id="tab-review" class="tab-panel">
        <div class="row card">
          <h2>Rate Your Experience</h2>
          <p class="small">Please click a star to leave a rating (1â€“5).</p>
          <div class="star-row" id="star-rating">
            <span class="star" data-value="1">★</span>
            <span class="star" data-value="2">★</span>
            <span class="star" data-value="3">★</span>
            <span class="star" data-value="4">★</span>
            <span class="star" data-value="5">★</span>
          </div>
          <button type="button" id="submit-review-btn">Submit Review</button>
          <div class="small" id="star-result" style="margin-top:8px;"></div>
        </div>
      </div>
      {% endif %}
      {% endif %}

    </div> <!-- end .app-shell -->

    <script>
      const KONVY_LOGGED_IN = {{ 'true' if logged_in else 'false' }};

      // Helper to post JSON
      async function postJSON(url, data) {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });
        const json = await res.json();
        if (!res.ok) {
          throw new Error(json.message || json.error || 'Unknown error');
        }
        return json;
      }

      function wait(ms) {
        return new Promise((resolve) => window.setTimeout(resolve, ms));
      }

      // =========== HELPERS TO EXTRACT LOGIN STRINGS ===========
      function findRawForKey(obj, keyName) {
        if (!obj || typeof obj !== 'object') return null;
        if (Object.prototype.hasOwnProperty.call(obj, keyName)) {
          const val = obj[keyName];
          if (val && typeof val === 'object' && 'raw' in val) {
            return val.raw;
          }
        }
        for (const k in obj) {
          if (!Object.prototype.hasOwnProperty.call(obj, k)) continue;
          const child = obj[k];
          if (child && typeof child === 'object') {
            const found = findRawForKey(child, keyName);
            if (found) return found;
          }
        }
        return null;
      }

      function extractLoginStrings(purchaseResult) {
        if (!purchaseResult || typeof purchaseResult !== 'object') {
          return { epic: null, email: null };
        }
        const epic = findRawForKey(purchaseResult, 'loginData');
        const email = findRawForKey(purchaseResult, 'emailLoginData');
        return { epic, email };
      }

      function buildLoginDisplayText(purchaseResult) {
        const { epic, email } = extractLoginStrings(purchaseResult);
        if (!epic && !email) {
          return 'No login details found in response.';
        }
        let s = '';
        if (epic) s += 'Epic Games: ' + epic + '\\n';
        if (email) s += 'Email Login: ' + email;
        return s;
      }

      function buildLoginDisplayHTML(purchaseResult) {
        const { epic, email } = extractLoginStrings(purchaseResult);
        if (!epic && !email) {
          return '<span class="small">No login details found in this purchase.</span>';
        }
        let html = '<div class="account-meta">';
        if (epic) {
          html += 'Epic Games:<br><code>' + escapeHtml(epic) + '</code><br><br>';
        }
        if (email) {
          html += 'Email Login:<br><code>' + escapeHtml(email) + '</code>';
        }
        html += '</div>';
        return html;
      }

      function escapeHtml(str) {
        return String(str)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      }

      const searchForm = document.getElementById('search-form');
      const searchResult = document.getElementById('search-result');

      if (searchForm) {
        searchForm.addEventListener('submit', async (e) => {
          e.preventDefault();
          searchResult.innerHTML = 'Searching...';
          const formData = new FormData(searchForm);

          const item = formData.get('item');
          const days = Number(formData.get('days') || 0);
          const skins = Number(formData.get('skins') || 0);

          let desc = `The following accounts have "${item}"`;
          if (days > 0) desc += `, have been offline for at least ${days} days`;
          if (skins > 0) desc += `, and have at least ${skins} skins`;
          document.getElementById('search-description').textContent = desc + ":";

          const payload = { item, days, skins };

          try {
            const data = await postJSON('/api/fortnite/search', payload);
            if (!data.accounts || data.accounts.length === 0) {
              searchResult.innerHTML = 'No accounts found.';
              return;
            }
            searchResult.innerHTML = '';
            data.accounts.forEach((acc) => {
              const div = document.createElement('div');
              div.className = 'card';
              div.innerHTML = `
                <div class="price">Price: $${acc.user_price.toFixed(2)}</div>
                <div class="account-meta">
                  Level: <span>${acc.level}</span> <br />
                  Skins: <span>${acc.skins}</span>,
                  Pickaxes: <span>${acc.pickaxes}</span>,
                  Emotes: <span>${acc.emotes}</span>,
                  Gliders: <span>${acc.gliders}</span><br />
                  V-Bucks: <span>${acc.vbucks}</span><br />
                  Last played: <span>${acc.last_played}</span>
                </div>
                <button data-item-id="${acc.item_id}" data-base-price="${acc.base_price}">Buy this account</button>
                <div class="small account-small">Item ID: ${acc.item_id}</div>
              `;
              const btn = div.querySelector('button');
              btn.addEventListener('click', async () => {
                // If not logged in, send to sign up instead of buying
                if (!KONVY_LOGGED_IN) {
                  window.location.href = "{{ url_for('register') }}";
                  return;
                }

                btn.disabled = true;
                btn.textContent = 'Buying...';
                try {
                  const itemId = Number(btn.dataset.itemId);
                  const res = await postJSON('/api/fortnite/buy', { item_id: itemId });
                  const loginText = buildLoginDisplayText(res.purchase_result);
                  alert(res.message + '\\n\\n' + loginText);
                  await loadMyAccounts();
                } catch (err) {
                  alert('Buy error: ' + err.message);
                }
                btn.disabled = false;
                btn.textContent = 'Buy this account';
              });
              searchResult.appendChild(div);
            });
          } catch (err) {
            searchResult.innerHTML = 'Error: ' + err.message;
          }
        });
      }

      const balanceForm = document.getElementById('balance-form');
      const balanceResult = document.getElementById('balance-result');
      if (balanceForm) {
        balanceForm.addEventListener('submit', async (e) => {
          e.preventDefault();
          balanceResult.innerHTML = 'Loading...';
          try {
            const res = await postJSON('/api/balance', {});
            balanceResult.innerHTML = 'Balance: $' + res.balance.toFixed(2);
          } catch (err) {
            balanceResult.innerHTML = 'Error: ' + err.message;
          }
        });
      }

      const topupForm = document.getElementById('topup-form');
      const topupResult = document.getElementById('topup-result');
      if (topupForm) {
        topupForm.addEventListener('submit', async (e) => {
          e.preventDefault();
          topupResult.innerHTML = 'Generating...';
          const formData = new FormData(topupForm);
          const amount = Number(formData.get('amount') || 0);
          try {
            const res = await postJSON('/api/topup', { amount });
            topupResult.innerHTML = `
              <div>Send payment here:</div>
              <a href="${res.checkout_url}" target="_blank">${res.checkout_url}</a>
              <div class="small">Order note will save your username automatically.</div>
            `;
          } catch (err) {
            topupResult.innerHTML = 'Error: ' + err.message;
          }
        });
      }

      const redeemForm = document.getElementById('redeem-form');
      const redeemResult = document.getElementById('redeem-result');
      if (redeemForm) {
        redeemForm.addEventListener('submit', async (e) => {
          e.preventDefault();
          redeemResult.innerHTML = 'Redeeming...';
          const formData = new FormData(redeemForm);
          const order_number = Number(formData.get('order_number') || 0);
          try {
            const res = await postJSON('/api/redeem', { order_number });
            redeemResult.innerHTML = res.message;
          } catch (err) {
            redeemResult.innerHTML = 'Error: ' + err.message;
          }
        });
      }

      // =================== MY ACCOUNTS VIEWER ===================
      let myAccounts = [];
      let myAccountsIndex = 0;

      async function loadMyAccounts() {
        if (!KONVY_LOGGED_IN) return;
        try {
          const res = await postJSON('/api/fortnite/my-accounts', {});
          myAccounts = res.accounts || [];
          myAccountsIndex = 0;
          renderMyAccount();
        } catch (err) {
          console.error('Failed to load my accounts:', err);
        }
      }

      function renderMyAccount() {
        const view = document.getElementById('my-accounts-view');
        const indicator = document.getElementById('my-accounts-indicator');
        const prevBtn = document.getElementById('prev-account-btn');
        const nextBtn = document.getElementById('next-account-btn');

        if (!view || !indicator || !prevBtn || !nextBtn) return;

        if (!myAccounts.length) {
          view.innerHTML = '<span class="small">No purchased accounts yet.</span>';
          indicator.textContent = '';
          prevBtn.disabled = true;
          nextBtn.disabled = true;
          return;
        }

        if (myAccountsIndex < 0) myAccountsIndex = 0;
        if (myAccountsIndex >= myAccounts.length) {
          myAccountsIndex = myAccounts.length - 1;
        }

        const acc = myAccounts[myAccountsIndex];
        const ts = acc.timestamp ? new Date(acc.timestamp * 1000) : null;
        const when = ts ? ts.toLocaleString() : 'Unknown time';

        const htmlLogins = buildLoginDisplayHTML(acc.purchase_result);

        view.innerHTML = `
          <div class="small">Purchased: ${escapeHtml(when)}</div>
          ${htmlLogins}
        `;

        indicator.textContent = `Account ${myAccountsIndex + 1} of ${myAccounts.length}`;

        prevBtn.disabled = myAccountsIndex === 0;
        nextBtn.disabled = myAccountsIndex === myAccounts.length - 1;
      }

      document.addEventListener('DOMContentLoaded', () => {
        const prevBtn = document.getElementById('prev-account-btn');
        const nextBtn = document.getElementById('next-account-btn');
        if (prevBtn && nextBtn) {
          prevBtn.addEventListener('click', () => {
            if (myAccountsIndex > 0) {
              myAccountsIndex--;
              renderMyAccount();
            }
          });
          nextBtn.addEventListener('click', () => {
            if (myAccountsIndex < myAccounts.length - 1) {
              myAccountsIndex++;
              renderMyAccount();
            }
          });
        }

        // Load accounts on page open (only if logged in)
        loadMyAccounts();

        // TAB SWITCHING
        const tabButtons = document.querySelectorAll('.tab-btn[data-tab-target]');
        const tabPanels = document.querySelectorAll('.tab-panel');
        tabButtons.forEach((btn) => {
          btn.addEventListener('click', () => {
            const target = btn.getAttribute('data-tab-target');
            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanels.forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            const panel = document.querySelector(target);
            if (panel) panel.classList.add('active');
          });
        });

        // STAR RATING (FAKE SUBMIT)
        const starRow = document.getElementById('star-rating');
        const starResult = document.getElementById('star-result');
        const submitReviewBtn = document.getElementById('submit-review-btn');
        let currentRating = 0;

        if (starRow && starResult && submitReviewBtn) {
          const stars = starRow.querySelectorAll('.star');

          stars.forEach(star => {
            star.addEventListener('click', () => {
              const value = Number(star.dataset.value);
              currentRating = value;

              stars.forEach(s => {
                const v = Number(s.dataset.value);
                s.classList.toggle('active', v <= value);
              });

              starResult.textContent = `Selected: ${value} out of 5. Click "Submit Review" to send.`;
            });
          });

          submitReviewBtn.addEventListener('click', () => {
            if (!currentRating) {
              starResult.textContent = 'Please select a star rating first.';
              return;
            }

            submitReviewBtn.disabled = true;
            submitReviewBtn.textContent = 'Submitted';
            starResult.textContent = `Thanks for your review! You rated us ${currentRating} out of 5.`;
          });
        }
      });

      // =================== SNOW ANIMATION ===================
      (function () {
        const canvas = document.getElementById('snow-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        let width, height;
        let flakes = [];

        function resize() {
          width = canvas.width = window.innerWidth;
          height = canvas.height = window.innerHeight;
        }
        window.addEventListener('resize', resize);
        resize();

        const FLAKE_COUNT = 150;

        function initFlakes() {
          flakes = [];
          for (let i = 0; i < FLAKE_COUNT; i++) {
            flakes.push({
              x: Math.random() * width,
              y: Math.random() * height,
              r: Math.random() * 2 + 1,
              v: Math.random() * 0.5 + 0.3,
              drift: (Math.random() - 0.5) * 0.5
            });
          }
        }

        function draw() {
          ctx.clearRect(0, 0, width, height);
          ctx.beginPath();
          for (const f of flakes) {
            ctx.moveTo(f.x, f.y);
            ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2);

            f.y += f.v;
            f.x += f.drift + Math.sin(f.y * 0.01) * 0.2;

            if (f.y > height + 5) {
              f.y = -5;
              f.x = Math.random() * width;
            }
            if (f.x > width + 5) f.x = -5;
            if (f.x < -5) f.x = width + 5;
          }
          ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
          ctx.fill();
          requestAnimationFrame(draw);
        }

        initFlakes();
        draw();
      })();
    </script>
  </body>
</html>
"""


REGISTER_HTML = """
<!doctype html>
<html>
  <head>
    <title>Konvy Accounts – Register</title>
    <style>
      * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }

      body {
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #000;
        background-image: radial-gradient(circle at top, #222 0, #000 55%);
        background-attachment: fixed;
        color: #f6f6f6;
        min-height: 100vh;
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 40px 16px;
        position: relative;
        overflow: hidden;
      }

      #snow-canvas {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: -1;
        pointer-events: none;
      }

      .auth-shell {
        width: 100%;
        max-width: 420px;
        padding: 26px 22px 24px;
        border-radius: 18px;
        background: rgba(0, 0, 0, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow:
          0 24px 60px rgba(0, 0, 0, 0.9),
          0 0 0 1px rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(18px);
      }

      .auth-title {
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        font-size: 0.85rem;
        color: #fdfdfd;
        margin-bottom: 4px;
      }

      .auth-heading {
        font-size: 1.35rem;
        font-weight: 500;
        margin-bottom: 4px;
      }

      .auth-sub {
        font-size: 0.8rem;
        color: #a3a3a3;
        margin-bottom: 18px;
      }

      form {
        margin-top: 8px;
      }

      label {
        display: block;
        margin-top: 12px;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #bfbfbf;
      }

      input {
        margin-top: 6px;
        padding: 9px 12px;
        width: 100%;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.18);
        background: rgba(0, 0, 0, 0.85);
        color: #f9f9f9;
        outline: none;
        font-size: 0.9rem;
        transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
      }

      input::placeholder {
        color: #666;
      }

      input:focus {
        border-color: #ffffff;
        background: rgba(0, 0, 0, 0.96);
        box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.4);
      }

      button {
        margin-top: 16px;
        padding: 9px 20px;
        width: 100%;
        border-radius: 999px;
        border: 1px solid #ffffff;
        background: #ffffff;
        color: #000000;
        font-size: 0.8rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        cursor: pointer;
        transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease;
      }

      button:hover {
        background: #000000;
        color: #ffffff;
        box-shadow: 0 0 0 1px #ffffff, 0 8px 18px rgba(0, 0, 0, 0.9);
        transform: translateY(-1px);
      }

      button:active {
        transform: translateY(0);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.8);
      }

      .auth-footer {
        margin-top: 16px;
        font-size: 0.8rem;
        color: #b5b5b5;
        text-align: center;
      }

      .auth-footer a {
        color: #ffffff;
        text-decoration: none;
        border-bottom: 1px solid rgba(255, 255, 255, 0.3);
      }

      .auth-footer a:hover {
        border-color: #ffffff;
      }

      .error {
        margin-top: 10px;
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 0.8rem;
        background: rgba(255, 77, 77, 0.1);
        border: 1px solid rgba(255, 77, 77, 0.5);
        color: #ffb3b3;
      }

      @media (max-width: 480px) {
        .auth-shell {
          padding: 22px 18px 20px;
          border-radius: 14px;
        }
      }
    </style>
  </head>
  <body>
    <canvas id="snow-canvas"></canvas>

    <div class="auth-shell">
      <div class="auth-title">Konvy Accounts</div>
      <div class="auth-heading">Create account</div>
      <div class="auth-sub">Register to start buying Fortnite accounts.</div>

      {% if error %}
      <div class="error">{{ error }}</div>
      {% endif %}

      <form method="post">
        <label>Username
          <input name="username" placeholder="yourname" value="{{ username_prefill or '' }}">
        </label>
        <label>Password
          <input name="password" type="password" placeholder="Choose a password">
        </label>
        <button type="submit">Register</button>
      </form>

      <div class="auth-footer">
        Already have an account?
        <a href="{{ url_for('login') }}">Sign in</a>
      </div>
    </div>

    <script>
      (function () {
        const canvas = document.getElementById('snow-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        let width, height;
        let flakes = [];

        function resize() {
          width = canvas.width = window.innerWidth;
          height = canvas.height = window.innerHeight;
        }
        window.addEventListener('resize', resize);
        resize();

        const FLAKE_COUNT = 140;

        function initFlakes() {
          flakes = [];
          for (let i = 0; i < FLAKE_COUNT; i++) {
            flakes.push({
              x: Math.random() * width,
              y: Math.random() * height,
              r: Math.random() * 2 + 1,
              v: Math.random() * 0.5 + 0.3,
              drift: (Math.random() - 0.5) * 0.5
            });
          }
        }

        function draw() {
          ctx.clearRect(0, 0, width, height);
          ctx.beginPath();
          for (const f of flakes) {
            ctx.moveTo(f.x, f.y);
            ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2);

            f.y += f.v;
            f.x += f.drift + Math.sin(f.y * 0.01) * 0.2;

            if (f.y > height + 5) {
              f.y = -5;
              f.x = Math.random() * width;
            }
            if (f.x > width + 5) f.x = -5;
            if (f.x < -5) f.x = width + 5;
          }
          ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
          ctx.fill();
          requestAnimationFrame(draw);
        }

        initFlakes();
        draw();
      })();
    </script>
  </body>
</html>
"""
TUTORIAL_HTML = """
<!doctype html>
<html>
  <head>
    <title>Konvy Accounts – Tutorial</title>
    <style>
      body {
        margin:0;
        padding:0;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI";
        background: #000;
        background-image: radial-gradient(circle at top, #222 0, #000 55%);
        color: #fff;
        min-height: 100vh;
        display:flex;
        justify-content:center;
        align-items:flex-start;
        padding:40px 16px;
        position:relative;
        overflow:hidden;
      }

      #snow-canvas {
        position:absolute;
        top:0; left:0;
        width:100%; height:100%;
        z-index:-1;
        pointer-events:none;
      }

      .tutorial-shell {
        max-width:900px;
        width:100%;
        padding:24px 22px;
        border-radius:18px;
        background: rgba(0,0,0,0.7);
        border:1px solid rgba(255,255,255,0.08);
        backdrop-filter: blur(18px);
      }

      h1 {
        margin-bottom:14px;
        font-size:1.5rem;
      }

      .yt-wrap {
        width:100%;
        aspect-ratio:16 / 9;
        border-radius:12px;
        overflow:hidden;
        margin-top:16px;
        box-shadow:0 0 20px rgba(0,0,0,0.8);
      }

      iframe {
        width:100%;
        height:100%;
        border:0;
      }

      a {
        color:#fff;
        text-decoration:underline;
      }
    </style>
  </head>

  <body>
    <canvas id="snow-canvas"></canvas>

    <div class="tutorial-shell">
      <h1>Konvy Accounts – Tutorial</h1>
      <p>Welcome! Watch this quick tutorial before using the site.</p>

      <div class="yt-wrap">
        <iframe 
          src="https://www.youtube.com/embed/uhL9-_EyKvM"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowfullscreen></iframe>
      </div>

      <p style="margin-top:20px;">
        When you're ready, <a href="/login">login here</a> or 
        <a href="/register">create an account</a>.
      </p>
    </div>

    <script>
      // snow animation reused
      (function(){
        const canvas = document.getElementById('snow-canvas');
        const ctx = canvas.getContext('2d');
        function resize(){
          canvas.width = window.innerWidth;
          canvas.height = window.innerHeight;
        }
        window.addEventListener('resize', resize);
        resize();

        let flakes = [];
        for (let i=0; i<130; i++){
          flakes.push({
            x: Math.random()*canvas.width,
            y: Math.random()*canvas.height,
            r: Math.random()*2+1,
            v: Math.random()*0.6+0.3,
            drift: (Math.random()-0.5)*0.5
          });
        }

        function draw(){
          ctx.clearRect(0,0,canvas.width,canvas.height);
          ctx.beginPath();
          for (const f of flakes){
            ctx.moveTo(f.x,f.y);
            ctx.arc(f.x,f.y,f.r,0,Math.PI*2);
            f.y += f.v;
            f.x += f.drift;
            if (f.y>canvas.height) f.y = -5;
            if (f.x>canvas.width) f.x = -5;
            if (f.x<0) f.x = canvas.width + 5;
          }
          ctx.fillStyle="rgba(255,255,255,0.85)";
          ctx.fill();
          requestAnimationFrame(draw);
        }
        draw();
      })();
    </script>
  </body>
</html>
"""














@app.route("/warranty")
def warranty():
    logged_in = "username" in session
    username = session.get("username", "Guest")
    balance = "0.00"
    if logged_in:
        balance = f"{get_balance(username) / 100:.2f}"
    return render_template(
        "warranty.html",
        logged_in=logged_in,
        username=username,
        balance=balance,
        active_page="warranty",
    )


@app.route("/support")
def support_page():
    logged_in = "username" in session
    username = session.get("username", "Guest")
    balance = "0.00"
    user_profile_pic = ""
    if logged_in:
        balance = f"{get_balance(username) / 100:.2f}"
        users = _load_users()
        user_profile_pic = (users.get(username, {}) or {}).get("profile_pic", "")
    return render_template(
        "support.html",
        logged_in=logged_in,
        username=username,
        balance=balance,
        active_page="support",
        is_support_admin=is_admin_user(username) if logged_in else False,
        user_profile_pic=user_profile_pic,
    )


@app.route("/terms")
def terms_page():
    logged_in = "username" in session
    username = session.get("username", "Guest")
    balance = "0.00"
    if logged_in:
        balance = f"{get_balance(username) / 100:.2f}"
    return render_template(
        "terms.html",
        logged_in=logged_in,
        username=username,
        balance=balance,
        active_page="terms",
    )



@app.route("/tutorial")
def tutorial():
    return render_template_string(TUTORIAL_HTML)

@app.route("/how-it-works")
def how_it_works():
    logged_in = "username" in session
    username = session.get("username", "Guest")
    balance = "0.00"
    if logged_in:
        balance = f"{get_balance(username) / 100:.2f}"
    return render_template(
        "how_it_works.html",
        logged_in=logged_in,
        username=username,
        balance=balance,
        active_page="how-it-works",
    )

# OG Accounts page
# Main dashboard route - now just shows search
@app.route("/dashboard")
def dashboard():
    logged_in = "username" in session
    username = session.get("username", "Guest")

    balance_cents = 0
    purchases = []
    has_topup = False

    if logged_in:
        balance_cents = get_balance(username)
        purchases = get_purchases(username)
        has_topup = user_has_any_topup(username)

    balance = f"{balance_cents / 100:.2f}"

    return render_template(
        "dashboard.html",
        username=username,
        balance=balance,
        purchases=purchases,
        logged_in=logged_in,
        has_topup=has_topup,
        active_page="home",
    )


# Balance page
@app.route("/balance")
@login_required_page
def balance_page():
    username = session["username"]
    balance_cents = get_balance(username)
    balance = f"{balance_cents / 100:.2f}"
    has_topup = user_has_any_topup(username)
    return render_template(
        "balance.html",
        username=username,
        balance=balance,
        logged_in=True,
        has_topup=has_topup,
        active_page="balance",
    )

# My Accounts page
@app.route("/my-accounts")
@login_required_page
def my_accounts_page():
    username = session["username"]
    balance_cents = get_balance(username)
    purchases = get_purchases(username)
    balance = f"{balance_cents / 100:.2f}"
    has_topup = user_has_any_topup(username)
    
    return render_template(
        "my_accounts.html",
        username=username,
        balance=balance,
        purchases=purchases,
        logged_in=True,
        has_topup=has_topup,
        active_page="my-accounts",
    )


@app.route("/purchase-processing")
@login_required_page
def purchase_processing_page():
    username = session["username"]
    balance_cents = get_balance(username)
    balance = f"{balance_cents / 100:.2f}"
    has_topup = user_has_any_topup(username)

    locked_purchase = get_purchase_lock()
    raw_item_id = request.args.get("item_id", "").strip()
    item_title = request.args.get("title", "").strip() or ""
    item_id = 0
    try:
        item_id = int(raw_item_id)
    except (TypeError, ValueError):
        item_id = 0

    if item_id <= 0 and locked_purchase:
        item_id = int(locked_purchase["item_id"])
        if not item_title:
            item_title = str(locked_purchase.get("item_title") or "").strip()

    if not item_title:
        item_title = DEFAULT_PURCHASE_ITEM_TITLE

    if item_id <= 0:
        return redirect(url_for("dashboard"))

    if locked_purchase and int(locked_purchase["item_id"]) != item_id:
        return redirect(
            url_for(
                "purchase_processing_page",
                item_id=locked_purchase["item_id"],
                title=locked_purchase["item_title"],
            )
        )

    if not locked_purchase:
        set_purchase_lock(item_id, item_title)

    return render_template(
        "purchase_processing.html",
        username=username,
        balance=balance,
        logged_in=True,
        has_topup=has_topup,
        active_page="home",
        item_id=item_id,
        item_title=item_title[:MAX_PURCHASE_ITEM_TITLE_LENGTH],
    )


def _extract_cosmetic_names(account: dict, field_name: str) -> List[str]:
    values = account.get(field_name) or []
    if not isinstance(values, list):
        return []
    names: List[str] = []
    for item in values:
        if isinstance(item, dict):
            name = item.get("title") or item.get("name")
        else:
            name = str(item)
        if name:
            names.append(str(name))
    return names


def _to_status_bool(value) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


@app.route("/account/<int:item_id>")
def account_detail_page(item_id: int):
    username = session.get("username")
    logged_in = bool(username)
    balance = "0.00"
    has_topup = False

    if logged_in:
        balance_cents = get_balance(username)
        balance = f"{balance_cents / 100:.2f}"
        has_topup = user_has_any_topup(username)

    try:
        account = find_account_by_item_id(item_id)
    except Exception as e:
        app.logger.error("Failed to load account %s: %s", item_id, e)
        account = None

    if not account:
        # Account is gone from marketplace - show as sold with available info
        _push_activity("view", username or "guest", {"item_id": item_id, "title": f"Account #{item_id}"})
        return render_template("account_detail.html",
            username=username or "Guest", balance=balance, logged_in=logged_in,
            has_topup=has_topup, active_page="home",
            account_detail={
                "item_id": item_id, "is_sold": True, "title": f"Account #{item_id}",
                "price": 0, "base_price": 0, "original_price": None, "discount_percent": 0,
                "level": 0, "vbucks": 0, "country": "Unknown", "last_activity": "N/A",
                "days_ago": None, "skins": [], "pickaxes": [], "emotes": [], "gliders": [],
                "preview_cosmetics": [], "bp_level": 0, "lifetime_wins": 0, "season_num": 0,
                "shop_skins": 0,
                "status": {"xbox_linkable": None, "psn_linkable": None, "email_changeable": None,
                    "email_access": None, "battle_pass": None, "stw_edition": None},
                "is_og": False, "konvy_score": 0,
                "rarity_breakdown": {"legendary": 0, "epic": 0, "rare": 0, "uncommon": 0},
                "featured_cosmetics": [], "skin_count": 0, "pickaxe_count": 0,
                "emote_count": 0, "glider_count": 0, "views": 0, "favorites": 0,
            }), 200

    _push_activity("view", username or "guest", {"item_id": item_id, "title": account.get("title") or account.get("title_en") or ""})
    is_sold = is_item_sold(item_id)

    skins = _extract_cosmetic_names(account, "fortniteSkins")
    pickaxes = _extract_cosmetic_names(account, "fortnitePickaxe")
    emotes = _extract_cosmetic_names(account, "fortniteDance")
    gliders = _extract_cosmetic_names(account, "fortniteGliders")

    try:
        base_price = float(account.get("price") or 0)
    except Exception:
        base_price = 0.0

    user_price = round(base_price * get_multiplier_for_account(account), 2)
    discount_info = get_active_discount()
    discounted_price = round(user_price * (100 - discount_info["percent"]) / 100, 2) if discount_info["active"] else user_price
    days_ago = compute_days_ago(account)

    status = {
        "xbox_linkable": _to_status_bool(account.get("xbox_linkable") or account.get("xboxLinkable") or account.get("xbl_linkable")),
        "psn_linkable": _to_status_bool(account.get("psn_linkable") or account.get("psnLinkable")),
        "email_changeable": _to_status_bool(account.get("change_email") or account.get("email_changeable")),
        "email_access": _to_status_bool(account.get("email_login_data") or account.get("email_access")) if account.get("email_login_data") is not None or account.get("email_access") is not None else True,
        "battle_pass": _to_status_bool(account.get("bp") or account.get("battle_pass")),
        "stw_edition": _to_status_bool(account.get("stw") or account.get("fortnite_stw")),
    }

    preview_cosmetics: List[str] = []
    for field_name in ("fortniteSkins", "fortnitePickaxe", "fortniteBackpack", "fortniteDance", "fortniteGliders"):
        values = account.get(field_name) or []
        if not isinstance(values, list):
            continue
        for cosmetic in values:
            if isinstance(cosmetic, dict):
                name = cosmetic.get("title") or cosmetic.get("name")
            else:
                name = str(cosmetic)
            if name:
                preview_cosmetics.append(str(name))
            if len(preview_cosmetics) >= MAX_PREVIEW_COSMETICS:
                break
        if len(preview_cosmetics) >= MAX_PREVIEW_COSMETICS:
            break

    is_og = account_has_og_skin(account)

    # Featured cosmetics - known rare/valuable skin names to check
    rare_skin_names = {
        "renegade raider", "aerial assault trooper", "black knight", "galaxy", "ikonik",
        "the reaper", "skull trooper", "ghoul trooper", "crackshot", "merry marauder",
        "recon expert", "elite agent", "havoc", "trailblazer", "raptor", "power chord",
        "dark voyager", "mission specialist", "flare", "the ace", "survival specialist",
        "diecast", "brilliant striker", "brite gunner", "bunny brawler", "whiplash",
        "shadow ops", "crimson elite", "blue squire", "blue team leader", "rose team leader",
        "commando", "jungle scout", "mogul master", "nomad", "rook", "scorpion",
    }
    featured = [name for name in skins if name.strip().lower() in rare_skin_names][:8]
    featured += [name for name in pickaxes if name.strip().lower() in {"reaper", "rainbow smash", "ac dc", "instigator"}][:2]
    featured = featured[:8]

    # Konvy Score (0-100)
    skin_score = min(len(skins) * 1.5, 30)
    win_score = min((account.get("fortnite_lifetime_wins") or 0) // 5, 20)
    level_score = min((account.get("fortnite_level") or 0) // 3, 20)
    bp_score = 15 if (account.get("bp") or account.get("battle_pass")) else 0
    og_score = 15 if is_og else min(len(featured) * 3, 10)
    konvy_score = min(int(skin_score + win_score + level_score + bp_score + og_score), 100)

    # Rarity breakdown (estimate from known skin rarities)
    rare_keywords = {"legendary": 0, "epic": 0, "rare": 0, "uncommon": 0}
    all_cosmetics = skins + pickaxes + emotes + gliders
    for cname in all_cosmetics:
        lowered = cname.strip().lower()
        if lowered in rare_skin_names: rare_keywords["legendary"] += 1
        elif any(k in lowered for k in ["knight", "reaper", "raider", "galaxy", "ikonik", "skull", "ghoul"]): rare_keywords["epic"] += 1
        elif any(k in lowered for k in ["ace", "agent", "assault", "brawler", "commando"]): rare_keywords["rare"] += 1
        else: rare_keywords["uncommon"] += 1
    rarity_breakdown = rare_keywords

    account_detail = {
        "item_id": item_id,
        "is_sold": is_sold,
        "title": account.get("title") or account.get("title_en") or f"{len(skins)} Skins",
        "price": discounted_price,
        "base_price": base_price,
        "original_price": user_price if discount_info["active"] else None,
        "discount_percent": discount_info["percent"] if discount_info["active"] else 0,
        "level": int(account.get("fortnite_level") or 0),
        "vbucks": int(account.get("fortnite_balance") or 0),
        "country": account.get("country") or "Unknown",
        "last_activity": f"{days_ago} days ago" if days_ago is not None else "Unknown",
        "days_ago": days_ago,
        "skins": skins,
        "pickaxes": pickaxes,
        "emotes": emotes,
        "gliders": gliders,
        "preview_cosmetics": preview_cosmetics,
        "bp_level": account.get("fortnite_book_level") or 0,
        "lifetime_wins": account.get("fortnite_lifetime_wins") or 0,
        "season_num": account.get("fortnite_season_num") or 0,
        "shop_skins": account.get("fortnite_shop_skins_count") or 0,
        "status": status,
        "is_og": is_og,
        "konvy_score": konvy_score,
        "rarity_breakdown": rarity_breakdown,
        "featured_cosmetics": featured,
        "skin_count": len(skins),
        "pickaxe_count": len(pickaxes),
        "emote_count": len(emotes),
        "glider_count": len(gliders),
        "views": _increment_view_count(item_id),
        "favorites": max(1, _get_view_count(item_id) // 10),
    }

    return render_template(
        "account_detail.html",
        username=username,
        balance=balance,
        logged_in=logged_in,
        has_topup=has_topup,
        active_page="home",
        account_detail=account_detail,
    )

@app.route("/transactions")
@login_required_page
def transactions_page():
    username = session["username"]
    balance_cents = get_balance(username)
    balance = f"{balance_cents / 100:.2f}"
    history = _load_topup_history()
    topups_raw = history.get(username, [])
    topups_raw = sorted(topups_raw, key=lambda x: x.get("timestamp", 0), reverse=True)
    # Format timestamps for display
    topups = []
    for t in topups_raw:
        entry = dict(t)
        ts = t.get("timestamp", 0)
        if ts:
            entry["date_str"] = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%b %d, %Y %H:%M UTC")
        else:
            entry["date_str"] = "—"
        topups.append(entry)
    has_topup = len(topups) > 0
    return render_template("transactions.html", username=username, balance=balance, topups=topups, logged_in=True, has_topup=has_topup, active_page="transactions")

@app.route("/redeem")
def redeem_page():
    if "username" in session:
        return redirect(url_for("balance_page"))
    return redirect(url_for("login"))


@app.route("/admin123", methods=["GET", "POST"])
def admin123_page():
    is_admin = bool(session.get("is_konvy_admin")) or is_admin_user(session.get("username", ""))
    error = ""
    notice = ""

    if request.method == "POST":
        action = request.form.get("action")

        if action == "logout":
            session.pop("is_konvy_admin", None)
            is_admin = False
            notice = "Logged out of admin panel."
        elif action == "login":
            password = request.form.get("password") or ""
            if password == KONVY_ADMIN_PASSWORD:
                session["is_konvy_admin"] = True
                is_admin = True
                notice = "Admin access granted."
            else:
                error = "Invalid admin password."
        elif action == "set_multiplier":
            if not is_admin:
                error = "Admin password required."
            else:
                raw_value = (request.form.get("multiplier") or "").strip()
                try:
                    multiplier = float(raw_value)
                except ValueError:
                    multiplier = 0.0

                if multiplier < MIN_LZT_MULTIPLIER or multiplier > MAX_LZT_MULTIPLIER:
                    error = f"Multiplier must be between {MIN_LZT_MULTIPLIER:.2f} and {MAX_LZT_MULTIPLIER:.0f}."
                else:
                    set_lzt_multiplier(multiplier)
                    notice = f"Saved multiplier: {multiplier:.2f}x"
        elif action == "set_og_multiplier":
            if not is_admin:
                error = "Admin password required."
            else:
                raw_value = (request.form.get("og_multiplier") or "").strip()
                try:
                    multiplier = float(raw_value)
                except ValueError:
                    multiplier = 0.0

                if multiplier < MIN_LZT_MULTIPLIER or multiplier > MAX_LZT_MULTIPLIER:
                    error = f"OG multiplier must be between {MIN_LZT_MULTIPLIER:.2f} and {MAX_LZT_MULTIPLIER:.0f}."
                else:
                    set_og_multiplier(multiplier)
                    notice = f"Saved OG multiplier: {multiplier:.2f}x"

    og_cfg = _load_og_config()
    return render_template(
        "admin123.html",
        is_admin=is_admin,
        current_multiplier=f"{get_lzt_multiplier():.2f}",
        current_og_multiplier=f"{get_og_multiplier():.2f}",
        error=error,
        notice=notice,
        og_skins=OG_SKINS,
        og_accounts=og_cfg.get("accounts", {}),
        active_page="admin",
    )

# ===================== ADMIN API ROUTES =====================

@app.route("/api/admin/pending-topups", methods=["GET", "POST"])
def api_admin_pending_topups():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403

    if request.method == "GET":
        pending = _load_pending_topups()
        return jsonify({"pending": pending})

    data = request.json or {}
    action = data.get("action")
    topup_id = data.get("id")

    pending = _load_pending_topups()
    topup = next((t for t in pending if t["id"] == topup_id), None)

    if not topup:
        return jsonify({"error": "Topup not found"}), 404

    username = topup["username"]
    amount_cents = topup["amount_cents"]
    order_id = topup["order_id"]

    if action == "approve":
        add_balance(username, amount_cents)
        set_user_verification_status(username, "verified")
        history = _load_topup_history()
        for rec in history.get(username, []):
            if rec.get("order_id") == order_id:
                rec["status"] = "completed"
        _save_topup_history(history)
        pending = [t for t in pending if t["id"] != topup_id]
        _save_pending_topups(pending)
        add_topup_notification(username, amount_cents, topup_id)
        return jsonify({"ok": True, "message": f"Approved and verified {username}"})

    elif action == "approve_verify_again":
        add_balance(username, amount_cents)
        set_user_verification_status(username, "verify_each")
        history = _load_topup_history()
        for rec in history.get(username, []):
            if rec.get("order_id") == order_id:
                rec["status"] = "completed"
        _save_topup_history(history)
        pending = [t for t in pending if t["id"] != topup_id]
        _save_pending_topups(pending)
        add_topup_notification(username, amount_cents, topup_id)
        return jsonify({"ok": True, "message": f"Approved (verify each time) {username}"})

    elif action == "deny":
        bl = _load_blacklist()
        bl.add(username)
        _save_blacklist(bl)
        set_user_verification_status(username, "blacklisted")
        history = _load_topup_history()
        for rec in history.get(username, []):
            if rec.get("order_id") == order_id:
                rec["status"] = "denied"
        _save_topup_history(history)
        pending = [t for t in pending if t["id"] != topup_id]
        _save_pending_topups(pending)
        return jsonify({"ok": True, "message": f"Denied and blacklisted {username}"})

    return jsonify({"error": "Unknown action"}), 400


@app.route("/ticket-uploads/<ticket_id>/<filename>")
def serve_ticket_upload(ticket_id: str, filename: str):
    """Serve a ticket attachment file. Accessible to ticket owner or admin."""
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 403
    # Validate ticket_id format to prevent path traversal
    if not re.fullmatch(r"tkt_[0-9a-f]{12}", ticket_id):
        return jsonify({"error": "Not found"}), 404
    # Validate filename format (stored as {16 hex chars}_{safe_name})
    if not re.fullmatch(r"[0-9a-f]{16}_.+", filename, re.IGNORECASE):
        return jsonify({"error": "Not found"}), 404
    is_admin = is_admin_user(session.get("username", ""))
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket:
        return jsonify({"error": "Not found"}), 404
    if not is_admin and str(ticket.get("username") or "") != session["username"]:
        return jsonify({"error": "Not found"}), 404
    # Verify the filename actually exists in this ticket's attachments
    all_attachments = [
        a.get("stored_name")
        for m in (ticket.get("messages") or [])
        for a in (m.get("attachments") or [])
    ]
    if filename not in all_attachments:
        return jsonify({"error": "Not found"}), 404
    ticket_dir = os.path.join(TICKET_UPLOADS_DIR, ticket_id)
    # Explicit canonicalization as defense-in-depth
    resolved_dir = os.path.realpath(ticket_dir)
    safe_root = os.path.realpath(TICKET_UPLOADS_DIR)
    if not resolved_dir.startswith(safe_root + os.sep):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(resolved_dir, filename)


@app.route("/api/admin/support-tickets", methods=["GET"])
def api_admin_support_tickets():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403
    tickets = _sort_support_tickets(_load_support_tickets())
    return jsonify({"tickets": [_serialize_ticket_for_user(t, with_internal_notes=True) for t in tickets]})


@app.route("/api/admin/support-tickets/<ticket_id>/reply", methods=["POST"])
def api_admin_support_ticket_reply(ticket_id: str):
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403
    message = request.form.get("message") or (request.json or {}).get("message") or ""
    uploaded_files = request.files.getlist("files[]")
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    attachments, upload_err = _save_ticket_attachments(ticket_id, uploaded_files)
    if upload_err:
        return jsonify({"error": upload_err}), 400
    ok, msg = _append_ticket_message(ticket, "admin", "Admin", message, attachments)
    if not ok:
        return jsonify({"error": msg}), 400
    _save_support_tickets(_sort_support_tickets(tickets))
    ticket_owner = str(ticket.get("username") or "")
    clean_message = (message or "").strip()
    site_url = request.url_root.rstrip("/") + "/support"
    threading.Thread(
        target=_send_ticket_reply_notification_email,
        args=(ticket_owner, ticket, clean_message, site_url),
        daemon=True,
    ).start()
    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_user(ticket, with_internal_notes=True)})


@app.route("/api/admin/support-tickets/<ticket_id>/close", methods=["POST"])
def api_admin_support_ticket_close(ticket_id: str):
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    ok, msg = _close_ticket(ticket, "admin")
    if not ok:
        return jsonify({"error": msg}), 400
    _save_support_tickets(_sort_support_tickets(tickets))
    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_user(ticket, with_internal_notes=True)})


@app.route("/api/admin/users", methods=["GET"])
def api_admin_users():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403

    users = _load_users()
    result = []
    for uname, info in users.items():
        balance_cents = get_balance(uname)
        result.append({
            "username": uname,
            "balance": balance_cents / 100,
            "verification_status": info.get("verification_status", "unverified"),
            "is_blacklisted": is_blacklisted(uname),
        })
    return jsonify({"users": result})


@app.route("/api/admin/set-balance", methods=["POST"])
def api_admin_set_balance():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json or {}
    uname = data.get("username", "").strip()
    new_balance_dollars = float(data.get("balance", 0))

    if not uname:
        return jsonify({"error": "Username required"}), 400

    users = _load_users()
    if uname not in users:
        return jsonify({"error": "User not found"}), 404

    current = get_balance(uname)
    new_cents = int(round(new_balance_dollars * 100))
    delta = new_cents - current
    add_balance(uname, delta)

    return jsonify({"ok": True, "new_balance": get_balance(uname) / 100})


@app.route("/api/admin/set-verification", methods=["POST"])
def api_admin_set_verification():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json or {}
    uname = data.get("username", "").strip()
    status = data.get("status", "").strip()

    valid_statuses = ["unverified", "verified", "verify_each", "blacklisted"]
    if status not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400

    users = _load_users()
    if uname not in users:
        return jsonify({"error": "User not found"}), 404

    bl = _load_blacklist()
    if status == "blacklisted":
        bl.add(uname)
    else:
        bl.discard(uname)
    _save_blacklist(bl)

    set_user_verification_status(uname, status)
    return jsonify({"ok": True})


@app.route("/api/admin/blacklist", methods=["GET", "POST"])
def api_admin_blacklist():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403

    if request.method == "GET":
        bl = _load_blacklist()
        return jsonify({"blacklist": list(bl)})

    data = request.json or {}
    action = data.get("action")
    uname = data.get("username", "").strip()

    bl = _load_blacklist()
    if action == "remove":
        bl.discard(uname)
        _save_blacklist(bl)
        set_user_verification_status(uname, "unverified")
        return jsonify({"ok": True})
    elif action == "add":
        bl.add(uname)
        _save_blacklist(bl)
        set_user_verification_status(uname, "blacklisted")
        return jsonify({"ok": True})

    return jsonify({"error": "Unknown action"}), 400


@app.route("/api/fortnite/name-account", methods=["POST"])
@login_required_api
def api_name_account():
    data = request.json or {}
    username = session["username"]
    purchase_index = int(data.get("purchase_index", -1))
    name = (data.get("name") or "").strip()[:50]

    if not name:
        return jsonify({"error": "Name required"}), 400

    purchases = _load_purchases()
    user_list = purchases.get(username, [])

    if purchase_index < 0 or purchase_index >= len(user_list):
        return jsonify({"error": "Invalid purchase index"}), 400

    user_list[purchase_index]["name"] = name
    purchases[username] = user_list
    _save_purchases(purchases)

    return jsonify({"ok": True, "name": name})








# ===================== API ROUTES =====================
# (rest of your code stays the same)




# ===================== API ROUTES =====================


@app.route("/api/balance", methods=["POST"])
@login_required_api
def api_balance():
    username = session["username"]
    cents = get_balance(username)
    return jsonify({"balance": cents / 100})


@app.route("/api/topup", methods=["POST"])
@login_required_api
def api_topup():
    data = request.json or {}
    username = session["username"]
    amount = float(data.get("amount") or 0)
    if amount <= 0:
        return jsonify({"error": "Amount must be > 0"}), 400

    quantity = int(round(amount))
    if quantity < 1:
        return jsonify({"error": "Minimum topup is $1"}), 400

    checkout_url = (
        f"https://{SHOPIFY_STORE_DOMAIN}/cart/"
        f"{STORE_CREDIT_VARIANT_ID}:{quantity}"
        f"?note=user:{username}"
    )

    return jsonify({"checkout_url": checkout_url})


@app.route("/api/user/pending-topups", methods=["GET"])
@login_required_api
def api_user_pending_topups():
    username = session["username"]
    pending = _load_pending_topups()
    user_pending = [t for t in pending if t["username"] == username]
    return jsonify({"pending": user_pending})


@app.route("/api/user/notifications", methods=["GET"])
@login_required_api
def api_user_notifications_get():
    username = session["username"]
    notifs = get_user_notifications(username)
    return jsonify({"notifications": notifs})


@app.route("/api/user/notifications/dismiss", methods=["POST"])
@login_required_api
def api_user_notifications_dismiss():
    username = session["username"]
    data = request.json or {}
    notif_id = data.get("id")
    if not notif_id:
        return jsonify({"error": "id required"}), 400
    ok = dismiss_notification(username, notif_id)
    return jsonify({"ok": ok})


@app.route("/api/user/notifications/dismiss-all", methods=["POST"])
@login_required_api
def api_user_notifications_dismiss_all():
    username = session["username"]
    notifs = get_user_notifications(username)
    notif_data = _load_topup_notifications()
    for n in notif_data.get(username, []):
        n["seen"] = True
    _save_topup_notifications(notif_data)
    return jsonify({"ok": True, "dismissed": len(notifs)})


@app.route("/api/support/tickets", methods=["GET", "POST"])
@login_required_api
def api_support_tickets():
    username = session["username"]
    if request.method == "GET":
        tickets = _sort_support_tickets(_load_support_tickets())
        if is_admin_user(username):
            return jsonify({"tickets": [_serialize_ticket_for_user(t) for t in tickets]})
        mine = [t for t in tickets if str(t.get("username") or "") == username]
        return jsonify({"tickets": [_serialize_ticket_for_user(t) for t in mine]})

    subject = request.form.get("subject") or (request.json or {}).get("subject") or ""
    message = request.form.get("message") or (request.json or {}).get("message") or ""
    uploaded_files = [f for f in request.files.getlist("files[]") if f.filename]

    # Validate files before creating the ticket
    if len(uploaded_files) > TICKET_UPLOAD_MAX_FILES_PER_MESSAGE:
        return jsonify({"error": f"Maximum {TICKET_UPLOAD_MAX_FILES_PER_MESSAGE} files per message."}), 400
    for f in uploaded_files:
        if not _ticket_upload_allowed(f.filename):
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "unknown"
            return jsonify({"error": f"File type not allowed: {ext}"}), 400
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > TICKET_UPLOAD_MAX_SIZE_BYTES:
            return jsonify({"error": f"File too large (max {TICKET_UPLOAD_MAX_SIZE_BYTES // (1024 * 1024)} MB): {f.filename}"}), 400

    ok, msg, ticket = create_support_ticket(
        username=username,
        subject=subject,
        message=message,
    )
    if not ok:
        return jsonify({"error": msg}), 400

    # Save files now that we have the ticket id
    if uploaded_files:
        attachments, upload_err = _save_ticket_attachments(ticket["id"], uploaded_files)
        if upload_err:
            return jsonify({"error": upload_err}), 400
        if attachments and ticket.get("messages"):
            ticket["messages"][0]["attachments"] = attachments
            all_tickets = _load_support_tickets()
            stored = _find_ticket(all_tickets, ticket["id"])
            if stored and stored.get("messages"):
                stored["messages"][0]["attachments"] = attachments
            _save_support_tickets(_sort_support_tickets(all_tickets))

    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_user(ticket)})


@app.route("/api/support/tickets/<ticket_id>/reply", methods=["POST"])
@login_required_api
def api_support_ticket_reply(ticket_id: str):
    username = session["username"]
    message = request.form.get("message") or ""
    if not message:
        try:
            message = (request.get_json(silent=True) or {}).get("message") or ""
        except Exception:
            message = ""
    uploaded_files = [f for f in request.files.getlist("files[]") if f.filename]
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    is_owner_or_admin = str(ticket.get("username") or "") == username or is_admin_user(username)
    if not is_owner_or_admin:
        return jsonify({"error": "Ticket not found"}), 404
    if str(ticket.get("username") or "") != username:
        author_type = "admin"
        author = "Admin"
    else:
        author_type = "user"
        author = username
    attachments, upload_err = _save_ticket_attachments(ticket_id, uploaded_files)
    if upload_err:
        return jsonify({"error": upload_err}), 400
    ok, msg = _append_ticket_message(ticket, author_type, author, message, attachments)
    if not ok:
        return jsonify({"error": msg}), 400
    _save_support_tickets(_sort_support_tickets(tickets))
    if author_type == "admin":
        ticket_owner = str(ticket.get("username") or "")
        clean_message = (message or "").strip()
        site_url = request.url_root.rstrip("/") + "/support"
        threading.Thread(
            target=_send_ticket_reply_notification_email,
            args=(ticket_owner, ticket, clean_message, site_url),
            daemon=True,
        ).start()
    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_user(ticket)})


@app.route("/api/support/tickets/<ticket_id>/close", methods=["POST"])
@login_required_api
def api_support_ticket_close(ticket_id: str):
    username = session["username"]
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    is_owner = str(ticket.get("username") or "") == username
    if not is_owner and not is_admin_user(username):
        return jsonify({"error": "Ticket not found"}), 404
    closed_by = "admin" if not is_owner else "user"
    ok, msg = _close_ticket(ticket, closed_by)
    if not ok:
        return jsonify({"error": msg}), 400
    _save_support_tickets(_sort_support_tickets(tickets))
    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_user(ticket)})


@app.route("/api/support/close-all", methods=["POST"])
@login_required_api
def api_support_close_all():
    username = session["username"]
    if not is_admin_user(username):
        return jsonify({"error": "Unauthorized"}), 403
    tickets = _load_support_tickets()
    now = int(time.time())
    closed = 0
    for t in tickets:
        if t.get("status") == "open":
            t["status"] = "closed"
            t["closed_at"] = now
            t["closed_by"] = "admin"
            t["updated_at"] = now
            closed += 1
    _save_support_tickets(_sort_support_tickets(tickets))
    return jsonify({"ok": True, "message": f"Closed {closed} ticket(s)"})

# ===================== SUPPORT: PRIORITY, NOTES, USER INFO =====================

@app.route("/api/support/tickets/<ticket_id>/priority", methods=["POST"])
@login_required_api
def api_support_ticket_priority(ticket_id: str):
    username = session["username"]
    if not is_admin_user(username):
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json or {}
    priority = (data.get("priority") or "").strip().lower()
    if priority not in ("low", "medium", "high"):
        return jsonify({"error": "Invalid priority (low/medium/high)"}), 400
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    ticket["priority"] = priority
    _save_support_tickets(_sort_support_tickets(tickets))
    return jsonify({"ok": True, "ticket": _serialize_ticket_for_user(ticket, with_internal_notes=True)})

@app.route("/api/support/tickets/<ticket_id>/notes", methods=["GET", "POST"])
@login_required_api
def api_support_ticket_notes(ticket_id: str):
    username = session["username"]
    if not is_admin_user(username):
        return jsonify({"error": "Unauthorized"}), 403
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    if request.method == "GET":
        return jsonify({"notes": ticket.get("internal_notes", [])})
    data = request.json or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Note content required"}), 400
    notes = ticket.setdefault("internal_notes", [])
    notes.append({
        "author": username,
        "content": content,
        "timestamp": int(time.time()),
    })
    _save_support_tickets(_sort_support_tickets(tickets))
    return jsonify({"ok": True, "notes": notes})

@app.route("/api/support/user-info/<username>")
@login_required_api
def api_support_user_info(username: str):
    viewer = session["username"]
    if not is_admin_user(viewer):
        return jsonify({"error": "Unauthorized"}), 403
    users = _load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    balance_cents = get_balance(username) if username else 0
    purchases = get_purchases(username)
    tickets = _load_support_tickets()
    user_tickets = [t for t in tickets if str(t.get("username") or "") == username]
    open_tickets = [t for t in user_tickets if str(t.get("status") or "") != "closed"]
    total_spent = sum(p.get("amount_cents", 0) or 0 for p in purchases)
    user_data = users.get(username, {})
    return jsonify({
        "username": username,
        "email": user_data.get("email", ""),
        "bio": user_data.get("bio", ""),
        "profile_pic": user_data.get("profile_pic", ""),
        "last_online": user_data.get("last_online", 0),
        "balance_cents": balance_cents,
        "total_spent_cents": total_spent,
        "purchase_count": len(purchases),
        "open_tickets": len(open_tickets),
        "total_tickets": len(user_tickets),
        "account_created": 0,
    })


@app.route("/api/redeem", methods=["POST"])
@login_required_api
def api_redeem():
    data = request.json or {}
    username = session["username"]
    order_number_raw = str(data.get("order_number") or "").strip()

    if not order_number_raw:
        return jsonify({"error": "order_number required"}), 400

    order_ref = order_number_raw[1:] if order_number_raw.startswith("#") else order_number_raw

    if not order_ref.isdigit():
        return jsonify({"error": "Invalid order format: use digits or # followed by digits"}), 400

    amount_cents, order_id_str, note, status, reason, api_error = get_shopify_order_by_ref(
        order_ref
    )

    if reason == "no_token":
        return jsonify({"error": "SHOPIFY_ADMIN_TOKEN not configured"}), 500

    if reason == "not_found":
        return jsonify({"error": f"No Shopify order found for reference {order_number_raw}"}), 404

    if reason == "api_error":
        app.logger.warning("Shopify API error while redeeming %s: %s", order_number_raw, api_error)
        return jsonify({"error": "Shopify API error"}), 500

    if reason == "not_paid":
        app.logger.info("Redeem rejected for unpaid order %s (status=%s)", order_number_raw, status)
        return jsonify({"error": "Order not paid yet"}), 400

    if reason != "ok":
        return jsonify({"error": "Could not validate order"}), 400

    expected_note = f"user:{username}"
    if (note or "").strip() != expected_note:
        app.logger.info(
            "Redeem note mismatch for %s: expected %s got %r",
            order_number_raw,
            expected_note,
            note,
        )
        return jsonify(
            {
                "error": "Order note does not match this user",
            }
        ), 403

    if is_redeemed(order_id_str):
        return jsonify({"error": "Order already redeemed"}), 400

    verification_status = get_user_verification_status(username)

    if verification_status == "blacklisted":
        return jsonify({"error": "Your account has been suspended."}), 403

    if verification_status in ("unverified", "verify_each"):
        add_pending_topup(username, amount_cents, order_id_str)
        add_topup_record(username, amount_cents, order_id_str, "pending")
        return jsonify({
            "message": (
                f"Order #{order_number_raw} submitted for verification. "
                "Your balance will be credited after admin review."
            ),
            "pending": True,
        })

    add_balance(username, amount_cents)
    mark_redeemed(order_id_str)
    add_topup_record(username, amount_cents, order_id_str, "completed")

    dollars_added = amount_cents / 100
    new_balance = get_balance(username) / 100

    return jsonify(
        {
            "message": (
                f"Redeemed order #{order_number_raw}: added ${dollars_added:.2f}. "
                f"New balance: ${new_balance:.2f}"
            )
        }
    )


@app.route("/webhooks/shopify/order-paid", methods=["POST"])
def shopify_order_paid_webhook():
    """
    Shopify sends this when an order is marked paid.
    Verifies HMAC signature, then credits the balance for the user
    specified in the order note (format: user:<username>).
    """
    if not SHOPIFY_WEBHOOK_SECRET:
        app.logger.error("SHOPIFY_WEBHOOK_SECRET not configured")
        return "", 500

    raw_body = request.get_data()

    # Verify HMAC-SHA256 signature from Shopify
    shopify_hmac = request.headers.get("X-Shopify-Hmac-Sha256", "")
    digest = hmac.new(
        SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).digest()
    expected_hmac = base64.b64encode(digest).decode("utf-8")
    if not hmac.compare_digest(expected_hmac, shopify_hmac):
        app.logger.warning("Shopify webhook HMAC mismatch")
        return "", 401

    try:
        order = json.loads(raw_body)
    except (ValueError, Exception) as exc:
        app.logger.error("Shopify webhook: failed to parse JSON body: %s", exc)
        return "", 400

    order_id_str = str(order.get("id", ""))
    financial_status = order.get("financial_status", "")
    total_price_str = order.get("total_price") or "0.00"
    note = (order.get("note") or "").strip()

    if financial_status != "paid":
        # Not a paid order; acknowledge but do nothing
        return "", 200

    if not note.startswith("user:"):
        app.logger.info(
            "Shopify webhook order %s has no user: note (%r); skipping balance credit",
            order_id_str, note,
        )
        return "", 200

    username = note[len("user:"):].strip()
    if not username:
        app.logger.info("Shopify webhook order %s: empty username in note", order_id_str)
        return "", 200

    # Validate that the username exists in the system
    users = _load_users()
    if username not in users:
        app.logger.warning(
            "Shopify webhook order %s: username %r not found; skipping balance credit",
            order_id_str, username,
        )
        return "", 200

    if is_redeemed(order_id_str):
        app.logger.info("Shopify webhook order %s already redeemed; skipping", order_id_str)
        return "", 200

    try:
        amount_dollars = float(total_price_str)
    except ValueError:
        app.logger.error("Shopify webhook order %s: bad total_price %r", order_id_str, total_price_str)
        return "", 200

    amount_cents = int(round(amount_dollars * 100))

    verification_status = get_user_verification_status(username)

    if verification_status == "blacklisted":
        app.logger.info("Shopify webhook order %s: user %r is blacklisted; skipping", order_id_str, username)
        return "", 200

    if verification_status in ("unverified", "verify_each"):
        add_pending_topup(username, amount_cents, order_id_str)
        add_topup_record(username, amount_cents, order_id_str, "pending")
        app.logger.info(
            "Shopify webhook: queued %d cents for user %r (order %s) for admin verification",
            amount_cents, username, order_id_str,
        )
        return "", 200

    add_balance(username, amount_cents)
    mark_redeemed(order_id_str)
    add_topup_record(username, amount_cents, order_id_str, "completed")

    app.logger.info(
        "Shopify webhook: credited %d cents to user %r for order %s",
        amount_cents, username, order_id_str,
    )
    return "", 200



@app.route("/api/fortnite/search", methods=["POST"])
def api_fortnite_search():
    try:
        data = request.json or {}
        item = data.get("item", "")
        days = _as_int(data.get("days")) or 0
        skins = _as_int(data.get("skins")) or 0
        budget = _as_float(data.get("budget"))
        if budget is None or budget <= 0:
            budget = 999999

        _push_activity("search", session.get("username", "guest"), {"query": item[:100] if item else "browse"})
        raw_items = [s.strip() for s in item.split(",") if s.strip()]
        market_params = build_market_search_params(data)
        has_direct_filters = bool(market_params)
        paid_items_min = _as_int(data.get("paid_items_min"))
        paid_items_max = _as_int(data.get("paid_items_max"))
        daybreak_max = _as_int(data.get("daybreak_max"))
        if paid_items_min is None:
            legacy_paid_items_min = _as_int(data.get("rl_purchases"))
            if legacy_paid_items_min is not None and legacy_paid_items_min >= 0:
                paid_items_min = legacy_paid_items_min
        has_local_filters = any(
            value is not None and value >= 0
            for value in (paid_items_min, paid_items_max, daybreak_max)
        )
        if not raw_items and not has_direct_filters and not has_local_filters:
            return jsonify({"error": "You must provide at least one item or one filter."}), 400

        item_results = []
        not_found = []

        if raw_items:
            for name in raw_items:
                try:
                    result = find_item_by_name(name)
                except Exception as e:
                    app.logger.error("Error resolving item '%s': %s", name, e)
                    return jsonify(
                        {"error": "Error resolving one or more items. Please try again."}
                    ), 500

                if not result:
                    not_found.append(name)
                else:
                    item_results.append(result)

            if not item_results and not has_direct_filters:
                return jsonify(
                    {"error": "No items found on marketplace.", "not_found": not_found}
                ), 404

        item_filters: List[Tuple[str, str]] = []
        for param_name, query_id, raw_id, matched_title, item_type in item_results:
            item_filters.append((param_name, query_id))

        min_days = days if days >= 0 else 0
        min_skins = skins if skins > 0 else None

        try:
            accounts, _ = fetch_cheapest_accounts(
                item_filters=item_filters,
                min_days=min_days,
                min_skins=min_skins,
                extra_params=market_params,
            )
        except Exception as e:
            app.logger.error("Error fetching accounts: %s", e)
            return jsonify({"accounts": [], "error": "Marketplace is temporarily unavailable. Please try again."}), 200

        if not accounts:
            return jsonify({"accounts": [], "not_found": not_found})

        result_accounts = []

        def _ts_fmt(ts):
            if isinstance(ts, (int, float)) and ts > 0:
                return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%b %d, %Y")
            return "N/A"

        for acc in accounts:
            price = acc.get("price")
            try:
                base_price = float(price)
            except Exception:
                base_price = 0.0

            user_price = base_price * get_multiplier_for_account(acc)

            # Filter by budget
            if user_price > budget:
                continue

            days_ago = compute_days_ago(acc)
            if daybreak_max is not None and daybreak_max >= 0:
                if days_ago is None or days_ago > daybreak_max:
                    continue

            paid_items_count = _as_int(acc.get("fortnite_rl_purchases"))
            if paid_items_min is not None and paid_items_min >= 0:
                if paid_items_count is None or paid_items_count < paid_items_min:
                    continue
            if paid_items_max is not None and paid_items_max >= 0:
                if paid_items_count is None or paid_items_count > paid_items_max:
                    continue

            last_played = f"{days_ago} days ago" if days_ago is not None else "N/A"
            preview_cosmetics: List[str] = []
            for field_name in ("fortniteSkins", "fortnitePickaxe", "fortniteBackpack", "fortniteDance", "fortniteGliders"):
                values = acc.get(field_name) or []
                if not isinstance(values, list):
                    continue
                for cosmetic in values:
                    if isinstance(cosmetic, dict):
                        name = cosmetic.get("title") or cosmetic.get("name")
                    else:
                        name = str(cosmetic)
                    if name:
                        preview_cosmetics.append(str(name))
                    if len(preview_cosmetics) >= MAX_PREVIEW_COSMETICS:
                        break
                if len(preview_cosmetics) >= MAX_PREVIEW_COSMETICS:
                    break

            discount_info = get_active_discount()
            discounted_price = round(user_price * (100 - discount_info["percent"]) / 100, 2) if discount_info["active"] else user_price
            result_accounts.append(
                {
                    "item_id": acc.get("item_id"),
                    "title": acc.get("title") or acc.get("title_en") or "",
                    "base_price": base_price,
                    "user_price": discounted_price,
                    "original_price": user_price if discount_info["active"] else None,
                    "discount_percent": discount_info["percent"] if discount_info["active"] else 0,
                    "level": acc.get("fortnite_level") or 0,
                    "skins": acc.get("fortnite_skin_count") or 0,
                    "pickaxes": acc.get("fortnite_pickaxe_count") or 0,
                    "emotes": acc.get("fortnite_dance_count") or 0,
                    "gliders": acc.get("fortnite_glider_count") or 0,
                    "vbucks": acc.get("fortnite_balance") or 0,
                    "last_played": last_played,
                    "days_ago": days_ago,
                    "preview_cosmetics": preview_cosmetics,
                    "bp_level": acc.get("fortnite_book_level") or 0,
                    "lifetime_wins": acc.get("fortnite_lifetime_wins") or 0,
                    "season_num": acc.get("fortnite_season_num") or 0,
                    "bps_purchased": acc.get("fortnite_books_purchased") or 0,
                    "shop_skins": acc.get("fortnite_shop_skins_count") or 0,
                    "shop_pickaxes": acc.get("fortnite_shop_pickaxes_count") or 0,
                    "shop_emotes": acc.get("fortnite_shop_dances_count") or 0,
                    "shop_gliders": acc.get("fortnite_shop_gliders_count") or 0,
                    "platform": acc.get("fortnite_platform") or "",
                    "register_date": _ts_fmt(acc.get("fortnite_register_date")),
                    "register_ts": acc.get("fortnite_register_date"),
                    "email_changeable": bool(acc.get("fortnite_change_email")),
                    "email_provider": acc.get("email_provider") or "",
                    "item_origin": acc.get("item_origin") or "",
                    "view_count": acc.get("view_count") or 0,
                    "fortnite_item_id": acc.get("fortnite_item_id") or 0,
                }
            )

        return jsonify({"accounts": result_accounts, "not_found": not_found})

    except Exception as e:
        app.logger.error("Unhandled error in api_fortnite_search: %s", e)
        return jsonify({"error": "An unexpected error occurred. Please try again."}), 500


@app.route("/api/fortnite/check-buy", methods=["POST"])
@login_required_api
def api_fortnite_check_buy():
    data = request.json or {}
    username = session["username"]
    item_id = int(data.get("item_id") or 0)

    if not item_id:
        return jsonify({"error": "item_id required"}), 400

    try:
        _, user_price, cost_cents = get_live_purchase_costs(item_id)
    except PurchaseFlowError as e:
        return jsonify({"error": e.code, "message": e.message}), e.status_code

    balance_cents = get_balance(username)

    if balance_cents < cost_cents:
        return _not_enough_balance_response(balance_cents, cost_cents)

    return jsonify(
        {
            "message": f"Account checked. Waiting {PURCHASE_DELAY_AFTER_CHECK_SECONDS} seconds before buying.",
            "price": round(user_price, 2),
        }
    )


@app.route("/api/fortnite/buy", methods=["POST"])
@login_required_api
def api_fortnite_buy():
    data = request.json or {}
    username = session["username"]
    item_id = int(data.get("item_id") or 0)

    if not item_id:
        return jsonify({"error": "item_id required"}), 400

    locked_purchase = get_purchase_lock()
    if locked_purchase and int(locked_purchase["item_id"]) != item_id:
        return _purchase_in_progress_response(waiting_for_other_item=True)

    if not locked_purchase:
        set_purchase_lock(item_id, _build_fallback_purchase_title(item_id))

    starting_balance = get_balance(username)

    try:
        _, user_price, cost_cents = get_live_purchase_costs(item_id)
    except PurchaseFlowError as e:
        return jsonify({"error": e.code, "message": e.message}), e.status_code

    if starting_balance < cost_cents:
        return _not_enough_balance_response(starting_balance, cost_cents)

    # STEP 1: fast-buy on market
    try:
        purchase_result = confirm_buy_account(item_id)
    except PurchaseFlowError as e:
        app.logger.warning("Purchase blocked for item %s: %s", item_id, e.message)
        return jsonify({"error": e.code, "message": e.message}), e.status_code
    except Exception as e:
        app.logger.error("confirm_buy_account failed for item %s: %s", item_id, e)
        return jsonify(
            {
                "error": "confirm_buy_failed",
                "message": "Purchase failed due to an unexpected server error. Please try again.",
            }
        ), 500

    recovered_purchase_result = _recover_purchase_result(item_id, "post_fast_buy", purchase_result)
    if recovered_purchase_result:
        purchase_result = recovered_purchase_result

    # STEP 2: optional, try to fetch latest order
    try:
        latest_order = get_latest_order()
    except Exception:
        latest_order = None

    balance_charged = False
    new_balance = starting_balance / 100
    try:
        # STEP 3: deduct balance
        add_balance(username, -cost_cents)
        balance_charged = True
        new_balance = get_balance(username) / 100

        # STEP 4: store purchased account for this user with the actual charged amount
        purchase_entry, owned_accounts, purchase_index = save_purchase_record(
            username,
            purchase_result,
            latest_order,
            amount_cents=cost_cents,
        )

        try:
            send_purchase_discord_webhook(
                purchase_result=purchase_result,
                latest_order=latest_order,
                user_price=user_price,
                username=username,
            )
        except Exception as e:
            app.logger.warning("Purchase webhook helper failed for item %s: %s", item_id, e)

        try:
            _send_purchase_email(username, purchase_result, user_price)
        except Exception as e:
            app.logger.warning("Purchase email failed for item %s: %s", item_id, e)

        item_title = (purchase_result.get("title") or purchase_result.get("title_en") or f"Account #{item_id}")
        _push_activity("purchase", username, {"item_id": item_id, "title": item_title, "price": user_price})

        response_payload = {
            "message": f"Purchase successful! Charged ${user_price:.2f}. New balance: ${new_balance:.2f}",
            "purchase_result": purchase_result,
            "latest_order": latest_order,
            "owned_accounts": owned_accounts,
            "purchase_index": purchase_index,
            "saved_entry": purchase_entry,
        }
    except Exception as e:
        app.logger.exception("Failed to finalize purchase for item %s: %s", item_id, e)
        recovered_purchase_result = _recover_purchase_result(
            item_id,
            "post_purchase_finalize_failure",
            purchase_result,
        )
        if recovered_purchase_result:
            purchase_result = recovered_purchase_result
        if not balance_charged:
            add_balance(username, -cost_cents)
            balance_charged = True
        new_balance = get_balance(username) / 100
        purchase_entry, owned_accounts, purchase_index = save_purchase_record(
            username,
            purchase_result,
            latest_order,
            amount_cents=cost_cents,
        )
        response_payload = {
            "message": (
                f"Purchase completed! Charged ${user_price:.2f}. "
                "Account details were recovered after an unexpected response."
            ),
            "purchase_result": purchase_result,
            "latest_order": latest_order,
            "owned_accounts": owned_accounts,
            "purchase_index": purchase_index,
            "saved_entry": purchase_entry,
            "recovered": True,
        }

    clear_purchase_lock()
    return jsonify(response_payload)


@app.route("/api/fortnite/purchase-lock/release", methods=["POST"])
@login_required_api
def api_release_purchase_lock():
    data = request.json or {}
    item_id = int(data.get("item_id") or 0)
    if not item_id:
        return jsonify({"error": "item_id required"}), 400

    locked_purchase = get_purchase_lock()
    if locked_purchase and int(locked_purchase["item_id"]) == item_id:
        clear_purchase_lock()
        return jsonify({"message": "Purchase lock cleared."})

    return jsonify({"message": "No active purchase lock for this item."})


@app.route("/api/fortnite/my-accounts", methods=["POST"])
@login_required_api
def api_fortnite_my_accounts():
    username = session["username"]
    accounts = get_purchases(username)
    return jsonify({"accounts": accounts})


# ===================== ADMIN FAKE ORDERS API =====================

@app.route("/api/admin/fake-orders/config", methods=["GET", "POST"])
def api_admin_fake_orders_config():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403

    if request.method == "GET":
        cfg = _load_fake_orders_config()
        return jsonify(cfg)

    data = request.json or {}
    cfg = _load_fake_orders_config()

    if "enabled" in data:
        cfg["enabled"] = bool(data["enabled"])

    if "usernames" in data:
        raw = data["usernames"]
        if isinstance(raw, list):
            cfg["usernames"] = [str(u).strip() for u in raw if str(u).strip()]
        elif isinstance(raw, str):
            cfg["usernames"] = [u.strip() for u in raw.splitlines() if u.strip()]

    _save_fake_orders_config(cfg)
    start_fake_orders_scheduler()
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/admin/fake-orders/fire-one", methods=["POST"])
def api_admin_fake_orders_fire_one():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403

    cfg = _load_fake_orders_config()
    usernames = [u for u in (cfg.get("usernames") or []) if u]
    if not usernames:
        return jsonify({"error": "No usernames configured"}), 400

    username = random.choice(usernames)
    threading.Thread(target=_send_one_fake_order, args=(username,), daemon=True).start()
    return jsonify({"ok": True, "username": username})


# ---- Admin: Discount Config ----
@app.route("/api/admin/discount", methods=["GET", "POST"])
def api_admin_discount():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403
    if request.method == "GET":
        cfg = _load_discount_config()
        return jsonify(cfg)
    data = request.json or {}
    cfg = _load_discount_config()
    if "enabled" in data:
        cfg["enabled"] = bool(data["enabled"])
    if "percent" in data:
        cfg["percent"] = max(0, min(100, int(data["percent"])))
    if "start" in data:
        cfg["start"] = data["start"]
    if "end" in data:
        cfg["end"] = data["end"]
    _save_discount_config(cfg)
    return jsonify({"ok": True, "config": cfg})

# ---- Admin: Referral Config ----
@app.route("/api/admin/referral", methods=["GET", "POST"])
def api_admin_referral():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403
    if request.method == "GET":
        return jsonify(_load_referrals())
    data = request.json or {}
    refs = _load_referrals()
    if "referral_credit_cents" in data:
        refs["referral_credit_cents"] = max(0, int(data["referral_credit_cents"]))
    _save_referrals(refs)
    return jsonify({"ok": True, "config": refs})

# ---- Admin: Loyalty Tiers ----
@app.route("/api/admin/loyalty", methods=["GET", "POST"])
def api_admin_loyalty():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403
    if request.method == "GET":
        return jsonify(_load_loyalty_config())
    data = request.json or {}
    if "tiers" in data:
        cfg = _load_loyalty_config()
        cfg["tiers"] = data["tiers"]
        _save_loyalty_config(cfg)
        return jsonify({"ok": True, "config": cfg})
    return jsonify({"error": "Invalid data"}), 400

# ---- Admin: OG Config ----
@app.route("/api/admin/og", methods=["GET", "POST"])
def api_admin_og():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403
    if request.method == "GET":
        return jsonify(_load_og_config())
    data = request.json or {}
    og_cfg = _load_og_config()
    action = data.get("action")
    if action == "add":
        skin_id = data.get("skin_id")
        item_id = data.get("item_id")
        if not skin_id or not item_id:
            return jsonify({"error": "skin_id and item_id required"}), 400
        og_cfg.setdefault("accounts", {}).setdefault(skin_id, [])
        og_cfg["accounts"][skin_id].append({"item_id": int(item_id), "added_at": time.time()})
        _save_og_config(og_cfg)
        skin_name = next((s["name"] for s in OG_SKINS if s["id"] == skin_id), skin_id)
        threading.Thread(target=_send_og_restock_webhook, args=(skin_name, int(item_id)), daemon=True).start()
        return jsonify({"ok": True, "config": og_cfg})
    elif action == "remove":
        skin_id = data.get("skin_id")
        idx = data.get("idx")
        if skin_id is not None and idx is not None:
            accs = og_cfg.get("accounts", {}).get(skin_id, [])
            if 0 <= int(idx) < len(accs):
                accs.pop(int(idx))
                og_cfg["accounts"][skin_id] = accs
                _save_og_config(og_cfg)
        return jsonify({"ok": True, "config": og_cfg})
    return jsonify({"error": "Invalid action"}), 400

# ---- API: Sales Dashboard ----
@app.route("/api/admin/sales-dashboard")
def api_admin_sales_dashboard():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403
    total_revenue_cents = 0
    total_purchases = 0
    user_purchases_map = {}
    if os.path.exists(PURCHASES_FILE):
        try:
            with open(PURCHASES_FILE, "r", encoding="utf-8") as f:
                all_purchases = json.load(f) or {}
            for uname, purchases in all_purchases.items():
                for p in purchases:
                    amt = p.get("amount_cents", 0) or 0
                    total_revenue_cents += amt
                    total_purchases += 1
                user_purchases_map[uname] = len(purchases)
        except Exception:
            pass
    from collections import Counter
    top_accounts = Counter()
    if os.path.exists(PURCHASES_FILE):
        try:
            with open(PURCHASES_FILE, "r", encoding="utf-8") as f:
                all_purchases = json.load(f) or {}
            for uname, purchases in all_purchases.items():
                for p in purchases:
                    title = p.get("item_title") or "Unknown"
                    top_accounts[title] += 1
        except Exception:
            pass
    return jsonify({
        "total_revenue": round(total_revenue_cents / 100, 2),
        "total_purchases": total_purchases,
        "total_users_with_purchases": len(user_purchases_map),
        "top_accounts": [{"title": t, "count": c} for t, c in top_accounts.most_common(20)],
    })

# ---- API: My referral code ----
@app.route("/api/user/referral-code")
@login_required_api
def api_user_referral_code():
    username = session["username"]
    code = generate_referral_code(username)
    refs = _load_referrals()
    credit = refs.get("referral_credit_cents", 500)
    return jsonify({"code": code, "credit_cents": credit})

# ---- API: My loyalty tier ----
@app.route("/api/user/loyalty-tier")
@login_required_api
def api_user_loyalty_tier():
    username = session["username"]
    total_spent = get_user_total_spent(username)
    tier = get_user_tier(total_spent)
    return jsonify({"total_spent_cents": total_spent, "tier": tier})

# ---- API: Redeem referral code ----
@app.route("/api/user/redeem-referral", methods=["POST"])
@login_required_api
def api_user_redeem_referral():
    username = session["username"]
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "Referral code required"}), 400
    refs = _load_referrals()
    referrer = None
    for uname, c in refs.get("codes", {}).items():
        if c == code:
            referrer = uname
            break
    if not referrer:
        return jsonify({"error": "Invalid referral code"}), 400
    if referrer == username:
        return jsonify({"error": "Cannot use your own code"}), 400
    apply_referral_credit(referrer, username)
    return jsonify({"ok": True, "message": f"Referral applied! {referrer} got credit."})

# ---- API: OG accounts available ----
@app.route("/api/ogs/available")
def api_ogs_available():
    og_cfg = _load_og_config()
    result = {}
    for skin in OG_SKINS:
        sid = skin["id"]
        accs = og_cfg.get("accounts", {}).get(sid, [])
        result[sid] = [{"item_id": a["item_id"]} for a in accs]
    return jsonify(result)

# ===================== PROFILE HELPERS =====================

def _get_user_profile(username: str) -> dict:
    users = _load_users()
    info = users.get(username, {})
    return {
        "username": username,
        "bio": info.get("bio", ""),
        "profile_pic": info.get("profile_pic", ""),
        "last_online": info.get("last_online", 0),
        "online": bool(info.get("online", False)),
        "email": info.get("email", ""),
    }

def _save_profile_pic(username: str, filename: str) -> str:
    os.makedirs(PROFILE_UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(PROFILE_UPLOAD_DIR, f"{username}.webp")
    src = os.path.join(PROFILE_UPLOAD_DIR, filename)
    if os.path.exists(src):
        os.replace(src, dest)
    return f"/profile-pics/{username}.webp"

# ===================== CUSTOMER NEWS HELPERS =====================

def _load_customer_news() -> list:
    if not os.path.exists(CUSTOMER_NEWS_FILE):
        return []
    try:
        with open(CUSTOMER_NEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []

def _save_customer_news(news: list) -> None:
    with open(CUSTOMER_NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(news, f, indent=2)

# ===================== MESSAGING HELPERS =====================

def _load_messages() -> dict:
    if not os.path.exists(MESSAGES_FILE):
        return {}
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def _save_messages(msgs: dict) -> None:
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(msgs, f, indent=2)

def _conversation_key(user1: str, user2: str) -> str:
    return "::".join(sorted([user1.lower(), user2.lower()]))

# ===================== PROFILE ROUTES =====================

@app.route("/u/<username>")
def user_profile_page(username: str):
    logged_in = "username" in session
    my_username = session.get("username", "")
    users = _load_users()
    # Case-insensitive username lookup
    actual_username = None
    for u in users:
        if u.lower() == username.lower():
            actual_username = u
            break
    if not actual_username:
        return render_template("profile.html",
            logged_in=logged_in,
            username=my_username,
            balance=f"{get_balance(my_username) / 100:.2f}" if logged_in else "0.00",
            active_page="profile",
            profile={"username": username, "bio": "", "profile_pic": "", "last_online": 0, "email": ""},
            is_owner=False,
            purchase_count=0,
            is_konvy_vip=False,
            user_not_found=True,
        ), 404
    profile = _get_user_profile(actual_username)
    purchases = get_purchases(actual_username)
    purchase_count = len(purchases)
    is_admin_viewer = is_admin_user(my_username) if my_username else False
    target_balance = get_balance(actual_username) / 100
    target_topups = []
    try:
        hist = _load_topup_history()
        target_topups = sorted(hist.get(actual_username, []), key=lambda x: x.get("timestamp", 0), reverse=True)
    except Exception:
        pass
    return render_template(
        "profile.html",
        logged_in=logged_in,
        username=my_username,
        balance=f"{get_balance(my_username) / 100:.2f}" if logged_in else "0.00",
        active_page="profile",
        profile=profile,
        is_owner=my_username.lower() == actual_username.lower(),
        purchase_count=purchase_count,
        is_konvy_vip=profile.get("email", "").lower() == "konvyvip@gmail.com",
        is_admin_viewer=is_admin_viewer,
        target_purchases=purchases,
        target_balance=target_balance,
        target_topups=target_topups,
    )

@app.route("/api/profile/update", methods=["POST"])
@login_required_api
def api_profile_update():
    username = session["username"]
    data = request.json or {}
    users = _load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    bio = (data.get("bio") or "").strip()[:500]
    users[username]["bio"] = bio
    _save_users(users)
    return jsonify({"ok": True, "bio": bio})

@app.route("/api/profile/upload-pic", methods=["POST"])
@login_required_api
def api_profile_upload_pic():
    username = session["username"]
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400
    os.makedirs(PROFILE_UPLOAD_DIR, exist_ok=True)
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "webp"
    allowed = {"png", "jpg", "jpeg", "gif", "webp"}
    if ext not in allowed:
        return jsonify({"error": "File type not allowed. Use png, jpg, gif, webp"}), 400
    filename = f"{username}.{ext}"
    path = os.path.join(PROFILE_UPLOAD_DIR, filename)
    f.save(path)
    pic_url = f"/profile-pics/{filename}"
    users = _load_users()
    if username in users:
        users[username]["profile_pic"] = pic_url
        _save_users(users)
    return jsonify({"ok": True, "profile_pic": pic_url})

@app.route("/profile-pics/<filename>")
def serve_profile_pic(filename: str):
    return send_from_directory(PROFILE_UPLOAD_DIR, filename)

# ===================== CUSTOMER SECTION ROUTES =====================

@app.route("/customer-section")
def customer_section_page():
    logged_in = "username" in session
    my_username = session.get("username", "")
    balance = "0.00"
    purchases = []
    if logged_in:
        balance_cents = get_balance(my_username) or 0
        balance = f"{balance_cents / 100:.2f}"
        purchases = get_purchases(my_username)
    if logged_in and not purchases and not is_admin_user(my_username):
        return render_template("customer_section.html", logged_in=logged_in, username=my_username, balance=balance, active_page="customer", news=[], purchases=[], owner_info={}, users={}, is_konvy_vip=False, no_purchases=True)
    news = _load_customer_news()
    users = _load_users()
    owner_info = _get_user_profile("Konvy")
    my_email = (users.get(my_username, {}).get("email") or "").lower() if my_username else ""
    return render_template(
        "customer_section.html",
        logged_in=logged_in,
        username=my_username,
        balance=balance,
        active_page="customer",
        news=news,
        purchases=purchases,
        owner_info=owner_info,
        users=users,
        is_konvy_vip=my_email == "konvyvip@gmail.com",
    )

@app.route("/api/customer-news", methods=["GET", "POST"])
@login_required_api
def api_customer_news():
    username = session["username"]
    users = _load_users()
    user_email = (users.get(username, {}).get("email") or "").lower()
    if user_email != "konvyvip@gmail.com":
        return jsonify({"error": "Only the site owner can post news"}), 403
    if request.method == "GET":
        return jsonify({"news": _load_customer_news()})
    data = request.json or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Content required"}), 400
    news = _load_customer_news()
    news.insert(0, {
        "id": int(time.time()),
        "author": username,
        "content": content,
        "created_at": int(time.time()),
    })
    _save_customer_news(news)
    return jsonify({"ok": True, "news": news})

@app.route("/api/customer-news/delete", methods=["POST"])
@login_required_api
def api_customer_news_delete():
    username = session["username"]
    users = _load_users()
    user_email = (users.get(username, {}).get("email") or "").lower()
    if user_email != "konvyvip@gmail.com":
        return jsonify({"error": "Only the site owner can delete news"}), 403
    data = request.json or {}
    news_id = data.get("id")
    if news_id is None:
        return jsonify({"error": "News ID required"}), 400
    news = _load_customer_news()
    news[:] = [item for item in news if item.get("id") != news_id]
    _save_customer_news(news)
    return jsonify({"ok": True, "news": news})

# ===================== MESSAGING ROUTES =====================

@app.route("/api/messages/conversations", methods=["GET"])
@login_required_api
def api_messages_conversations():
    username = session["username"].lower()
    all_msgs = _load_messages()
    convos = {}
    for key, msgs in all_msgs.items():
        parts = key.split("::")
        if username in parts:
            other = parts[0] if parts[1] == username else parts[1]
            last_msg = msgs[-1] if msgs else None
            unread = sum(1 for m in msgs if m.get("to", "").lower() == username and not m.get("read"))
            convos[other] = {
                "last_message": last_msg,
                "unread": unread,
                "updated_at": last_msg["timestamp"] if last_msg else 0,
            }
    sorted_convos = sorted(convos.items(), key=lambda x: -x[1]["updated_at"])
    return jsonify({"conversations": [{"with": u, **d} for u, d in sorted_convos]})

@app.route("/api/messages/<other_user>", methods=["GET", "POST"])
@login_required_api
def api_messages_with(other_user: str):
    my_username = session["username"].lower()
    other_lower = other_user.lower()
    users = _load_users()
    if other_lower not in users:
        return jsonify({"error": "User not found"}), 404
    key = _conversation_key(my_username, other_lower)
    all_msgs = _load_messages()
    if key not in all_msgs:
        all_msgs[key] = []
    if request.method == "POST":
        data = request.json or {}
        content = (data.get("content") or "").strip()
        if not content:
            return jsonify({"error": "Message content required"}), 400
        all_msgs[key].append({
            "from": my_username,
            "to": other_lower,
            "content": content,
            "timestamp": int(time.time()),
            "read": False,
        })
        _save_messages(all_msgs)
        return jsonify({"ok": True})
    # GET: mark messages as read
    for m in all_msgs[key]:
        if m.get("to", "").lower() == my_username:
            m["read"] = True
    _save_messages(all_msgs)
    return jsonify({"messages": all_msgs[key]})



# ===================== PROFILE SETTINGS =====================

@app.route("/api/profile/send-email-code", methods=["POST"])
@login_required_api
def api_profile_send_email_code():
    username = session["username"]
    data = request.json or {}
    new_email = _normalize_email(data.get("email") or "")
    if not _is_valid_email_address(new_email):
        return jsonify({"error": "Invalid email address"}), 400
    users = _load_users()
    existing = find_username_by_email(new_email)
    if existing and existing != username:
        return jsonify({"error": "Email already in use by another account"}), 400
    code = _generate_one_time_code()
    users[username]["email_verification_code_hash"] = _hash_one_time_code(code)
    users[username]["email_verification_expires_at"] = int(time.time()) + EMAIL_CODE_TTL_SECONDS
    users[username]["pending_email"] = new_email
    _save_users(users)
    ok, msg = _send_email_message(
        new_email,
        "Verify your new email — Konvy Accounts",
        f"Your verification code is: {code}\nExpires in 15 minutes.",
        _itemz_email_html(
            "Verify Your New Email",
            f"Enter this code on Konvy Accounts to confirm your email change.",
            code,
            EMAIL_CODE_TTL_SECONDS // 60,
            "If you did not request this, you can ignore this message.",
        ),
    )
    if not ok:
        return jsonify({"error": msg}), 500
    return jsonify({"ok": True, "message": "Verification code sent"})

@app.route("/api/profile/confirm-email", methods=["POST"])
@login_required_api
def api_profile_confirm_email():
    username = session["username"]
    data = request.json or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "Verification code required"}), 400
    users = _load_users()
    user = users.get(username)
    if not user:
        return jsonify({"error": "User not found"}), 404
    stored_hash = user.get("email_verification_code_hash", "")
    expires = int(user.get("email_verification_expires_at") or 0)
    if not stored_hash or int(time.time()) > expires:
        return jsonify({"error": "Verification code expired. Request a new one."}), 400
    if not check_password_hash(stored_hash, code):
        return jsonify({"error": "Invalid verification code"}), 400
    new_email = user.get("pending_email", "")
    if not new_email:
        return jsonify({"error": "No pending email change"}), 400
    user["email"] = new_email
    user["email_verified"] = True
    user.pop("email_verification_code_hash", None)
    user.pop("email_verification_expires_at", None)
    user.pop("pending_email", None)
    _save_users(users)
    return jsonify({"ok": True, "message": "Email updated successfully"})

@app.route("/api/profile/change-password", methods=["POST"])
@login_required_api
def api_profile_change_password():
    username = session["username"]
    data = request.json or {}
    current = (data.get("current_password") or "")
    new_pass = (data.get("new_password") or "")
    if not current or not new_pass:
        return jsonify({"error": "Current and new password required"}), 400
    if len(new_pass) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400
    if not verify_user(username, current):
        return jsonify({"error": "Current password is incorrect"}), 403
    users = _load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    users[username]["password_hash"] = generate_password_hash(new_pass)
    _save_users(users)
    return jsonify({"ok": True, "message": "Password changed successfully"})

@app.route("/api/profile/change-username", methods=["POST"])
@login_required_api
def api_profile_change_username():
    username = session["username"]
    data = request.json or {}
    new_username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not new_username or not password:
        return jsonify({"error": "New username and password required"}), 400
    if password == new_username:
        return jsonify({"error": "Password cannot be the same as username"}), 400
    if not verify_user(username, password):
        return jsonify({"error": "Password is incorrect"}), 403
    if _username_exists_ci(new_username):
        return jsonify({"error": "That username is already taken"}), 400
    if len(new_username) < 2:
        return jsonify({"error": "Username must be at least 2 characters"}), 400
    if username.lower() == new_username.lower():
        return jsonify({"error": "That's your current username"}), 400
    old_username = username
    _rename_user_in_all_stores(old_username, new_username)
    session["username"] = new_username
    return jsonify({"ok": True, "message": "Username changed! Redirecting...", "new_username": new_username})

# ===================== ADMIN MANAGEMENT =====================

@app.route("/api/admin/manage", methods=["GET", "POST"])
def api_admin_manage():
    if not is_admin_user(session.get("username", "")):
        return jsonify({"error": "Unauthorized"}), 403
    if request.method == "GET":
        return jsonify({"admins": _load_admins()})
    data = request.json or {}
    action = data.get("action")
    target = (data.get("username") or "").strip()
    if not target:
        return jsonify({"error": "Username required"}), 400
    admins = _load_admins()
    if action == "add":
        users = _load_users()
        if target not in users:
            return jsonify({"error": "User not found"}), 404
        if target.lower() not in [a.lower() for a in admins]:
            admins.append(target)
            _save_admins(admins)
        return jsonify({"ok": True, "admins": admins})
    elif action == "remove":
        admins = [a for a in admins if a.lower() != target.lower()]
        _save_admins(admins)
        return jsonify({"ok": True, "admins": admins})
    return jsonify({"error": "Invalid action"}), 400

# ===================== PURCHASE EMAIL =====================

def _get_email_login_url(email_login: str) -> str:
    return "https://id.rambler.ru/login-20/login?back=https%3A%2F%2Fmail.rambler.ru%2F&rname=mail&theme=mail&session=false"

def _send_purchase_email(username: str, purchase_result: dict, user_price: float):
    users = _load_users()
    user_data = users.get(username)
    if not user_data:
        return
    recipient = (user_data.get("email") or "").strip()
    if not recipient:
        return
    login_data = purchase_result.get("loginData") or purchase_result.get("login_data") or {}
    email_data = purchase_result.get("emailLoginData") or purchase_result.get("email_login_data") or {}
    game_login = login_data.get("login") or login_data.get("username") or "N/A"
    game_pass = login_data.get("password") or "N/A"
    email_login = email_data.get("login") or email_data.get("username") or "N/A"
    email_pass = email_data.get("password") or "N/A"
    email_url = _get_email_login_url(email_login)
    item_title = purchase_result.get("title") or purchase_result.get("title_en") or "Fortnite Account"
    subject = f"Your purchase is ready — {item_title}"
    body = f"""Hi {username},

Your purchase of {item_title} (${user_price:.2f}) is complete!

FORTNITE LOGIN
Login: {game_login}
Password: {game_pass}

EMAIL ACCESS
Website: {email_url}
Login: {email_login}
Password: {email_pass}

Please change the password and email credentials as soon as possible.

Thanks,
Konvy Accounts Team"""
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{subject}</title></head>
<body style="margin:0;padding:0;background:#0d0d0d;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d0d;min-height:100vh;">
<tr><td align="center" style="padding:40px 16px;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">
    <tr><td align="center" style="padding-bottom:28px;">
      <span style="font-family:'Segoe UI',Arial,sans-serif;font-size:26px;font-weight:900;letter-spacing:-0.5px;">
        <span style="color:#00c8ff;">Konvy</span><span style="color:#ffffff;"> Accounts</span>
      </span>
    </td></tr>
    <tr><td style="background:#161616;border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:36px 32px;">
      <p style="margin:0 0 6px;font-size:22px;font-weight:700;color:#ffffff;">Purchase Complete 🎉</p>
      <p style="margin:0 0 24px;font-size:14px;color:#a1a1aa;">Your account <strong style="color:#e4e4e7;">{item_title}</strong> (${user_price:.2f}) is ready below.</p>
      <div style="background:#0d0d0d;border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:20px;margin-bottom:16px;">
        <p style="margin:0 0 10px;font-size:13px;font-weight:700;color:#00c8ff;letter-spacing:0.04em;">FORTNITE LOGIN</p>
        <p style="margin:0;font-size:14px;color:#e4e4e7;"><strong style="color:#a1a1aa;">Login:</strong> {game_login}</p>
        <p style="margin:6px 0 0;font-size:14px;color:#e4e4e7;"><strong style="color:#a1a1aa;">Password:</strong> {game_pass}</p>
      </div>
      <div style="background:#0d0d0d;border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:20px;margin-bottom:16px;">
        <p style="margin:0 0 10px;font-size:13px;font-weight:700;color:#00c8ff;letter-spacing:0.04em;">EMAIL ACCESS</p>
        <p style="margin:0;font-size:14px;color:#e4e4e7;"><strong style="color:#a1a1aa;">Website:</strong> <a href="{email_url}" style="color:#00c8ff;text-decoration:none;">{email_url}</a></p>
        <p style="margin:6px 0 0;font-size:14px;color:#e4e4e7;"><strong style="color:#a1a1aa;">Login:</strong> {email_login}</p>
        <p style="margin:6px 0 0;font-size:14px;color:#e4e4e7;"><strong style="color:#a1a1aa;">Password:</strong> {email_pass}</p>
      </div>
      <p style="margin:20px 0 0;font-size:13px;color:#71717a;text-align:center;line-height:1.55;">
        Change your password and email credentials as soon as possible.
      </p>
    </td></tr>
    <tr><td align="center" style="padding-top:24px;">
      <p style="margin:0;font-size:12px;color:#3f3f46;">
        &copy; 2026 Konvy Accounts &nbsp;&bull;&nbsp;
        <a href="mailto:support@konvyaccounts.com" style="color:#00c8ff;text-decoration:none;">support@konvyaccounts.com</a>
      </p>
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>"""
    _send_email_message(recipient, subject, body, html_body)

# ===================== FAKE REVIEWS API =====================

@app.route("/api/admin/fake-reviews", methods=["GET", "POST"])
@login_required_api
def api_admin_fake_reviews():
    username = session["username"]
    if not is_admin_user(username):
        return jsonify({"error": "Unauthorized"}), 403
    if request.method == "GET":
        return jsonify(_load_fake_reviews_config())
    data = request.json or {}
    cfg = _load_fake_reviews_config()
    if "enabled" in data:
        cfg["enabled"] = bool(data["enabled"])
    if "usernames" in data:
        cfg["usernames"] = data["usernames"] if isinstance(data["usernames"], list) else []
    if "per_hour" in data:
        cfg["per_hour"] = max(1, min(int(data["per_hour"]), 60))
    if "texts" in data:
        cfg["texts"] = data["texts"] if isinstance(data["texts"], list) else []
    _save_fake_reviews_config(cfg)
    return jsonify({"ok": True, "config": cfg})

@app.route("/api/admin/fake-reviews/fire-one", methods=["POST"])
@login_required_api
def api_admin_fake_reviews_fire_one():
    username = session["username"]
    if not is_admin_user(username):
        return jsonify({"error": "Unauthorized"}), 403
    cfg = _load_fake_reviews_config()
    if not cfg.get("usernames"):
        return jsonify({"error": "No usernames configured"}), 400
    usernames = cfg["usernames"]
    texts = cfg.get("texts", [])
    chosen = random.choice(usernames)
    text = random.choice(texts) if texts else ""
    reviews = _load_reviews()
    review = {
        "id": f"rev_{secrets.token_hex(8)}",
        "username": chosen,
        "rating": 5,
        "text": text,
        "image": "",
        "account_item_id": None,
        "account_title": "",
        "status": "approved",
        "created_at": int(time.time()),
    }
    reviews.insert(0, review)
    _save_reviews(reviews)
    return jsonify({"ok": True, "message": f"Posted 5-star review as {chosen}"})

# ===================== TWO-FACTOR AUTH =====================

@app.route("/api/profile/toggle-2fa", methods=["POST"])
@login_required_api
def api_profile_toggle_2fa():
    username = session["username"]
    users = _load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    current = users[username].get("twofa_enabled", False)
    users[username]["twofa_enabled"] = not current
    _save_users(users)
    return jsonify({"ok": True, "enabled": not current, "message": "2FA " + ("enabled" if not current else "disabled")})

@app.route("/api/profile/2fa-status", methods=["GET"])
@login_required_api
def api_profile_2fa_status():
    username = session["username"]
    users = _load_users()
    return jsonify({"enabled": bool(users.get(username, {}).get("twofa_enabled", False))})

@app.route("/verify-twofa", methods=["GET", "POST"])
def verify_twofa():
    pending = session.get("pending_twofa_username", "")
    if not pending:
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("verify_twofa.html", error="", username=pending, logged_in=False, balance="0.00", active_page="login")
    code = (request.form.get("code") or "").strip()
    users = _load_users()
    user_data = users.get(pending, {})
    stored_hash = user_data.get("twofa_code", "")
    expires = int(user_data.get("twofa_expires") or 0)
    if not stored_hash or int(time.time()) > expires:
        return render_template("verify_twofa.html", error="Code expired. Please log in again.", username=pending, logged_in=False, balance="0.00", active_page="login")
    if not check_password_hash(stored_hash, code):
        return render_template("verify_twofa.html", error="Invalid code.", username=pending, logged_in=False, balance="0.00", active_page="login")
    user_data.pop("twofa_code", None)
    user_data.pop("twofa_expires", None)
    _save_users(users)
    session["username"] = pending
    session.permanent = True
    session.pop("pending_twofa_username", None)
    _push_activity("online", pending)
    return redirect(url_for("index"))

# ===================== USER MANAGEMENT (OWNER) =====================

@app.route("/api/admin/user-manage", methods=["POST"])
@login_required_api
def api_admin_user_manage():
    username = session["username"]
    users = _load_users()
    viewer_data = users.get(username, {})
    if (viewer_data.get("email") or "").lower() != "konvyvip@gmail.com":
        return jsonify({"error": "Only the owner can manage users"}), 403
    data = request.json or {}
    target = (data.get("username") or "").strip()
    action = data.get("action")
    if not target or target not in users:
        return jsonify({"error": "User not found"}), 404
    if action == "set_balance":
        try:
            bal = float(data.get("balance", 0))
            from balances_file import _load_balances, _save_balances
            bals = _load_balances()
            bals[target] = int(bal * 100)
            _save_balances(bals)
            return jsonify({"ok": True, "message": f"Balance set to ${bal:.2f}"})
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    elif action == "set_verification":
        status = data.get("status", "unverified")
        if status not in ("unverified", "verified", "verify_each", "blacklisted"):
            return jsonify({"error": "Invalid status"}), 400
        set_user_verification_status(target, status)
        return jsonify({"ok": True, "message": f"Status set to {status}"})
    elif action == "set_role":
        role = data.get("role", "user")
        if role not in ("user", "support"):
            return jsonify({"error": "Invalid role"}), 400
        users[target]["role"] = role
        _save_users(users)
        return jsonify({"ok": True, "message": f"Role set to {role}"})
    elif action == "ban":
        set_user_verification_status(target, "blacklisted")
        return jsonify({"ok": True, "message": f"{target} banned"})
    elif action == "delete_reviews":
        reviews = _load_reviews()
        reviews[:] = [r for r in reviews if r.get("username", "").lower() != target.lower()]
        _save_reviews(reviews)
        return jsonify({"ok": True, "message": f"Deleted all reviews by {target}"})
    return jsonify({"error": "Invalid action"}), 400

# ===================== REVIEWS =====================

@app.route("/reviews")
def reviews_page():
    logged_in = "username" in session
    my_username = session.get("username", "")
    reviews = _load_reviews()
    approved = [r for r in reviews if r.get("status") == "approved"]
    all_users = _load_users()
    owner_email = (all_users.get(my_username, {}).get("email") or "").lower() if my_username else ""
    return render_template("reviews.html", logged_in=logged_in, username=my_username,
        balance=f"{get_balance(my_username) / 100:.2f}" if logged_in else "0.00",
        active_page="reviews", reviews=approved,
        is_konvy_vip=owner_email == "konvyvip@gmail.com",
        all_users=all_users)

@app.route("/api/reviews", methods=["GET", "POST"])
@login_required_api
def api_reviews():
    username = session["username"]
    if request.method == "GET":
        return jsonify({"reviews": _load_reviews()})
    data = request.json or {}
    rating = int(data.get("rating") or 0)
    text = (data.get("text") or "").strip()
    if rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be 1-5"}), 400
    if text and len(text) > 2000:
        return jsonify({"error": "Review text too long (max 2000)"}), 400
    # Look up the selected account
    account_item_id = None
    account_title = ""
    account_index = data.get("account_index")
    if account_index is not None:
        try:
            purchases = get_purchases(username)
            idx = int(account_index)
            if 0 <= idx < len(purchases):
                pr = purchases[idx].get("purchase_result", {})
                account_item_id = pr.get("item_id") or pr.get("fortnite_item_id")
                account_title = pr.get("title") or pr.get("title_en") or ""
        except (ValueError, TypeError):
            pass
    image_url = (data.get("image") or "").strip()
    reviews = _load_reviews()
    review = {
        "id": f"rev_{secrets.token_hex(8)}",
        "username": username,
        "rating": rating,
        "text": text,
        "image": image_url,
        "account_item_id": account_item_id,
        "account_title": account_title,
        "status": "pending",
        "created_at": int(time.time()),
    }
    reviews.insert(0, review)
    _save_reviews(reviews)
    _push_activity("review", username, {"rating": rating})
    return jsonify({"ok": True, "review": review})

@app.route("/api/reviews/upload-image", methods=["POST"])
@login_required_api
def api_reviews_upload_image():
    username = session["username"]
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400
    os.makedirs(REVIEW_UPLOADS_DIR, exist_ok=True)
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "jpg"
    allowed = {"png", "jpg", "jpeg", "gif", "webp"}
    if ext not in allowed:
        return jsonify({"error": "File type not allowed"}), 400
    filename = f"{username}_{secrets.token_hex(4)}.{ext}"
    path = os.path.join(REVIEW_UPLOADS_DIR, filename)
    f.save(path)
    return jsonify({"ok": True, "url": f"/review-uploads/{filename}"})

@app.route("/review-uploads/<filename>")
def serve_review_upload(filename: str):
    return send_from_directory(REVIEW_UPLOADS_DIR, filename)

@app.route("/api/admin/reviews/manage", methods=["POST"])
@login_required_api
def api_admin_reviews_manage():
    username = session["username"]
    if not is_admin_user(username):
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json or {}
    review_id = data.get("id")
    action = data.get("action")
    if not review_id or action not in ("approve", "deny", "hold", "delete"):
        return jsonify({"error": "Invalid request"}), 400
    reviews = _load_reviews()
    if action == "delete":
        reviews[:] = [r for r in reviews if r.get("id") != review_id]
        _save_reviews(reviews)
        return jsonify({"ok": True, "reviews": reviews})
    for r in reviews:
        if r.get("id") == review_id:
            r["status"] = {"approve": "approved", "deny": "denied", "hold": "hold"}[action]
            _save_reviews(reviews)
            return jsonify({"ok": True, "reviews": reviews})
    return jsonify({"error": "Review not found"}), 404

# ===================== ACTIVITY FEED =====================

@app.route("/api/activity")
def api_activity():
    limit = min(int(request.args.get("limit", 50)), 100)
    activity = _load_activity()
    return jsonify({"activity": activity[:limit]})

@app.route("/activity")
def activity_page():
    return redirect(url_for("dashboard"))

# ===================== LZT BALANCE REFRESH =====================

@app.route("/api/balance/lzt", methods=["POST"])
@login_required_api
def api_balance_lzt():
    username = session["username"]
    if not is_admin_user(username):
        return jsonify({"error": "Unauthorized"}), 403
    cents = get_lzt_balance_cents(force=True)
    return jsonify({"balance": cents / 100})

# ===================== ACCOUNT GIFTING =====================

@app.route("/api/fortnite/gift", methods=["POST"])
@login_required_api
def api_fortnite_gift():
    username = session["username"]
    data = request.json or {}
    recipient = (data.get("recipient") or "").strip()
    item_id = int(data.get("item_id") or 0)
    if not recipient or not item_id:
        return jsonify({"error": "Recipient and item_id required"}), 400
    if recipient.lower() == username.lower():
        return jsonify({"error": "Cannot gift to yourself"}), 400
    users = _load_users()
    if recipient not in users:
        return jsonify({"error": "Recipient not found"}), 404
    # Verify user owns the account (has it in purchases)
    purchases = get_purchases(username)
    found = None
    for p in purchases:
        pr = p.get("purchase_result", {})
        pid = pr.get("item_id") or (pr.get("fortnite_item_id"))
        if pid and int(pid) == item_id:
            found = p
            break
    if not found:
        return jsonify({"error": "Account not found in your purchases"}), 404
    # Transfer to recipient
    all_purchases = _load_purchases()
    user_purchases = all_purchases.get(username, [])
    user_purchases = [p for p in user_purchases if p is not found]
    all_purchases[username] = user_purchases
    if recipient not in all_purchases:
        all_purchases[recipient] = []
    found["gifted_by"] = username
    found["gifted_at"] = int(time.time())
    all_purchases[recipient].append(found)
    _save_purchases(all_purchases)
    _push_activity("gift", username, {"to": recipient, "item_id": item_id})
    return jsonify({"ok": True, "message": f"Account gifted to {recipient}!"})

# ===================== SEO ROUTES =====================

@app.route("/robots.txt")
def robots_txt():
    return Response("User-agent: *\nAllow: /\nSitemap: https://konvyaccounts.com/sitemap.xml\n", mimetype="text/plain")

@app.route("/sitemap.xml")
def sitemap_xml():
    urls = [
        {"loc": "https://konvyaccounts.com/", "priority": "1.0"},
        {"loc": "https://konvyaccounts.com/dashboard", "priority": "1.0"},
        {"loc": "https://konvyaccounts.com/reviews", "priority": "0.8"},
        {"loc": "https://konvyaccounts.com/support", "priority": "0.7"},
        {"loc": "https://konvyaccounts.com/how-it-works", "priority": "0.6"},
        {"loc": "https://konvyaccounts.com/warranty", "priority": "0.6"},
        {"loc": "https://konvyaccounts.com/terms", "priority": "0.5"},
    ]
    # Add account pages from recent purchases for indexing
    try:
        purchases = _load_purchases()
        seen = set()
        for uname, accs in purchases.items():
            for a in accs:
                pr = a.get("purchase_result", {})
                item_id = pr.get("item_id") or pr.get("fortnite_item_id")
                if item_id and item_id not in seen:
                    seen.add(item_id)
                    urls.append({"loc": f"https://konvyaccounts.com/account/{item_id}", "priority": "0.7"})
                    if len(seen) >= 50:
                        break
            if len(seen) >= 50:
                break
    except Exception:
        pass
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        xml += f"  <url><loc>{u['loc']}</loc><priority>{u['priority']}</priority></url>\n"
    xml += "</urlset>"
    return Response(xml, mimetype="application/xml")

# ===================== ONLINE USERS LIST =====================

@app.route("/api/users/online")
@login_required_api
def api_users_online():
    viewer = session["username"]
    if not is_admin_user(viewer):
        return jsonify({"error": "Unauthorized"}), 403
    all_users = _load_users()
    result = []
    for uname, udata in all_users.items():
        online = bool(udata.get("online", False))
        role = udata.get("role", "user")
        if uname.lower() == "konvy" or (udata.get("email") or "").lower() == "konvyvip@gmail.com":
            role = "owner"
        result.append({
            "username": uname,
            "online": online,
            "role": role,
            "last_online": udata.get("last_online", 0),
            "profile_pic": udata.get("profile_pic", "") or "",
        })
    result.sort(key=lambda x: (not x["online"], x["username"].lower()))
    return jsonify({"users": result})

# ===================== ONLINE STATUS API =====================

@app.route("/api/status/<username>")
def api_user_status(username: str):
    users = _load_users()
    for u in users:
        if u.lower() == username.lower():
            last_online = users[u].get("last_online", 0)
            online = bool(users[u].get("online", False))
            return jsonify({"online": online, "last_online": last_online})
    return jsonify({"online": False, "last_online": 0})

# ===================== PING (online/offline) =====================

@app.route("/api/ping", methods=["POST", "GET"])
def api_ping():
    username = session.get("username")
    if not username:
        return jsonify({"ok": False}), 200
    try:
        status = request.args.get("status", "online")
        users = _load_users()
        if username in users:
            now = int(time.time())
        if status == "offline":
            users[username]["last_online"] = now
            users[username]["online"] = False
            _save_users(users)
            _push_activity("offline", username)
        else:
            users[username]["last_online"] = now
            users[username]["online"] = True
            _save_users(users)
            _push_activity("online", username)
    except Exception:
        pass
    return jsonify({"ok": True}), 200

# ===================== WIPE ALL DATA =====================

@app.route("/api/admin/wipe-all", methods=["POST"])
@login_required_api
def api_admin_wipe_all():
    username = session["username"]
    users = _load_users()
    user_data = users.get(username, {})
    if (user_data.get("email") or "").lower() != "konvyvip@gmail.com":
        return jsonify({"error": "Only the owner can wipe data"}), 403
    files_to_clear = [
        ("support_tickets.json", "Tickets"),
        ("purchased_accounts.json", "Purchases"),
        ("balances.json", "Balances"),
        ("topup_history.json", "Topup history"),
        ("pending_topups.json", "Pending topups"),
        ("topup_notifications.json", "Notifications"),
        ("activity.json", "Activity feed"),
        ("reviews.json", "Reviews"),
        ("messages.json", "Messages"),
        ("global_chat.json", "Global chat"),
        ("redeemed_orders.json", "Redeemed orders"),
        ("account_views.json", "Account views"),
        ("customer_news.json", "Customer news"),
        ("admins.json", "Admins"),
        ("chat_bans.json", "Chat bans"),
    ]
    # Wipe all users except the owner
    owner_username = username
    owner_email = user_data.get("email", "")
    try:
        all_users = _load_users()
        keep = {owner_username: all_users.get(owner_username, {})}
        # Also keep any user whose email matches the owner
        for uname, udata in all_users.items():
            if udata.get("email", "").lower() == owner_email.lower() and uname != owner_username:
                keep[uname] = udata
        _save_users(keep)
        cleared.append("Users (kept owner)")
    except Exception:
        pass
    cleared = []
    for fname, label in files_to_clear:
        fpath = os.path.join(DATA_DIR, fname)
        try:
            if os.path.exists(fpath):
                with open(fpath, "w", encoding="utf-8") as f:
                    if fname in ("balances.json", "purchased_accounts.json", "account_views.json", "messages.json"):
                        json.dump({}, f)
                    elif fname in ("admins.json", "chat_bans.json"):
                        json.dump({"banned_ips": [], "timed_out_users": {}} if fname == "chat_bans.json" else [], f)
                    else:
                        json.dump([], f)
                cleared.append(label)
        except Exception:
            pass
    return jsonify({"ok": True, "message": f"Cleared {len(cleared)} data sets: {', '.join(cleared)}"})

# ===================== RUN =====================

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    ensure_cosmetic_lookup_runtime_initialized()
    start_fake_orders_scheduler()
    app.run(host="0.0.0.0", port=port)
