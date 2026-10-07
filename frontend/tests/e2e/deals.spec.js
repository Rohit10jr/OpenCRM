// Deals: the page for a seeded deal, and the create dialog, which makes an organization
// and a contact along with the deal through crm_deal.create_deal.
import { test, expect } from './fixtures.js'
import { uniqueName } from './helpers.js'
import { recordLinks } from './ui.js'

test('a deal created through the API opens with its tabs, status and side panel', async ({
  page,
  api,
}) => {
  const org = await api.create('CRM Organization', { organization_name: uniqueName('E2E Org') })
  const deal = await api.create('CRM Deal', { organization: org.name, status: 'Qualification' })

  await page.goto('/crm/deals')
  await expect(recordLinks(page, '/crm/deals').filter({ hasText: org.name })).toBeVisible()

  await page.goto(`/crm/deals/${deal.name}`)
  await expect(page.getByRole('tab', { name: 'Activity' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Qualification', exact: true })).toBeVisible()
  await expect(page.getByText('Organization Details')).toBeVisible()
  await expect(page.getByText('Contacts', { exact: true }).first()).toBeVisible()
})

test('Create Deal through the dialog, with a new organization and contact', async ({ page, api }) => {
  await page.goto('/crm/deals')
  await page.getByRole('button', { name: 'Create' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Create Deal' })).toBeVisible()

  const orgName = uniqueName('E2E Org')
  const first = uniqueName('E2E')
  const email = `${first.replace(/\W+/g, '.').toLowerCase()}@example.com`
  await dialog.getByRole('textbox', { name: 'Organization Name', exact: true }).fill(orgName)
  await dialog.getByRole('textbox', { name: 'First Name', exact: true }).fill(first)
  await dialog.getByRole('textbox', { name: 'Email', exact: true }).fill(email)
  await dialog.getByRole('button', { name: 'Create' }).click()

  await page.waitForURL(/\/crm\/deals\/CRM-DEAL-/)
  const name = decodeURIComponent(new URL(page.url()).pathname.split('/').pop())
  // Clean up in reverse order: the deal, then the contact, then the organization.
  api.track('CRM Organization', orgName)
  for (const contact of await api.list('Contact', { filters: { email_id: email } })) {
    api.track('Contact', contact.name)
  }
  api.track('CRM Deal', name)

  const deal = await api.get('CRM Deal', name)
  expect(deal.organization).toBe(orgName)
  await expect(page.getByText(orgName).first()).toBeVisible()
})
