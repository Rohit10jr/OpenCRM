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
    ("accounts/directory.py", "get_users", "User._default_manager"): (
        "get_users is the CRM directory, gated by a CRM role, and reads enabled users "
        "as the old one does (crm_app/api/session.py:80-98), not through User's list rule."
    ),
    ("accounts/directory.py", "get_users", "Group.objects"): (
        "get_users reads the role names of the users it already selected, in one query."
    ),
    ("accounts/directory.py", "get_user_info", "User._default_manager"): (
        "get_user_info returns five public fields for named users, including built-in "
        "and disabled ones, as the old one does (session.py:151-155); CRM role required."
    ),
    ("accounts/user_roles.py", "_set_roles", "Group.objects"): (
        "Role names resolve to their groups after the manager-pair and role checks."
    ),
    ("accounts/user_roles.py", "_remove_roles", "Group.objects"): (
        "Role names resolve to their groups after the manager-pair and role checks."
    ),
    ("accounts/user_roles.py", "update_user_role", "User._default_manager"): (
        "The old action loads the target directly after the manager-pair check and "
        "applies no User object rule (crm_app/api/user.py:139-147; spec 4.2)."
    ),
    ("accounts/user_roles.py", "update_user_role", "CRMSalesHierarchy._default_manager"): (
        "The demotion guard reads the target's node and whether it has reports, as the "
        "old action does (user.py:164-177); the chart is readable by everyone."
    ),
    ("accounts/user_roles.py", "remove_crm_roles_from_user", "User._default_manager"): (
        "As update_user_role: a direct load after the manager-pair check (user.py:197)."
    ),
    (
        "accounts/user_roles.py",
        "remove_crm_roles_from_user",
        "CRMSalesHierarchy._default_manager",
    ): (
        "Removing CRM roles deletes the user's chart node, as the old action does "
        "(user.py:215), after the manager-pair and System Manager checks."
    ),
    ("accounts/front_door.py", "reset_password", "User._default_manager"): (
        "Forgot password runs before any request user exists; it finds the account by "
        "address and answers one sentence whatever it finds (old auth_pages.py:81)."
    ),
    ("accounts/authentication.py", "revoke_all_tokens", "OutstandingToken.objects"): (
        "Blacklists one account's own refresh tokens; its callers authorized it first: "
        "logout_all_sessions after the reset key or old password proved who it is, and "
        "the User rename after the System Manager rule (ACCOUNTS §10.4)."
    ),
    ("contacts/actions.py", "_require_contact", "Contact._default_manager"): (
        "The contact calls must tell a missing contact from a refused one only by the "
        "same 403, then apply the Contact object rule to the loaded row (old "
        "contact.py:26-41, FINDINGS 12); the list rule would turn a refusal into a 404."
    ),
    ("contacts/child_rows.py", "_row_and_contact", "model._default_manager"): (
        "The row routes look the row up first, by its name and its contact, so a missing "
        "row or one of another contact is 404 before any rule (old client.py:409-411,424)."
    ),
    ("contacts/child_rows.py", "_row_and_contact", "Contact._default_manager"): (
        "The row's contact, loaded only once the row is found, so the Contact write rule "
        "can be applied to it (403 on edit, 404 on delete, old client.py:213-223,551-572)."
    ),
    ("contacts/actions.py", "set_as_primary", "Contact._default_manager"): (
        "Writes the derived mirror columns and user of the contact the object rule just "
        "allowed, with update() so `modified` is not bumped (FINDINGS 67, PE-35)."
    ),
    ("accounts/rename.py", "name_taken", "User._default_manager"): (
        "The rename's taken check must see every account, the built-ins and those the "
        "User list rule hides, case-insensitively (ACCOUNTS §10.2 row 6)."
    ),
    ("accounts/rename.py", "on_user_renamed", "User._default_manager"): (
        "Inside the authorized rename's transaction: one update of the renamed row "
        "itself, then that row for the token revocation (ACCOUNTS §10.3-10.4)."
    ),
    ("accounts/password_reset.py", "issue_key", "User._default_manager"): (
        "A write-only update of one account's reset-key columns from a guest endpoint."
    ),
    ("accounts/password_reset.py", "resolve_key", "User._default_manager"): (
        "Finds the account a reset key belongs to: the key is the credential, not a row rule."
    ),
    ("accounts/password_reset.py", "consume_key", "User._default_manager"): (
        "A conditional write-only update clearing one account's reset key."
    ),
    ("accounts/invitations.py", "invite_by_email", "User._default_manager"): (
        "invite_by_email finds which addresses already belong to members, after the "
        "manager-pair and role checks (old misc.py:103-105)."
    ),
    ("accounts/invitations.py", "invite_by_email", "CRMInvitation._default_manager"): (
        "invite_by_email finds invitations of any status for the addresses, after the "
        "manager-pair and role checks (old misc.py:106-110)."
    ),
    ("accounts/invitations.py", "accept_invitation", "CRMInvitation._default_manager"): (
        "A guest redeems by key: the key is the credential, not a row rule "
        "(old auth_pages.py:346)."
    ),
    ("accounts/invitations.py", "accept_invitation", "User._default_manager"): (
        "Loads the account the redeemed invitation names, to mint its key or tokens."
    ),
    ("accounts/invitations.py", "_accept", "CRMInvitation._default_manager"): (
        "The conditional claim: a write-only update of the one invitation being redeemed."
    ),
    ("accounts/invitations.py", "_accept", "Group.objects"): (
        "Resolves the invitation's role and its implied roles to groups."
    ),
    ("accounts/invitations.py", "_create_user_if_not_exists", "User._default_manager"): (
        "Accepting reuses an existing account by the invited address (auth_pages.py:419)."
    ),
    ("accounts/tasks.py", "send_invitation_email", "CRMInvitation._default_manager"): (
        "A queued job without a request user: reads the one invitation it was given and "
        "stamps its send time."
    ),
    ("accounts/tasks.py", "expire_invitations", "CRMInvitation._default_manager"): (
        "The scheduled sweep: a write-only status update of stale pending invitations."
    ),
    ("accounts/tasks.py", "flush_expired_tokens", "OutstandingToken.objects"): (
        "The scheduled count of already-expired tokens before SimpleJWT flushes them."
    ),
    (
        "configuration/views.py",
        "OnboardingStatusView.post",
        "type(request.user)._default_manager",
    ): (
        "A write-only update of the authenticated caller's own onboarding column, as "
        "the old update does (crm_app/api/onboarding.py:84), timestamps untouched."
    ),
    ("configuration/mail.py", "saved_outgoing_account", "EmailAccount._default_manager"): (
        "The server-side choice of which saved account carries a message, for core.mail; "
        "no caller sees the row, as the old find_outgoing_account (communication.py:400-440)."
    ),
    ("configuration/mail.py", "default_signature", "EmailAccount._default_manager"): (
        "The signature fallback reads one column of the default outgoing account for the "
        "caller's own signature, as the old get_user_signature (misc.py:62-67)."
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
    ("configuration/list_engine.py", "kanban_link_columns", "target._default_manager"): (
        "A kanban's columns are its column field's link target's names, read through that "
        "target's own list rule (old doc.py:432-448); a target no resource serves gives none."
    ),
    ("configuration/view_settings.py", "kanban_link_columns", "model._default_manager"): (
        "A saved kanban's columns are a link target's names, read through that target's "
        "own list rule (old view_settings.py:91-100); a target no resource serves gives none."
    ),
    ("core/mixins/rename.py", "RenameMixin.rename", "self.document_model._default_manager"): (
        "Rename must distinguish a missing row from one excluded by its list rule, then "
        "apply the resource's object-write rule to the directly loaded document."
    ),
    ("core/mixins/rename.py", "RenameMixin.name_taken", "self.document_model._default_manager"): (
        "The taken check (moved out of rename into its hook) must see every row, list "
        "rule or not, as upstream's validate_rename does: a hidden row still holds the name."
    ),
    ("core/rename.py", "repoint_json_name_lists", "other_model._default_manager"): (
        "A user rename rewrites the old name in every _assign/_liked_by list, schema-wide "
        "and write-only, after the User resource has authorized the rename (ACCOUNTS §10.6)."
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
    # Operator paths called only by restore_defaults (CONFIGURATION §10.3), never by a
    # request; by path, so another app's restore.py is still scanned (A-78 finding 8).
    excluded_paths = {"configuration/restore.py", "contacts/restore.py"}

    def is_excluded(path, root):
        relative = path.relative_to(root)
        app_relative = path.relative_to(root.parent).as_posix()
        return (
            path.name in excluded_names
            or app_relative in excluded_paths
            or any(part in excluded_directories for part in relative.parts[:-1])
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
