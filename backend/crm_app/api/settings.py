"""``crm.api.settings.create_email_account``. Ported from ``crm/api/settings.py``."""

from __future__ import annotations

from frappe_core.exceptions import throw
from frappe_core.mail import validate_email_account
from frappe_core.query import parse_json_param
from frappe_core.whitelist import whitelist

#: ``crm/api/settings.py:56-99`` verbatim. Per-provider overrides layered on the common
#: defaults below.
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

#: ``crm/api/settings.py:22-29`` - applied to every account before the per-service
#: overrides.
COMMON_DEFAULTS = {
    "email_sync_option": "ALL",
    "initial_sync_count": 100,
    "create_contact": True,
    "track_email_status": True,
    "use_tls": True,
    "use_imap": True,
    "smtp_port": 587,
}


@whitelist("crm.api.settings.create_email_account")
def create_email_account(data: str | dict):
    """``crm/api/settings.py:5-53``.

    **Credentials are checked before saving**, as upstream does
    (``email_account.py:156-168``): a live SMTP session for outgoing, a live IMAP login
    for incoming. See :mod:`frappe_core.mail`.

    Phase 3 skipped this on the grounds that the port had no mail layer. It has one -
    Django's SMTP backend - and the gap mattered: a mistyped password saved cleanly and
    the first anyone knew was that invitations never arrived. ``EmailAdd.vue:149``
    already holds the error message for the loud version.

    One upstream behaviour is still **not** reproduced: the ``imap_folder`` child row.
    ``Email Account`` has no child tables in this port.

    The early return string ``"Service not supported"`` is upstream's, and the frontend
    displays it as-is.
    """
    from crm_app.api.user import only_for
    from frappe_platform.models import EmailAccount

    # Upstream has no explicit guard here - it leans on the Email Account doctype's own
    # role permissions, which this port does not model. Without a check, *any*
    # authenticated user could create a credential-bearing mail account and set it as
    # the default outgoing one, i.e. redirect the system's mail. Restricted to the roles
    # that administer settings. Logged as a deliberate divergence.
    only_for(["System Manager", "Sales Manager"])

    payload = parse_json_param(data, {}) or {}
    if not isinstance(payload, dict):
        throw("Invalid data")

    service = payload.get("service")
    service_config = EMAIL_SERVICE_CONFIG.get(service)
    if not service_config:
        # Upstream returns this string rather than raising (crm/api/settings.py:9-10).
        return "Service not supported"

    fields = {
        "email_id": payload.get("email_id") or "",
        "email_account_name": payload.get("email_account_name") or "",
        "service": service,
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
        throw("Email account name is required")

    # Validate before the row exists, so a rejected account leaves nothing behind.
    # Upstream checks inside validate(), which is the same point in its lifecycle.
    validate_email_account(EmailAccount(**fields))

    account = EmailAccount._default_manager.create(**fields)
    return account.name
