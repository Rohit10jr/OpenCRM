from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.build_http_suite import SuiteBuildError, build_suite, parse_route_map, rewrite_http
from scripts.http_parser import parse_http


ROUTE_MAP_TEXT = """\
## FOUNDATION
### Method paths
| Dotted path | Verbs | Access | Old source | New route | New app | Status |
|---|---|---|---|---|---|---|
| `login` | POST | guest | `auth.py:login` | `POST /api/v1/auth/login/` | accounts | built |
| `logout` | POST/GET | auth | `auth.py:logout` | `POST /api/v1/auth/logout/` | accounts | built |
| `frappe.auth.get_logged_user` | GET/POST | auth | `auth.py:me` | `GET /api/v1/auth/me/` | accounts | built |
| `token/refresh` | POST | guest | `auth.py:refresh` | `POST /api/v1/auth/token/refresh/` | accounts | built |
| `frappe.client.set_value` | POST | auth | `client.py:set_value` | each resource's | core | built |
| `frappe.client.get` | GET/POST | auth | `client.py:get` | each resource's | core | built |
| `future.method` | POST | auth | `future.py:method` | future | core | — |

## SALES
### Doctypes
| DocType | Kind | Naming | Old protection | Declared fields | Old model | New route | New app | Status |
|---|---|---|---|---|---|---|---|---|
| CRM Widget | main | default | open |  | `crm.Widget` | `GET /api/v1/widgets/`, `POST /api/v1/widgets/`, `GET /api/v1/widgets/<name>/`, `PATCH /api/v1/widgets/<name>/`, `DELETE /api/v1/widgets/<name>/` | sales | built |
| CRM Future | main | default | open |  | `crm.Future` |  | sales | — |
"""


def test_built_method_path_is_rewritten_and_host_moves_to_8001():
    source = """\
@host = http://localhost:8000
### 1.1 -> 200
POST {{host}}/api/method/login
Content-Type: application/json

{"usr": "Administrator", "pwd": "{{$dotenv ADMIN_PWD}}"}
"""
    result = rewrite_http(source, parse_route_map(ROUTE_MAP_TEXT))
    assert "@host = http://localhost:8001" in result
    assert "POST {{host}}/api/v1/auth/login/" in result
    assert "{{$dotenv ADMIN_PWD}}" in result


def test_doctype_search_rewrites_without_claiming_resource_searches():
    route_map = parse_route_map(
        ROUTE_MAP_TEXT
        + """
## SHARED_ACTIONS
| Dotted path | New route | Status |
|---|---|---|
| `frappe.desk.search.search_link` | `GET /api/v1/doctypes/search/`, `POST /api/v1/doctypes/search/` | built |
"""
    )
    source = """\
### doctypes -> 200
POST http://localhost:8000/api/method/frappe.desk.search.search_link
Content-Type: application/json

{"doctype": "DocType", "txt": "CRM"}
### users -> 200
POST http://localhost:8000/api/method/frappe.desk.search.search_link
Content-Type: application/json

{"doctype": "User", "txt": "Ada"}
"""

    result = rewrite_http(source, route_map)

    assert "POST {{host}}/api/v1/doctypes/search/" in result
    assert '{"txt": "CRM"}' in result
    assert "# @waiting SHARED_ACTIONS" in result


def test_set_value_becomes_patch_with_field_value_body():
    source = """\
@host = http://localhost:8000
### update -> 200
POST {{host}}/api/method/frappe.client.set_value
Content-Type: application/json

{"doctype": "CRM Widget", "name": "W/1", "fieldname": "status", "value": "Won"}
"""
    result = rewrite_http(source, parse_route_map(ROUTE_MAP_TEXT))
    assert "PATCH {{host}}/api/v1/widgets/W/1/" in result
    assert '{"status": "Won"}' in result
    assert '"doctype"' not in result


def test_resource_create_uses_method_envelope_and_status():
    source = """\
@host = http://localhost:8000
### create -> 201
# @name created
# @expect $.data.name exists
POST {{host}}/api/resource/CRM%20Widget
Content-Type: application/json

{"title": "Example"}
"""
    result = rewrite_http(source, parse_route_map(ROUTE_MAP_TEXT))
    assert "### create -> 200" in result
    assert "POST {{host}}/api/v1/widgets/" in result
    assert "# @expect $.message.name exists" in result
    assert '# @resource-envelope {"data"}/201 -> {"message"}/200' in result


