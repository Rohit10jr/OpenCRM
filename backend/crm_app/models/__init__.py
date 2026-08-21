"""CRM doctypes, split by PHASE_1_MODELS.md section 5 cluster.

Import order follows the dependency order between clusters: taxonomy is referenced by
core sales, the SLA models are referenced by both leads and deals, and the telephony
``SingletonMixin`` is reused by ``FCRM Settings``.

Phase 7 adds ``whatsapp`` (the one doctype ported from ``frappe_whatsapp``) and
``lead_syncing`` (the five Facebook doctypes). Still absent: ``crm_product_sync_issue`` and
``erpnext_crm_settings``.
"""

from crm_app.models.taxonomy import *  # noqa: F401,F403
from crm_app.models.sla import *  # noqa: F401,F403
from crm_app.models.core_sales import *  # noqa: F401,F403
from crm_app.models.telephony import *  # noqa: F401,F403
from crm_app.models.metadata import *  # noqa: F401,F403
from crm_app.models.whatsapp import *  # noqa: F401,F403
from crm_app.models.lead_syncing import *  # noqa: F401,F403
