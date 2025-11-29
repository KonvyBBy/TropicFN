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
    render_template_string,
    redirect,
    url_for,
    session,
)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

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
    print("WARNING: SHOPIFY_ADMIN_TOKEN not set – /redeem will not work.")

# --- Fortnite browse limits ---
MAX_ACCOUNTS = 50
MAX_PAGES = 10

# --- Redeemed orders tracking ---
REDEEMED_FILE = os.path.join(DATA_DIR, "redeemed_orders.json")

# --- Purchased accounts tracking ---
PURCHASES_FILE = os.path.join(DATA_DIR, "purchased_accounts.json")

# --- Pricing ---
UPCHARGE_MULTIPLIER = 1.8  # same as bot

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


def find_item_by_name(item_name: str, max_pages: int = 20):
    """
    Scan Fortnite listings, match cosmetic by title.
    Returns (param_name, query_id, raw_id, matched_title, item_type).
    """
    target = norm(item_name)

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
                for item in acc.get(field_name, []):
                    title = item.get("title") or ""
                    if norm(title) == target:
                        raw_id = item.get("id")
                        if not raw_id:
                            continue
                        if isinstance(raw_id, str) and raw_id.startswith("cid_"):
                            query_id = raw_id[4:]
                        else:
                            query_id = raw_id
                        return param_name, query_id, raw_id, title, type_name

    return None


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

    for param_name, query_id in item_filters:
        if param_name in base_params:
            existing = base_params[param_name]
            if isinstance(existing, list):
                existing.append(query_id)
            else:
                base_params[param_name] = [existing, query_id]
        else:
            base_params[param_name] = query_id

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


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ===================== MAIN HTML =====================

INDEX_HTML = """
<!doctype html>
<html>
  <head>
    <title>Konvy Accounts – Web Panel</title>
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
          Logged in as <strong>{{ username }}</strong> |
          <a href="/logout">Logout</a>
        </div>
      </div>

      <p class="small">
        Search Fortnite accounts, check balance, top up via Shopify, redeem orders, and leave a review.
      </p>

      <!-- TAB BAR -->
      <div class="tab-bar">
        <button class="tab-btn active" data-tab-target="#tab-buy">Buy Account</button>
        <button class="tab-btn" data-tab-target="#tab-balance">Reload Balance</button>
        <button class="tab-btn" data-tab-target="#tab-my-accounts">My Account Info</button>
        <button class="tab-btn" data-tab-target="#tab-redeem">Redeem</button>
        {% if has_purchases %}
        <button class="tab-btn" data-tab-target="#tab-review">Review</button>
        {% endif %}
      </div>

      <!-- (rest of your HTML + JS stays the same, I only changed body + #snow-canvas CSS) -->

    </div>

    <script>
      /* keep all your existing JS here, INCLUDING the snow animation,
         but make sure the resize() looks like this: */
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





@app.route("/")
@login_required_page
def index():
    username = session["username"]
    has_purchases = bool(get_purchases(username))
    return render_template_string(
        INDEX_HTML,
        username=username,
        has_purchases=has_purchases,
    )



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
@login_required_api
def api_fortnite_search():
    data = request.json or {}
    item = data.get("item", "")
    days = int(data.get("days") or 0)
    skins = int(data.get("skins") or 0)

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

        user_price = base_price * UPCHARGE_MULTIPLIER
        days_ago = compute_days_ago(acc)
        last_played = f"{days_ago} days ago" if days_ago is not None else "N/A"

        result_accounts.append(
            {
                "item_id": acc.get("item_id"),
                "base_price": base_price,
                "user_price": user_price,
                "level": acc.get("fortnite_level"),
                "skins": acc.get("fortnite_skin_count"),
                "pickaxes": acc.get("fortnite_pickaxe_count"),
                "emotes": acc.get("fortnite_dance_count"),
                "gliders": acc.get("fortnite_glider_count"),
                "vbucks": acc.get("fortnite_balance"),
                "last_played": last_played,
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

    user_price = base_price * UPCHARGE_MULTIPLIER
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






