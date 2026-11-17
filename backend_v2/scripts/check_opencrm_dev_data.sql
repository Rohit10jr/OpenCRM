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
