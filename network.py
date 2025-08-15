import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry


def _create_session() -> requests.Session:
    """Create and configure a requests Session with retry strategy."""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


_session = None


def get_session() -> requests.Session:
    """Return a shared Session instance."""
    global _session
    if _session is None:
        _session = _create_session()
    return _session


# Singleton session for modules that prefer direct access
session = get_session()


def safe_get(url: str, **kwargs):
    """Wrapper around session.get with default timeout."""
    return get_session().get(url, timeout=10, **kwargs)
