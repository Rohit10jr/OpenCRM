"""Phone-number parsing and "who is this number?" resolution.

Ports `crm/utils/__init__.py:14-68` (`parse_phone_number`, `are_same_phone_number`) and
`crm/integrations/api.py:302-381` (`get_contact`).

Provider-neutral on purpose: an inbound Twilio call and an inbound Exotel call ask the
same question, and so does the manual "Log a call" flow with every integration off. So
this is **not** behind a feature flag.

## The two-stage match, and why it is not just a database lookup

Upstream matches in two stages and the order matters:

1. A **normalised `LIKE`** narrows the candidates in SQL — spaces, dashes, brackets and
   `+` stripped from both sides, then `%<digits>%`. This is a *substring* match, so it
   deliberately over-matches: `98765` finds `+91 98765 43210`.
2. `are_same_phone_number` then compares the survivors properly, via E.164, and the
   over-matching from stage 1 is discarded.

Skipping stage 2 would attach a call to whichever contact happened to share a digit run.
Skipping stage 1 would mean parsing every contact in the database per call.

**Contacts are searched through their `phone_nos` child rows, not `mobile_no`** — upstream
changed this deliberately so a call from someone's secondary number still resolves
(`api.py:307-309`).
"""

from __future__ import annotations

import phonenumbers
from phonenumbers import NumberParseException
from phonenumbers import PhoneNumberFormat as PNF

#: `crm/utils/__init__.py:14` — upstream's default region, used when a number arrives
#: without a country code. Not a guess we can improve on: it is what upstream's stored
#: numbers were parsed against.
DEFAULT_REGION = "IN"

#: Stripped from both sides before the SQL `LIKE`. `api.py:306-313`.
_PUNCTUATION = (" ", "-", "(", ")", "+")


def parse_phone_number(phone_number: str, default_country: str = DEFAULT_REGION) -> dict:
    """`crm/utils/__init__.py:14-37`. Never raises — a parse failure is a return value.

    The caller branches on ``is_valid``, so an exception here would turn "somebody dialled
    a malformed number" into a 500 on an inbound webhook.
    """
    try:
        number = phonenumbers.parse(phone_number, default_country)
    except NumberParseException as exc:
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        "is_valid": phonenumbers.is_valid_number(number),
        "country_code": number.country_code,
        "national_number": str(number.national_number),
        "formats": {
            "international": phonenumbers.format_number(number, PNF.INTERNATIONAL),
            "national": phonenumbers.format_number(number, PNF.NATIONAL),
            "E164": phonenumbers.format_number(number, PNF.E164),
            "RFC3966": phonenumbers.format_number(number, PNF.RFC3966),
        },
        "type": phonenumbers.number_type(number),
        "country": phonenumbers.region_code_for_number(number),
        "is_possible": phonenumbers.is_possible_number(number),
    }


def are_same_phone_number(
    number1: str, number2: str, default_region: str = DEFAULT_REGION, validate: bool = True
) -> bool:
    """`crm/utils/__init__.py:40-68` — compare in E.164, so format never matters.

    ``validate=False`` is upstream's ``exact_match`` path: when the *caller's* number could
    not be parsed at all, requiring both sides to be valid would reject every candidate, so
    the comparison falls back to "do these normalise to the same string".
    """
    try:
        parsed1 = phonenumbers.parse(number1, default_region)
        parsed2 = phonenumbers.parse(number2, default_region)
    except NumberParseException:
        return False

    if validate and not (
        phonenumbers.is_valid_number(parsed1) and phonenumbers.is_valid_number(parsed2)
    ):
        return False

    return phonenumbers.format_number(parsed1, PNF.E164) == phonenumbers.format_number(
        parsed2, PNF.E164
    )


def _strip(value: str) -> str:
    for char in _PUNCTUATION:
        value = value.replace(char, "")
    return value


