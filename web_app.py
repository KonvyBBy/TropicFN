# web_app.py
import os
import time
import json
from typing import List, Tuple, Optional, Set

import requests
from flask import (
    Flask,
    request,
    jsonify,
    render_template,          # âœ… ADD
    render_template_string,
    redirect,
    url_for,
    session,
)


from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps


# ===================== FORTNITE ICON LOOKUP =====================

FORTNITE_COSMETICS_SEARCH_URL = "https://fortnite-api.com/v2/cosmetics/br/search/all"
COSMETIC_ICON_CACHE_FILE = "cosmetic_icon_cache.json"

def fortnite_api_get_outfit_icon_url_by_name(name: str):
    name = (name or "").strip()
    if not name:
        return None

    cache = {}
    if os.path.exists(COSMETIC_ICON_CACHE_FILE):
        try:
            with open(COSMETIC_ICON_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f) or {}
        except Exception:
            cache = {}

    key = f"outfit::{name.lower()}"
    if key in cache:
        return cache[key]

    params = {
        "name": name,
        "matchMethod": "contains",
        "language": "en",
        "searchLanguage": "en",
    }

    try:
        r = requests.get(FORTNITE_COSMETICS_SEARCH_URL, params=params, timeout=8)
        if r.status_code != 200:
            cache[key] = None
            return None

        data = (r.json() or {}).get("data") or []
        for item in data:
            t = item.get("type", {})
            t_val = (t.get("value") or t.get("backendValue") or "").lower()
            if t_val == "outfit":
                images = item.get("images") or {}
                url = images.get("icon") or images.get("smallIcon") or images.get("featured")
                cache[key] = url
                with open(COSMETIC_ICON_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=2)
                return url

        cache[key] = None
        return None

    except Exception:
        return None




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

if not SHOPIFY_ADMIN_TOKEN:
    print("WARNING: SHOPIFY_ADMIN_TOKEN not set â€“ /redeem will not work.")

# --- Fortnite browse limits ---
MAX_ACCOUNTS = 50
MAX_PAGES = 10

# --- Redeemed orders tracking ---
REDEEMED_FILE = os.path.join(DATA_DIR, "redeemed_orders.json")

# --- Purchased accounts tracking ---
PURCHASES_FILE = os.path.join(DATA_DIR, "purchased_accounts.json")

# --- Pricing ---
# --- Pricing Tiers ---
UPCHARGE_TIERS = [
    {"min": 0,  "max": 5,  "multiplier": 3.3},
    {"min": 5,  "max": 10, "multiplier": 3.0},
    {"min": 10, "max": 15, "multiplier": 2.3},
    {"min": 15, "max": 20, "multiplier": 2.3},
    {"min": 20, "max": 25, "multiplier": 2.4},
    {"min": 25, "max": 30, "multiplier": 2.2},
    {"min": 30, "max": 35, "multiplier": 2.05},
    {"min": 35, "max": 40, "multiplier": 1.95},
    {"min": 40, "max": 45, "multiplier": 1.85},
    {"min": 45, "max": 50, "multiplier": 1.75},
    {"min": 50, "max": 60, "multiplier": 1.65},
    {"min": 60, "max": 70, "multiplier": 1.6},
    {"min": 70, "max": 80, "multiplier": 1.55},
    {"min": 80, "max": 90, "multiplier": 1.5},
    {"min": 90, "max": 100,"multiplier": 1.45},
    {"min": 100,"max": 999999,"multiplier": 1.4}
]






def get_upcharge_multiplier(base_price: float) -> float:
    """Get the appropriate upcharge multiplier based on base price."""
    for tier in UPCHARGE_TIERS:
        if tier["min"] <= base_price < tier["max"]:
            return tier["multiplier"]
    return 1.5  # Default fallback

# --- User storage ---
USERS_FILE = os.path.join(DATA_DIR, "users.json")
FAVORITES_FILE = os.path.join(DATA_DIR, "favorites.json")


# --- Balances (reuse your balances_file) ---
from balances_file import get_balance, add_balance  # uses balances.json


# ===================== USER HELPERS =====================

# --- Favorites tracking ---

def _load_favorites() -> dict:
    if not os.path.exists(FAVORITES_FILE):
        return {}
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_favorites(favorites: dict) -> None:
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favorites, f, indent=2)



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


