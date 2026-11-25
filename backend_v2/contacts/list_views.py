"""The Contacts and Organizations list definitions (specs/CONTACTS.md §10 row 7;
CONFIGURATION §4.8). The old `default_list_data`, verbatim, widths and all:
Contact's from `backend/frappe_platform/models.py:412-432` (upstream
`crm/overrides/contact.py`), CRM Organization's from `crm_app/models/core_sales.py:141-160`.
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
        "annual_revenue",
        "modified",
    )
