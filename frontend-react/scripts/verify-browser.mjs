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

/**
 * Every non-2xx API response, with its path and status.
 *
 * The console handler below only ever said "Failed to load resource: 404", which names
 * neither the endpoint nor the screen that asked for it — a run with twelve of those told
 * you something was wrong and nothing else. This records the actual request, so a failure
 * is a dotted path you can look up in `BACKEND_GAPS.md`.
 */
const apiFailures = []
page.on('response', async (response) => {
  const url = response.url()
  if (!url.includes('/api/')) return
  const status = response.status()
  if (status < 400) return
  // The dotted path is the useful half; the host and query string are noise.
  const path = url.replace(/^https?:\/\/[^/]+/, '').split('?')[0]

  // The body, because a bare "400" says a request was refused and not why. Frappe puts the
  // reason in `exception` or `message`, and that sentence is usually the whole diagnosis.
  let reason = ''
  try {
    const body = await response.text()
    const parsed = JSON.parse(body)
    reason = parsed.exception || parsed.message || parsed._error_message || ''
    if (typeof reason !== 'string') reason = JSON.stringify(reason)
    if (!reason) reason = body.slice(0, 160)
  } catch {
    // A redirect or an already-consumed body. The status and path still stand.
  }
  apiFailures.push({ path, status, step: currentStep, reason: reason.slice(0, 200) })
})

page.on('console', (message) => {
  // Resource errors are recorded above with their URL; this line would add a duplicate
  // that names nothing.
  if (message.text().startsWith('Failed to load resource')) return
  if (message.type() === 'error') problems.push(`console: ${message.text()}`)
})
page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))

/** Which step is running, so a failed request can name the screen that made it. */
let currentStep = 'startup'

const step = async (label, fn) => {
  currentStep = label
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
  // Wait for the feed to settle first. `activitiesPending` follows `isFetching`, so the
  // timeline shows "Loading activity…" through any refetch — asserting straight after the
  // panel appears was asserting against a spinner.
  await page.waitForFunction(
    () =>
      document.querySelectorAll('ol li').length > 0 ||
      /Nothing has happened here yet/.test(document.body.innerText),
    { timeout: 15000 },
  )
  const entries = await page.$$eval('ol li', (ls) => ls.length)
  console.log(`        ${entries} activity entries`)
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
    if (!button) throw new Error('no "Assigned to" button in the header')
    await button.click()
    // 15s, not 5s. The menu opens immediately and its *entries* wait on the user list, and
    // run 5 added several queries to a record open — enough that a five-second bound
    // started failing here intermittently and nowhere else.
    await page.waitForSelector('[role="menu"] button', { timeout: 15000 })
  }

  /**
   * Toggle one *named* person, never "the first button".
   *
   * With nine people in the list, position means nothing: after a reload the first entry is
   * somebody else, so clicking it assigned a second user instead of unassigning the first.
   * The search box exists precisely so a name can be addressed directly.
   */
  const WHO = 'Grace'
  const togglePerson = async () => {
    await openPicker()
    const search = await page.$('[role="menu"] input')
    if (search) {
      await search.type(WHO)
      await page.waitForFunction(
        (name) => {
          const buttons = [...document.querySelectorAll('[role="menu"] button')]
          // `every` alone is true for an empty list, which let this proceed to click
          // nothing. At least one match, and all of them matching.
          return buttons.length > 0 && buttons.every((b) => b.innerText.includes(name))
        },
        { timeout: 5000 },
        WHO,
      )
    }
    const [match] = await page.$$('[role="menu"] button')
    await match.click()
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
    await togglePerson()
    await page.waitForFunction(
      () =>
        document
          .querySelector('header button[title="Assigned to"]')
          ?.innerText.includes('Assign'),
      { timeout: 15000 },
    )
    await page.keyboard.press('Escape')
  }

  const who = WHO
  await togglePerson()
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
  await togglePerson()
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
  // Run 5 replaced the textarea with TipTap, so the target is the editor's contenteditable
  // and the chunk holding it is loaded on demand — hence waiting for it rather than the
  // form around it.
  await page.waitForSelector('.ProseMirror', { timeout: 15000 })

  const stamp = `verify comment ${Date.now() % 100000}`
  await page.click('.ProseMirror')
  await page.type('.ProseMirror', stamp)
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
  // Run 5 replaced the textarea with TipTap, so the target is the editor's contenteditable
  // and the chunk holding it is loaded on demand — hence waiting for it rather than the
  // form around it.
  await page.waitForSelector('.ProseMirror', { timeout: 15000 })
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
  //
  // Clicked in-page for the same reason the Delete button below is: the table re-renders
  // while the list settles, and a handle Puppeteer resolved a moment earlier is detached
  // from the document by the time it is clicked. That is the failure this step hit after
  // run 5 made the toolbar above the table fetch more.
  await page.evaluate(() => {
    const box = document.querySelector('table thead th:first-child button[role="checkbox"]')
    if (!box) throw new Error('no select-all checkbox')
    box.click()
  })
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
  // Run 5 moved delete out of the row and into a per-view "..." submenu, alongside rename,
  // duplicate, pin and publish. Two clicks now: open the row's menu, then Delete.
  const [manage] = await page.$$(
    'xpath/.//button[starts-with(@aria-label, "Manage verify-view-")]',
  )
  if (!manage) throw new Error('the view row has no manage menu')
  await manage.click()
  const [del] = await page.$$('xpath/.//div[@role="menuitem"][normalize-space()="Delete"]')
  if (!del) throw new Error('the manage menu has no Delete item')
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

