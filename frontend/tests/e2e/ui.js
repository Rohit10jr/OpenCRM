// Locators for the app's fixed furniture, shared by the specs. (A spec file must not be
// imported by another: Playwright would register its tests twice.)

/** The sidebar: frappe-ui's `Sidebar` root carries this data attribute. */
export const sidebar = (page) => page.locator('[data-slot="sidebar"]')

/** The user menu's trigger at the top of the sidebar: the first button in it. */
export const userMenuButton = (page) => sidebar(page).locator('button').first()

/** Row links point at `/crm/<section>/<record>`; the sidebar and breadcrumb point at `/view`. */
export function recordLinks(page, base) {
  return page.locator(`a[href^="${base}/"]:not([href*="${base}/view"])`)
}

// Each list page: its sidebar label, path, and how a row shows up once loaded.
// Leads, deals, contacts and organizations render rows as links to the record; tasks and
// call logs render rows as buttons that open a dialog; notes are cards.
export const LISTS = [
  { label: 'Leads', path: '/crm/leads', rows: (page) => recordLinks(page, '/crm/leads') },
  { label: 'Deals', path: '/crm/deals', rows: (page) => recordLinks(page, '/crm/deals') },
  { label: 'Contacts', path: '/crm/contacts', rows: (page) => recordLinks(page, '/crm/contacts') },
  {
    label: 'Organizations',
    path: '/crm/organizations',
    rows: (page) => recordLinks(page, '/crm/organizations'),
  },
  { label: 'Notes', path: '/crm/notes', rows: (page) => page.locator('div.h-56.cursor-pointer') },
  { label: 'Tasks', path: '/crm/tasks', rows: (page) => page.locator('div.overflow-y-auto button') },
  {
    label: 'Call Logs',
    path: '/crm/call-logs',
    rows: (page) => page.locator('div.overflow-y-auto button'),
  },
]
