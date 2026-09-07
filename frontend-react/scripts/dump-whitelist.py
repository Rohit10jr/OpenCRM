"""Print every whitelisted dotted path, one per line.

Run with the backend's interpreter, from the repo root:

    ../frappe_django_crm/backend/.venv/Scripts/python.exe \
        frontend-react/scripts/dump-whitelist.py

Reads the backend, changes nothing. It exists because
``test_every_frontend_dotted_path_resolves`` in ``backend/tests/`` does this check for the
*Vue* client and is hardcoded to that path, and ``backend/`` is a fixed contract in this
worktree — so the React side needs its own way to ask the same question.
"""

from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3] / "frappe_django_crm_react" / "backend"
sys.path.insert(0, str(ROOT))
# `config.settings` is a package whose `__init__` configures nothing — `manage.py:9` points
# at `.local`, and pointing anywhere else leaves SECRET_KEY empty and fails on the first
# module that reads it.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

# Importing a module is what registers its endpoints, so every module has to be imported
# or its paths look missing.
#
# **Walked, not listed.** The first version named the modules by hand and swallowed
# ImportError, which reported the whole of WhatsApp and ERPNext as unserved — a checker
# that invents gaps is worse than no checker, because the gaps look like work. An import
# that fails now says so on stderr and is counted.
import importlib  # noqa: E402
import pkgutil  # noqa: E402
import warnings  # noqa: E402

# Only the two trees that carry endpoints. Walking all of `crm_app` fails on `models`,
# because `pkgutil` imports each package to find its children and that import happens
# outside any try/except this file can put around it.
#
# `frappe_core.api` is in the list because the list engine lives there: `crm.api.doc.get_data`
# is registered in `frappe_core/api/doc.py`, not in `crm_app`, and `crm_app/api/__init__.py:11`
# says so explicitly. Leaving it out reported the single most-used endpoint in the client as
# unserved.
ROOTS = ("crm_app.api", "crm_app.integrations", "frappe_core.api")

failed = []
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    for root in ROOTS:
        package = importlib.import_module(root)
        for module in pkgutil.walk_packages(package.__path__, prefix=f"{root}."):
            if ".migrations" in module.name:
                continue
            try:
                importlib.import_module(module.name)
            except Exception as exc:  # noqa: BLE001 - reported, not hidden
                failed.append(f"{module.name}: {exc}")

if failed:
    print("could not import:", file=sys.stderr)
    for line in failed:
        print(f"  {line}", file=sys.stderr)

from frappe_core.whitelist import all_methods  # noqa: E402

for path in sorted(all_methods()):
    print(path)
