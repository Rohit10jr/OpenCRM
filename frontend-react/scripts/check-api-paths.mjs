/**
 * Every dotted path this client calls, checked against every path the backend serves.
 *
 * **This catches a whole bug class in about a second, with no browser and no servers.**
 * Run 5 shipped `crm.api.is_call_integration_enabled` where the served path is
 * `crm.integrations.api.is_call_integration_enabled`. Typecheck passed — it is a string.
 * The 404 was swallowed by `retry: false` and a falsy check, so the Call button silently
 * hid itself on every record and nothing anywhere said why. This would have caught it the
 * moment it was written.
 *
 * `backend/tests/test_phase3_endpoints.py::test_every_frontend_dotted_path_resolves` does
 * exactly this for the *Vue* client, but its path is hardcoded to that worktree and
 * `backend/` is a fixed contract here — hence a second copy on this side rather than an
 * edit over there.
 *
 *   npm run check:api
 *
 * A path that is *deliberately* unserved goes in `KNOWN_GAPS` below with a reason, so the
 * check stays green and the list of gaps stays honest. That list should match
 * `docs/react-spike/BACKEND_GAPS.md`; if it drifts, one of the two is wrong.
 */
import { execFileSync } from 'node:child_process'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = 'src'
const PYTHON = '../../frappe_django_crm/backend/.venv/Scripts/python.exe'
const DUMP = 'scripts/dump-whitelist.py'

/**
 * Paths the client calls on purpose that this backend does not serve.
 *
 * Each is a real gap with an entry in `BACKEND_GAPS.md`, wired to the real endpoint under
 * the run-5 policy: fail visibly rather than mock. They are listed rather than silenced so
 * that a *new* missing path still fails this check.
 */
const KNOWN_GAPS = new Map([
  ['frappe.core.doctype.communication.email.make', 'BACKEND_GAPS.md §1 — sending email'],
  ['upload_file', 'BACKEND_GAPS.md §2 — no multipart route exists'],
  ['crm.fcrm.doctype.crm_deal.api.get_deal_contacts', 'BACKEND_GAPS.md §3 — deal contacts'],
  [
    'crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal',
    'BACKEND_GAPS.md §5 — implemented at conversion.py:263, never whitelisted',
  ],
])

/** Dotted paths in quotes. Deliberately loose — a false positive is cheaper than a miss. */
const PATH_PATTERN = /['"`]((?:crm|frappe)\.[a-z_0-9.]+)['"`]/g

/**
 * Strip comments before scanning.
 *
 * These files *document* the endpoints they do not call — `useViews.ts` explains why it
 * uses `/api/resource` instead of `create_or_update_default_view`, and `CreateModal.tsx`
 * names the unserved `crm_deal.create_deal` to say it deliberately avoids it. Counting
 * those as calls reported three permanent failures, and a check that is always red is a
 * check nobody reads.
 *
 * Only comment *lines* are dropped, not trailing `//` after code: a URL in a string
 * contains `//` and cutting there would swallow a real call further along the line.
 */
function withoutComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((line) => !/^\s*(\/\/|\*)/.test(line))
    .join('\n')
}

function sourceFiles(dir) {
  const found = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) found.push(...sourceFiles(full))
    else if (/\.tsx?$/.test(full) && !/\.test\.tsx?$/.test(full)) found.push(full)
  }
  return found
}

const called = new Map()
for (const file of sourceFiles(SRC)) {
  const text = withoutComments(readFileSync(file, 'utf8'))
  for (const [, path] of text.matchAll(PATH_PATTERN)) {
    // A path only counts if it is being *called*, not named in a comment or a banner.
    // `MissingEndpoint` takes the path as a prop precisely so the gap is on screen.
    if (!called.has(path)) called.set(path, new Set())
    called.get(path).add(relative(SRC, file))
  }
}

let served
try {
  served = new Set(
    execFileSync(PYTHON, [DUMP], { encoding: 'utf8' })
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean),
  )
} catch (error) {
  console.error('Could not read the backend whitelist. Is the venv where it was?')
  console.error(`  tried: ${PYTHON} ${DUMP}`)
  console.error(error.message)
  process.exit(2)
}

const missing = []
for (const [path, files] of called) {
  if (served.has(path)) continue
  if (KNOWN_GAPS.has(path)) continue
  missing.push({ path, files: [...files] })
}

console.log(`${called.size} dotted paths called, ${served.size} served.`)

if (KNOWN_GAPS.size) {
  console.log('\nknown gaps (called on purpose, not served):')
  for (const [path, why] of KNOWN_GAPS) {
    // A gap that is no longer a gap should be deleted from the list, not left to rot.
    const note = served.has(path) ? '  ← NOW SERVED, remove from KNOWN_GAPS' : ''
    console.log(`  ${path}${note}`)
    console.log(`      ${why}`)
  }
}

if (!missing.length) {
  console.log('\nno unexpected missing paths.')
  process.exit(0)
}

console.log('\nUNEXPECTED missing paths:')
for (const { path, files } of missing) {
  console.log(`  ${path}`)
  console.log(`      called from: ${files.join(', ')}`)
}
console.log(
  '\nEach is either a typo in the client or a real new gap. If it is a gap, add it to' +
    '\nBACKEND_GAPS.md and to KNOWN_GAPS in this file — in that order.',
)
process.exit(1)