def get_contact(phone_number: str, country: str = DEFAULT_REGION, exact_match: bool = False) -> dict:
    """`crm/integrations/api.py:302-381`.

    Returns the matched Contact (with ``deal`` set when it is a deal's primary contact), or
    the matched Lead, or ``{"mobile_no": phone_number}`` when nothing matches — never
    ``None``. Callers branch on ``.get("name")``.

    **Order is load-bearing.** A contact that is a deal's primary contact wins outright; a
    lead is only consulted if no such contact matched; a plain contact is the last resort.
    Upstream returns from inside the loop, so the *first* qualifying row by `modified desc`
    wins, and that is reproduced.
    """
    from django.db.models import F, Func, Value

    from crm_app.models import CRMContacts, CRMLead
    from frappe_platform.models import ContactPhone

    if not phone_number:
        return {"mobile_no": phone_number}

    cleaned = _strip(phone_number.strip())

    def normalise(field: str):
        expression = F(field)
        for char in _PUNCTUATION:
            expression = Func(expression, Value(char), Value(""), function="REPLACE")
        return expression

    # --- contacts, via their phone_nos child rows -------------------------------------
    rows = (
        ContactPhone._default_manager.filter(parenttype="Contact")
        .annotate(_norm=normalise("phone"))
        .filter(_norm__contains=cleaned)
        .select_related("parent_contact")
        .order_by("-parent_contact__modified")
    )

    contacts = [
        {
            "name": row.parent_contact.pk,
            "full_name": row.parent_contact.full_name,
            "image": row.parent_contact.image,
            "mobile_no": row.parent_contact.mobile_no,
            "matched_phone": row.phone,
        }
        for row in rows
    ]

    for contact in contacts:
        deal = (
            CRMContacts._default_manager.filter(contact=contact["name"], is_primary=True)
            .values_list("parent_deal", flat=True)
            .first()
        )
        if deal and are_same_phone_number(
            contact["matched_phone"], phone_number, country, validate=not exact_match
        ):
            contact["deal"] = deal
            return contact

    # --- leads -------------------------------------------------------------------------
    leads = (
        CRMLead._default_manager.filter(converted=False)
        .annotate(_norm=normalise("mobile_no"))
        .filter(_norm__contains=cleaned)
        .order_by("-modified")
        .values("name", "lead_name", "image", "mobile_no")
    )

    for lead in leads:
        if are_same_phone_number(
            lead["mobile_no"], phone_number, country, validate=not exact_match
        ):
            return {**lead, "lead": lead["name"], "full_name": lead["lead_name"]}

    # --- a contact that is not a deal's primary ----------------------------------------
    if contacts and are_same_phone_number(
        contacts[0]["matched_phone"], phone_number, country, validate=not exact_match
    ):
        return contacts[0]

    return {"mobile_no": phone_number}


def get_contact_by_phone_number(phone_number: str) -> dict:
    """`crm/integrations/api.py:157-165`.

    A number that parses is searched by its **national** part, so a call from
    ``+91 98765 43210`` matches a contact stored as ``09876543210``. One that does not
    parse is searched verbatim, with ``exact_match`` — which is what turns off the
    is-valid requirement on the far side of the comparison.
    """
    number = parse_phone_number(phone_number)
    if number.get("is_valid"):
        return get_contact(number.get("national_number"), number.get("country"))
    return get_contact(phone_number, number.get("country") or DEFAULT_REGION, exact_match=True)


def get_contact_lead_or_deal_from_number(number: str):
    """`crm/integrations/api.py:140-154` — returns ``(docname, doctype)``, in that order.

    The tuple is reversed relative to how everything else in this codebase names the pair,
    and it is upstream's order (`handler.py` unpacks it that way). Kept.
    """
    contact = get_contact_by_phone_number(number)
    if not contact.get("name"):
        return None, None

    if contact.get("lead"):
        return contact["lead"], "CRM Lead"
    if contact.get("deal"):
        return contact["deal"], "CRM Deal"
    return contact["name"], "Contact"