/* ------------------------------------------------------------------ run 5 screens
 *
 * Everything below covers work that shipped in run 5 with no browser coverage at all —
 * 16 settings screens, the dashboard, notifications, four record tabs, the toolbar
 * controls, and the responsive layout.
 *
 * These are deliberately shallower than the steps above. The ones above assert a *round
 * trip* — type something, reload, see it survive. Most of these assert that a screen
 * renders its own content and asks for the right endpoints, because that is the failure
 * that has actually been happening: a screen that looks fine while a 404 hides a feature.
 * The API-failure list at the end of the run is doing half the work of these steps.
 */
console.log('run 5 — settings screens')

// Every settings screen, by its route. A screen that throws takes its own step down and
// leaves the rest running, which is the point of one step per screen rather than a loop
// inside one step.
for (const [path, marker] of [
  ['/settings/profile', 'Profile'],
  ['/settings/preferences', 'Preferences'],
  ['/settings/general', 'General'],
  ['/settings/brand', 'Brand'],
  ['/settings/defaults', 'Defaults'],
  ['/settings/home-actions', 'Home'],
  ['/settings/hierarchy', 'hierarchy'],
  ['/settings/assignment-rules', 'ssignment'],
  ['/settings/email-accounts', 'mail'],
  ['/settings/email-templates', 'emplate'],
  ['/settings/telephony', 'wilio'],
  ['/settings/whatsapp', 'WhatsApp'],
  ['/settings/erpnext', 'RPNext'],
  ['/settings/lead-syncing', 'ead'],
  ['/settings/sla', 'ervice'],
]) {
  await step(`settings ${path} renders`, async () => {
    await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
    // The nav is always there, so waiting for it proves nothing. Wait for the pane.
    await page.waitForFunction(
      (text) => document.body.innerText.includes(text),
      { timeout: 15000 },
      marker,
    )
  })
}

