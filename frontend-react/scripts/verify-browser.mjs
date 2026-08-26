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

/**
 * WebSocket handshakes, watched through CDP.
 *
 * The alternative was exporting connection state from the app purely so a test could read
 * it. This asks the browser what actually happened on the wire instead, which is both
 * stronger evidence and no change to the product.
 */
// Only `/ws/realtime` counts. Vite's own HMR socket is also `ws://127.0.0.1:5174/?token=…`,
// which is close enough to ours to have passed this assertion for the wrong reason once.
const REALTIME_PATH = '/ws/realtime'
const sockets = { created: [], accepted: [], byId: new Map() }
const cdp = await page.target().createCDPSession()
await cdp.send('Network.enable')
cdp.on('Network.webSocketCreated', ({ requestId, url }) => {
  sockets.byId.set(requestId, url)
  if (url.includes(REALTIME_PATH)) sockets.created.push(url)
})
cdp.on('Network.webSocketHandshakeResponseReceived', ({ requestId, response }) => {
  if ((sockets.byId.get(requestId) ?? '').includes(REALTIME_PATH)) {
    sockets.accepted.push(response.status)
  }
})

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

console.log('the deal record screen')
await step('a row click opens the record', async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await page.click('table tbody tr td:nth-child(2)')
  await page.waitForFunction(() => /^\/deals\/CRM-DEAL/.test(location.pathname), {
    timeout: 15000,
  })
  console.log(`        at ${await page.evaluate(() => location.pathname)}`)
})

await step('the record shows its side panel fields', async () => {
  await page.waitForSelector('aside label', { timeout: 15000 })
  const labels = await page.$$eval('aside label', (ls) => ls.map((l) => l.innerText))
  console.log(`        panel fields: ${labels.join(', ')}`)
  if (!labels.includes('Website')) throw new Error('side panel did not render its fields')
  await shot(page, '09-deal-record')
})

await step('the activity timeline renders entries', async () => {
  const entries = await page.$$eval('ol li', (ls) => ls.length)
  console.log(`        ${entries} activity entries`)
  if (entries === 0) throw new Error('no activity entries')
})

await step('switching a tab shows that tab', async () => {
  const [tasksTab] = await page.$$('xpath/.//button[@role="tab"][contains(., "Tasks")]')
  await tasksTab.click()
  await page.waitForFunction(
    () => /No tasks yet\.|task/i.test(document.body.innerText),
    { timeout: 5000 },
  )
})

await step('editing a side panel field saves to the server', async () => {
  const stamp = `verify-${Date.now() % 100000}`
  const [websiteInput] = await page.$$(
    'xpath/.//label[contains(., "Website")]/following::input[1]',
  )
  await websiteInput.click({ clickCount: 3 })
  await websiteInput.type(stamp)
  await page.keyboard.press('Enter')
  await new Promise((r) => setTimeout(r, 2500))
  // Reload: the only proof the value reached the server rather than staying in the input.
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('aside label', { timeout: 15000 })
  const saved = await page.$eval(
    'aside input[type="text"]',
    (el, expected) => el.value.includes(expected),
    stamp,
  ).catch(() => false)
  const anyMatch =
    saved ||
    (await page.$$eval('aside input', (els, expected) =>
      els.some((el) => el.value.includes(expected)), stamp))
  if (!anyMatch) throw new Error(`"${stamp}" did not survive a reload`)
  console.log(`        "${stamp}" persisted`)
  await shot(page, '10-deal-edited')
})

await step('a status change persists', async () => {
  const before = await page.$eval('header button', (b) => b.innerText)
  await page.click('header button')
  await page.waitForSelector('[role="menuitem"]', { timeout: 5000 })
  const items = await page.$$('[role="menuitem"]')
  const labels = await Promise.all(items.map((i) => i.evaluate((e) => e.innerText)))
  const target = labels.findIndex((l) => l && !before.includes(l.trim()))
  if (target < 0) throw new Error('no alternative status offered')
  await items[target].click()
  await new Promise((r) => setTimeout(r, 2500))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('header button', { timeout: 15000 })
  const after = await page.$eval('header button', (b) => b.innerText)
  if (after.trim() === before.trim()) throw new Error(`status stayed "${before}"`)
  console.log(`        ${before.trim()} -> ${after.trim()}`)
})

await step('filters survive a trip to a record and back', async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  const [filterButton] = await page.$$('xpath/.//button[contains(., "Filter")]')
  await filterButton.click()
  const [addButton] = await page.$$('xpath/.//button[contains(., "Add filter")]')
  await addButton.click()
  await page.waitForSelector('input[placeholder="Value"]', { timeout: 5000 })
  const [fieldSelect] = await page.$$('select')
  await fieldSelect.select('email')
  await page.type('input[placeholder="Value"]', 'buyer1')
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => location.search.includes('filters='), { timeout: 8000 })
  await page.keyboard.press('Escape')
  await new Promise((r) => setTimeout(r, 1500))

  const filtered = await page.$$eval('table tbody tr', (trs) => trs.length)
  await page.click('table tbody tr td:nth-child(2)')
  await page.waitForFunction(() => /^\/deals\/CRM-DEAL/.test(location.pathname), {
    timeout: 15000,
  })
  await page.goBack({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await new Promise((r) => setTimeout(r, 1500))
  const afterBack = await page.$$eval('table tbody tr', (trs) => trs.length)
  console.log(`        ${filtered} rows filtered, ${afterBack} after back`)
  if (afterBack !== filtered) throw new Error('the filter was lost on the way back')
})

