"""Facebook Lead Ads sync — behind `ENABLE_FACEBOOK_LEAD_SYNC`.

Ports `crm/lead_syncing/`. The six scheduled tasks were registered in phase 5 as flag-gated
no-ops; this fills them in.

## Idempotency is the whole risk, and it has two layers

`PHASE_7_INTEGRATIONS.md` §4: *"Lead sync is idempotent — re-running creates no
duplicates."* Upstream implements that twice over, and both layers are needed:

1. **`last_synced_at` narrows the fetch.** `fetch_leads` asks Facebook for leads created
   after the last sync. That is an optimisation, not a guarantee: it relies on Facebook's
   clock, on the write succeeding after the fetch, and on nothing being back-dated.
2. **`validate_duplicate_lead` is the guarantee.** Before inserting, it looks for an
   existing lead with the same mapped field values *and the same form id*. A hit raises
   `DuplicateLeadError`, which is caught and logged rather than raised — a duplicate is an
   expected outcome of a re-run, not a failure.

Losing layer 2 would not show up in normal operation, because layer 1 hides it. It shows up
the first time a sync is re-run after a partial failure, which is exactly when the operator
is least able to tell a real lead from a duplicate.

## `lead_owner` is set, and it has to be

`AS_BUILT.md` §4: a lead with no `lead_owner` is invisible to everyone but a manager, there
is deliberately no server-side default, and **"any caller creating a lead or deal is
responsible for setting the owner — that includes integrations, imports and scripts."**

A sync that omitted it would create leads nobody can see, silently. See
`sync.DEFAULT_LEAD_OWNER` for what it is set to and why that is a decision rather than an
obvious answer.
"""
