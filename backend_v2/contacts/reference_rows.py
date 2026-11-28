"""The lists every database has: salutations, genders and industries (specs/CONTACTS.md
§4 "Reference rows").

Salutations and genders: the framework's setup wizard writes them
(`install_fixtures.py:20-49`), so a Link to either is valid from the start. A data
migration writes them here (`contacts/0002`), as `backend/` does
(`frappe_platform/migrations/0014`). The 51 industries (`backend/crm_app/setup.py:159`)
are written by `contacts/0004_industries`. `restore_defaults` (`contacts/restore.py`)
puts back a row someone deleted, as the old `seed_defaults` does
(`backend/frappe_platform/reference_data.py:34-57`; CONFIGURATION §10).
"""

#: `install_fixtures.py:20-49`, in upstream's order.
GENDERS = (
    "Male",
    "Female",
    "Other",
    "Transgender",
    "Genderqueer",
    "Non-Conforming",
    "Prefer not to say",
)
SALUTATIONS = ("Mr", "Ms", "Mx", "Dr", "Mrs", "Madam", "Miss", "Master", "Prof")

#: `backend/crm_app/setup.py:159` (`install.py:381-509`), in upstream's order.
INDUSTRIES = (
    "Accounting",
    "Advertising",
    "Aerospace",
    "Agriculture",
    "Airline",
    "Apparel & Accessories",
    "Automotive",
    "Banking",
    "Biotechnology",
    "Broadcasting",
    "Brokerage",
    "Chemical",
    "Computer",
    "Consulting",
    "Consumer Products",
    "Cosmetics",
    "Defense",
    "Department Stores",
    "Education",
    "Electronics",
    "Energy",
    "Entertainment & Leisure, Executive Search",
    "Financial Services",
    "Food",
    "Beverage & Tobacco",
    "Grocery",
    "Health Care",
    "Internet Publishing",
    "Investment Banking",
    "Legal",
    "Manufacturing",
    "Motion Picture & Video",
    "Music",
    "Newspaper Publishers",
    "Online Auctions",
    "Pension Funds",
    "Pharmaceuticals",
    "Private Equity",
    "Publishing",
    "Real Estate",
    "Retail & Wholesale",
    "Securities & Commodity Exchanges",
    "Service",
    "Soap & Detergent",
    "Software",
    "Sports",
    "Technology",
    "Telecommunications",
    "Television",
    "Transportation",
    "Venture Capital",
)
