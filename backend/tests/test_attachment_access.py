"""`Comment`, `Communication` and `File` defer to the document they hang off.

Each of these is *about* something else. Unruled, each leaked what the record itself
refused - and the attachment is often worse than the record: a deal row leaks a number,
its Communications leak the reasoning.

Written as the attacks, against a deal the caller is refused.
"""

import pytest

from crm_app.models import CRMDeal, CRMDealStatus
from frappe_core.session import session_user
from frappe_platform.models import Comment, Communication, File

pytestmark = pytest.mark.django_db

BODY = "We can go down to 400k if they push back."
REMARK = "Client is desperate, hold firm on price."


@pytest.fixture
def hidden_deal(administrator, bob):
    """A deal owned by bob, with an email, a private attachment and a comment on it."""
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=bob, deal_value=555555)
        Communication.objects.create(
            subject="Contract terms",
            content=BODY,
            sender="bob@example.com",
            recipients="client@acme.com",
            reference_doctype="CRM Deal",
            reference_name=deal.name,
        )
        File.objects.create(
            file_name="signed-contract.pdf",
            file_url="/private/files/signed-contract.pdf",
            is_private=True,
            attached_to_doctype="CRM Deal",
            attached_to_name=deal.name,
        )
        Comment.objects.create(
            comment_type="Comment",
            content=REMARK,
            reference_doctype="CRM Deal",
            reference_name=deal.name,
        )
    return deal


@pytest.fixture
def own_deal(administrator, alice):
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Won", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice, deal_value=10)
        Comment.objects.create(
            comment_type="Comment",
            content="mine",
            reference_doctype="CRM Deal",
            reference_name=deal.name,
        )
    return deal


# --- the leaks, closed -------------------------------------------------------------------


@pytest.mark.parametrize("doctype", ["Comment", "Communication", "File"])
def test_the_list_hides_rows_hanging_off_an_invisible_record(alice, hidden_deal, api_as, doctype):
    client = api_as(alice)
    assert client.get(f"/api/resource/CRM Deal/{hidden_deal.name}").status_code == 403
    assert client.get(f"/api/resource/{doctype}").json()["data"] == []


def test_an_email_body_is_not_readable(alice, hidden_deal, api_as):
    """**The worst of the three.** Every email exchanged about any lead or deal was
    readable by anyone with a login."""
    row = Communication.objects.get(reference_name=hidden_deal.name)
    assert api_as(alice).get(f"/api/resource/Communication/{row.name}").status_code == 403


def test_a_private_attachment_is_not_readable(alice, hidden_deal, api_as):
    row = File.objects.get(attached_to_name=hidden_deal.name)
    assert api_as(alice).get(f"/api/resource/File/{row.name}").status_code == 403


def test_an_internal_remark_is_not_readable(alice, hidden_deal, api_as):
    # The fixture's attachment also writes an "Attachment" comment on the deal, as
    # upstream's File does (file.py:988-994); the remark is the one typed by a person.
    row = Comment.objects.get(reference_name=hidden_deal.name, comment_type="Comment")
    assert api_as(alice).get(f"/api/resource/Comment/{row.name}").status_code == 403


# --- forgery, closed ---------------------------------------------------------------------


def test_a_comment_cannot_be_forged_onto_an_invisible_record(alice, hidden_deal, api_as):
    """Returned 201 before the rule. Commenting is an edit of the record's history, so it
    needs **write** on the parent, not read."""
    response = api_as(alice).post(
        "/api/resource/Comment",
        {
            "comment_type": "Comment",
            "content": "forged",
            "reference_doctype": "CRM Deal",
            "reference_name": hidden_deal.name,
        },
        format="json",
    )
    assert response.status_code == 403
    assert not Comment.objects.filter(content="forged").exists()


def test_the_other_create_door_is_closed_too(alice, hidden_deal, api_as):
    """`frappe.client.insert` had the identical gap - it also checked `create` against an
    empty instance, which has no reference for the rule to look at. Two doors, one rule;
    the stricter one is decoration if the other stands open."""
    response = api_as(alice).post(
        "/api/method/frappe.client.insert",
        {
            "doc": {
                "doctype": "Comment",
                "comment_type": "Comment",
                "content": "forged via insert",
                "reference_doctype": "CRM Deal",
                "reference_name": hidden_deal.name,
            }
        },
        format="json",
    )
    assert response.status_code == 403
    assert not Comment.objects.filter(content="forged via insert").exists()


def test_an_attachment_cannot_be_moved_onto_an_invisible_record(alice, own_deal, hidden_deal, api_as):
    """Reparenting is a write against the destination, and the destination is what
    matters - otherwise anything you own becomes a foothold on anything you do not."""
    mine = Comment.objects.get(reference_name=own_deal.name)
    response = api_as(alice).put(
        f"/api/resource/Comment/{mine.name}",
        {"reference_name": hidden_deal.name},
        format="json",
    )
    assert response.status_code in (403, 400)


