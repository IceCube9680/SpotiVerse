# info.py
import os

# Default user settings
DEFAULT_SETTINGS = {
    "preferred_format": "mp3",
    "preferred_quality": 64,
    "downloads_today": 0,
    "total_downloads": 0,
    "premium": False,
    "premium_plan": None,
    "premium_until": None,
    "lifetime_premium": False,
    "banned": False,
    "join_date": None
}

SEARCH_PROVIDERS = ["spotify", "youtube", "deezer", "soundcloud", "jiosaavn"]
DEFAULT_SEARCH_PROVIDER = "spotify"

# Default Base Premium Plans (Configurable & Overridable)
DEFAULT_PREMIUM_PLANS = [
    {
        "id": "1_month",
        "name": "1 Month",
        "duration": "30d",
        "days": 30,
        "price": 99,
        "currency": "INR",
        "symbol": "₹",
        "savings": None,
        "badge": None,
        "active": True,
        "sort_order": 1
    },
    {
        "id": "3_months",
        "name": "3 Months",
        "duration": "90d",
        "days": 90,
        "price": 249,
        "currency": "INR",
        "symbol": "₹",
        "savings": "16% OFF",
        "badge": "⭐ Most Popular",
        "active": True,
        "sort_order": 2
    },
    {
        "id": "6_months",
        "name": "6 Months",
        "duration": "180d",
        "days": 180,
        "price": 399,
        "currency": "INR",
        "symbol": "₹",
        "savings": "33% OFF",
        "badge": None,
        "active": True,
        "sort_order": 3
    },
    {
        "id": "1_year",
        "name": "1 Year",
        "duration": "365d",
        "days": 365,
        "price": 699,
        "currency": "INR",
        "symbol": "₹",
        "savings": "41% OFF",
        "badge": None,
        "active": True,
        "sort_order": 4
    },
    {
        "id": "lifetime",
        "name": "Lifetime",
        "duration": "lifetime",
        "days": 36500,
        "price": 1499,
        "currency": "INR",
        "symbol": "₹",
        "savings": "Best Value",
        "badge": "👑 Lifetime Access",
        "active": True,
        "sort_order": 5
    }
]

def get_premium_plans():
    """
    Returns list of active premium plans with environment overrides if present.
    Supports env vars: PREMIUM_PLAN_1_NAME, PREMIUM_PLAN_1_PRICE, PREMIUM_PLAN_1_DURATION, etc.
    """
    plans = []
    # Check if numbered env vars are defined
    plan_idx = 1
    custom_plans_found = False
    while True:
        name_var = f"PREMIUM_PLAN_{plan_idx}_NAME"
        price_var = f"PREMIUM_PLAN_{plan_idx}_PRICE"
        dur_var = f"PREMIUM_PLAN_{plan_idx}_DURATION"
        if os.getenv(name_var) and os.getenv(price_var):
            custom_plans_found = True
            name = os.getenv(name_var)
            try:
                price = int(os.getenv(price_var, 0))
            except ValueError:
                price = 0
            dur = os.getenv(dur_var, "30d")
            
            days = 30
            if dur.lower() in ("lifetime", "perm", "forever"):
                days = 36500
            elif dur.endswith("d"):
                try:
                    days = int(dur[:-1])
                except ValueError:
                    days = 30
            elif dur.endswith("m"):
                try:
                    days = int(dur[:-1]) * 30
                except ValueError:
                    days = 30
            elif dur.endswith("y"):
                try:
                    days = int(dur[:-1]) * 365
                except ValueError:
                    days = 365
            
            plans.append({
                "id": f"plan_{plan_idx}",
                "name": name,
                "duration": dur,
                "days": days,
                "price": price,
                "currency": os.getenv("PREMIUM_CURRENCY", "INR"),
                "symbol": os.getenv("PREMIUM_CURRENCY_SYMBOL", "₹"),
                "savings": os.getenv(f"PREMIUM_PLAN_{plan_idx}_SAVINGS"),
                "badge": os.getenv(f"PREMIUM_PLAN_{plan_idx}_BADGE"),
                "active": True,
                "sort_order": plan_idx
            })
            plan_idx += 1
        else:
            break

    if custom_plans_found and plans:
        return plans

    return [dict(p) for p in DEFAULT_PREMIUM_PLANS]

def get_plan_by_id(plan_id: str):
    """Find a plan by plan_id"""
    plans = get_premium_plans()
    for p in plans:
        if str(p["id"]).lower() == str(plan_id).lower() or str(p["name"]).lower() == str(plan_id).lower():
            return p
    return None

def parse_duration_to_timedelta(duration_str: str):
    """Parse custom duration syntax like '7d', '30d', '90d', '180d', '1y', 'lifetime' into timedelta"""
    from datetime import timedelta
    if not duration_str:
        return timedelta(days=30)
    dur = str(duration_str).strip().lower()
    if dur in ("lifetime", "perm", "forever", "infinity"):
        return timedelta(days=36500)
    if dur.endswith("d"):
        try:
            return timedelta(days=int(dur[:-1]))
        except ValueError:
            return timedelta(days=30)
    if dur.endswith("m"):
        try:
            return timedelta(days=int(dur[:-1]) * 30)
        except ValueError:
            return timedelta(days=30)
    if dur.endswith("y"):
        try:
            return timedelta(days=int(dur[:-1]) * 365)
        except ValueError:
            return timedelta(days=365)
    try:
        return timedelta(days=int(dur))
    except ValueError:
        return timedelta(days=30)

# Backward compatibility map
PREMIUM_PLANS = {
    "weekly": {"price": 49, "days": 7, "emoji": "🟢"},
    "monthly": {"price": 99, "days": 30, "emoji": "🟡"},
    "3months": {"price": 249, "days": 90, "emoji": "⭐"},
    "6months": {"price": 399, "days": 180, "emoji": "🔥"},
    "yearly": {"price": 699, "days": 365, "emoji": "🔴"},
    "lifetime": {"price": 1499, "days": 36500, "emoji": "👑"}
}