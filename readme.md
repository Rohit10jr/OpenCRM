recreate the frappe CRM into django CRM

## Setting up the database

```bash
cd backend
python manage.py migrate
python manage.py seed_defaults
```

`seed_defaults` is Frappe CRM's install step (`crm/install.py:after_install`), which
`bench install-app` runs once on a site and this port has to run by hand: the lead, deal
and communication statuses, the field layouts every create dialog and side panel reads,
industries, lead sources, lost reasons, quick filters, the user menu, the standard form
scripts and the manager dashboard (`crm_app/setup.py`). It keeps rows that already exist,
so running it again is safe; `--force` rewrites the field layouts and the dashboard.

## Getting in

**There is no default password.** Frappe ships `Administrator` with one set at install
time; this port deliberately does not, so there is no known credential to forget to change.
Both built-in users are seeded with an unusable password
(`frappe_platform/migrations/0002_seed_roles_and_users.py`).

So the first login has to be made, once, from a shell:

```bash
python manage.py createsuperuser
```

Use your own email address as the name — it becomes the account's primary key, and every
record you create is stamped with it. The account is given the **System Manager** role,
which is what actually grants authority here: `is_superuser` is read nowhere in the
permission layer, on purpose.

After that, log in and **invite everyone else through the CRM** rather than repeating this.
The invitation flow assigns roles properly and is the path phase 8 built.

### If you are locked out

`Administrator` already exists with the right roles and no password. Give it one:

```bash
python manage.py changepassword Administrator
```

That name is the username — `USERNAME_FIELD` is `name`, and this account's name is the
literal string `Administrator`, not an email address.

Use it to get back in, then go back to working as yourself: anything done as
`Administrator` is stamped to an account no particular person owns. Note also that
`Administrator`'s seeded email is `admin@example.com`, which nobody receives — **password
reset cannot recover this account**, and the reset endpoint will not tell you so, because
its response is deliberately identical whatever happened.
