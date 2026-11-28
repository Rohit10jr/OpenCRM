"""The Contacts and Organizations list definitions (specs/CONTACTS.md §10 row 7;
CONFIGURATION §4.8).

Contact's is the old `default_list_data` verbatim (`backend/frappe_platform/models.py:
412-432`), which is upstream's (`crm/overrides/contact.py:7-49`).

CRM Organization's is the old one (`crm_app/models/core_sales.py:141-160`) with
`currency` in the rows, between `industry` and `annual_revenue`, as upstream has it
(`crm/fcrm/doctype/crm_organization/crm_organization.py:79-88`): the list formats the
revenue in the organization's own currency, which the old rows left out (PE-38). Two
differences from upstream stay, as decided (`specs/CONTACTS.md` §4, the old widths):
the Organization column is `11rem` where upstream's is `16rem`, and the Industry column
has no `options`.
"""

from configuration.list_views import ListView


class ContactListView(ListView):
    columns = (
        {"label": "Name", "type": "Data", "key": "full_name", "width": "17rem"},
        {"label": "Email", "type": "Data", "key": "email_id", "width": "12rem"},
        {"label": "Phone", "type": "Data", "key": "mobile_no", "width": "12rem"},
        {"label": "Organization", "type": "Data", "key": "company_name", "width": "12rem"},
        {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
    )
    rows = ("name", "full_name", "company_name", "email_id", "mobile_no", "modified", "image")


class OrganizationListView(ListView):
    columns = (
        {"label": "Organization", "type": "Data", "key": "organization_name", "width": "11rem"},
        {"label": "Website", "type": "Data", "key": "website", "width": "14rem"},
        {"label": "Industry", "type": "Link", "key": "industry", "width": "14rem"},
        {"label": "Annual Revenue", "type": "Currency", "key": "annual_revenue", "width": "14rem"},
        {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
    )
    rows = (
        "name",
        "organization_name",
        "organization_logo",
        "website",
        "industry",
        "currency",
        "annual_revenue",
        "modified",
    )
