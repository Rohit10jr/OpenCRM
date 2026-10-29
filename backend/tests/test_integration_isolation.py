"""With every integration flag off, no provider SDK may be imported.

`PHASE_7_INTEGRATIONS.md` §4, first criterion: *"All flags off → full test suite passes, no
integration code imported."* The runbook is blunt about it — *"Assert that, do not assume
it"* — because this is the criterion easiest to fail by accident. One `import twilio` at
module scope in a file `apps.py` reaches, and the flag stops meaning anything: the SDK is a
hard dependency of starting the process, and a deployment that never enables Twilio still
cannot boot without it installed.

The failure is invisible in a normal test run, because the developer machine has every SDK
installed. It shows up as an ImportError in production, on the deployment that opted out.

## What is deliberately *not* isolated

`crm_app.integrations.api`, `.phone` and `.call_log` are imported unconditionally by
`apps.py`, and that is correct:

* `is_call_integration_enabled` is called on every page load and must answer "no" with both
  flags off;
* the manual "Log a call" flow writes `CRM Call Log` with every integration disabled.

None of them imports a provider SDK. That is the line this file holds — not "no integration
module is imported" but "no *provider* is".
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parent.parent

#: Distribution names of provider SDKs. A module here appearing in `sys.modules` after a
#: flags-off boot means something imported it at module scope.
PROVIDER_MODULES = ("twilio", "exotel", "facebook", "facebook_business")

#: The five flags, all off by default (`config/settings/base.py`).
FLAGS = (
    "ENABLE_ERPNEXT",
    "ENABLE_TWILIO",
    "ENABLE_EXOTEL",
    "ENABLE_FACEBOOK_LEAD_SYNC",
    "ENABLE_WHATSAPP",
)


def test_every_integration_flag_is_off_by_default():
    """The default deployment runs no integration. If one of these flips to `default=True`,
    every other test in this file starts proving something weaker than it claims."""
    from django.conf import settings

    for flag in FLAGS:
        assert getattr(settings, flag) is False, f"{flag} is on by default"


def test_each_flag_is_independent():
    """§4: *"Each integration enables independently."* They must not share a switch."""
    import config.settings.base as base_settings

    source = Path(base_settings.__file__).read_text(encoding="utf-8")
    for flag in FLAGS:
        assert f'env.bool("{flag}"' in source, f"{flag} is not read from its own env var"


def test_no_provider_sdk_is_imported_with_the_flags_off():
    """A subprocess, not this one.

    This test session has already imported whatever the other tests needed, so checking
    `sys.modules` here would prove nothing. A fresh interpreter that sets up Django exactly
    as the server does is the only honest way to ask the question.

    **Two guards, both mutation-checked.** Adding `import twilio` to
    `crm_app/integrations/api.py` fails the `returncode == 0` assertion, because the SDK is
    not installed here — which is exactly the production symptom: a deployment that opted
    out of Twilio can no longer boot. And the `sys.modules` probe was confirmed to actually
    detect a present module (asked for `django` alongside the providers, it reported
    `django`), so a green result means "absent", not "the check does not work".
    """
    script = (
        "import django, os, sys; "
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test'); "
        "django.setup(); "
        f"leaked = [m for m in {PROVIDER_MODULES!r} if m in sys.modules]; "
        "print('LEAKED:' + ','.join(leaked))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    line = [s for s in result.stdout.splitlines() if s.startswith("LEAKED:")]
    assert line, f"probe did not report; stdout={result.stdout[-500:]}"
    leaked = [m for m in line[0].removeprefix("LEAKED:").split(",") if m]
    assert leaked == [], (
        f"{leaked} imported at module scope with every integration flag off. "
        "A flag that is off must not cost an import — move it inside the function that "
        "needs it, behind the flag check."
    )


def test_the_shared_telephony_path_works_with_every_flag_off(db):
    """The other half of the criterion: "off" must not mean "broken".

    `CRM Call Log` is written by the manual flow regardless of any provider.
    """
    from crm_app.integrations import call_log

    log, created = call_log.record_call(
        call_id="CA-isolation",
        medium=call_log.MEDIUM_MANUAL,
        call_type="Outgoing",
        status="Completed",
    )
    assert created is True
    assert log.telephony_medium == "Manual"


def test_the_call_integration_endpoint_answers_no_rather_than_failing(db):
    """The frontend calls this on load. With both flags off it must return a shape, not
    raise — otherwise every page load errors on a deployment with no telephony."""
    from crm_app.integrations.api import is_call_integration_enabled

    result = is_call_integration_enabled()
    assert result["integrations"] == {"twilio": False, "exotel": False}
    assert result["default_calling_medium"] is None


def test_a_settings_row_alone_does_not_enable_a_provider(db, settings):
    """The deployment flag is the **outer** gate.

    Upstream has only the settings checkbox, because it has no deployment flag. Ours is an
    `and`: turning `enabled` on in the database must not activate an integration the
    operator has not enabled for this deployment. Otherwise the flag is advisory, and
    anyone who can write the settings row can switch on outbound calling.
    """
    from crm_app.integrations.api import is_call_integration_enabled
    from crm_app.models import CRMTwilioSettings

    row = CRMTwilioSettings.load()
    row.enabled = True
    row.save()

    settings.ENABLE_TWILIO = False
    assert is_call_integration_enabled()["integrations"]["twilio"] is False

    settings.ENABLE_TWILIO = True
    assert is_call_integration_enabled()["integrations"]["twilio"] is True
