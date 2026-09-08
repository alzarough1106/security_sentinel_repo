"""
Lightweight, dependency-free User-Agent parser.

This is NOT a full replacement for the `user-agents`/`ua-parser` PyPI
packages (which rely on a large, frequently-updated regex database). It
covers the browsers/operating systems/device types seen in the vast
majority of real-world business software usage, with zero external
dependencies -- so this module works out-of-the-box on Odoo.sh and
Odoo Online (SaaS), where arbitrary `pip install` is not available to
end customers.
"""
import re


class ParsedUserAgent:
    __slots__ = ("browser_family", "browser_version", "os_family", "is_mobile", "is_tablet")

    def __init__(self, browser_family="Other", browser_version="", os_family="Other",
                 is_mobile=False, is_tablet=False):
        self.browser_family = browser_family
        self.browser_version = browser_version
        self.os_family = os_family
        self.is_mobile = is_mobile
        self.is_tablet = is_tablet


_BROWSER_PATTERNS = [
    ("Edge", re.compile(r"Edg(?:A|iOS)?/([\d.]+)")),
    ("Opera", re.compile(r"OPR/([\d.]+)")),
    ("Opera", re.compile(r"Opera[/ ]([\d.]+)")),
    ("Samsung Internet", re.compile(r"SamsungBrowser/([\d.]+)")),
    ("Firefox", re.compile(r"FxiOS/([\d.]+)")),
    ("Firefox", re.compile(r"Firefox/([\d.]+)")),
    ("Chrome", re.compile(r"CriOS/([\d.]+)")),
    ("Chrome", re.compile(r"Chrome/([\d.]+)")),
    ("Internet Explorer", re.compile(r"MSIE ([\d.]+)")),
    ("Internet Explorer", re.compile(r"Trident/.*rv:([\d.]+)")),
    ("Safari", re.compile(r"Version/([\d.]+).*Safari")),
    ("Safari", re.compile(r"Safari/([\d.]+)")),
]

_OS_PATTERNS = [
    ("Windows", re.compile(r"Windows NT ([\d.]+)")),
    ("Chrome OS", re.compile(r"CrOS")),
    ("iOS", re.compile(r"iPhone OS ([\d_]+)")),
    ("iPadOS", re.compile(r"iPad.*OS ([\d_]+)")),
    ("Mac OS", re.compile(r"Mac OS X ([\d_.]+)")),
    ("Android", re.compile(r"Android ([\d.]+)")),
    ("Linux", re.compile(r"Linux")),
]

_WINDOWS_VERSION_MAP = {"10.0": "10 / 11", "6.3": "8.1", "6.2": "8", "6.1": "7"}


def _detect_browser(ua):
    for name, pattern in _BROWSER_PATTERNS:
        match = pattern.search(ua)
        if match:
            return name, match.group(1)
    return "Other", ""


def _detect_os(ua):
    for name, pattern in _OS_PATTERNS:
        match = pattern.search(ua)
        if match:
            version = match.groups()[0] if match.groups() else ""
            if name == "Windows":
                version = _WINDOWS_VERSION_MAP.get(version, version)
            return name, version.replace("_", ".")
    return "Other", ""


def _detect_device(ua, os_family):
    ua_lower = ua.lower()
    is_tablet = "ipad" in ua_lower or (os_family == "Android" and "mobile" not in ua_lower) or "tablet" in ua_lower
    is_mobile = (not is_tablet) and (
        "mobi" in ua_lower or "iphone" in ua_lower or ("android" in ua_lower and "mobile" in ua_lower)
    )
    return is_mobile, is_tablet


def parse(ua_string):
    """Parse a raw User-Agent header into a ParsedUserAgent.
    Never raises -- returns a best-effort/"Other" result on unknown input."""
    if not ua_string:
        return ParsedUserAgent()
    try:
        browser_family, browser_version = _detect_browser(ua_string)
        os_family, os_version = _detect_os(ua_string)
        is_mobile, is_tablet = _detect_device(ua_string, os_family)
        full_os = f"{os_family} {os_version}".strip() if os_version else os_family
        return ParsedUserAgent(
            browser_family=browser_family, browser_version=browser_version,
            os_family=full_os, is_mobile=is_mobile, is_tablet=is_tablet,
        )
    except Exception:
        return ParsedUserAgent()