def test_unbuilt_method_is_kept_and_marked_with_its_unit():
    source = "### future -> 200\nPOST http://localhost:8000/api/method/future.method\n"
    result = rewrite_http(source, parse_route_map(ROUTE_MAP_TEXT))
    assert "# @waiting FOUNDATION" in result
    assert "/api/method/future.method" in result


def test_cleanup_sections_and_cleanup_titles_are_marked():
    source = """\
# ---- cleanup first ----
### 0.1 find leftovers -> 200
POST http://localhost:8000/api/method/login
### 0.2 remove leftover -> 200|404
POST http://localhost:8000/api/method/logout
### 1.1 normal request -> 200
POST http://localhost:8000/api/method/login
### 2.1 cleanup later -> 200|404
POST http://localhost:8000/api/method/logout
"""
    result = rewrite_http(source, parse_route_map(ROUTE_MAP_TEXT))
    blocks = parse_http(result).blocks

    assert blocks[1].cleanup
    assert blocks[2].cleanup
    assert not blocks[3].cleanup
    assert blocks[4].cleanup


def test_auth_wrong_verbs_and_added_cases_are_negative_405s():
    source = """\
@host = http://localhost:8000
### 1.12 GET login -> 403
# @expect $.exc_type == PermissionError
GET {{host}}/api/method/login
### 1.13 login -> 200
POST {{host}}/api/method/login
### 2.11 GET logout -> 200
GET {{host}}/api/method/logout
### 2.12 login -> 200
POST {{host}}/api/method/login
"""
    result = rewrite_http(source, parse_route_map(ROUTE_MAP_TEXT), "01_auth.http")
    assert result.count("# @negative") == 4
    assert "GET {{host}}/api/v1/auth/login/" in result
    assert "POST {{host}}/api/v1/auth/me/" in result
    assert "GET {{host}}/api/v1/auth/token/refresh/" in result
    assert "GET {{host}}/api/v1/auth/logout/" in result
    assert result.count("-> 405") == 4


def test_pe3_filter_get_blocks_are_comments_not_requests():
    blocks = []
    cases = ((5, '{"doctype": "CRM Widget", "filters": {}}'), (6, '{"doctype": "CRM Widget", "filters": {}}'), (7, '{"doctype": "CRM Widget"}'))
    for number, body in cases:
        blocks.append(
            f"### 2.{number} case\nPOST http://localhost:8000/api/method/frappe.client.get\n"
            f"Content-Type: application/json\n\n{body}\n"
        )
    result = rewrite_http(
        "".join(blocks), parse_route_map(ROUTE_MAP_TEXT), "13_bulk_and_misc.http"
    )
    assert result.count("# @not-served PE-3") == 3
    assert "/api/method/frappe.client.get" not in result


def test_builder_is_idempotent():
    with TemporaryDirectory(dir=Path(__file__).parents[1] / "scripts") as directory:
        temporary = Path(directory)
        source = temporary / "source"
        output = temporary / "output"
        source.mkdir()
        (source / "one.http").write_text(
            "### login -> 200\nPOST http://localhost:8000/api/method/login\n",
            encoding="utf-8",
        )
        route_map = temporary / "PORT_MAP.md"
        route_map.write_text(ROUTE_MAP_TEXT, encoding="utf-8")
        build_suite(source, output, route_map)
        first = (output / "one.http").read_bytes()
        build_suite(source, output, route_map)
        assert (output / "one.http").read_bytes() == first


def test_malformed_route_map_row_names_its_line():
    malformed = """\
## UNIT
| Dotted path | New route | Status |
|---|---|---|
| `login` | `POST /api/v1/auth/login/` |
"""
    with pytest.raises(SuiteBuildError, match="row at line 4"):
        parse_route_map(malformed)


def test_unknown_method_path_names_the_file_and_line():
    source = "### unknown\nPOST http://localhost:8000/api/method/not.in.map\n"
    with pytest.raises(SuiteBuildError, match=r"fixture.http:1:.*not\.in\.map"):
        rewrite_http(source, parse_route_map(ROUTE_MAP_TEXT), "fixture.http")


