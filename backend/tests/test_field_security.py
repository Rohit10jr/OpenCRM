"""Stage 1 - a hidden field must be hidden from *questions about it*, not just output.

`SENSITIVE_FIELDS` kept credentials out of responses from phase 1 onwards, and that was
read as "the credential is protected". It was not. Hiding a value from the response stops
it being *handed over*; it does nothing about a caller who asks whether the value starts
with "S". The row count answers, and `like` narrows one character per request.

Recovered a real SMTP password this way as a plain Sales User, before the guard below::

    stored:    'Sw0rdfish!'
    recovered: 'sw0rdfish!'      # lowercase only because `like` maps to an
                                 # I-prefixed lookup, for MariaDB parity

Upstream is not safe here because it checks something - it is safe because the value is
not in the table. `password` is a `Password` fieldtype, which Frappe writes to a separate
`__Auth` table via `set_encrypted_password` (`frappe/utils/password.py:52`). There is no
column on `tabEmail Account` to filter against.

We hold the value in the row until the encryption work lands, so the guard has to be
explicit. It stays afterwards: the same reasoning covers every future secret, and a check
that is redundant is cheaper than remembering why it was removed.

The four entry points that name a field: **filters**, **or_filters**, **order_by**,
**group_by**. `group_by` was already guarded; the other three were not.
"""

import pytest

from frappe_core.exceptions import ValidationError
from frappe_core.field_security import sensitive_fields
from frappe_core.filters import FilterError, build_q
from frappe_core.query import resolve_group_by, resolve_order_by
from frappe_core.session import session_user
from frappe_platform.models import EmailAccount, User

# Most of this needs no database - it is field-name resolution over a model class.
SECRET = "Sw0rdfish!"


# --- the four entry points --------------------------------------------------------------


@pytest.mark.parametrize("fieldname", ["password", "api_secret"])
def test_a_filter_naming_a_secret_is_rejected(fieldname):
    with pytest.raises(FilterError, match="Cannot filter"):
        build_q(EmailAccount, [[fieldname, "=", SECRET]])


@pytest.mark.parametrize(
    "operator,value",
    [("=", SECRET), ("like", "Sw%"), ("in", [SECRET]), ("!=", "x"), ("is", "set")],
)
def test_no_operator_offers_a_way_round(operator, value):
    """The oracle does not need equality - `like`, `in` and even `is set` all leak."""
    with pytest.raises(FilterError, match="Cannot filter"):
        build_q(EmailAccount, [["password", operator, value]])


def test_or_filters_are_guarded_too(db):
    """`or_filters` builds through the same function, which is why one guard covers both -
    pinned so a future refactor that splits them cannot quietly drop one."""
    with pytest.raises(FilterError, match="Cannot filter"):
        build_q(EmailAccount, [["password", "=", SECRET]], combine="OR")


def test_ordering_by_a_secret_is_refused():
    """Weaker than a filter but the same shape: sort order is a comparison, and a caller
    who can sort by a secret can bisect it across requests.

    Refused rather than silently dropped, which is what an unknown field already does
    here - a dropped clause returns rows in an order the caller did not ask for, and they
    have no way to know.
    """
    with pytest.raises(ValidationError, match="Cannot order by"):
        resolve_order_by(EmailAccount, "password desc")
    assert resolve_order_by(EmailAccount, "modified desc") == ["-modified"]


def test_grouping_by_a_secret_is_refused():
    """Already guarded before this change. Pinned so it stays that way."""
    with pytest.raises(ValidationError, match="Cannot group by"):
        resolve_group_by(EmailAccount, "password")


# --- every declared secret, not just the ones we thought of -----------------------------


@pytest.mark.parametrize(
    "model", [EmailAccount, User], ids=["EmailAccount", "User"]
)
def test_every_declared_secret_on_a_model_is_unfilterable(model):
    """Parametrised over the models rather than a hand-written field list, so a secret
    added later is covered without anyone remembering to extend this test."""
    for fieldname in sensitive_fields(model):
        if fieldname not in {f.name for f in model._meta.get_fields()}:
            continue
        with pytest.raises(FilterError, match="Cannot filter"):
            build_q(model, [[fieldname, "=", "anything"]])


# --- the attack itself ------------------------------------------------------------------


@pytest.mark.django_db
def test_a_secret_cannot_be_recovered_by_probing(alice, administrator, api_as):
    """**The exploit, inverted.** This is the loop that recovered 'sw0rdfish!'.

    Written as the attack rather than as a unit test of the guard, because the guard is
    one of four places this could leak and a unit test of one function would not have
    caught the other three.
    """
    with session_user(administrator.name):
        EmailAccount.objects.create(
            email_account_name="Support",
            email_id="support@example.com",
            password=SECRET,
            smtp_server="smtp.example.com",
        )

    client = api_as(alice)
    for prefix in ("S%", "s%", "Sw%", "%fish%", SECRET):
        response = client.get(f'/api/resource/Email Account?filters=[["password","like","{prefix}"]]')
        assert response.status_code == 400, f"{prefix!r} was answered, not refused"


@pytest.mark.django_db
def test_an_ordinary_filter_still_works(alice, administrator, api_as):
    """The guard must not have made the endpoint useless."""
    with session_user(administrator.name):
        EmailAccount.objects.create(
            email_account_name="Support",
            email_id="support@example.com",
            password=SECRET,
            smtp_server="smtp.example.com",
        )

    response = api_as(alice).get(
        '/api/resource/Email Account?filters=[["email_id","=","support@example.com"]]'
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
