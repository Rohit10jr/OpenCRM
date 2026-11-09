import { Buffer } from 'node:buffer'

import { test, expect } from './fixtures.js'
import { login, uniqueName } from './helpers.js'
import { users } from './users.js'

const IMPORT_TIMEOUT = 120_000

async function uploadAndOpenPreview(page, api, doctype, csv, firstHeader) {
  await page.goto(`/crm/data-import/doctype/${encodeURIComponent(doctype)}`)

  const fileName = `${uniqueName('E2E Import').replaceAll(' ', '-')}.csv`
  const uploadFinished = page.waitForResponse(
    (response) =>
      response.url().includes('/api/method/upload_file') && response.request().method() === 'POST',
  )
  await page.locator('input[type="file"]').setInputFiles({
    name: fileName,
    mimeType: 'text/csv',
    buffer: Buffer.from(csv),
  })

  const uploadResponse = await uploadFinished
  expect(uploadResponse.ok()).toBe(true)
  const uploadedFile = (await uploadResponse.json()).message
  api.track('File', uploadedFile.name)
  await expect(page.getByText(fileName, { exact: true })).toBeVisible()

  const dataImportCreated = page.waitForURL(
    (url) => /^\/crm\/data-import\/[^/]+$/.test(url.pathname) && !url.pathname.endsWith('/doctype'),
  )
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await dataImportCreated
  const dataImportName = decodeURIComponent(new URL(page.url()).pathname.split('/').pop())
  api.track('Data Import', dataImportName)

  await expect(page.getByText(firstHeader, { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page.getByText('Review and Import', { exact: true })).toBeVisible()

  return dataImportName
}

async function runImportAndWait(page, status) {
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  await expect(page.getByText(status, { exact: true })).toBeVisible({ timeout: IMPORT_TIMEOUT })
}

test('imports Contacts from an uploaded CSV', async ({ page, api }) => {
  const firstName = uniqueName('E2E Import')
  const lastName = 'Contact'
  const email = `${firstName.replace(/\W+/g, '.').toLowerCase()}@example.com`
  const mobile = '+1 555 0100'
  const csv =
    'First Name,Last Name,Email ID (Email IDs),Number (Contact Numbers)\r\n' +
    `${firstName},${lastName},${email},${mobile}\r\n`

  await page.goto('/crm/data-import/doctype/Contact')
  await expect(page.getByText('Google Sheet', { exact: true })).toBeHidden()
  await expect(page.getByText('Device', { exact: true })).toBeVisible()

  await uploadAndOpenPreview(page, api, 'Contact', csv, 'First Name')
  await runImportAndWait(page, 'Success')

  const contacts = await api.list('Contact', {
    filters: { first_name: firstName, last_name: lastName },
    fields: ['name', 'email_id', 'mobile_no'],
  })
  expect(contacts).toHaveLength(1)
  api.track('Contact', contacts[0].name)
  expect(contacts[0].email_id).toBe(email)
  expect(contacts[0].mobile_no).toBe(mobile)

  await page.getByRole('button', { name: 'Done', exact: true }).click()
  await page.waitForURL(/\/crm\/contacts(?:\/|$)/)
  await expect(page.getByText(`${firstName} ${lastName}`, { exact: true })).toBeVisible()
})

test('retries a failed import row without importing the successful row twice', async ({ page, api }) => {
  const existingName = uniqueName('E2E Existing Org')
  const newName = uniqueName('E2E Imported Org')
  await api.create('CRM Organization', { organization_name: existingName })
  const csv = `Organization Name\r\n${newName}\r\n${existingName}\r\n`

  await uploadAndOpenPreview(page, api, 'CRM Organization', csv, 'Organization Name')
  await runImportAndWait(page, 'Partial Success')
  api.track('CRM Organization', newName)

  await expect(page.getByText('Import Logs', { exact: true })).toBeVisible()
  await expect(
    page.getByText('1 row imported successfully, 1 row failed.', { exact: true }),
  ).toBeVisible()
  const logRows = page.locator('table').last().locator('tbody tr')
  await expect(logRows).toHaveCount(2)
  await expect(logRows.filter({ hasText: existingName })).toContainText('already exists')

  await api.remove('CRM Organization', existingName)
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByText('Success', { exact: true })).toBeVisible({ timeout: IMPORT_TIMEOUT })

  for (const organizationName of [newName, existingName]) {
    const organizations = await api.list('CRM Organization', {
      filters: { organization_name: organizationName },
      fields: ['name'],
    })
    expect(organizations).toHaveLength(1)
  }
})

test.describe('Sales User list options', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('offers Export but not Import', async ({ page }) => {
    await login(page, users.sales)
    await page.goto('/crm/contacts')

    const optionsButton = page.locator('button:has(> .lucide-more-horizontal)')
    await expect(optionsButton).toBeVisible()
    await optionsButton.click()
    await expect(page.getByRole('menuitem', { name: 'Export', exact: true })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: 'Import', exact: true })).toHaveCount(0)
  })
})
