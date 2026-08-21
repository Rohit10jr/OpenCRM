"""Exotel — voice, behind `ENABLE_EXOTEL`.

Ports `crm/integrations/exotel/handler.py`. The settings doctype, its encrypted
`api_token` and its manager-only rule already existed (phase 1 + the phase-4 security
review); this adds the provider adapter.

**`apps.py` imports this package unconditionally, and that is deliberate.** An earlier
version of this paragraph said the opposite — that the import was flag-gated — and it was
never true; the phase-7 review caught the contradiction between the sentence and the code.

The endpoints are registered always, the way upstream registers `make_a_call` always and
refuses inside it with *"Please setup Exotel intergration"*. Gating **registration** on the
flag would turn that dialog into a 404 and break the frontend contract, and
`is_call_integration_enabled` has to answer on every page load regardless.

What must not happen at import time is loading a **provider SDK**, and nothing here does —
every `requests` import is inside the function that makes the call.
`tests/test_integration_isolation.py` holds that line, and its docstring is explicit that
the rule is "no *provider* is imported", not "no integration module is".

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