# --- the legitimate cases still work -----------------------------------------------------


def test_you_can_still_see_attachments_on_your_own_record(alice, own_deal, api_as):
    rows = api_as(alice).get("/api/resource/Comment").json()["data"]
    assert [r["content"] for r in rows] == ["mine"]


def test_you_can_still_comment_on_your_own_record(alice, own_deal, api_as):
    assert api_as(alice).post(
        "/api/resource/Comment",
        {
            "comment_type": "Comment",
            "content": "my note",
            "reference_doctype": "CRM Deal",
            "reference_name": own_deal.name,
        },
        format="json",
    ).status_code == 201


def test_a_public_file_stays_public(alice, administrator, api_as):
    """`is_private = 0` is upstream's own carve-out (`file.py:916`) and the product relies
    on it - brand logos and avatars are Files that every client must fetch."""
    with session_user(administrator.name):
        logo = File.objects.create(
            file_name="brand-logo.png", file_url="/files/brand-logo.png", is_private=False
        )
    assert api_as(alice).get(f"/api/resource/File/{logo.name}").status_code == 200


def test_your_own_upload_is_yours(alice, hidden_deal, api_as):
    """`file.py:919`. Ownership survives wherever the file ended up attached - otherwise
    uploading to a record you then lose access to would strand your own file."""
    with session_user(alice.name):
        mine = File.objects.create(
            file_name="my-notes.pdf",
            file_url="/private/files/my-notes.pdf",
            is_private=True,
            attached_to_doctype="CRM Deal",
            attached_to_name=hidden_deal.name,
        )
    assert api_as(alice).get(f"/api/resource/File/{mine.name}").status_code == 200


def test_a_private_file_attached_to_nothing_is_its_owners_alone(alice, bob, api_as):
    """`file.py:932-951`: past the public and own-upload short-circuits a file is only
    reachable through the document it is attached to; one attached to nothing falls to
    `return False` (FINDINGS.md 22). The orphan carve-out is for comments, not files."""
    with session_user(alice.name):
        mine = File.objects.create(
            file_name="draft.pdf", file_url="/private/files/draft.pdf", is_private=True
        )
    assert api_as(alice).get(f"/api/resource/File/{mine.name}").status_code == 200
    response = api_as(bob).get(f"/api/resource/File/{mine.name}")
    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"
    names = [r["name"] for r in api_as(bob).get("/api/resource/File").json()["data"]]
    assert mine.name not in names
    assert mine.name in [r["name"] for r in api_as(alice).get("/api/resource/File").json()["data"]]


def test_a_public_file_attached_to_nothing_is_still_public(alice, bob, api_as):
    with session_user(alice.name):
        logo = File.objects.create(
            file_name="avatar.png", file_url="/files/avatar.png", is_private=False
        )
    assert api_as(bob).get(f"/api/resource/File/{logo.name}").status_code == 200


def test_a_row_referencing_nothing_is_not_hidden(alice, api_as, administrator):
    """Orphans hide nothing, and the product creates them - refusing them here would break
    rows that were never about a record in the first place."""
    with session_user(administrator.name):
        Comment.objects.create(comment_type="Comment", content="standalone")
    rows = api_as(alice).get("/api/resource/Comment").json()["data"]
    assert "standalone" in [r["content"] for r in rows]


def test_a_row_referencing_an_unrestricted_doctype_is_not_hidden(alice, api_as, administrator):
    """Only doctypes with a row rule can hide a parent. A comment on an Organization -
    which everyone can read - needs no check, and building one per registered doctype
    would make the subquery enormous for no gain."""
    from crm_app.models import CRMOrganization

    with session_user(administrator.name):
        org = CRMOrganization.objects.create(organization_name="Acme")
        Comment.objects.create(
            comment_type="Comment",
            content="about acme",
            reference_doctype="CRM Organization",
            reference_name=org.name,
        )
    rows = api_as(alice).get("/api/resource/Comment").json()["data"]
    assert "about acme" in [r["content"] for r in rows]


def test_the_timeline_still_works(alice, bob, administrator, api_as):
    """The one legitimate consumer of all three, and the regression to watch.

    `get_activities` checks read on the parent and then reads Comments and Communications
    over the ORM, so a wire-level rule leaves it untouched - but that is worth proving
    rather than assuming.
    """
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Open", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice, deal_value=1)
        Comment.objects.create(
            comment_type="Comment",
            content="timeline entry",
            reference_doctype="CRM Deal",
            reference_name=deal.name,
        )

    response = api_as(alice).get(f"/api/method/crm.api.activities.get_activities?name={deal.name}")
    assert response.status_code == 200
