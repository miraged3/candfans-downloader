from network import safe_get
from config import HEADERS, cfg


def get_subscription_list():
    """Fetch subscription list using configured base URL."""
    resp = safe_get(cfg["base_url"], headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def parse_subscription_list(resp_json):
    """Parse subscription list JSON into a simplified list."""
    subs = []
    for item in resp_json.get("data", []):
        subs.append({"user_code": item["user_code"], "plan_id": item["plan_id"]})
    return subs


def get_user_info_by_code(user_code):
    """Retrieve user information by user_code."""
    resp = safe_get(cfg["get_users_url"], headers=HEADERS, params={"user_code": user_code})
    resp.raise_for_status()
    data = resp.json()
    user = data["data"]["user"]
    return {
        "user_code": user["user_code"],
        "username": user["username"],
        "user_id": user["id"],
    }


def get_user_mine(headers=None):
    """Retrieve information of the currently logged in user."""
    resp = safe_get(
        "https://candfans.jp/api/user/get-user-mine",
        headers=headers or HEADERS,
    )
    resp.raise_for_status()
    return resp.json()


def get_timeline(user_id, page=1, record=12):
    """Fetch timeline posts for a user."""
    params = {
        "user_id": user_id,
        "sort_order": "new",
        "record": record,
        "page": page,
        "post_type[0]": 1,
    }
    resp = safe_get(cfg["get_timeline_url"], headers=HEADERS, params=params)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])
