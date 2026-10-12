// What a plain Sales User sees: no dashboard editing and no management settings.
// Signs in fresh as ada, so the administrator state from auth.setup.js is not used.
import { test, expect } from './fixtures.js'
import { login } from './helpers.js'
import { users } from './users.js'
import { userMenuButton } from './ui.js'

test.use({ storageState: { cookies: [], origins: [] } })

test('a Sales User gets the dashboard without the Edit button', async ({ page }) => {
  await login(page, users.sales)
  await page.goto('/crm/dashboard')
  await expect(page.locator('.vgl-item:not(.vgl-item--placeholder)')).toHaveCount(17)
  await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit' })).toHaveCount(0)
})

test('a Sales User gets Settings without the management sections', async ({ page }) => {
  await login(page, users.sales)
  await page.goto('/crm/leads')
  await userMenuButton(page).click()
  await page.getByRole('menuitem', { name: 'Settings' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('button', { name: 'Profile', exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Users', exact: true })).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: 'Invite User', exact: true })).toHaveCount(0)
})
