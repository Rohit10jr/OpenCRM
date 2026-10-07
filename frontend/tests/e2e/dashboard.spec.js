// The dashboard: upstream's seventeen tiles (docs/FINDINGS.md 41), the period control,
// refresh, and the administrator's edit mode.
import { test, expect } from './fixtures.js'
import { waitForMethod } from './helpers.js'

const NUMBER_TITLES = [
  'Total leads',
  'Ongoing deals',
  'Won deals',
  'Average won deal value',
  'Average deal value',
  'Avg. time to close a lead',
  'Avg. time to close a deal',
]

// Chart titles are drawn by ECharts as SVG text; only charts with data draw one for sure.
const CHART_TITLES = ['Deals by stage', 'Leads by source', 'Deals by source', 'Funnel conversion']

// The grid keeps one extra `.vgl-item` as its drag placeholder; the tiles are the rest.
const tiles = (page) => page.locator('.vgl-item:not(.vgl-item--placeholder)')

async function openDashboard(page) {
  const loaded = waitForMethod(page, 'crm.api.dashboard.get_dashboard')
  await page.goto('/crm/dashboard')
  const response = await loaded
  expect(response.status()).toBe(200)
  await expect(tiles(page)).toHaveCount(17)
  return response
}

test('renders the seventeen default tiles with their titles', async ({ page }) => {
  const response = await openDashboard(page)
  const tiles = (await response.json()).message
  expect(tiles.map((tile) => tile.name)).toContain('spacer')
  for (const title of NUMBER_TITLES) {
    await expect(page.getByText(title, { exact: true })).toBeVisible()
  }
  for (const title of CHART_TITLES) {
    await expect(page.getByText(title, { exact: true }).first()).toBeVisible()
  }
})

test('choosing another period asks the backend for that range', async ({ page }) => {
  await openDashboard(page)
  await page.getByRole('button', { name: 'Last 30 Days' }).click()
  const reload = waitForMethod(page, 'crm.api.dashboard.get_dashboard')
  await page.getByRole('menuitem', { name: 'Last 7 Days' }).click()
  const response = await reload
  const body = JSON.parse(response.request().postData() || '{}')
  const days = (new Date(body.to_date) - new Date(body.from_date)) / 86_400_000
  expect(days).toBeLessThanOrEqual(7)
  await expect(page.getByRole('button', { name: 'Last 7 Days' })).toBeVisible()
  await expect(tiles(page)).toHaveCount(17)
})

test('Refresh fetches the dashboard again', async ({ page }) => {
  await openDashboard(page)
  const reload = waitForMethod(page, 'crm.api.dashboard.get_dashboard')
  await page.getByRole('button', { name: 'Refresh' }).click()
  expect((await reload).status()).toBe(200)
})

test('an administrator can enter edit mode and cancel out of it', async ({ page }) => {
  await openDashboard(page)
  await page.getByRole('button', { name: 'Edit' }).click()
  await expect(page.getByRole('button', { name: 'Chart' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reset to Default' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save' })).toBeDisabled()
  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('button', { name: 'Edit' })).toBeVisible()
  await expect(tiles(page)).toHaveCount(17)
})
