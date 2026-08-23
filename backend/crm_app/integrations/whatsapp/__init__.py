"""WhatsApp — behind `ENABLE_WHATSAPP`.

Ports `crm/api/whatsapp.py`'s six endpoints and its message model. **`frappe_whatsapp` is
not vendored** — that is a decision the human already made and the runbook says not to
reopen.

## What that means in practice

Upstream's endpoints are a thin layer over another Frappe app: they create
`WhatsApp Message` rows and that app's own hooks talk to Meta's Cloud API. So the split
here is:

* **Ported** — the six endpoints, the access rules, the message model, the realtime event,
  and the agent notification. All of it is CRM behaviour and all of it is in this repo's
  source.
* **Stubbed at a named seam** — `provider.send_message`, which is where `frappe_whatsapp`
  would hand the message to Meta. It refuses when the flag is on and no provider is
  configured, in the same shape as phase 5's `_reconcile_products`.

A message therefore reaches the database, the timeline, the realtime feed and the assigned
agent's notifications exactly as upstream, and stops at the point where it would leave the
building. That is the largest honest subset, and the boundary is one function.

## `WhatsApp Templates` is not ported

`get_whatsapp_messages` enriches template messages with the rendered template body
(`whatsapp.py:186-215`). Templates live in `frappe_whatsapp`, so there is nothing to render
from: the columns are kept, the enrichment is skipped, and `template_name` is absent from
the response for template messages. Recorded in the progress file rather than faked.
"""
