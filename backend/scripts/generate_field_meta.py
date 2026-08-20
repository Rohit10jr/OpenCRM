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
import pathlib
import sys

CRM_DOCTYPE_DIR = pathlib.Path(
    r"D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm\fcrm\doctype"
)
OUTPUT = pathlib.Path(__file__).resolve().parent.parent / "crm_app" / "data" / "doctype_meta.json"

#: Kept verbatim per field - everything the metadata layer or a layout needs.
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

        meta[doctype] = {
            "istable": doc.get("istable", 0),
            "issingle": doc.get("issingle", 0),
            "autoname": doc.get("autoname"),
            "title_field": doc.get("title_field"),
            "fields": fields,
        }
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
