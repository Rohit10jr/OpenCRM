"""The default rows' shared constants (specs/CONFIGURATION.md §10.3).

The rows themselves are written by `configuration/0012_default_rows`; the restore writers
that put back a missing one come with `restore_defaults` (§10.8 step 3). Moved here from
the retired `configuration/dev_data.py`.
"""

from __future__ import annotations

import functools
import json
import pathlib

DATA_FILE = pathlib.Path(__file__).resolve().parent / "data" / "default_rows.json"

PRODUCT_SCRIPT_DOCTYPES = ("CRM Lead", "CRM Deal")
FORECASTING_SCRIPT_NAME = "Forecasting Script"


@functools.cache
def default_rows() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def product_details_script(doctype: str) -> str:
    """`crm_products.py:112-193`: the class is named after the doctype, spaces removed."""
    return "class " + doctype.replace(" ", "") + " {" + default_rows()["product_details_script_body"]


def product_script_name(doctype: str) -> str:
    return "Product Details Script for " + doctype
