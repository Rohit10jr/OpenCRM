"""Generate `configuration/data/doctype_meta.json` from the Frappe CRM DocType JSON.

Ported from `backend/scripts/generate_field_meta.py` (specs/CONFIGURATION.md 4.5). The
models dropped the layout fieldtypes and collapsed several Frappe fieldtypes onto one
Django type, but the metadata layer needs both back: the filterable and group-by
allowlists are defined in Frappe fieldtypes (`Long Text`, `Duration`, `Rating`, ...),
and a default layout is the field order with its `Tab Break` / `Section Break` /
`Column Break` rows.

Generated rather than read at run time because the CRM source tree is a development
dependency: a deployed backend has none. The output is committed, and
`tests/test_field_meta.py` regenerates and compares, so it cannot drift silently.

Run:  python scripts/generate_field_meta.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

# Upstream Frappe CRM's package: CRM_UPSTREAM_DIR when set (CI checks frappe/crm out and
# sets it, .github/workflows/backend_v2.yml), else the owner's local checkout.
CRM_DOCTYPE_DIR = (
    pathlib.Path(
        os.environ.get(
            "CRM_UPSTREAM_DIR",
            r"D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm",
        )
    )
    / "fcrm"
    / "doctype"
)
OUTPUT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "configuration"
    / "data"
    / "doctype_meta.json"
)

#: Kept verbatim per field: everything the metadata layer, a layout or a form control
#: needs, then the DocField properties `getdoctype` sends to the browser.
FIELD_KEYS = (
    "fieldname",
    "fieldtype",
    "label",
    "options",
    "reqd",
    "hidden",
    "read_only",
    "permlevel",
    "default",
    "in_standard_filter",
    "in_list_view",
    "precision",
    # -- form behaviour and value properties, for getdoctype ------------------------
    "depends_on",
    "mandatory_depends_on",
    "read_only_depends_on",
    "description",
    "length",
    "non_negative",
    "fetch_from",
    "fetch_if_empty",
    "unique",
    "set_only_once",
    "no_copy",
    "ignore_user_permissions",
    "in_preview",
    "in_global_search",
    "bold",
    "translatable",
    "allow_in_quick_entry",
    "columns",
    "print_hide",
    "report_hide",
    "search_index",
)

#: Doctype-level properties kept when the JSON declares them, beyond the four that are
#: always emitted below.
DOCTYPE_KEYS = (
    "editable_grid",
    "translated_doctype",
    "sort_field",
    "sort_order",
    "naming_rule",
    "allow_rename",
    "track_changes",
    "quick_entry",
    "grid_page_length",
    "max_attachments",
)


def build() -> dict:
    if not CRM_DOCTYPE_DIR.exists():
        raise SystemExit(f"CRM source not found at {CRM_DOCTYPE_DIR}")

    meta: dict[str, dict] = {}
    for directory in sorted(CRM_DOCTYPE_DIR.iterdir()):
        json_path = directory / f"{directory.name}.json"
        if not json_path.exists():
            continue
        doc = json.loads(json_path.read_text(encoding="utf-8"))
        doctype = doc.get("name")
        if not doctype:
            continue

        fields = []
        for field in doc.get("fields", []):
            entry = {k: field.get(k) for k in FIELD_KEYS if field.get(k) not in (None, "", 0)}
            entry["fieldname"] = field.get("fieldname")
            entry["fieldtype"] = field.get("fieldtype")
            fields.append(entry)

        entry = {
            "istable": doc.get("istable", 0),
            "issingle": doc.get("issingle", 0),
            "autoname": doc.get("autoname"),
            "title_field": doc.get("title_field"),
        }
        # An empty or zero property is "not declared"; the reader supplies the default.
        entry.update(
            {k: doc.get(k) for k in DOCTYPE_KEYS if doc.get(k) not in (None, "", 0)}
        )
        entry["fields"] = fields
        meta[doctype] = entry
    return meta


def main() -> int:
    meta = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    total = sum(len(d["fields"]) for d in meta.values())
    print(f"wrote {OUTPUT} - {len(meta)} doctypes, {total} fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())