def create_user(username: str, password: str) -> bool:
    """
    Create a new user. Returns False if username already exists.
    """
    users = _load_users()
    if username in users:
        return False
    users[username] = {
        "password_hash": generate_password_hash(password),
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

    data = resp.json()
    return data.get("item") or data.get("data") or data



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
        resp = requests.get(MARKET_API_URL, headers=market_headers, params=params)

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
):
    """
    Get up to MAX_ACCOUNTS cheapest accounts that match filters.
    """
    base_params = {
        "order_by": "price_to_up",  # cheapest first
    }

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

    if min_days is not None and min_days >= 0:
        base_params["daybreak"] = min_days

    if min_skins is not None and min_skins >= 0:
        base_params["smin"] = min_skins

    all_accounts = []

    for page in range(1, MAX_PAGES + 1):
        params = dict(base_params)
        params["page"] = page

        resp = requests.get(MARKET_API_URL, headers=market_headers, params=params)

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


def fast_buy_account(item_id: int, price: float):
    """
    Uses docs: POST /{item_id}/fast-buy with {price}.
    """
    url = f"https://prod-api.lzt.market/{item_id}/fast-buy"
    headers_fb = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {MARKET_API_TOKEN}",
    }
    payload = {"price": float(price)}
    resp = requests.post(url, headers=headers_fb, json=payload, timeout=60)

    if resp.status_code == 403:
        try:
            data = resp.json()
            errors = " ".join(data.get("errors", []))
            if "sold" in errors.lower():
                raise RuntimeError("This listing has already been sold.")
        except Exception:
            pass

    if not resp.ok:
        raise RuntimeError(f"Fast-buy failed: {resp.status_code} - {resp.text[:300]}")

    return resp.json()


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


def get_shopify_order_by_number(order_number: int):
    """
    Look up Shopify order by #number.
    Note format used: user:<username>
    """
    if not SHOPIFY_ADMIN_TOKEN:
        return None, None, None, None, "no_token"

    order_name = f"#{order_number}"
    url = f"https://{SHOPIFY_ADMIN_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/orders.json"
    params = {
        "status": "any",
        "name": order_name,
        "limit": 1,
    }
    headers_shopify = {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
        "Content-Type": "application/json",
    }

    resp = requests.get(url, headers=headers_shopify, params=params)
    if resp.status_code != 200:
        return None, None, None, None, "api_error"

    data = resp.json()
    orders = data.get("orders", [])
    if not orders:
        return None, None, None, None, "not_found"

    order = orders[0]
    order_id_str = str(order.get("id"))
    note = order.get("note", "")
    financial_status = order.get("financial_status")

    if financial_status != "paid":
        return None, None, None, financial_status, "not_paid"

    total_price_str = order.get("total_price") or "0.00"
    try:
        amount_dollars = float(total_price_str)
    except Exception:
        return None, None, None, None, "bad_price"

    amount_cents = int(round(amount_dollars * 100))

    return amount_cents, order_id_str, note, financial_status, "ok"


# ===================== FLASK APP =====================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-this")


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


def user_has_purchases(username):
    purchases = get_purchases(username)
    return len(purchases) > 0



# ===================== AUTH ROUTES =====================


# ===================== AUTH ROUTES =====================

