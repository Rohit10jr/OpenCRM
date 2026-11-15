from scripts.http_parser import parse_http, resolve_variables


def test_parser_covers_the_walkthrough_syntax_losslessly():
    text = """\
# preamble
@host = http://localhost:8000
@pwd = {{$dotenv ADMIN_PWD}}
@method = login

### named request -> 200|404
# @name signed_in
# @expect $.message.items[0].name contains Example
# @expect $.message.enabled == true
# @expect $.message.state != closed
# @expect $.message.items excludes Hidden
# @expect $.message.access exists
# @expect $.message.secret absent
# @expect $.message.items count 1
POST {{host}}/api/method/{{method}}
X-Test: yes
Content-Type: application/json

{"pwd": "{{pwd}}"}

### form request
POST {{host}}/form
Content-Type: application/x-www-form-urlencoded

name={{signed_in.response.body.$.message.items[0].name}}&enabled=1
###
@token = {{signed_in.response.body.$.message.access}}
"""
    parsed = parse_http(text)
    named = parsed.blocks[1]
    assert parsed.render() == text
    assert named.name == "signed_in"
    assert named.expected_statuses == {200, 404}
    assert [item.operator for item in named.expectations] == [
        "contains",
        "==",
        "!=",
        "excludes",
        "exists",
        "absent",
        "count",
    ]
    assert named.request == ("POST", "{{host}}/api/method/{{method}}")
    assert named.headers_and_body()[1] == '{"pwd": "{{pwd}}"}'
    assert parsed.blocks[2].headers_and_body()[1].startswith("name={{signed_in.response")
    assert resolve_variables(
        "{{host}}/api/method/{{method}}",
        {"host": "http://localhost:8000", "method": "login"},
    ) == "http://localhost:8000/api/method/login"
