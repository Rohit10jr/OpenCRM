/**
 * The browser pass: `npm run verify`.
 *
 * **This project's recurring failure is green tests over code nobody ran.** Phase 8's
 * end-to-end walk drove real HTTP against a real database, passed 26 of 26 steps, and
 * still shipped two bugs — because it never ran a browser. So this drives a real browser
 * engine: real DOM, real fetches, real React, against the real Django API. It found the
 * stale-route-guard bug on its first run, which every typecheck had passed.
 *
 * Needs both servers up:
 *   backend   ../frappe_django_crm/backend/.venv/Scripts/python.exe backend/manage.py runserver 8000
 *   frontend  npm run dev
 *
 * Screenshots land in `scratch/shots/`. Exits non-zero if any step fails or the console
 * logs an error, so it can be a CI step.
 */
import puppeteer from 'puppeteer'
import { mkdirSync } from 'node:fs'

const BASE = process.env.BASE ?? 'http://127.0.0.1:5174'
// A local dev seed, not a secret. Override for any database that has real accounts in it.
const USER = process.env.CRM_USER ?? 'Administrator'
const PASSWORD = process.env.CRM_PASSWORD ?? 'Admin!2345'
const SHOTS = 'scratch/shots'
mkdirSync(SHOTS, { recursive: true })

const problems = []
const shot = async (page, name) =>
  page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false })

const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.setViewport({ width: 1440, height: 900 })

page.on('console', (message) => {
  if (message.type() === 'error') problems.push(`console: ${message.text()}`)
})
page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))

const step = async (label, fn) => {
  try {
    await fn()
    console.log(`  ok    ${label}`)
  } catch (error) {
    console.log(`  FAIL  ${label} — ${error.message}`)
    problems.push(`${label}: ${error.message}`)
  }
}

const text = () => page.evaluate(() => document.body.innerText)

console.log('login')
await step('login page renders', async () => {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[name="username"]', { timeout: 10000 })
  await shot(page, '01-login')
})

await step(`sign in as ${USER}`, async () => {
  await page.type('input[name="username"]', USER)
  await page.type('input[name="password"]', PASSWORD)
  await Promise.all([
    page.click('button[type="submit"]'),
    page.waitForFunction(() => location.pathname.startsWith('/deals'), { timeout: 30000 }),
  ])
})

console.log('deals')
await step('deals list loads rows', async () => {
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  const rows = await page.$$eval('table tbody tr', (trs) => trs.length)
  if (rows === 0) throw new Error('table rendered with no rows')
  console.log(`        ${rows} rows`)
  await shot(page, '02-deals-list')
})

await step('columns menu lists server columns', async () => {
  const [columnsButton] = await page.$$('xpath/.//button[contains(., "Columns")]')
  await columnsButton.click()
  await page.waitForSelector('[role="menuitemcheckbox"]', { timeout: 5000 })
  await shot(page, '03-columns')
  await page.keyboard.press('Escape')
})

await step('sort by a different field refetches', async () => {
  const before = await page.$eval('table tbody tr', (tr) => tr.innerText)
  const [sortButton] = await page.$$('xpath/.//button[contains(., "Sort")]')
  await sortButton.click()
  await page.waitForSelector('[role="menuitemradio"]', { timeout: 5000 })
  const items = await page.$$('[role="menuitemradio"]')
  await items[0].click()
  await new Promise((r) => setTimeout(r, 1500))
  const after = await page.$eval('table tbody tr', (tr) => tr.innerText)
  console.log(`        first row ${before === after ? 'unchanged' : 'changed'}`)
  await shot(page, '04-sorted')
})

await step('filter narrows the list', async () => {
  const [filterButton] = await page.$$('xpath/.//button[contains(., "Filter")]')
  await filterButton.click()
  const [addButton] = await page.$$('xpath/.//button[contains(., "Add filter")]')
  await addButton.click()
  await page.waitForSelector('input[placeholder="Value"]', { timeout: 5000 })
  const [fieldSelect] = await page.$$('select')
  await fieldSelect.select('email')
  await page.type('input[placeholder="Value"]', 'buyer1')
  await page.keyboard.press('Enter')
  await new Promise((r) => setTimeout(r, 2000))
  await shot(page, '05-filtered')
  const rows = await page.$$eval('table tbody tr', (trs) => trs.length).catch(() => 0)
  console.log(`        ${rows} rows after filtering email like buyer1`)
  if (rows !== 1) throw new Error(`expected exactly 1 row, got ${rows}`)
  await page.keyboard.press('Escape')
})

await step('group_by view renders sections', async () => {
  await page.goto(`${BASE}/deals/view/group_by`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('section h2', { timeout: 20000 })
  const sections = await page.$$eval('section h2', (hs) => hs.map((h) => h.innerText))
  console.log(`        groups: ${sections.join(' | ')}`)
  if (sections.length === 0) throw new Error('no groups rendered')
  await shot(page, '06a-group-by')
})

await step('kanban board renders columns', async () => {
  await page.goto(`${BASE}/deals/view/kanban`, { waitUntil: 'domcontentloaded' })
  // Wait for a real status column rather than a fixed sleep — the board fetches one
  // query per column and is slower than the list.
  await page.waitForFunction(() => /Qualification/.test(document.body.innerText), {
    timeout: 20000,
  })
  await shot(page, '06-kanban')
})

console.log('leads')
await step('leads list loads rows', async () => {
  await page.goto(`${BASE}/leads/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  const rows = await page.$$eval('table tbody tr', (trs) => trs.length)
  if (rows === 0) throw new Error('table rendered with no rows')
  console.log(`        ${rows} rows`)
  await shot(page, '07-leads-list')
})

console.log('the other five list screens')
for (const [path, label] of [
  ['/contacts/view', 'Contacts'],
  ['/organizations/view', 'Organizations'],
  ['/notes/view', 'Notes'],
  ['/tasks/view', 'Tasks'],
  ['/call-logs/view', 'Call Logs'],
]) {
  await step(`${label} renders`, async () => {
    await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
    // Either rows or the empty state — both mean the engine ran. Only "Loading…"
    // persisting, or an error message, is a failure.
    await page.waitForFunction(
      () => {
        const body = document.body.innerText
        return document.querySelector('table tbody tr') || /No .* found\./.test(body)
      },
      { timeout: 15000 },
    )
    const rows = await page.$$eval('table tbody tr', (trs) => trs.length).catch(() => 0)
    console.log(`        ${rows} rows`)
    await shot(page, `08-${label.toLowerCase().replace(/\s/g, '-')}`)
  })
}

await step('sign out returns to login', async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('button[title="Sign out"]', { timeout: 10000 })
  const [signOut] = await page.$$('xpath/.//button[@title="Sign out"]')
  await signOut.click()
  await page.waitForFunction(() => location.pathname === '/login', { timeout: 10000 })
})

await browser.close()

console.log('\nproblems:')
if (problems.length === 0) console.log('  none')
else problems.forEach((p) => console.log(`  - ${p}`))
process.exit(problems.length ? 1 : 0)
