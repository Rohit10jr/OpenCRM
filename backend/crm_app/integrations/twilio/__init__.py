"""Twilio — voice, behind `ENABLE_TWILIO`.

Ports `crm/integrations/twilio/`. The settings doctype, its encrypted `api_secret` and
`auth_token`, and its manager-only rule already existed.

## No Twilio SDK

Upstream imports `twilio.rest.Client`, `twilio.jwt.access_token` and
`twilio.twiml.voice_response` at module scope. This port uses none of them, for three
reasons that all point the same way:

1. **`PHASE_7_INTEGRATIONS.md` §4 forbids import-time coupling.** A module-scope SDK import
   makes the package a hard dependency of *booting*, on a deployment that has Twilio
   switched off.
2. **Everything needed is a documented public format**, not a Frappe or Twilio internal:
   request signatures are HMAC-SHA1 over a canonical string, TwiML is XML with a fixed
   shape, and an access token is a JWT with documented claims. Writing them is
   transcription, not invention — which is the line `CLAUDE.md` draws.
3. It keeps the provider surface visible. The SDK hides which HTTP calls are made and what
   they carry; here every outbound request goes through
   `crm_app.integrations.http.request` and therefore has a timeout and a retry policy.

The cost is stated plainly in the progress file: an SDK upgrade would track Twilio's API
changes for us and this does not.

## The webhook signature — the one place this port is much stricter

**Upstream does not verify Twilio's signature at all.** `validate_twilio_request` compares
the `AccountSid` in the payload against the configured one — and an Account SID is *not a
secret*. It is in every webhook Twilio sends, in the Twilio console, and in any log that
recorded a request. So upstream's webhook authentication is "know a value that everyone who
has seen one request already knows".

Twilio signs every request with `X-Twilio-Signature`, and `PHASE_7_INTEGRATIONS.md` §3 says
to verify signatures and not to skip it because it is inconvenient. So this verifies it.
`UPSTREAM_BUGS` #27.
"""
