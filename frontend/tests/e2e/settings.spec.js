// The user menu at the top of the sidebar (docs/FINDINGS.md 42) and the Settings dialog
// it opens, which reads the FCRM Settings document (FINDINGS.md 37).
import { test, expect } from './fixtures.js'
import { userMenuButton } from './ui.js'

async function openUserMenu(page) {
  await page.goto('/crm/leads')
  await userMenuButton(page).click()
}

test('the user menu lists the standard items', async ({ page }) => {
  await openUserMenu(page)
  for (const item of ['Settings', 'About', 'Log out']) {
    await expect(page.getByRole('menuitem', { name: item })).toBeVisible()
  }
})

test('Settings opens on the profile page and switches to General', async ({ page }) => {
  await openUserMenu(page)
  await page.getByRole('menuitem', { name: 'Settings' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('Manage your profile & login information.')).toBeVisible()

  await dialog.getByRole('button', { name: 'General', exact: true }).click()
  await expect(dialog.getByText('General Settings')).toBeVisible()
  await expect(dialog.getByText('Timeline timestamp format')).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
})

test('an administrator sees the management sections', async ({ page }) => {
  await openUserMenu(page)
  await page.getByRole('menuitem', { name: 'Settings' }).click()
  const dialog = page.getByRole('dialog')
  for (const item of ['Users', 'Invite User', 'Brand', 'Dashboard']) {
    await expect(dialog.getByRole('button', { name: item, exact: true })).toBeVisible()
  }
})

test('About opens its dialog', async ({ page }) => {
  await openUserMenu(page)
  await page.getByRole('menuitem', { name: 'About' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
})
