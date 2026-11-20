"""Reject direct manager access along request-reachable domain and core paths."""

import ast
from pathlib import Path
from tempfile import TemporaryDirectory

from django.apps import apps


BASE_DIR = Path(__file__).resolve().parents[2]

# A direct manager read is correct only where the row-rule queryset is deliberately not
# the operation being performed. Keys are (relative file, qualified function, access).
DIRECT_MANAGER_READS = {
    (
        "accounts/authentication.py",
        "bump_token_version",
        "type(user)._default_manager",
    ): (
        "Token revocation is a write-only conditional update of the authenticated "
        "caller's own row, not a read of resource rows."
    ),
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
    ("core/tasks.py", "clear_old_versions", "Version.objects"): (
        "Retention housekeeping is a scheduled job without a request user and deletes "
        "only expired saved-view history."
    ),
    (
        "core/mixins/bulk_delete.py",
        "authorize_bulk_delete",
        "model._default_manager",
    ): (
        "Bulk delete loads all existing rows and list-visible names in two batched "
        "queries before applying the resource's object-delete rule."
    ),
    (
        "core/mixins/bulk_delete.py",
        "perform_bulk_delete",
        "model._default_manager",
    ): (
        "Bulk delete rechecks remaining links, then removes the already-authorized "
        "target names with one queryset delete inside the shared transaction."
    ),
    ("core/mixins/linked.py", "linked_documents", "model._default_manager"): (
        "The batched link scan starts at each source manager, then immediately applies "
        "that source model's independently callable list rule."
    ),
    ("core/mixins/linked.py", "linked_documents", "parent_model._default_manager"): (
        "Polymorphic child rows require a batched parent lookup before the actual "
        "parent's object-read rule can be applied."
    ),
    (
        "core/mixins/linked.py",
        "LinkedDocumentsMixin.linked_documents",
        "model._default_manager",
    ): (
        "Unlink intentionally loads each named item directly so a write-object-rule "
        "refusal can be skipped silently instead of becoming list invisibility."
    ),
    ("core/mixins/linked.py", "_clear_reference", "type(instance)._default_manager"): (
        "Unlink clears reference pairs with a plain update to avoid modified stamps "
        "and Version rows, matching the old endpoint."
    ),
    ("core/mixins/linked.py", "_clear_link_fields", "type(instance)._default_manager"): (
        "Unlink clears direct foreign keys with a plain update to avoid modified stamps "
        "and Version rows, matching the old endpoint."
    ),
    ("core/mixins/linked.py", "_clear_contact", "type(instance)._default_manager"): (
        "The contact-specific unlink path clears its direct field with a plain update, "
        "matching the old endpoint's unstamped write."
    ),
    ("core/mixins/rename.py", "RenameMixin.rename", "self.document_model._default_manager"): (
        "Rename must distinguish a missing row from one excluded by its list rule, then "
        "apply the resource's object-write rule to the directly loaded document."
    ),
    ("core/rename.py", "_repoint_foreign_keys", "relation.related_model._default_manager"): (
        "Rename performs schema-wide write-only foreign-key updates after the target "
        "resource has already authorized the operation."
    ),
    ("core/rename.py", "_repoint_child_parents", "spec['model']._default_manager"): (
        "Rename performs write-only updates of declared polymorphic child parents so "
        "the original row's cleanup hook cannot delete them."
    ),
    ("core/rename.py", "_repoint_dynamic_links", "other_model._default_manager"): (
        "Rename performs write-only updates of every declared doctype/name pair; these "
        "are references being preserved, not resource rows being disclosed."
    ),
    ("core/rename.py", "_repoint_text_links", "other_model._default_manager"): (
        "Rename (PE-5) performs write-only updates of every declared plain-text Link "
        "column holding the old name; references being preserved, nothing disclosed."
    ),
    ("core/rename.py", "rename_document", "model._default_manager"): (
        "The authorized rename locks and copies the original through its manager, then "
        "deletes the old key and restores parked unique values in one transaction."
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
    excluded_directories = {"migrations", "models", "tests", "management"}
    excluded_names = {"models.py", "admin.py", "apps.py", "dev_data.py"}

    def is_excluded(path, root):
        relative = path.relative_to(root)
        return path.name in excluded_names or any(
            part in excluded_directories for part in relative.parts[:-1]
        )

    def defines_routed_handler(path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and any(
                ast.unparse(base).endswith(("ViewSet", "APIView", "View"))
                for base in node.bases
            ):
                return True
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    target = (
                        decorator.func
                        if isinstance(decorator, ast.Call)
                        else decorator
                    )
                    name = ast.unparse(target)
                    if name == "api_view" or name.endswith(".api_view"):
                        return True
        return False

    files = set()
    for config in apps.get_app_configs():
        root = Path(config.path)
        if root.parent != BASE_DIR:
            continue
        candidates = {
            path
            for path in root.rglob("*.py")
            if not is_excluded(path, root)
        }
        if root.name != "core":
            files.update(candidates)
            continue

        files.update(
            path
            for path in candidates
            if path.relative_to(root).as_posix()
            in {"views.py", "viewsets.py", "tasks.py", "rename.py"}
            or path.relative_to(root).parts[0] == "mixins"
            or defines_routed_handler(path)
        )
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


def test_source_files_follow_request_reachable_paths(monkeypatch):
    with TemporaryDirectory(dir=BASE_DIR) as temporary_directory:
        temporary_root = Path(temporary_directory)
        domain = temporary_root / "sales"
        core = temporary_root / "core"
        domain.mkdir()
        core.mkdir()
        (domain / "selectors.py").write_text("SELECTOR = True\n", encoding="utf-8")
        (domain / "dev_data.py").write_text("DEV_DATA = True\n", encoding="utf-8")
        (core / "imports.py").write_text(
            "class ImportViewSet(ModelViewSet):\n    pass\n",
            encoding="utf-8",
        )
        (core / "query.py").write_text("QUERY = True\n", encoding="utf-8")

        app_configs = [
            type("AppConfig", (), {"path": str(domain)})(),
            type("AppConfig", (), {"path": str(core)})(),
        ]
        monkeypatch.setitem(globals(), "BASE_DIR", temporary_root)
        monkeypatch.setattr(apps, "get_app_configs", lambda: app_configs)

        relative_paths = {
            path.relative_to(temporary_root).as_posix() for path in _source_files()
        }

        assert relative_paths == {"core/imports.py", "sales/selectors.py"}
