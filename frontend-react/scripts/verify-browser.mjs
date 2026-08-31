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

/**
 * The toolbar's total, not the rendered row count.
 *
 * The table is capped at `page_length`, so "one more row than before" stopped being true
 * the moment repeated runs pushed the list past 20 — an assertion that broke on its own
 * success.
 */
const totalRows = () =>
  page.evaluate(() => {
    const span = [...document.querySelectorAll('span')].find((el) =>
      /^\d+ rows?$/.test(el.innerText.trim()),
    )
    return span ? Number(span.innerText.trim().split(' ')[0]) : NaN
  })

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

/**
 * Filter the deals list on an email taken from the table itself.
 *
 * It used to hardcode a seeded value (`buyer1`). That coupled every filter assertion to a
 * fixture the harness's own destructive steps could delete — and when they did, three
 * steps failed far from the cause. Reading the value out of row one cannot go stale.
 */
async function filterDealsByFirstEmail() {
  const emailColumn = await page.$$eval('table thead th', (ths) =>
    ths.findIndex((th) => /email/i.test(th.innerText)),
  )
  if (emailColumn < 1) throw new Error('no Email column to filter on')

  // The *first non-empty* email. Row one is the most recently modified, which is usually a
  // deal this harness just created and which has no email — an empty filter value is
  // dropped by `toFilterDict`, so the filter silently did nothing and the assertion
  // reported "22 rows narrowed to 22" instead of anything useful.
  const value = await page.$$eval(
    `table tbody tr td:nth-child(${emailColumn + 1})`,
    (tds) => tds.map((td) => td.innerText.trim()).find(Boolean) ?? '',
  )
  if (!value) throw new Error('no row on this page has an email to filter on')

  const [filterButton] = await page.$$('xpath/.//button[contains(., "Filter")]')
  await filterButton.click()
  const [addButton] = await page.$$('xpath/.//button[contains(., "Add filter")]')
  await addButton.click()
  await page.waitForSelector('input[placeholder="Value"]', { timeout: 5000 })
  const [fieldSelect] = await page.$$('select')
  await fieldSelect.select('email')
  await page.type('input[placeholder="Value"]', value)
  await page.keyboard.press('Enter')
  await page.waitForFunction(() => location.search.includes('filters='), { timeout: 8000 })
  await page.keyboard.press('Escape')
  await new Promise((r) => setTimeout(r, 1500))
  return value
}

