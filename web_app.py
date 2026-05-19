# web_app.py



import os
import time
import json
import hmac
import hashlib
import base64
import datetime
import logging
import secrets
import smtplib
import threading
from email.message import EmailMessage
from typing import List, Tuple, Optional, Set, Dict, Any

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
)


from werkzeug.security import generate_password_hash, check_password_hash
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
MARKET_API_TIMEOUT = 12
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

# --- Support tickets ---
SUPPORT_TICKETS_FILE = os.path.join(DATA_DIR, "support_tickets.json")

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

# --- User storage ---
USERS_FILE = os.path.join(DATA_DIR, "users.json")


# --- Balances (reuse your balances_file) ---
from balances_file import get_balance, add_balance  # uses balances.json


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
    """Render a branded ItemZ HTML email."""
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
        <span style="color:#0EF475;">Item</span><span style="color:#ffffff;">Z</span>
      </span>
    </td></tr>

    <!-- Card -->
    <tr><td style="background:#161616;border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:36px 32px;">

      <!-- Title -->
      <p style="margin:0 0 6px;font-size:22px;font-weight:700;color:#ffffff;">{title}</p>
      <p style="margin:0 0 28px;font-size:14px;color:#a1a1aa;line-height:1.55;">{subtitle}</p>

      <!-- Code box -->
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center" style="padding:22px 0;background:#0d0d0d;border:1px solid rgba(14,244,117,0.25);border-radius:14px;">
          <span style="font-size:38px;font-weight:900;letter-spacing:10px;color:#0EF475;font-family:'Courier New',monospace;">{code}</span>
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
        &copy; 2026 ItemZ &nbsp;&bull;&nbsp;
        <a href="mailto:support@itemz.gg" style="color:#0EF475;text-decoration:none;">support@itemz.gg</a>
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
    subject = "Your ItemZ verification code"
    body = (
        f"Hi {username},\n\n"
        f"Your ItemZ email verification code is: {code}\n\n"
        f"This code expires in {expire_minutes} minutes.\n"
        "If you did not create this account, you can ignore this email.\n"
    )
    html_body = _itemz_email_html(
        title="Verify Your Email",
        subtitle=f"Hi {username}, enter the code below to verify your ItemZ account.",
        code=code,
        expire_minutes=expire_minutes,
        footer_note="If you did not create an ItemZ account, you can safely ignore this email.",
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
    subject = "Your ItemZ password reset code"
    body = (
        f"Hi {username},\n\n"
        f"Your ItemZ password reset code is: {code}\n\n"
        f"This code expires in {expire_minutes} minutes.\n"
        "If you did not request a password reset, you can ignore this email.\n"
    )
    html_body = _itemz_email_html(
        title="Reset Your Password",
        subtitle=f"Hi {username}, use the code below to reset your ItemZ password.",
        code=code,
        expire_minutes=expire_minutes,
        footer_note="If you did not request a password reset, you can safely ignore this email.",
    )
    ok, msg = _send_email_message(recipient, subject, body, html_body)
    if not ok:
        return False, msg
    return True, "We sent a 6-digit reset code to your email."


def create_user(username: str, password: str, email: str) -> bool:
    """
    Create a new user with an email address.
    Returns False if username already exists.
    """
    users = _load_users()
    if username in users:
        return False

    normalized_email = _normalize_email(email)
    users[username] = {
        "password_hash": generate_password_hash(password),
        "email": normalized_email,
        "email_verified": False if normalized_email else True,
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
        text = text[:max_length].strip()
    return text


def _sort_support_tickets(tickets: list) -> list:
    return sorted(
        tickets,
        key=lambda t: (int(t.get("updated_at") or 0), int(t.get("created_at") or 0)),
        reverse=True,
    )


def _serialize_ticket_for_user(ticket: dict) -> dict:
    messages = ticket.get("messages") if isinstance(ticket.get("messages"), list) else []
    last_message = messages[-1] if messages else {}
    return {
        "id": str(ticket.get("id") or ""),
        "subject": str(ticket.get("subject") or "Support Request"),
        "status": str(ticket.get("status") or "open"),
        "created_at": int(ticket.get("created_at") or 0),
        "updated_at": int(ticket.get("updated_at") or 0),
        "closed_at": int(ticket.get("closed_at") or 0),
        "closed_by": str(ticket.get("closed_by") or ""),
        "messages": messages,
        "needs_user_response": str(last_message.get("author_type") or "") == "admin",
        "last_message_preview": str(last_message.get("message") or "")[:140],
    }


def _serialize_ticket_for_admin(ticket: dict) -> dict:
    messages = ticket.get("messages") if isinstance(ticket.get("messages"), list) else []
    last_message = messages[-1] if messages else {}
    ticket_copy = _serialize_ticket_for_user(ticket)
    ticket_copy.update(
        {
            "username": str(ticket.get("username") or ""),
            "needs_admin_response": (
                ticket_copy["status"] == "open"
                and str(last_message.get("author_type") or "") == "user"
            ),
        }
    )
    return ticket_copy


def _find_ticket(tickets: list, ticket_id: str) -> Optional[dict]:
    for ticket in tickets:
        if str(ticket.get("id")) == str(ticket_id):
            return ticket
    return None


def _new_ticket_message(author_type: str, author: str, message: str) -> dict:
    return {
        "id": secrets.token_hex(8),
        "author_type": author_type,
        "author": author,
        "message": message,
        "timestamp": int(time.time()),
    }


def create_support_ticket(username: str, subject: str, message: str) -> Tuple[bool, str, Optional[dict]]:
    clean_subject = _format_ticket_text(subject, SUPPORT_TICKET_SUBJECT_MAX_LENGTH)
    clean_message = _format_ticket_text(message, SUPPORT_TICKET_MESSAGE_MAX_LENGTH)
    if not clean_subject:
        return False, "Subject is required.", None
    if not clean_message:
        return False, "Message is required.", None

    now = int(time.time())
    ticket = {
        "id": f"tkt_{secrets.token_hex(6)}",
        "username": username,
        "subject": clean_subject,
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "closed_at": 0,
        "closed_by": "",
        "messages": [_new_ticket_message("user", username, clean_message)],
    }
    tickets = _load_support_tickets()
    tickets.append(ticket)
    _save_support_tickets(_sort_support_tickets(tickets))
    return True, "Ticket created.", ticket


def _append_ticket_message(ticket: dict, author_type: str, author: str, message: str) -> Tuple[bool, str]:
    if str(ticket.get("status") or "") != "open":
        return False, "Ticket is already closed."
    clean_message = _format_ticket_text(message, SUPPORT_TICKET_MESSAGE_MAX_LENGTH)
    if not clean_message:
        return False, "Message is required."
    messages = ticket.get("messages") if isinstance(ticket.get("messages"), list) else []
    messages.append(_new_ticket_message(author_type, author, clean_message))
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


def add_purchase(username: str, purchase_result, latest_order) -> dict:
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
    }
    user_list.append(entry)
    purchases[username] = user_list
    _save_purchases(purchases)
    return entry


def get_purchases(username: str):
    purchases = _load_purchases()
    return purchases.get(username, [])


def save_purchase_record(
    username: str,
    purchase_result: Any,
    latest_order: Optional[dict],
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

            if updated:
                user_list[index] = existing_entry
                purchases[username] = user_list
                _save_purchases(purchases)

            return existing_entry, user_list, index

    entry = add_purchase(username, purchase_result, latest_order)
    user_list = get_purchases(username)
    return entry, user_list, len(user_list) - 1


def _format_purchase_webhook_currency(amount: Any) -> str:
    try:
        numeric_amount = float(amount or 0)
    except (TypeError, ValueError):
        numeric_amount = 0.0
    return f"${numeric_amount:.2f}"


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
            "value": str(username or "Unknown"),
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
        "username": "Itemz",
        "avatar_url": DISCORD_PURCHASE_THUMBNAIL_URL,
        "embeds": [
            {
                "title": "✅ Order Confirmed - Thank You!",
                "description": "Your Itemz Fortnite purchase was completed successfully.",
                "color": 0x0EF475,
                "author": {
                    "name": "Itemz Purchase Notification",
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
                    "text": "Powered by Itemz • discord.gg/itemz",
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
    return data.get("item") or data


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
    live_price = get_live_account_purchase_price(item_id)
    user_price = live_price * get_lzt_multiplier_for_pricing()
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


ensure_cosmetic_lookup_runtime_initialized()


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
        if not session.get("is_konvy_admin"):
            return redirect(url_for("konvyadmin_page"))
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
    <title>ItemZ â€“ Login</title>
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
      <div class="auth-title">ItemZ</div>
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

    session["username"] = username
    session.pop("pending_verify_username", None)
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
    <title>ItemZ – Web Panel</title>
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
        <div class="topbar-title">ItemZ â€“ Web Panel</div>
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
          <h2>How ItemZ Works</h2>
          <p class="small">
            Watch this quick tutorial, then follow the steps below to use ItemZ.
          </p>

          <div class="yt-wrap">
            <iframe
              src="https://www.youtube.com/embed/uhL9-_EyKvM"
              title="ItemZ Tutorial"
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
    <title>ItemZ â€“ Register</title>
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
      <div class="auth-title">ItemZ</div>
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
    <title>ItemZ â€“ Tutorial</title>
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
      <h1>ItemZ â€“ Tutorial</h1>
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
    if logged_in:
        balance = f"{get_balance(username) / 100:.2f}"
    return render_template(
        "support.html",
        logged_in=logged_in,
        username=username,
        balance=balance,
        active_page="support",
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
        return redirect(url_for("dashboard_page"))

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
        return redirect(url_for("dashboard_page"))

    skins = _extract_cosmetic_names(account, "fortniteSkins")
    pickaxes = _extract_cosmetic_names(account, "fortnitePickaxe")
    emotes = _extract_cosmetic_names(account, "fortniteDance")
    gliders = _extract_cosmetic_names(account, "fortniteGliders")

    try:
        base_price = float(account.get("price") or 0)
    except Exception:
        base_price = 0.0

    user_price = round(base_price * get_lzt_multiplier_for_pricing(), 2)
    days_ago = compute_days_ago(account)

    status = {
        "xbox_linkable": _to_status_bool(account.get("xbox_linkable") or account.get("xboxLinkable") or account.get("xbl_linkable")),
        "psn_linkable": _to_status_bool(account.get("psn_linkable") or account.get("psnLinkable")),
        "email_changeable": _to_status_bool(account.get("change_email") or account.get("email_changeable")),
        "email_access": _to_status_bool(account.get("email_login_data") or account.get("email_access")),
        "battle_pass": _to_status_bool(account.get("bp") or account.get("battle_pass")),
        "stw_edition": _to_status_bool(account.get("stw") or account.get("fortnite_stw")),
    }

    account_detail = {
        "item_id": item_id,
        "title": account.get("title") or account.get("title_en") or f"{len(skins)} Skins",
        "price": user_price,
        "base_price": base_price,
        "level": int(account.get("fortnite_level") or 0),
        "vbucks": int(account.get("fortnite_balance") or 0),
        "country": account.get("country") or "Unknown",
        "last_activity": f"{days_ago} days ago" if days_ago is not None else "Unknown",
        "skins": skins,
        "pickaxes": pickaxes,
        "emotes": emotes,
        "gliders": gliders,
        "status": status,
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


@app.route("/konvyadmin", methods=["GET", "POST"])
def konvyadmin_page():
    is_admin = bool(session.get("is_konvy_admin"))
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

    return render_template(
        "konvyadmin.html",
        is_admin=is_admin,
        current_multiplier=f"{get_lzt_multiplier():.2f}",
        error=error,
        notice=notice,
    )

# ===================== ADMIN API ROUTES =====================

@app.route("/api/admin/pending-topups", methods=["GET", "POST"])
def api_admin_pending_topups():
    if not session.get("is_konvy_admin"):
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


@app.route("/api/admin/support-tickets", methods=["GET"])
def api_admin_support_tickets():
    if not session.get("is_konvy_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    tickets = _sort_support_tickets(_load_support_tickets())
    return jsonify({"tickets": [_serialize_ticket_for_admin(t) for t in tickets]})


@app.route("/api/admin/support-tickets/<ticket_id>/reply", methods=["POST"])
def api_admin_support_ticket_reply(ticket_id: str):
    if not session.get("is_konvy_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json or {}
    message = data.get("message")
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    ok, msg = _append_ticket_message(ticket, "admin", "Admin", message)
    if not ok:
        return jsonify({"error": msg}), 400
    _save_support_tickets(_sort_support_tickets(tickets))
    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_admin(ticket)})


@app.route("/api/admin/support-tickets/<ticket_id>/close", methods=["POST"])
def api_admin_support_ticket_close(ticket_id: str):
    if not session.get("is_konvy_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    ok, msg = _close_ticket(ticket, "admin")
    if not ok:
        return jsonify({"error": msg}), 400
    _save_support_tickets(_sort_support_tickets(tickets))
    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_admin(ticket)})


@app.route("/api/admin/users", methods=["GET"])
def api_admin_users():
    if not session.get("is_konvy_admin"):
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
    if not session.get("is_konvy_admin"):
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
    if not session.get("is_konvy_admin"):
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
    if not session.get("is_konvy_admin"):
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
        mine = [t for t in tickets if str(t.get("username") or "") == username]
        return jsonify({"tickets": [_serialize_ticket_for_user(t) for t in mine]})

    data = request.json or {}
    ok, msg, ticket = create_support_ticket(
        username=username,
        subject=data.get("subject"),
        message=data.get("message"),
    )
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_user(ticket)})


@app.route("/api/support/tickets/<ticket_id>/reply", methods=["POST"])
@login_required_api
def api_support_ticket_reply(ticket_id: str):
    username = session["username"]
    data = request.json or {}
    message = data.get("message")
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket or str(ticket.get("username") or "") != username:
        return jsonify({"error": "Ticket not found"}), 404
    ok, msg = _append_ticket_message(ticket, "user", username, message)
    if not ok:
        return jsonify({"error": msg}), 400
    _save_support_tickets(_sort_support_tickets(tickets))
    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_user(ticket)})


@app.route("/api/support/tickets/<ticket_id>/close", methods=["POST"])
@login_required_api
def api_support_ticket_close(ticket_id: str):
    username = session["username"]
    tickets = _load_support_tickets()
    ticket = _find_ticket(tickets, ticket_id)
    if not ticket or str(ticket.get("username") or "") != username:
        return jsonify({"error": "Ticket not found"}), 404
    ok, msg = _close_ticket(ticket, "user")
    if not ok:
        return jsonify({"error": msg}), 400
    _save_support_tickets(_sort_support_tickets(tickets))
    return jsonify({"ok": True, "message": msg, "ticket": _serialize_ticket_for_user(ticket)})


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
            return jsonify({"error": "Error fetching accounts. Please try again."}), 500

        if not accounts:
            return jsonify({"accounts": [], "not_found": not_found})

        result_accounts = []
        for acc in accounts:
            price = acc.get("price")
            try:
                base_price = float(price)
            except Exception:
                base_price = 0.0

            user_price = base_price * get_lzt_multiplier_for_pricing()

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
            for field_name in ("fortniteSkins", "fortnitePickaxe", "fortniteDance", "fortniteGliders"):
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

            result_accounts.append(
                {
                    "item_id": acc.get("item_id"),
                    "title": acc.get("title") or acc.get("title_en") or "",
                    "base_price": base_price,
                    "user_price": user_price,
                    "level": acc.get("fortnite_level") or 0,
                    "skins": acc.get("fortnite_skin_count") or 0,
                    "pickaxes": acc.get("fortnite_pickaxe_count") or 0,
                    "emotes": acc.get("fortnite_dance_count") or 0,
                    "gliders": acc.get("fortnite_glider_count") or 0,
                    "vbucks": acc.get("fortnite_balance") or 0,
                    "last_played": last_played,
                    "days_ago": days_ago,
                    "preview_cosmetics": preview_cosmetics,
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

        # STEP 4: store purchased account for this user
        purchase_entry, owned_accounts, purchase_index = save_purchase_record(
            username,
            purchase_result,
            latest_order,
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


# ===================== RUN =====================

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    ensure_cosmetic_lookup_runtime_initialized()
    app.run(host="0.0.0.0", port=port)
