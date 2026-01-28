import copy
from importlib import metadata
from pathlib import Path

import yaml

from app_log import log

# Global configuration and headers
cfg: dict = {}
HEADERS: dict = {}


def load_config(path: str = "config.yaml") -> dict:
    """Load configuration from *path* and refresh HEADERS.

    If *path* does not exist a new configuration file is created automatically
    using ``config_demo.yaml`` as a template (falling back to a minimal built-in
    default when the demo file is missing).
    """

    cfg_path = Path(path)
    if not cfg_path.exists():
        template_path = Path(__file__).with_name("config_demo.yaml")
        if template_path.exists():
            with open(template_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            # Fallback defaults used when the demo file is unavailable
            data = {
                "base_url": "https://candfans.jp/api/user/get-entry-plans",
                "get_users_url": "https://candfans.jp/api/user/get-users",
                "get_timeline_url": "https://candfans.jp/api/contents/get-timeline",
                "download_dir": "./downloads",
                "headers": {
                    "accept": "application/json",
                    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                    "priority": "u=1, i",
                    "referer": "https://candfans.jp/mypage/plan/admission",
                    "sec-ch-ua": '\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '\"Windows\"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                    "x-xsrf-token": "",
                },
                "cookie": "",
            }
        save_config(data, path)
        return cfg

    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cfg.clear()
    if data:
        cfg.update(data)
    refresh_headers_from_cfg()
    return cfg


def save_config(config: dict, path: str = "config.yaml") -> None:
    """Persist *config* to *path* and refresh HEADERS."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    cfg.clear()
    cfg.update(config)
    refresh_headers_from_cfg()


def refresh_headers_from_cfg() -> None:
    """Refresh HEADERS using values from global cfg."""
    HEADERS.clear()
    headers = copy.deepcopy(cfg.get("headers", {})) if cfg else {}
    cookie = cfg.get("cookie") if cfg else None
    if cookie:
        headers["Cookie"] = cookie
    HEADERS.update(headers)


def check_requirements(req_file: str = "requirements.txt") -> bool:
    """Check whether required packages are installed.

    Returns True if all requirements are satisfied, False otherwise.
    """
    req_path = Path(req_file)
    if not req_path.exists():
        log(f"Warning: {req_file} not found, skipping dependency check")
        return True

    with open(req_path, encoding="utf-8") as f:
        requirements = [r.strip() for r in f.read().splitlines() if r.strip() and not r.startswith("#")]

    missing_packages = []
    for req in requirements:
        try:
            if ">=" in req:
                pkg_name, version_required = req.split(">=", 1)
                installed_version = metadata.version(pkg_name)
                if installed_version < version_required:
                    raise metadata.PackageNotFoundError
            elif "==" in req:
                pkg_name, version_required = req.split("==", 1)
                installed_version = metadata.version(pkg_name)
                if installed_version != version_required:
                    raise metadata.PackageNotFoundError
            else:
                metadata.version(req)
        except metadata.PackageNotFoundError:
            missing_packages.append(req)

    if missing_packages:
        log("Missing or incompatible dependencies:")
        for pkg in missing_packages:
            log(f"  - {pkg}")
        return False
    return True
