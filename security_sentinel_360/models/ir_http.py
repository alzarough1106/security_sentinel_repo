from datetime import timedelta
import logging
from odoo import models, fields
from odoo.http import request, root, SessionExpiredException
from werkzeug.utils import redirect

_logger = logging.getLogger(__name__)

try:
    from .lib import ua_parser
except ImportError:
    ua_parser = None

IGNORED_PATHS = ("/longpolling", "/bus/", "/websocket")


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _dispatch(cls, *args, **kwargs):
        if request and any(request.httprequest.path.startswith(p) for p in IGNORED_PATHS):
            return super()._dispatch(*args, **kwargs)

        redirect_res = cls._enforce_killed_session()
        if redirect_res:
            return redirect_res

        cls._track_session()
        return super()._dispatch(*args, **kwargs)

    @classmethod
    def _enforce_killed_session(cls):
        """Checks session validity; redirects HTTP requests or raises SessionExpiredException for JSON."""
        if not (request and getattr(request, "session", None) and request.session.uid and request.session.sid):
            return None
        if not getattr(request, "db", None) or "res.users.session" not in request.env:
            return None

        db_name = request.session.db or getattr(request, "db", None)

        try:
            with request.env.cr.savepoint():
                SessionModel = request.env["res.users.session"].sudo()
                session_rec = SessionModel.search([
                    ("session_token", "=", request.session.sid),
                ], limit=1)

                if not session_rec:
                    return None

                is_killed = session_rec.state == "killed"
                is_idle = False

                if session_rec.state == "active":
                    param = request.env["ir.config_parameter"].sudo().get_param(
                        "security_sentinel_360.idle_timeout_minutes", "60"
                    )
                    try:
                        timeout_min = int(param)
                    except (ValueError, TypeError):
                        timeout_min = 60

                    limit = fields.Datetime.now() - timedelta(minutes=timeout_min)
                    if session_rec.last_activity and session_rec.last_activity < limit:
                        is_idle = True
                        session_rec.write({
                            "state": "killed",
                            "logout_date": fields.Datetime.now(),
                        })

                if is_killed or is_idle:
                    request.session.logout(keep_db=True)
                    if db_name:
                        request.session.db = db_name
                    root.session_store.save(request.session)

                    req_type = getattr(request, "_request_type", "http")
                    if req_type == "json":
                        raise SessionExpiredException("Session has been terminated or timed out.")

                    # Pass explicit database name in redirect URL to prevent _dispatch_nodb 404 errors
                    login_url = f"/web/login?db={db_name}" if db_name else "/web/login"
                    return redirect(login_url)

        except SessionExpiredException:
            raise
        except Exception as e:
            _logger.warning("Failed to enforce killed/idle session: %s", e)

        return None

    @classmethod
    def _parse_user_agent(cls, req):
        """Extracts browser, version, OS, and device type from HTTP request with fallbacks."""
        user_agent_str = req.httprequest.headers.get("User-Agent", "")
        browser, browser_version, os_name, device = "Unknown", "", "Unknown", "Desktop"

        if ua_parser and hasattr(ua_parser, "parse"):
            try:
                parsed = ua_parser.parse(user_agent_str)
                if isinstance(parsed, dict):
                    browser = parsed.get("browser") or browser
                    browser_version = parsed.get("browser_version") or parsed.get("version") or ""
                    os_name = parsed.get("os") or parsed.get("operating_system") or os_name
                    device = parsed.get("device") or parsed.get("device_type") or device
                elif hasattr(parsed, "browser"):
                    browser = getattr(parsed.browser, "family", str(parsed.browser))
                    browser_version = getattr(parsed.browser, "version_string", "")
                    os_name = getattr(parsed.os, "family", str(parsed.os))
                    if getattr(parsed, "is_mobile", False):
                        device = "Mobile"
                    elif getattr(parsed, "is_tablet", False):
                        device = "Tablet"
            except Exception as e:
                _logger.warning("Custom ua_parser parsing failed: %s", e)

        if browser == "Unknown" or os_name == "Unknown":
            try:
                ua = req.httprequest.user_agent
                if ua:
                    if browser == "Unknown" and getattr(ua, "browser", None):
                        browser = ua.browser.capitalize()
                        browser_version = getattr(ua, "version", "") or ""
                    if os_name == "Unknown" and getattr(ua, "platform", None):
                        os_map = {
                            "macos": "macOS",
                            "windows": "Windows",
                            "linux": "Linux",
                            "iphone": "iOS",
                            "ipad": "iPadOS",
                            "android": "Android",
                        }
                        os_name = os_map.get(ua.platform.lower(), ua.platform.capitalize())
                    if getattr(ua, "platform", "") in ("iphone", "ipad", "android"):
                        device = "Mobile" if ua.platform != "ipad" else "Tablet"
            except Exception as e:
                _logger.warning("Werkzeug user_agent fallback failed: %s", e)

        return browser, browser_version, os_name, device

    @classmethod
    def _track_session(cls):
        if not (request and request.session.uid and request.session.sid):
            return
        if getattr(request.session, "should_rotate", False):
            return

        if not getattr(request, "db", None) or "res.users.session" not in request.env or request.env.cr.closed:
            return

        try:
            with request.env.cr.savepoint():
                SessionModel = request.env["res.users.session"].sudo()
                existing = SessionModel.search([("session_token", "=", request.session.sid)], limit=1)
                if existing:
                    if existing.state == "active":
                        now = fields.Datetime.now()
                        threshold = now - timedelta(seconds=60)
                        request.env.cr.execute("""
                            UPDATE res_users_session
                            SET last_activity = %s
                            WHERE id = %s
                              AND (last_activity IS NULL OR last_activity < %s)
                        """, (now, existing.id, threshold))
                    return
                cls._create_session_record(request.session.uid)
        except Exception as e:
            _logger.warning("Session tracking error suppressed: %s", e)

    @classmethod
    def _create_session_record(cls, uid):
        if not getattr(request, "db", None) or "res.users.session" not in request.env:
            return

        browser, browser_version, os_name, device = cls._parse_user_agent(request)
        ip_address = request.httprequest.remote_addr or request.httprequest.headers.get("X-Forwarded-For", "").split(",")[0].strip()

        try:
            with request.env.cr.savepoint():
                SessionModel = request.env["res.users.session"].sudo()

                if browser != "Unknown" and os_name != "Unknown":
                    prior_session = SessionModel.search([
                        ("user_id", "=", uid),
                        ("browser", "=", browser),
                        ("operating_system", "=", os_name),
                    ], limit=1)
                    is_new = not bool(prior_session)
                else:
                    is_new = True

                new_session = SessionModel.create({
                    "user_id": uid,
                    "session_token": request.session.sid,
                    "ip_address": ip_address,
                    "browser": browser,
                    "browser_version": browser_version,
                    "operating_system": os_name,
                    "device_type": device,
                    "state": "active",
                    "is_new_device": is_new,
                })

                if is_new:
                    try:
                        new_session._notify_new_login()
                    except Exception as ne:
                        _logger.warning("Failed to send new login notification: %s", ne)

        except Exception as e:
            _logger.error("Failed to create session record: %s", e)