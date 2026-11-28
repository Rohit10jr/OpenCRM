"""The test resources' list definitions (CONFIGURATION section 4.8)."""

from configuration.list_views import ListView


class WidgetListView(ListView):
    """Every hook set, so the list engine's tests see each one used."""

    columns = (
        {"label": "Widget Name", "type": "Data", "key": "widget_name", "width": "12rem"},
        {"label": "Status", "type": "Select", "key": "status", "width": "8rem"},
        {"label": "Notes", "type": "Text", "key": "notes", "width": "10rem"},
        {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
    )
    rows = ("name", "widget_name", "status", "notes", "modified")
    kanban_settings = {"title_field": "widget_name", "kanban_fields": '["status"]'}
    #: A hidden field drops its column, as CRM Lead's `converted` does.
    hidden_fields = ("notes",)

    @classmethod
    def parse(cls, data):
        for row in data:
            row["parsed"] = True
        return data
