// The sidebar, every list page, the notifications panel and the catch-all page.
import { test, expect } from './fixtures.js'
import { LISTS, sidebar } from './ui.js'

test('the sidebar offers every section and the notifications button', async ({ page }) => {
  await page.goto('/crm/leads')
  for (const name of ['Dashboard', ...LISTS.map((list) => list.label)]) {
    await expect(sidebar(page).getByRole('link', { name, exact: true })).toBeVisible()
  }
  await expect(sidebar(page).getByRole('button', { name: 'Notifications' })).toBeVisible()
})

for (const list of LISTS) {
  test(`${list.label}: the list page loads and shows rows or its empty state`, async ({ page }) => {
    await page.goto(list.path)
    await expect(page.locator('#app-header').getByText(list.label, { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Create' })).toBeVisible()
    // Never a blank pane: either rows, or the empty state that names the section.
    await expect(list.rows(page).first().or(page.getByText(`No ${list.label} Found`))).toBeVisible()
  })
}

test('clicking a sidebar link changes the page', async ({ page }) => {
  await page.goto('/crm/leads')
  await sidebar(page).getByRole('link', { name: 'Contacts', exact: true }).click()
  await expect(page).toHaveURL(/\/crm\/contacts/)
  await expect(page.locator('#app-header').getByText('Contacts', { exact: true })).toBeVisible()
})

test('the notifications panel opens from the sidebar', async ({ page }) => {
  await page.goto('/crm/leads')
  await sidebar(page).getByRole('button', { name: 'Notifications' }).click()
  // The panel's own header, beside the sidebar label of the same name.
  await expect(page.getByText('Notifications', { exact: true })).toHaveCount(2)
})

test('an unknown path shows the invalid-page message', async ({ page }) => {
  await page.goto('/crm/no-such-page')
  await expect(page.getByText('Invalid page or not permitted to access')).toBeVisible()
})
