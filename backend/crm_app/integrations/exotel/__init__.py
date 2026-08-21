"""Exotel — voice, behind `ENABLE_EXOTEL`.

Ports `crm/integrations/exotel/handler.py`. The settings doctype, its encrypted
`api_token` and its manager-only rule already existed (phase 1 + the phase-4 security
review); this adds the provider adapter.

**Nothing here is imported at module scope by `apps.py`.** The endpoints register through
`crm_app.integrations.exotel.handler`, which `apps.py` imports only when `ENABLE_EXOTEL`
is on — so a deployment with Exotel off never loads this package, and
`tests/test_integration_isolation.py` holds that line.

## Exotel has no request signatures

That is the fact that shapes the whole webhook design. `PHASE_7_INTEGRATIONS.md` §3 says
"verify signatures", and there is nothing to verify: upstream's own comment says
*"workaround security since exotel does not support request signature"*. The substitute is
a shared secret in the query string, which is weaker in two specific ways — it appears in
access logs and in `Referer` headers — and is the best available.

So the token is treated as the credential it is: `RESTRICTED_FIELDS` (already, and
stricter than upstream's plain `Data`), compared in constant time, and required to be
non-empty before any request is accepted.
"""
