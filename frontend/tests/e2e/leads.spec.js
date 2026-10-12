// Leads: the list (docs/FINDINGS.md 40), the create dialog, the page, its status
// dropdown (which needs the seeded form scripts, FINDINGS.md 43) and deletion.
import { test, expect } from './fixtures.js'
import { uniqueName } from './helpers.js'
import { recordLinks } from './ui.js'

const TABS = ['Activity', 'Emails', 'Comments', 'Data', 'Calls', 'Tasks', 'Notes', 'Attachments']

function emailFor(name) {
  return `${name.replace(/\W+/g, '.').toLowerCase()}@example.com`
}

async function seedLead(api, first) {
  return api.create('CRM Lead', {
    first_name: first,
    last_name: 'Seeded',
    email: emailFor(first),
    status: 'New',
  })
}

test('a lead created through the API shows in the list and opens its page', async ({ page, api }) => {
  const first = uniqueName('E2E')
  const lead = await seedLead(api, first)

  await page.goto('/crm/leads')
  const row = recordLinks(page, '/crm/leads').filter({ hasText: first })
  await expect(row).toBeVisible()
  // The row link lays out as `display: contents`, so click the text inside it.
  await row.getByText(first).click()

  await expect(page).toHaveURL(new RegExp(`/crm/leads/${lead.name}`))
  await expect(page.getByText(`${first} Seeded`).first()).toBeVisible()
  for (const tab of TABS) {
    await expect(page.getByRole('tab', { name: tab })).toBeVisible()
  }
  await expect(page.getByRole('button', { name: 'Convert to Deal' })).toBeVisible()
})

test('the status dropdown in the header changes the status', async ({ page, api }) => {
  const lead = await seedLead(api, uniqueName('E2E'))
  await page.goto(`/crm/leads/${lead.name}`)
  // Scoped to the header: the activity tab has a "New" button of its own.
  const header = page.locator('#app-header')
  await header.getByRole('button', { name: 'New', exact: true }).click()
  await page.getByRole('menuitem', { name: 'Contacted' }).click()
  await expect(header.getByRole('button', { name: 'Contacted', exact: true })).toBeVisible()
  await expect.poll(async () => (await api.get('CRM Lead', lead.name)).status).toBe('Contacted')
})

test('Create Lead through the dialog lands on the new lead', async ({ page, api }) => {
  await page.goto('/crm/leads')
  await page.getByRole('button', { name: 'Create' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Create Lead' })).toBeVisible()

  const first = uniqueName('E2E')
  await dialog.getByRole('textbox', { name: 'First Name', exact: true }).fill(first)
  await dialog.getByRole('textbox', { name: 'Last Name', exact: true }).fill('Dialog')
  await dialog.getByRole('textbox', { name: 'Email', exact: true }).fill(emailFor(first))
  await dialog.getByRole('button', { name: 'Create' }).click()

  await page.waitForURL(/\/crm\/leads\/CRM-LEAD-/)
  const name = decodeURIComponent(new URL(page.url()).pathname.split('/').pop())
  api.track('CRM Lead', name)
  await expect(page.getByText(`${first} Dialog`).first()).toBeVisible()
  expect((await api.get('CRM Lead', name)).email).toBe(emailFor(first))
})

test('the dialog refuses a lead without a first name', async ({ page }) => {
  // The dialog reports the refusal by throwing, which the page leaves uncaught.
  test.info().annotations.push({ type: 'allow-page-errors' })
  await page.goto('/crm/leads')
  await page.getByRole('button', { name: 'Create' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Create' }).click()
  await expect(dialog.getByText('First Name is mandatory')).toBeVisible()
  await expect(dialog).toBeVisible()
})

test('a lead can be deleted from its page', async ({ page, api }) => {
  const lead = await seedLead(api, uniqueName('E2E'))
  await page.goto(`/crm/leads/${lead.name}`)
  // The delete control is an icon-only button with a tooltip, so it has no name; the
  // text editor's hidden "Delete table" button carries the same icon, hence `visible`.
  await page.locator('button:has(.lucide-trash-2)').locator('visible=true').first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Are you sure you want to delete')).toBeVisible()
  await dialog.getByRole('button', { name: 'Delete' }).click()
  await page.waitForURL(/\/crm\/leads\/view/)
  expect(await api.list('CRM Lead', { filters: { name: lead.name } })).toHaveLength(0)
})