console.log('run 5 — dashboard and notifications')
await step('the dashboard renders tiles', async () => {
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => !/Loading/.test(document.body.innerText), {
    timeout: 20000,
  })
  const body = await text()
  if (/Could not|error/i.test(body)) throw new Error('the dashboard reported an error')

  // Asserted, not just counted. The first version printed a line count and passed on zero,
  // which is the exact shape of failure this harness exists to catch: a screen that fetches
  // successfully, renders nothing, and reports success.
  const main = await page.$eval('main', (el) => el.innerText.trim()).catch(() => '')
  console.log(`        ${main.split('\n').filter(Boolean).length} lines in <main>`)
  await shot(page, '30-dashboard')
  if (!main) throw new Error('the dashboard fetched without error and rendered nothing')
  void body
})

await step('notifications render', async () => {
  await page.goto(`${BASE}/notifications`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => /Notifications/.test(document.body.innerText), {
    timeout: 15000,
  })
})

console.log('run 5 — record tabs')
const openFirstDeal = async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await page.click('table tbody tr td:nth-child(2)')
  await page.waitForFunction(() => /^\/deals\/CRM-DEAL/.test(location.pathname), {
    timeout: 15000,
  })
}

const openTab = async (label) => {
  // The tab strip renders after `get_activities` returns, so the URL changing is not
  // enough to look for a tab by name — that raced and reported "no Emails tab" on a deal
  // that had one a moment later.
  await page.waitForSelector('[role="tab"]', { timeout: 15000 })
  const [tab] = await page.$$(
    `xpath/.//button[@role="tab"][starts-with(normalize-space(), "${label}")]`,
  )
  if (!tab) {
    const seen = await page.$$eval('[role="tab"]', (ts) => ts.map((t) => t.innerText))
    throw new Error(`no ${label} tab — saw: ${seen.join(', ')}`)
  }
  await tab.click()
}

await step('the Emails tab shows the thread and the composer', async () => {
  await openFirstDeal()
  await openTab('Emails')
  // The composer's banner names the unserved send endpoint — its presence is the run-5
  // policy working, not a failure.
  await page.waitForFunction(
    () => /Sending email|No emails on this record/.test(document.body.innerText),
    { timeout: 15000 },
  )
  await shot(page, '31-emails-tab')
})

await step('the Calls tab renders', async () => {
  await openTab('Calls')
  await page.waitForFunction(
    () => /No calls logged|Completed|No Answer/.test(document.body.innerText),
    { timeout: 15000 },
  )
})

await step('a task can be created from a deal and deleted again', async () => {
  // Each tab step reopens the deal rather than inheriting whatever the last one left. The
  // first version chained them, so one failure mid-step left a dialog open and took the
  // next two down with it — reporting three bugs where there was one.
  await openFirstDeal()
  await openTab('Tasks')
  const title = `verify task ${Date.now() % 100000}`

  const [newTask] = await page.$$('xpath/.//button[contains(., "New task")]')
  if (!newTask) throw new Error('no "New task" button')
  await newTask.click()
  await page.waitForSelector('[role="dialog"]', { timeout: 10000 })
  // The dialog opens before its fields do — it fetches the doctype's Quick Entry layout on
  // open, and shows "Loading…" until that lands. Probing before then found a dialog with
  // no inputs and called it a bug.
  await page.waitForFunction(
    () => {
      const dialog = document.querySelector('[role="dialog"]')
      return dialog && !/Loading/.test(dialog.innerText)
    },
    { timeout: 15000 },
  )

  // The form is the doctype's Quick Entry layout, so the field is found by its label
  // rather than by a name the client chose.
  /**
   * Typed and then blurred, not assigned.
   *
   * `FieldInput` commits on blur or Enter, never per keystroke — each commit is a
   * `set_value` round trip, so the panel deliberately does not fire one per character.
   * Setting `.value` and dispatching `input` therefore updates the DOM and never the
   * draft, and the create posted with no title: *"title: This field is required."* Which
   * is a fair description of a harness that never typed anything.
   */
  const typed = await page.evaluate(() => {
    const dialog = document.querySelector('[role="dialog"]')
    const input = dialog?.querySelector('input[type="text"]')
    if (!input) return false
    input.focus()
    return true
  })
  if (typed) {
    await page.keyboard.type(title)
    await page.keyboard.press('Tab')
  }
  if (!typed) {
    // Name what the dialog *does* have. "No text input" could mean the layout is empty,
    // or that the title field is a control this probe does not recognise, and those are
    // different bugs.
    const shape = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"]')
      if (!dialog) return 'no dialog at all'
      const controls = [...dialog.querySelectorAll('input, select, textarea')].map(
        (el) => `${el.tagName.toLowerCase()}[type=${el.getAttribute('type') ?? '-'}]`,
      )
      return controls.length
        ? `controls: ${controls.join(', ')}`
        : `no controls; text: ${dialog.innerText.slice(0, 120).replace(/\n/g, ' | ')}`
    })
    throw new Error(`the task dialog has no text input — ${shape}`)
  }

  const [create] = await page.$$('xpath/.//div[@role="dialog"]//button[@type="submit"]')
  if (!create) throw new Error('the task dialog has no submit button')
  await create.click()

  await page.waitForFunction(
    (value) => document.body.innerText.includes(value),
    { timeout: 15000 },
    title,
  )

  // Reload: proves the task reached the server, and that it came back attached to *this*
  // deal rather than merely to the task list.
  await page.reload({ waitUntil: 'domcontentloaded' })
  await openTab('Tasks')
  await page.waitForFunction(
    (value) => document.body.innerText.includes(value),
    { timeout: 15000 },
    title,
  )
  console.log(`        "${title}" survived a reload on the deal`)
  await shot(page, '32-task-created')
})

