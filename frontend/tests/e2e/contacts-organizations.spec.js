// Contacts and organizations: their create dialogs and pages.
import { test, expect } from './fixtures.js'
import { uniqueName } from './helpers.js'

test('New Organization creates and opens the organization', async ({ page, api }) => {
  await page.goto('/crm/organizations')
  await page.getByRole('button', { name: 'Create' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'New Organization' })).toBeVisible()

  const orgName = uniqueName('E2E Org')
  await dialog.getByRole('textbox', { name: 'Organization Name', exact: true }).fill(orgName)
  await dialog.getByRole('button', { name: 'Create' }).click()

  await page.waitForURL(/\/crm\/organizations\/(?!view)/)
  api.track('CRM Organization', orgName)
  await expect(page.getByText(orgName).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Delete' })).toBeVisible()
})

test('New Contact creates and opens the contact', async ({ page, api }) => {
  await page.goto('/crm/contacts')
  await page.getByRole('button', { name: 'Create' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'New Contact' })).toBeVisible()

  const first = uniqueName('E2E')
  const email = `${first.replace(/\W+/g, '.').toLowerCase()}@example.com`
  // Contact's labels come from the model here rather than upstream's JSON, so their
  // case differs ("first name", FINDINGS.md 44); match the names loosely.
  await dialog.getByRole('textbox', { name: /^first ?name$/i }).fill(first)
  await dialog.getByRole('textbox', { name: /^last ?name$/i }).fill('Contact')
  await dialog.getByRole('textbox', { name: /^email/i }).fill(email)
  await dialog.getByRole('button', { name: 'Create' }).click()

  await page.waitForURL(/\/crm\/contacts\/(?!view)/)
  const name = decodeURIComponent(new URL(page.url()).pathname.split('/').pop())
  api.track('Contact', name)
  await expect(page.getByText(`${first} Contact`).first()).toBeVisible()
  expect((await api.get('Contact', name)).email_id).toBe(email)
})

test('an organization page shows its details and a labelled Delete button', async ({ page, api }) => {
  const org = await api.create('CRM Organization', {
    organization_name: uniqueName('E2E Org'),
    website: 'https://example.com',
  })
  await page.goto(`/crm/organizations/${encodeURIComponent(org.name)}`)
  await expect(page.locator('#app-header').getByText(org.name)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Delete' })).toBeVisible()
})
