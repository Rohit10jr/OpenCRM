"""Reject direct manager reads in views and services unless explicitly justified."""

import ast
from pathlib import Path

from django.apps import apps


BASE_DIR = Path(__file__).resolve().parents[2]

# A direct manager read is correct only where the row-rule queryset is deliberately not
# the operation being performed. Keys are (relative file, qualified function, access).
DIRECT_MANAGER_READS = {
    ("accounts/services.py", "login", "get_user_model()._default_manager"): (
        "Authentication must locate the account before a request user exists; lockout "
        "and password verification protect this lookup."
    ),
    ("accounts/services.py", "refresh_token", "get_user_model()._default_manager"): (
        "Refresh validates the token subject and revocation counter, not a resource row."
    ),
    ("core/views.py", "DocumentViewSet.get_queryset", "self.document_model.objects"): (
        "This is the one list entry point and applies list_rule immediately afterward."
    ),
    (
        "core/views.py",
        "SingletonViewSet._singleton",
        "self.document_model._default_manager",
    ): (
        "Singleton lookup deliberately starts unnarrowed and then applies its object rule."
    ),
    (
        "core/views.py",
        "SingletonViewSet.value",
        "self.document_model._default_manager",
    ): (
        "The scalar singleton lookup applies the read object rule before returning a value."
    ),
}


class _ManagerReadVisitor(ast.NodeVisitor):
    def __init__(self, relative_path):
        self.relative_path = relative_path
        self.scope = []
        self.found = set()

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Attribute(self, node):
        if node.attr in {"objects", "_default_manager"}:
            self.found.add(
                (self.relative_path, ".".join(self.scope), ast.unparse(node))
            )
        self.generic_visit(node)


def _source_files():
    files = set()
    for config in apps.get_app_configs():
        root = Path(config.path)
        if root.parent == BASE_DIR:
            for name in ("views.py", "viewsets.py", "services.py"):
                files.update(root.rglob(name))
    return sorted(files)


def _manager_reads():
    found = set()
    for path in _source_files():
        relative = path.relative_to(BASE_DIR).as_posix()
        visitor = _ManagerReadVisitor(relative)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        found.update(visitor.found)
    return found


def test_views_and_services_have_no_unreviewed_direct_manager_reads():
    actual = _manager_reads()
    unexpected = sorted(actual - set(DIRECT_MANAGER_READS))
    stale = sorted(set(DIRECT_MANAGER_READS) - actual)
    assert not unexpected, (
        "Direct manager reads bypass the resource queryset; use the ViewSet queryset or "
        f"record a narrow reviewed exception: {unexpected}"
    )
    assert not stale, f"Stale direct-manager allowlist entries: {stale}"


def test_each_direct_manager_read_has_a_real_reason():
    assert all(len(reason.strip()) > 40 for reason in DIRECT_MANAGER_READS.values())
