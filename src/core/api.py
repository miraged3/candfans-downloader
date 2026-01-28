from .network import safe_get
from .config import HEADERS, cfg


def get_subscription_list():
    """Fetch subscription list using configured base URL."""
    resp = safe_get(cfg["base_url"], headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def parse_subscription_list(resp_json):
    """Parse subscription list JSON into a simplified list."""
    subs = []
    for item in resp_json.get("data", []):
        subs.append(
            {"user_code": item["user_code"], "plan_id": item["plan_id"]})
    return subs


def get_user_info_by_code(user_code):
    """Retrieve user information by user_code."""
    resp = safe_get(cfg["get_users_url"], headers=HEADERS,
                    params={"user_code": user_code})
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


def get_purchased_contents():
    """Fetch purchased contents list."""
    resp = safe_get(
        "https://candfans.jp/api/contents/get-purchased-contents", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def parse_purchased_contents(resp_json):
    """Parse purchased contents JSON into a flattened list.

    Args:
        resp_json: Response from get_purchased_contents()

    Returns:
        List of purchased content items with added 'purchase_month' field
    """
    all_contents = []
    data = resp_json.get("data", {})

    for month_key, contents_list in data.items():
        # Extract month from key like "2025年09月 購入履歴"
        purchase_month = month_key.split()[0]  # "2025年09月"

        for content in contents_list:
            # Add purchase month to each content item
            content_with_month = content.copy()
            content_with_month["purchase_month"] = purchase_month
            all_contents.append(content_with_month)

    return all_contents
