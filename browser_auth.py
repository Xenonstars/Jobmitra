"""
Browser Auth — launches a visible Chrome window so the user can manually
sign in to job sites (LinkedIn, Naukri, Indeed). Session cookies are saved
to disk and reused by headless crawlers.
"""

import asyncio
import json
import os
import structlog
from typing import Optional

logger = structlog.get_logger(__name__)

COOKIE_DIR = os.path.join(os.path.dirname(__file__), "data_folder", "cookies")
os.makedirs(COOKIE_DIR, exist_ok=True)

SITE_URLS = {
    "linkedin": "https://www.linkedin.com/login",
    "naukri": "https://www.naukri.com/nlogin/login",
    "indeed": "https://www.indeed.co.in/account/login",
}

SITE_VERIFY = {
    "linkedin": "linkedin.com/feed",
    "naukri": "naukri.com/mnjuser/homepage",
    "indeed": "indeed.co.in/?from=gnav-homepage",
}


def _cookie_path(site: str) -> str:
    return os.path.join(COOKIE_DIR, f"{site}_cookies.json")


def load_cookies(site: str) -> list[dict]:
    """Load saved cookies for a site. Returns [] if none found."""
    path = _cookie_path(site)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def save_cookies(site: str, cookies: list[dict]) -> None:
    """Persist cookies to disk."""
    path = _cookie_path(site)
    with open(path, "w") as f:
        json.dump(cookies, f, indent=2)
    logger.info("cookies_saved", site=site, count=len(cookies))


def has_cookies(site: str) -> bool:
    """Check if we have saved cookies for a site."""
    return os.path.exists(_cookie_path(site))


def clear_cookies(site: str) -> None:
    """Delete saved cookies for a site."""
    path = _cookie_path(site)
    if os.path.exists(path):
        os.remove(path)
        logger.info("cookies_cleared", site=site)


async def launch_auth_browser(site: str) -> bool:
    """
    Launch a VISIBLE Chrome browser pointed at the login page.
    The user signs in manually. Cookies are saved when they close the browser
    or navigate to the expected post-login page.

    Returns True if cookies were saved successfully.
    """
    if site not in SITE_URLS:
        logger.error("unknown_site", site=site)
        return False

    from playwright.async_api import async_playwright

    login_url = SITE_URLS[site]
    verify_fragment = SITE_VERIFY.get(site, "")

    logger.info("auth_browser_launch", site=site, url=login_url)

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ],
    )

    # Try to load existing cookies for a faster re-login
    context = await browser.new_context()
    existing = load_cookies(site)
    if existing:
        await context.add_cookies(existing)
        logger.info("existing_cookies_loaded", site=site, count=len(existing))

    page = await context.new_page()
    await page.goto(login_url, wait_until="networkidle")

    print(f"\n{'='*60}")
    print(f"  🔐 Sign in to {site.upper()}")
    print(f"  The browser window will stay open until you finish.")
    print(f"  Login page: {login_url}")
    if verify_fragment:
        print(f"  After login, navigate to: {verify_fragment}")
    print(f"{'='*60}\n")

    # Wait for the user to log in — we poll until the verify URL is reached
    # or until 5 minutes elapse
    timeout = 300  # seconds
    interval = 2
    elapsed = 0

    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            current_url = page.url
            if verify_fragment and verify_fragment in current_url:
                logger.info("login_detected", site=site, url=current_url)
                # Extra wait for cookies to be fully set
                await asyncio.sleep(2)
                break
            # Also break if the page was closed or navigated away
            if page.is_closed():
                logger.info("browser_closed_by_user", site=site)
                break
        except Exception:
            # Page might have been closed
            break

    # Save cookies
    cookies = await context.cookies()
    if cookies:
        save_cookies(site, cookies)
        print(f"\n✅ Cookies saved for {site.upper()} ({len(cookies)} cookies)")
    else:
        print(f"\n⚠️  No cookies captured for {site.upper()}")

    await browser.close()
    await playwright.stop()

    return len(cookies) > 0


# ── Synchronous wrapper for Streamlit ────────────────────────────────────

def launch_auth_browser_sync(site: str) -> bool:
    """Synchronous wrapper for launch_auth_browser (for Streamlit)."""
    return asyncio.run(launch_auth_browser(site))