def test_real_foundation_blocks_are_runnable_and_later_blocks_wait():
    root = Path(__file__).resolve().parents[2]
    routes = parse_route_map(
        (root / "backend_v2/docs/PORT_MAP.md").read_text(encoding="utf-8")
    )
    auth = rewrite_http(
        (root / "docs/http/01_auth.http").read_text(encoding="utf-8"), routes, "01_auth.http"
    )
    lockout = rewrite_http(
        (root / "docs/http/99_lockout.http").read_text(encoding="utf-8"), routes, "99_lockout.http"
    )
    # The route map alone decides (specs/ACCOUNTS.md section 7): a block whose method
    # path is built runs on its new route, and one whose path is not waits on its unit.
    for block in parse_http(auth).blocks:
        if not block.request:
            continue
        number = (block.title or "").split(" ", 1)[0]
        if number in {f"1.{n}" for n in range(1, 12)} | {"1.13"}:
            assert "# @waiting" not in block.lines
        if any(line.startswith("# @waiting") for line in block.lines):
            assert "/api/method/" in block.request[1]
        else:
            assert "/api/v1/" in block.request[1]
    for block in parse_http(lockout).blocks:
        if block.request and (block.title or "").startswith(("1.", "2.")):
            assert "# @waiting" not in block.lines
            assert "/api/v1/auth/login/" in block.request[1]
        elif block.request:
            assert "# @waiting ACCOUNTS" in block.lines


ACCOUNTS_ROUTE_MAP = ROUTE_MAP_TEXT + """
## ACCOUNTS
### Method paths
| Dotted path | Verbs | Access | Old source | New route | New app | Status |
|---|---|---|---|---|---|---|
| `crm.api.session.get_users` | GET/POST | auth | `session.py:get_users` | `GET /api/v1/users/directory/` | accounts | built |
| `crm.api.user.update_user_role` | GET/POST | auth | `user.py:update_user_role` | `POST /api/v1/users/<name>/update-role/` (`user` in the URL) | accounts | built |
| `crm.api.accept_invitation` | GET/POST | guest | `auth_pages.py:accept_invitation` | `POST /api/v1/auth/accept-invitation/` | accounts | built |
"""


def test_a_post_body_moves_into_the_query_of_a_get_only_route():
    source = """\
### 1.1 get users -> 200
POST http://localhost:8000/api/method/crm.api.session.get_users
Authorization: Bearer {{token}}
Content-Type: application/json

{"include_all": 1, "label": "{{who}}"}
"""
    result = rewrite_http(source, parse_route_map(ACCOUNTS_ROUTE_MAP))
    request = next(block for block in parse_http(result).blocks if block.request).request
    assert request == ("GET", "{{host}}/api/v1/users/directory/?include_all=1&label={{who}}")
    assert "Authorization: Bearer {{token}}" in result
    assert '"include_all"' not in result
    assert "# @negative" not in result


def test_a_named_body_input_moves_into_the_url():
    source = """\
### 3.2 update role -> 200
POST http://localhost:8000/api/method/crm.api.user.update_user_role
Content-Type: application/json

{"user": "ada@example.com", "new_role": "Sales User"}
"""
    result = rewrite_http(source, parse_route_map(ACCOUNTS_ROUTE_MAP))
    block = next(block for block in parse_http(result).blocks if block.request)
    assert block.request == ("POST", "{{host}}/api/v1/users/ada@example.com/update-role/")
    assert block.headers_and_body()[1] == '{"new_role": "Sales User"}'


def test_a_get_on_a_post_only_route_is_still_a_negative_405():
    source = """\
### 5.3 accept by GET -> 200
GET http://localhost:8000/api/method/crm.api.accept_invitation?key=abc
"""
    result = rewrite_http(source, parse_route_map(ACCOUNTS_ROUTE_MAP))
    assert "# @negative" in result
    assert "GET {{host}}/api/v1/auth/accept-invitation/" in result


def test_a_url_input_missing_from_the_body_is_an_error():
    source = """\
### 3.x -> 200
POST http://localhost:8000/api/method/crm.api.user.update_user_role
Content-Type: application/json

{"new_role": "Sales User"}
"""
    with pytest.raises(SuiteBuildError, match="no input for <name>"):
        rewrite_http(source, parse_route_map(ACCOUNTS_ROUTE_MAP))
