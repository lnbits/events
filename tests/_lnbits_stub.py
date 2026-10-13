"""Minimal stubs for lnbits modules so the extension imports standalone.

LNbits is not a dependency of these tests; registering these fake modules lets
``events.models`` and ``events.services`` import without a real LNbits install.
"""
import base64
import secrets
import sys
import types

lnbits = types.ModuleType("lnbits")
lnbits_core = types.ModuleType("lnbits.core")
lnbits_core_models = types.ModuleType("lnbits.core.models")
lnbits_core_users = types.ModuleType("lnbits.core.models.users")
lnbits_core_svc = types.ModuleType("lnbits.core.services")
lnbits_core_notif = types.ModuleType("lnbits.core.services.notifications")
lnbits_helpers = types.ModuleType("lnbits.helpers")
lnbits_settings = types.ModuleType("lnbits.settings")
lnbits_db = types.ModuleType("lnbits.db")

sys.modules["lnbits"] = lnbits
sys.modules["lnbits.core"] = lnbits_core
sys.modules["lnbits.core.models"] = lnbits_core_models
sys.modules["lnbits.core.models.users"] = lnbits_core_users
sys.modules["lnbits.core.services"] = lnbits_core_svc
sys.modules["lnbits.core.services.notifications"] = lnbits_core_notif
sys.modules["lnbits.helpers"] = lnbits_helpers
sys.modules["lnbits.settings"] = lnbits_settings
sys.modules["lnbits.db"] = lnbits_db


class UserNotifications:
    def __init__(self, *a, **k):
        pass


lnbits_core_users.UserNotifications = UserNotifications


async def send_user_notification(*a, **k):
    return None


lnbits_core_notif.send_user_notification = send_user_notification


def is_valid_email_address(v):
    return isinstance(v, str) and "@" in v


def urlsafe_short_hash():
    return base64.urlsafe_b64encode(secrets.token_bytes(6)).decode().rstrip("=")


lnbits_helpers.is_valid_email_address = is_valid_email_address
lnbits_helpers.urlsafe_short_hash = urlsafe_short_hash


class _Settings:
    host = "127.0.0.1"
    port = 5000


lnbits_settings.settings = _Settings()


class FilterModel:
    pass


lnbits_db.FilterModel = FilterModel