await step('the Notes tab renders its own controls', async () => {
  await openFirstDeal()
  await openTab('Notes')
  await page.waitForFunction(
    () => /New note|No notes yet/.test(document.body.innerText),
    { timeout: 15000 },
  )
})

console.log('run 5 — list toolbar')
await step('the quick filter row renders', async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  const picker = await page.$('button[title="Choose quick filters"]')
  if (!picker) throw new Error('no quick-filter picker')
})

await step('adding a column persists across a reload', async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table thead th', { timeout: 15000 })
  const before = await page.$$eval('table thead th', (ths) => ths.length)

  const [columns] = await page.$$('xpath/.//button[contains(., "Columns")]')
  if (!columns) throw new Error('no Columns button')
  await columns.click()
  await page.waitForSelector('[role="menu"]', { timeout: 5000 })

  // The first unchecked item is under "Add a column" — checking it is the add.
  const added = await page.evaluate(() => {
    const items = [...document.querySelectorAll('[role="menuitemcheckbox"]')]
    const unchecked = items.find((i) => i.getAttribute('aria-checked') === 'false')
    if (!unchecked) return null
    const label = unchecked.innerText.trim()
    unchecked.click()
    return label
  })
  if (!added) throw new Error('no addable column offered')
  await page.keyboard.press('Escape')

  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table thead th', { timeout: 15000 })
  const after = await page.$$eval('table thead th', (ths) => ths.length)
  console.log(`        added "${added}": ${before} columns -> ${after} after a reload`)
  if (after <= before) throw new Error(`column "${added}" did not persist`)

  // Put it back, so the next run starts where this one did.
  const [again] = await page.$$('xpath/.//button[contains(., "Columns")]')
  await again.click()
  await page.waitForSelector('[role="menu"]', { timeout: 5000 })
  await page.evaluate((label) => {
    const item = [...document.querySelectorAll('[role="menuitemcheckbox"]')].find(
      (i) => i.innerText.trim() === label && i.getAttribute('aria-checked') === 'true',
    )
    item?.click()
  }, added)
  await page.keyboard.press('Escape')
})

await step('the kanban board settings dialog opens', async () => {
  await page.goto(`${BASE}/deals/view/kanban`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => !/Loading/.test(document.body.innerText), {
    timeout: 20000,
  })
  const [board] = await page.$$('xpath/.//button[contains(., "Board")]')
  if (!board) throw new Error('no Board settings button')
  await board.click()
  await page.waitForSelector('[role="dialog"]', { timeout: 10000 })
  await page.keyboard.press('Escape')
})

