-- Read-only comparison for the owner to run against the old opencrm database.
-- It reports missing or extra role assignments for the four development users,
-- followed by whether each account exists and has a usable Django password hash.
WITH expected(name, role) AS (
    VALUES
        ('Administrator', 'Administrator'),
        ('Administrator', 'System Manager'),
        ('ada@example.com', 'Sales User'),
        ('grace@example.com', 'Sales Manager'),
        ('alan@example.com', 'Sales User')
), actual AS (
    SELECT users.name, roles.name AS role
    FROM "tabUser" AS users
    JOIN "tabUser_groups" AS memberships ON memberships.user_id = users.name
    JOIN auth_group AS roles ON roles.id = memberships.group_id
    WHERE users.name IN (
        'Administrator', 'ada@example.com', 'grace@example.com', 'alan@example.com'
    )
)
SELECT COALESCE(expected.name, actual.name) AS name,
       COALESCE(expected.role, actual.role) AS role,
       CASE
           WHEN actual.name IS NULL THEN 'missing'
           WHEN expected.name IS NULL THEN 'unexpected'
           ELSE 'matches'
       END AS comparison
FROM expected
FULL OUTER JOIN actual USING (name, role)
ORDER BY name, role;

SELECT name, password IS NOT NULL AND password NOT LIKE '!%' AS usable_password
FROM "tabUser"
WHERE name IN (
    'Administrator', 'ada@example.com', 'grace@example.com', 'alan@example.com'
)
ORDER BY name;

-- ACCOUNTS (A-21 D-C): do the profile columns the body diff sees match what
-- backend_v2's seed gives a fresh suite user (accounts/dev_data.py SEEDED_USERS)?
-- Reports only whether each column matches, never its value.
WITH expected(name, first_name) AS (
    VALUES
        ('Administrator', 'Administrator'),
        ('ada@example.com', 'Ada'),
        ('grace@example.com', 'Grace'),
        ('alan@example.com', 'Alan')
)
SELECT users.name,
       users.first_name = expected.first_name AS first_name_matches,
       users.last_name = '' AS last_name_matches,
       users.full_name = expected.first_name AS full_name_matches,
       users.user_image = '' AS user_image_matches,
       users.language = '' AS language_matches,
       users.user_type = 'System User' AS user_type_matches,
       users.enabled AS enabled_matches,
       users.time_zone = '' AS time_zone_matches,
       users.mobile_no = '' AS mobile_no_matches,
       users.phone = '' AS phone_matches,
       users.email_signature = '' AS email_signature_matches
FROM expected
LEFT JOIN "tabUser" AS users USING (name)
ORDER BY name;