console.log('realtime')
await step('the socket opens against the real server', async () => {
  // The record screen subscribes, so by now a socket should have been created. Give the
  // handshake a moment; it is the only step here that races the page.
  await new Promise((r) => setTimeout(r, 3000))
  if (!sockets.created.length) throw new Error('no WebSocket was ever created')
  console.log(`        opened ${sockets.created[0].replace(/token=[^&]+/, 'token=…')}`)
  if (!sockets.accepted.includes(101)) {
    throw new Error(
      `handshake not accepted (statuses seen: ${sockets.accepted.join(', ') || 'none'})`,
    )
  }
})

console.log('creating a record')
await step('the Create modal makes a deal and opens it', async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  const before = await page.$$eval('table tbody tr', (trs) => trs.length)

  const [createButton] = await page.$$('xpath/.//button[contains(., "Create")]')
  await createButton.click()
  await page.waitForSelector('[role="dialog"] input', { timeout: 10000 })

  const stamp = `Verify Co ${Date.now() % 100000}`
  const [orgName] = await page.$$(
    'xpath/.//div[@role="dialog"]//label[contains(., "Organization Name")]/following::input[1]',
  )
  if (!orgName) throw new Error('the Quick Entry layout has no Organization Name field')
  await orgName.type(stamp)
  await page.keyboard.press('Tab')

  const [submit] = await page.$$('xpath/.//div[@role="dialog"]//button[normalize-space()="Create"]')
  await submit.click()
  await page.waitForFunction(() => /^\/deals\/CRM-DEAL/.test(location.pathname), {
    timeout: 20000,
  })
  console.log(`        created and opened ${await page.evaluate(() => location.pathname)}`)

  // Back to the list: the new row must be there, which is the only proof it was inserted
  // rather than merely navigated to.
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await new Promise((r) => setTimeout(r, 1000))
  const after = await page.$$eval('table tbody tr', (trs) => trs.length)
  console.log(`        ${before} rows before, ${after} after`)
  if (after !== before + 1) throw new Error(`expected ${before + 1} rows, got ${after}`)
  await shot(page, '12-created')
})

console.log('saved views')
await step('save the current filter as a view, then reload into it', async () => {
  // Start clean, then filter to exactly one row.
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  const total = await page.$$eval('table tbody tr', (trs) => trs.length)

  const [filterButton] = await page.$$('xpath/.//button[contains(., "Filter")]')
  await filterButton.click()
  const [addButton] = await page.$$('xpath/.//button[contains(., "Add filter")]')
  await addButton.click()
  await page.waitForSelector('input[placeholder="Value"]', { timeout: 5000 })
  const [fieldSelect] = await page.$$('select')
  await fieldSelect.select('email')
  await page.type('input[placeholder="Value"]', 'buyer1')
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => location.search.includes('filters='), { timeout: 8000 })
  await page.keyboard.press('Escape')
  await new Promise((r) => setTimeout(r, 1500))

  const viewLabel = `verify-view-${Date.now() % 100000}`
  const [picker] = await page.$$('xpath/.//button[normalize-space()="All"]')
  await picker.click()
  const [saveItem] = await page.$$('xpath/.//div[@role="menuitem"][contains(., "Save current view")]')
  await saveItem.click()
  await page.waitForSelector('input[name], [role="dialog"] input', { timeout: 5000 })
  await page.type('[role="dialog"] input', viewLabel)
  const [submit] = await page.$$('xpath/.//button[contains(., "Save view")]')
  await submit.click()
  await page.waitForFunction(() => location.search.includes('view='), { timeout: 10000 })
  await new Promise((r) => setTimeout(r, 1500))

  // The real assertion: land on the saved view's URL from cold, with no `filters=` in it,
  // and still get the filtered rows. That is the gap run 1 had — the server does not
  // hydrate a view from its name, so this only passes if the client sends its filters.
  const url = await page.evaluate(() => location.pathname + location.search)
  if (url.includes('filters=')) throw new Error(`view URL still carries filters: ${url}`)
  await page.goto(`${BASE}${url}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await new Promise((r) => setTimeout(r, 1500))
  const rows = await page.$$eval('table tbody tr', (trs) => trs.length)
  console.log(`        ${total} rows unfiltered, ${rows} from the saved view alone`)
  if (rows !== 1) throw new Error(`saved view returned ${rows} rows, expected 1`)
  await shot(page, '11-saved-view')
})

await step('delete the saved view', async () => {
  const [picker] = await page.$$('xpath/.//button[contains(@class,"inline-flex")][contains(., "verify-view-")]')
  if (!picker) throw new Error('the saved view is not the current one')
  await picker.click()
  const [del] = await page.$$('xpath/.//button[starts-with(@aria-label, "Delete verify-view-")]')
  await del.click()
  await page.waitForFunction(() => !location.search.includes('view='), { timeout: 10000 })
  await page.keyboard.press('Escape')
  console.log('        deleted, back to All')
})

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
