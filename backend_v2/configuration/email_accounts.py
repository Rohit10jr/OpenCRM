"""`crm.api.settings.create_email_account` (specs/CONFIGURATION.md section 4.4).

Ported from `backend/crm_app/api/settings.py`. The one way the CRM creates an Email
Account with its service's settings: the checks run in the old order (the role check
first), and the account's credentials are checked against its server before the row
exists, so a rejected account leaves nothing behind.
"""

from __future__ import annotations

from accounts.user_roles import only_for
from configuration.models import EmailAccount
from core.exceptions import APIError, ValidationError
from core.mail import validate_email_account
from core.query import parse_json_param
from core.secrets import ensure_key

#: `crm/api/settings.py:56-99` verbatim: per-provider overrides on the common defaults.
EMAIL_SERVICE_CONFIG: dict[str, dict] = {
    "Frappe Mail": {
        "domain": "",
        "password": "",
        "awaiting_password": False,
        "ascii_encode_password": False,
        "login_id_is_different": False,
        "login_id": "",
        "use_imap": False,
        "use_ssl": False,
        "validate_ssl_certificate": False,
        "use_starttls": False,
        "email_server": "",
        "incoming_port": 0,
        "always_use_account_email_id_as_sender": True,
        "use_tls": False,
        "use_ssl_for_outgoing": False,
        "smtp_server": "",
        "smtp_port": None,
        "no_smtp_authentication": False,
    },
    "GMail": {"email_server": "imap.gmail.com", "use_ssl": True, "smtp_server": "smtp.gmail.com"},
    "Outlook": {
        "email_server": "imap-mail.outlook.com",
        "use_ssl": True,
        "smtp_server": "smtp-mail.outlook.com",
    },
    "Sendgrid": {"smtp_server": "smtp.sendgrid.net", "smtp_port": 587},
    "SparkPost": {"smtp_server": "smtp.sparkpostmail.com"},
    "Yahoo": {
        "email_server": "imap.mail.yahoo.com",
        "use_ssl": True,
        "smtp_server": "smtp.mail.yahoo.com",
        "smtp_port": 587,
    },
    "Yandex": {
        "email_server": "imap.yandex.com",
        "use_ssl": True,
        "smtp_server": "smtp.yandex.com",
        "smtp_port": 587,
    },
}

#: `crm/api/settings.py:22-29`: applied to every account before the per-service overrides.
COMMON_DEFAULTS = {
    "email_sync_option": "ALL",
    "initial_sync_count": 100,
    "create_contact": True,
    "track_email_status": True,
    "use_tls": True,
    "use_imap": True,
    "smtp_port": 587,
}


def create_email_account(data, *, user):
    """`crm/api/settings.py:5-53`, as the old backend serves it.

    1. System Manager or Administrator, else 403 "Not permitted" (PE-27);
    2. `data` an object, else 417 "Invalid data";
    3. an unknown service answers the string "Service not supported";
    4. "Email account name is required";
    5. with a credential to store, the encryption key must exist, before any connection;
    6. the credentials are checked against the server; anything the mail libraries raise
       is a 417 with its text, as upstream's `except Exception as e: frappe.throw(str(e))`;
    7. the insert; a duplicate name is a 409 here, after validation.
    """
    only_for(["System Manager"], user)

    payload = parse_json_param(data, {}) or {}
    if not isinstance(payload, dict):
        raise ValidationError("Invalid data")

    service = payload.get("service")
    service_config = EMAIL_SERVICE_CONFIG.get(service)
    if not service_config:
        return "Service not supported"

    fields = {
        "email_id": payload.get("email_id") or "",
        "email_account_name": payload.get("email_account_name") or "",
        "service": service,
        # bool(), as backend/: the string "0" is true.
        "enable_incoming": bool(payload.get("enable_incoming")),
        "enable_outgoing": bool(payload.get("enable_outgoing")),
        "default_incoming": bool(payload.get("default_incoming")),
        "default_outgoing": bool(payload.get("default_outgoing")),
        **COMMON_DEFAULTS,
        **service_config,
    }

    if service == "Frappe Mail":
        fields.update(
            {
                "api_key": payload.get("api_key") or "",
                "api_secret": payload.get("api_secret") or "",
                "frappe_mail_site": payload.get("frappe_mail_site") or "",
                "append_to": "CRM Lead",
            }
        )
    else:
        fields["password"] = payload.get("password") or ""
        fields["append_to"] = "CRM Lead"

    if not fields["email_account_name"]:
        raise ValidationError("Email account name is required")

    # A credential is about to be stored encrypted: with no key the save would fail after
    # a successful login, and the screen would call that "invalid credentials".
    if fields.get("password") or fields.get("api_secret"):
        ensure_key()

    account = EmailAccount(**fields)
    try:
        validate_email_account(account)
    except APIError:
        raise
    except Exception as exc:  # noqa: BLE001 - upstream catches everything at this point
        raise ValidationError(str(exc)) from None

    account.save(user=user)
    return account.name