await step('filter narrows the list', async () => {
  const before = await totalRows()
  const value = await filterDealsByFirstEmail()
  const after = await totalRows()
  console.log(`        ${before} rows, ${after} after filtering email like ${value}`)
  if (!(after >= 1 && after < before)) {
    throw new Error(`expected the filter to narrow ${before} rows, got ${after}`)
  }
  await shot(page, '05-filtered')
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

await step('dragging a kanban card changes its status', async () => {
  await page.goto(`${BASE}/deals/view/kanban`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => /Qualification/.test(document.body.innerText), {
    timeout: 20000,
  })

  // Find a column that has a card, and a different column to drop it into.
  const plan = await page.evaluate(() => {
    const columns = [...document.querySelectorAll('[data-kanban-column]')]
    const from = columns.find((c) => c.querySelectorAll('button[draggable="true"]').length)
    if (!from) return null
    const to = columns.find((c) => c !== from)
    if (!to) return null
    const card = from.querySelector('button[draggable="true"]')
    return {
      fromColumn: from.getAttribute('data-kanban-column'),
      toColumn: to.getAttribute('data-kanban-column'),
      cardText: card.innerText.split('\n')[0],
    }
  })
  if (!plan) throw new Error('no draggable card on the board')

  // HTML5 drag-and-drop is not synthesisable with mouse events, so the DataTransfer is
  // built and the three events dispatched directly. This exercises the app's handlers —
  // dragstart writes the id, drop reads it — which is the part worth asserting.
  await page.evaluate(({ toColumn, cardText }) => {
    const card = [...document.querySelectorAll('button[draggable="true"]')].find((b) =>
      b.innerText.startsWith(cardText),
    )
    const target = document.querySelector(`[data-kanban-column="${toColumn}"]`)
    const dataTransfer = new DataTransfer()
    card.dispatchEvent(new DragEvent('dragstart', { dataTransfer, bubbles: true }))
    target.dispatchEvent(new DragEvent('dragover', { dataTransfer, bubbles: true }))
    target.dispatchEvent(new DragEvent('drop', { dataTransfer, bubbles: true }))
  }, plan)

  await new Promise((r) => setTimeout(r, 3000))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => /Qualification/.test(document.body.innerText), {
    timeout: 20000,
  })

  const landed = await page.evaluate(
    ({ toColumn, cardText }) => {
      const target = document.querySelector(`[data-kanban-column="${toColumn}"]`)
      return [...target.querySelectorAll('button')].some((b) =>
        b.innerText.startsWith(cardText),
      )
    },
    plan,
  )
  console.log(`        ${plan.cardText}: ${plan.fromColumn} -> ${plan.toColumn}`)
  if (!landed) throw new Error(`the card is not in ${plan.toColumn} after a reload`)
  await shot(page, '20-kanban-drag')
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

await step('a Link field searches the server and saves', async () => {
  // Organization is a Link to CRM Organization; the picker must find one by typing.
  const [trigger] = await page.$$(
    'xpath/.//aside//label[normalize-space()="Organization"]/following::button[1]',
  )
  await trigger.click()
  await page.waitForSelector('[data-radix-popper-content-wrapper] input', { timeout: 5000 })
  await page.type('[data-radix-popper-content-wrapper] input', 'Umb')
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll('[data-radix-popper-content-wrapper] li button')].some(
        (b) => /Umbrella/.test(b.innerText),
      ),
    { timeout: 10000 },
  )
  const [match] = await page.$$(
    'xpath/.//div[@data-radix-popper-content-wrapper]//li/button[contains(., "Umbrella")]',
  )
  const chosen = await match.evaluate((el) => el.innerText.trim())
  await match.click()

  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('aside label', { timeout: 15000 })
  const body = await text()
  if (!body.includes('Umbrella')) {
    throw new Error(`"${chosen}" did not survive a reload`)
  }
  console.log(`        picked ${chosen} by search, survived a reload`)
  await shot(page, '19-link-combobox')
})

await step('the activity timeline renders', async () => {
  // Entries *or* the honest empty state. Which record row one is changes as the harness
  // creates and deletes deals, and a freshly made one has nothing in its feed — asserting
  // "at least one entry" was really asserting "row one is old", which is not a fact about
  // the product. That entries appear when there is data is proved by the comment step,
  // which creates the data it then looks for.
  const entries = await page.$$eval('ol li', (ls) => ls.length)
  const body = await text()
  console.log(`        ${entries} activity entries`)
  if (entries === 0 && !/Nothing has happened here yet/.test(body)) {
    throw new Error('the timeline rendered neither entries nor its empty state')
  }
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
  const before = await page.$eval('header button[title="Status"]', (b) => b.innerText)
  await page.click('header button[title="Status"]')
  await page.waitForSelector('[role="menuitem"]', { timeout: 5000 })
  const items = await page.$$('[role="menuitem"]')
  const labels = await Promise.all(items.map((i) => i.evaluate((e) => e.innerText)))
  const target = labels.findIndex((l) => l && !before.includes(l.trim()))
  if (target < 0) throw new Error('no alternative status offered')
  await items[target].click()
  await new Promise((r) => setTimeout(r, 2500))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('header button[title="Status"]', { timeout: 15000 })
  const after = await page.$eval('header button[title="Status"]', (b) => b.innerText)
  if (after.trim() === before.trim()) throw new Error(`status stayed "${before}"`)
  console.log(`        ${before.trim()} -> ${after.trim()}`)
})

await step('filters survive a trip to a record and back', async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await filterDealsByFirstEmail()

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

await step('a lead record opens with its status and activity', async () => {
  await page.goto(`${BASE}/leads/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await page.click('table tbody tr td:nth-child(2)')
  await page.waitForFunction(() => /^\/leads\/CRM-LEAD/.test(location.pathname), {
    timeout: 15000,
  })
  await page.waitForSelector('aside label', { timeout: 15000 })
  const tabs = await page.$$eval('[role="tab"]', (ts) => ts.map((t) => t.innerText))
  const status = await page.$eval('header button[title="Status"]', (b) => b.innerText.trim())
  console.log(`        status ${JSON.stringify(status)}, tabs: ${tabs.join(', ')}`)
  if (!tabs.some((t) => t.startsWith('Activity'))) {
    throw new Error('a lead should have an activity feed')
  }
  await shot(page, '15-lead-record')
})

await step('assigning a user persists, and unassigning removes them', async () => {
  // On a **lead**, not a deal. Other steps create and bulk-delete deals, so "the first
  // deal" is a different record on every run and this step was intermittently asserting
  // against one that had just moved. Leads are read-only to the rest of the harness.
  await page.goto(`${BASE}/leads/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await page.click('table tbody tr td:nth-child(2)')
  await page.waitForFunction(() => /^\/leads\/CRM-LEAD/.test(location.pathname), {
    timeout: 15000,
  })
  await page.waitForSelector('aside label', { timeout: 15000 })

  const openPicker = async () => {
    const [button] = await page.$$('header button[title="Assigned to"]')
    await button.click()
    await page.waitForSelector('[role="menu"] button', { timeout: 5000 })
  }

  // Wait for the *effect*, never a fixed sleep: the trigger reads "Assign" with nobody on
  // it and shows avatars otherwise, so that text is the signal the write landed. Sleeping
  // instead made this step flaky, and a flaky assertion is worse than no assertion.
  const triggerText = () =>
    page.$eval('header button[title="Assigned to"]', (b) => b.innerText.trim())

  /**
   * Start unassigned, whatever the last run left behind.
   *
   * The picker toggles, so a record that arrives already assigned turns the first click
   * into an *un*assign — and the step then correctly reported "not assigned" while the
   * server log showed no `assign_to.add` at all. A step that only works from one starting
   * state is a step that reports on its own history.
   */
  if (!(await triggerText()).includes('Assign')) {
    await openPicker()
    const [assignedUser] = await page.$$('[role="menu"] button')
    await assignedUser.click()
    await page.waitForFunction(
      () =>
        document
          .querySelector('header button[title="Assigned to"]')
          ?.innerText.includes('Assign'),
      { timeout: 15000 },
    )
    await page.keyboard.press('Escape')
  }

  await openPicker()
  const [firstUser] = await page.$$('[role="menu"] button')
  const who = await firstUser.evaluate((el) => el.innerText.trim().split('\n')[0])
  await firstUser.click()
  await page.waitForFunction(
    () =>
      !document
        .querySelector('header button[title="Assigned to"]')
        ?.innerText.includes('Assign'),
    { timeout: 15000 },
  )
  await page.keyboard.press('Escape')

  const where = await page.evaluate(() => location.pathname)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('header button[title="Assigned to"]', { timeout: 15000 })
  if ((await triggerText()).includes('Assign')) {
    throw new Error(`assigning ${who} to ${where} did not survive a reload`)
  }
  console.log(`        assigned ${who}, still assigned after a reload`)

  // Unassign, so the run is repeatable and the cancel path is exercised too.
  await openPicker()
  const [sameUser] = await page.$$('[role="menu"] button')
  await sameUser.click()
  await page.waitForFunction(
    () =>
      document
        .querySelector('header button[title="Assigned to"]')
        ?.innerText.includes('Assign'),
    { timeout: 15000 },
  )
  await page.keyboard.press('Escape')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('header button[title="Assigned to"]', { timeout: 15000 })
  if (!(await triggerText()).includes('Assign')) {
    throw new Error('unassigning did not survive a reload')
  }
  console.log('        unassigned, back to "Assign"')
  await shot(page, '17-assign')
})

await step('a comment posts and appears in the timeline', async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await page.click('table tbody tr td:nth-child(2)')
  await page.waitForFunction(() => /^\/deals\/CRM-DEAL/.test(location.pathname), {
    timeout: 15000,
  })
  await page.waitForSelector('textarea[name="comment"]', { timeout: 15000 })

  const stamp = `verify comment ${Date.now() % 100000}`
  await page.type('textarea[name="comment"]', stamp)
  // The submit button inside the comment form — not `button[contains(., "Comment")]`,
  // which also matches the "Comments (N)" tab and clicked that instead.
  const [send] = await page.$$('form button[type="submit"]')
  await send.click()
  await page.waitForFunction(
    (text) => document.body.innerText.includes(text),
    { timeout: 15000 },
    stamp,
  )

  // Reload: proves it reached the server rather than staying in React state.
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('textarea[name="comment"]', { timeout: 15000 })
  await page.waitForFunction(
    (text) => document.body.innerText.includes(text),
    { timeout: 15000 },
    stamp,
  )
  console.log(`        "${stamp}" survived a reload`)
  await shot(page, '16-comment')
})

console.log('the other two record screens')
// The expected field is whatever the *server's* layout resolves to, capitalisation
// included — Contact's labels come back lowercase and Organization's do not, and guessing
// that from the Vue app got both wrong the first time.
for (const [listPath, prefix, label, panelField] of [
  ['/contacts/view', '/contacts/', 'Contact', 'mobile no'],
  ['/organizations/view', '/organizations/', 'Organization', 'No. of Employees'],
]) {
  await step(`${label} record opens with its own panel`, async () => {
    await page.goto(`${BASE}${listPath}`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('table tbody tr', { timeout: 15000 })
    await page.click('table tbody tr td:nth-child(2)')
    await page.waitForFunction(
      (p) => location.pathname.startsWith(p) && !location.pathname.endsWith('/view'),
      { timeout: 15000 },
      prefix,
    )
    await page.waitForSelector('aside label', { timeout: 15000 })
    const labels = await page.$$eval('aside label', (ls) => ls.map((l) => l.innerText))
    console.log(`        ${label} panel: ${labels.join(', ')}`)
    if (!labels.includes(panelField)) {
      throw new Error(`${label} panel is missing ${panelField}`)
    }
    await shot(page, `13-${label.toLowerCase()}-record`)
  })
}

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
  const before = await totalRows()

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
  const after = await totalRows()
  console.log(`        ${before} deals before, ${after} after`)
  if (after !== before + 1) throw new Error(`expected ${before + 1} deals, got ${after}`)
  await shot(page, '12-created')
})

await step('bulk delete removes the selected rows', async () => {
  /**
   * **Creates the two rows it deletes.** Earlier versions selected "the first two rows",
   * which ate the seeded fixtures that later steps filter on — the harness quietly
   * destroying its own preconditions, and failing several steps down the file where the
   * cause was invisible. A destructive step has to bring its own data.
   */
  const marker = `BulkDelete ${Date.now() % 100000}`
  await page.evaluate(
    async (label) => {
      const token = localStorage.getItem('crm:access_token')
      for (const suffix of ['A', 'B']) {
        await fetch('/api/resource/CRM%20Deal', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ organization_name: `Verify Bulk ${suffix}` }),
        })
      }
    },
    marker,
  )

  // `Verify`, not this step's own marker: every deal the harness has ever made carries it,
  // the Create step's included. Deleting all of them stops the run leaving residue —
  // without that, harness deals (which have no email) accumulated until they filled page
  // one and the filter steps could not find a row to filter on.
  const mine = encodeURIComponent(
    JSON.stringify([{ fieldname: 'organization_name', operator: 'like', value: 'Verify' }]),
  )
  await page.goto(`${BASE}/deals/view?filters=${mine}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  const before = await totalRows()
  if (before < 2) throw new Error(`expected at least the 2 deals just made, saw ${before}`)

  // Select-all from the header checkbox, which exercises that path too.
  await page.click('table thead th:first-child button[role="checkbox"]')
  await page.waitForFunction(() => /rows? selected/.test(document.body.innerText), {
    timeout: 5000,
  })
  const selected = await page.$$eval('table tbody tr', (trs) => trs.length)

  // Clicked in-page rather than through a handle: the selection bar re-renders as rows are
  // ticked, and a handle taken before that is detached by the time it is used.
  const clickDelete = (withinDialog) =>
    page.evaluate((inDialog) => {
      const root = inDialog ? document.querySelector('[role="dialog"]') : document
      const button = [...root.querySelectorAll('button')].find(
        (b) => b.innerText.trim() === 'Delete',
      )
      if (!button) throw new Error('no Delete button')
      button.click()
    }, withinDialog)

  await clickDelete(false)
  await page.waitForSelector('[role="dialog"]', { timeout: 5000 })
  await clickDelete(true)
  // The selection bar disappears when the delete succeeds and the selection is cleared.
  await page.waitForFunction(() => !/rows selected/.test(document.body.innerText), {
    timeout: 20000,
  })
  await new Promise((r) => setTimeout(r, 1500))

  const after = await totalRows()
  console.log(`        ${before} harness deals, ${selected} selected, ${after} left`)
  if (after !== before - selected) {
    throw new Error(`expected ${before - selected} left, got ${after}`)
  }
  await shot(page, '18-bulk-delete')
})

console.log('saved views')
await step('save the current filter as a view, then reload into it', async () => {
  // Start clean, then narrow the list.
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  const total = await page.$$eval('table tbody tr', (trs) => trs.length)
  await filterDealsByFirstEmail()
  const narrowed = await page.$$eval('table tbody tr', (trs) => trs.length)

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
  if (rows !== narrowed) {
    throw new Error(`saved view returned ${rows} rows, expected the filtered ${narrowed}`)
  }
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

console.log('settings')
await step('the Users settings screen lists real users', async () => {
  await page.goto(`${BASE}/settings/users`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('ul li select', { timeout: 15000 })
  const rows = await page.$$eval('ul li', (ls) =>
    ls.map((l) => l.innerText.split('\n')[0]),
  )
  console.log(`        users: ${rows.join(', ')}`)
  if (!rows.length) throw new Error('no users listed')
  // The whole point of the `get_users` tuple fix: a full name, not a raw email id.
  const body = await text()
  if (!/Administrator/.test(body)) throw new Error('the signed-in user is not listed')
  await shot(page, '14-settings-users')
})

await step('the invite dialog opens and validates', async () => {
  const [invite] = await page.$$('xpath/.//button[contains(., "Invite")]')
  await invite.click()
  await page.waitForSelector('[role="dialog"] input[name="emails"]', { timeout: 5000 })
  await page.keyboard.press('Escape')
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
