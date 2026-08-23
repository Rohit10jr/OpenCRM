"""Phase 7 — external-service glue.

One subpackage per upstream source module, mirroring `crm/integrations/`. Every
integration sits behind its own flag in `config/settings/base.py`, all off by default.

**Nothing here may be imported at module scope by non-integration code**, and no module
here may import a provider SDK at module scope. `PHASE_7_INTEGRATIONS.md` §3: *"The CRM
must be fully functional with all five disabled — no import-time coupling."* A flag that
is off must not cost an import, and `tests/test_integration_isolation.py` asserts it
rather than trusting it.

The provider-neutral parts — phone-number resolution and the call-log write path — live
in `phone.py` and `call_log.py` and are **not** flag-gated: they are shared by Twilio and
Exotel, and by the manual "Log a call" flow that exists with every integration off.
"""