console.log('run 5 — other screens')
await step('an organization shows its deals and contacts', async () => {
  await page.goto(`${BASE}/organizations/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await page.click('table tbody tr td:nth-child(2)')
  await page.waitForFunction(() => /^\/organizations\//.test(location.pathname), {
    timeout: 15000,
  })
  await page.waitForFunction(
    () => /Deals \(\d+\)/.test(document.body.innerText),
    { timeout: 15000 },
  )
})

await step('a call log row opens its detail', async () => {
  await page.goto(`${BASE}/call-logs/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => !/Loading/.test(document.body.innerText), {
    timeout: 20000,
  })
  const rows = await page.$$('table tbody tr')
  if (!rows.length) {
    console.log('        no call logs in this database — nothing to open')
    return
  }
  await page.click('table tbody tr td:nth-child(2)')
  await page.waitForSelector('[role="dialog"]', { timeout: 10000 })
  await page.keyboard.press('Escape')
})

await step('the data import screen renders', async () => {
  await page.goto(`${BASE}/data-import`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => !/^\s*$/.test(document.body.innerText), {
    timeout: 15000,
  })
})

await step('the welcome screen renders its checklist', async () => {
  await page.goto(`${BASE}/welcome`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => /Welcome to Frappe CRM/.test(document.body.innerText), {
    timeout: 15000,
  })
})

await step('the sidebar collapses to a drawer on a narrow viewport', async () => {
  await page.setViewport({ width: 640, height: 900 })
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('button[aria-label="Open menu"]', { timeout: 15000 })

  // The sidebar is off-canvas rather than removed, so the test is its position, not its
  // presence — `-translate-x-full` puts it left of the viewport.
  const hidden = await page.evaluate(() => {
    const aside = document.querySelector('aside')
    return aside ? aside.getBoundingClientRect().right <= 0 : false
  })
  if (!hidden) throw new Error('the sidebar is still on screen at 640px')

  await page.click('button[aria-label="Open menu"]')
  await page.waitForFunction(
    () => {
      const aside = document.querySelector('aside')
      return aside && aside.getBoundingClientRect().right > 0
    },
    { timeout: 5000 },
  )
  await shot(page, '33-mobile-drawer')
  await page.setViewport({ width: 1440, height: 900 })
})

console.log('sign out')
await step('sign out returns to login', async () => {
  await page.goto(`${BASE}/deals/view`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('button[title="Sign out"]', { timeout: 10000 })
  const [signOut] = await page.$$('xpath/.//button[@title="Sign out"]')
  await signOut.click()
  await page.waitForFunction(() => location.pathname === '/login', { timeout: 10000 })
})

await browser.close()

console.log('\nfailed API calls:')
if (apiFailures.length === 0) console.log('  none')
else {
  // One line per distinct path+status, with the steps that triggered it. The same missing
  // endpoint called from four screens is one gap, not four.
  const grouped = new Map()
  for (const failure of apiFailures) {
    const key = `${failure.status} ${failure.path}`
    if (!grouped.has(key)) grouped.set(key, { steps: new Set(), reasons: new Set() })
    grouped.get(key).steps.add(failure.step)
    if (failure.reason) grouped.get(key).reasons.add(failure.reason)
  }
  for (const [key, { steps, reasons }] of grouped) {
    console.log(`  ${key}`)
    for (const reason of reasons) console.log(`      why: ${reason}`)
    console.log(`      during: ${[...steps].join('; ')}`)
  }
}

console.log('\nproblems:')
if (problems.length === 0) console.log('  none')
else problems.forEach((p) => console.log(`  - ${p}`))

process.exit(problems.length || apiFailures.length ? 1 : 0)
