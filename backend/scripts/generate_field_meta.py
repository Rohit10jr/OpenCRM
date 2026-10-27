"""Generate `crm_app/data/doctype_meta.json` from the Frappe CRM DocType JSON.

Phase 4. The models deliberately dropped the layout fieldtypes and collapsed several
Frappe fieldtypes onto the same Django one (C7), but the metadata layer needs both back:

* **C7** - the filterable and group-by allowlists are defined in terms of Frappe
  fieldtypes (`Long Text`, `Duration`, `Rating`, ...), which cannot be recovered from
  `CharField` / `IntegerField`.
* **Layouts** - `get_default_layout` walks the fields *in declaration order* and starts a
  new tab/section/column at each `Tab Break` / `Section Break` / `Column Break`. That
  ordering is the layout.

Generated rather than read at runtime because the CRM source tree is a *development*
dependency: a deployed backend has no `crm/fcrm/doctype/` to read. The output is
committed, and `test_generated_field_meta_is_current` regenerates and compares, so it
cannot drift from the source silently.

Run:  python scripts/generate_field_meta.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

# Upstream Frappe CRM's package: CRM_UPSTREAM_DIR when set (CI checks frappe/crm out
# and sets it, .github/workflows/backend.yml), else the owner's local checkout.
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
OUTPUT = pathlib.Path(__file__).resolve().parent.parent / "crm_app" / "data" / "doctype_meta.json"

#: Kept verbatim per field - everything the metadata layer, a layout, or a form control
#: needs. The second block was added when ``frappe.desk.form.load.getdoctype`` was
#: ported: upstream sends the whole DocField row to the browser, and the shipped frontend
#: reads a good deal more of it than the metadata layer alone ever did -
#: ``FieldLayout/Field.vue`` and ``SidePanelLayout.vue`` between them use ``depends_on``,
#: ``mandatory_depends_on``, ``read_only_depends_on``, ``description`` and ``fetch_from``.
#: The rest of the block is the remainder of the DocField properties that say something
#: about a *value* (its length, sign, uniqueness, copy and print behaviour); they cost a
#: few kilobytes in the generated file and mean a later reader never has to regenerate.
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
#: always emitted below. A Frappe ``Meta`` carries every DocType property; these are the
#: ones something in this port or in the frontend reaches for - ``editable_grid`` and
#: ``grid_page_length`` drive ``Controls/Grid.vue``, ``translated_doctype`` drives
#: ``stores/meta.js:isTranslatable``, ``sort_field``/``sort_order`` are the list default,
#: and the rest describe the document's own rules.
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
        # Same rule as the fields: an empty or zero property is "not declared", and the
        # reader supplies the default. Keeps the file to what the DocType actually says.
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