LOGIN_HTML = """
<!doctype html>
<html>
  <head>
    <title>Konvy Accounts â€“ Login</title>
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
          <input name="password" type="password" placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢">
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
    icons = []

    for name in names:
        url = fortnite_api_get_outfit_icon_url_by_name(name)
        icons.append({
            "name": name,
            "icon": url
        })

    return {"icons": icons}


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
    error = None
    username_prefill = ""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        username_prefill = username

        if not verify_user(username, password):
            error = "Invalid username or password."
        else:
            session["username"] = username
            return redirect(url_for("index"))

    return render_template_string(
        LOGIN_HTML,
        error=error,
        username_prefill=username_prefill,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    username_prefill = ""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        username_prefill = username

        if not username or not password:
            error = "Username and password are required."
        else:
            created = create_user(username, password)
            if not created:
                error = "That username is already taken."
            else:
                session["username"] = username
                return redirect(url_for("index"))

    return render_template_string(
        REGISTER_HTML,
        error=error,
        username_prefill=username_prefill,
    )

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
        <div class="topbar-title">Konvy Accounts â€“ Web Panel</div>
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
          <h2>Redeem Shopify Order</h2>
          <form id="redeem-form">
            <label>Order number (without #)
              <input name="order_number" type="number" />
            </label>
            <button type="submit">Redeem</button>
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
            <span class="star" data-value="1">â˜…</span>
            <span class="star" data-value="2">â˜…</span>
            <span class="star" data-value="3">â˜…</span>
            <span class="star" data-value="4">â˜…</span>
            <span class="star" data-value="5">â˜…</span>
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
          throw new Error(json.error || 'Unknown error');
        }
        return json;
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
                  const buyPayload = {
                    item_id: Number(btn.dataset.itemId),
                    base_price: Number(btn.dataset.basePrice)
                  };
                  const res = await postJSON('/api/fortnite/buy', buyPayload);
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
    <title>Konvy Accounts â€“ Register</title>
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
    <title>Konvy Accounts â€“ Tutorial</title>
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
      <h1>Konvy Accounts â€“ Tutorial</h1>
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

@app.route("/api/favorites/add", methods=["POST"])
@login_required_api
def api_add_favorite():
    data = request.json or {}
    username = session["username"]
    item_id = int(data.get("item_id") or 0)
    
    if not item_id:
        return jsonify({"error": "item_id required"}), 400
    
    favorites = _load_favorites()
    user_favs = favorites.get(username, [])
    
    if item_id not in user_favs:
        user_favs.append(item_id)
        favorites[username] = user_favs
        _save_favorites(favorites)
    
    return jsonify({"message": "Added to favorites", "favorites": user_favs})


@app.route("/api/favorites/remove", methods=["POST"])
@login_required_api
def api_remove_favorite():
    data = request.json or {}
    username = session["username"]
    item_id = int(data.get("item_id") or 0)
    
    favorites = _load_favorites()
    user_favs = favorites.get(username, [])
    
    if item_id in user_favs:
        user_favs.remove(item_id)
        favorites[username] = user_favs
        _save_favorites(favorites)
    
    return jsonify({"message": "Removed from favorites", "favorites": user_favs})


@app.route("/api/favorites/list", methods=["POST"])
@login_required_api
def api_list_favorites():
    username = session["username"]
    favorites = _load_favorites()
    user_favs = favorites.get(username, [])
    return jsonify({"favorites": user_favs})















@app.route("/warranty")
def warranty():
    return render_template("warranty.html")


@app.route("/tutorial")
def tutorial():
    return render_template_string(TUTORIAL_HTML)


# 2. Remove @login_required_page from dashboard
@app.route("/dashboard")
def dashboard():
    # Check if logged in
    logged_in = "username" in session
    username = session.get("username", "Guest")
    
    balance_cents = 0
    purchases = []
    
    if logged_in:
        balance_cents = get_balance(username)
        purchases = get_purchases(username)
    
    balance = f"{balance_cents / 100:.2f}"
    
    return render_template(
        "dashboard.html",
        username=username,
        balance=balance,
        purchases=purchases,
        logged_in=logged_in
    )






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


@app.route("/api/redeem", methods=["POST"])
@login_required_api
def api_redeem():
    data = request.json or {}
    username = session["username"]
    order_number = int(data.get("order_number") or 0)

    if not order_number:
        return jsonify({"error": "order_number required"}), 400

    amount_cents, order_id_str, note, status, reason = get_shopify_order_by_number(
        order_number
    )

    if reason == "no_token":
        return jsonify({"error": "SHOPIFY_ADMIN_TOKEN not configured"}), 500

    if reason == "not_found":
        return jsonify({"error": f"No order found with number #{order_number}"}), 404

    if reason == "api_error":
        return jsonify({"error": "Shopify API error"}), 500

    if reason == "not_paid":
        return jsonify({"error": f"Order not paid yet (status: {status})"}), 400

    if reason != "ok":
        return jsonify({"error": "Could not validate order"}), 400

    expected_note = f"user:{username}"
    if (note or "").strip() != expected_note:
        return jsonify(
            {
                "error": "Order note does not match this user",
                "details": f"expected {expected_note}, got {note!r}",
            }
        ), 403

    if is_redeemed(order_id_str):
        return jsonify({"error": "Order already redeemed"}), 400

    add_balance(username, amount_cents)
    mark_redeemed(order_id_str)

    dollars_added = amount_cents / 100
    new_balance = get_balance(username) / 100

    return jsonify(
        {
            "message": (
                f"Redeemed order #{order_number}: added ${dollars_added:.2f}. "
                f"New balance: ${new_balance:.2f}"
            )
        }
    )


@app.route("/api/fortnite/search", methods=["POST"])
def api_fortnite_search():
    data = request.json or {}
    item = data.get("item", "")
    days = int(data.get("days") or 0)
    skins = int(data.get("skins") or 0)
    budget = float(data.get("budget") or 999999)  # Changed from min/max to single budget

    raw_items = [s.strip() for s in item.split(",") if s.strip()]
    if not raw_items:
        return jsonify({"error": "You must provide at least one item name."}), 400

    item_results = []
    not_found = []

    for name in raw_items:
        try:
            result = find_item_by_name(name)
        except Exception as e:
            return jsonify(
                {"error": f"Error while resolving item '{name}': {e}"}
            ), 500

        if not result:
            not_found.append(name)
        else:
            item_results.append(result)

    if not item_results:
        return jsonify(
            {"error": "No items found on marketplace.", "not_found": not_found}
        ), 404

    item_filters: List[Tuple[str, str]] = []
    for param_name, query_id, raw_id, matched_title, item_type in item_results:
        item_filters.append((param_name, query_id))

    min_days = days if days >= 0 else 0
    min_skins = skins if skins > 0 else None

    try:
        accounts, base_params = fetch_cheapest_accounts(
            item_filters=item_filters,
            min_days=min_days,
            min_skins=min_skins,
        )
    except Exception as e:
        return jsonify({"error": f"Error fetching accounts: {e}"}), 500

    if not accounts:
        return jsonify({"accounts": [], "not_found": not_found})

    result_accounts = []
    for acc in accounts:
        price = acc.get("price")
        try:
            base_price = float(price)
        except Exception:
            base_price = 0.0

        user_price = base_price * get_upcharge_multiplier(base_price)
        
# Filter by budget
        if user_price > budget:
            continue
        
        days_ago = compute_days_ago(acc)
        last_played = f"{days_ago} days ago" if days_ago is not None else "N/A"

        result_accounts.append(
            {
                "item_id": acc.get("item_id"),
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
            }
        )

    return jsonify({"accounts": result_accounts, "not_found": not_found})


@app.route("/api/fortnite/buy", methods=["POST"])
@login_required_api
def api_fortnite_buy():
    data = request.json or {}
    username = session["username"]
    item_id = int(data.get("item_id") or 0)
    base_price = float(data.get("base_price") or 0)

    if not item_id or base_price <= 0:
        return jsonify({"error": "item_id and base_price required"}), 400

    user_price = base_price * get_upcharge_multiplier(base_price)
    cost_cents = int(round(user_price * 100))
    starting_balance = get_balance(username)

    if starting_balance < cost_cents:
        missing = (cost_cents - starting_balance) / 100
        return jsonify(
            {
                "error": "not_enough_balance",
                "message": f"Not enough balance. Missing ${missing:.2f}",
            }
        ), 400

    # STEP 1: fast-buy on market
    try:
        purchase_result = fast_buy_account(item_id, base_price)
    except Exception as e:
        return jsonify({"error": "fast_buy_failed", "message": str(e)}), 500

    # STEP 2: optional, try to fetch latest order
    try:
        latest_order = get_latest_order()
    except Exception:
        latest_order = None

    # STEP 3: deduct balance
    add_balance(username, -cost_cents)
    new_balance = get_balance(username) / 100

    # STEP 4: store purchased account for this user
    purchase_entry = add_purchase(username, purchase_result, latest_order)
    owned_accounts = get_purchases(username)

    return jsonify(
        {
            "message": f"Purchase successful! Charged ${user_price:.2f}. New balance: ${new_balance:.2f}",
            "purchase_result": purchase_result,
            "latest_order": latest_order,
            "owned_accounts": owned_accounts,
            "saved_entry": purchase_entry,
        }
    )


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
    app.run(host="0.0.0.0", port=port)











