/**
 * Value formatting for list cells.
 *
 * The Vue app spreads this across `utils/index.js`, `stores/meta.js`
 * (`getFormattedCurrency` and friends) and a `dayjs` dependency. Here it is `Intl`, which
 * ships with the browser and does the same job for the four types a list actually shows.
 */

export function formatDate(value: unknown, withTime = false): string {
  if (!value) return ''
  const date = new Date(value as string)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  })
}

const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 60 * 60 * 1000],
  ['month', 30 * 24 * 60 * 60 * 1000],
  ['day', 24 * 60 * 60 * 1000],
  ['hour', 60 * 60 * 1000],
  ['minute', 60 * 1000],
]

/** "3 days ago". The `modified` and `creation` columns show this rather than a date. */
export function timeAgo(value: unknown): string {
  if (!value) return ''
  const date = new Date(value as string)
  if (Number.isNaN(date.getTime())) return ''
  const elapsed = date.getTime() - Date.now()
  for (const [unit, ms] of UNITS) {
    if (Math.abs(elapsed) >= ms) return RELATIVE.format(Math.round(elapsed / ms), unit)
  }
  return RELATIVE.format(Math.round(elapsed / 1000), 'second')
}

/**
 * A stored UTC timestamp as the local wall-clock value `<input type="datetime-local">`
 * expects.
 *
 * **Slicing the ISO string would have been wrong**, and quietly: the API stores and
 * returns UTC (`2026-09-01T14:30:00Z`), while `datetime-local` has no timezone at all. A
 * `.slice(0, 16)` shows 14:30 to a reader in Berlin whose deadline is really 16:30, and
 * saving it back writes their local 14:30 as 14:30 UTC. It round-trips consistently and is
 * off by the offset for everyone outside UTC.
 *
 * Lives here rather than in `FieldInput.tsx` because it is a date utility like the two
 * above it, and because a pure function in a component file is a pure function nobody
 * tests.
 */
export function toLocalInput(value: unknown): string {
  if (!value) return ''
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return ''
  const offsetMs = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16)
}

export function formatCurrency(value: unknown, currency = 'USD'): string {
  const amount = Number(value)
  if (value === null || value === undefined || value === '' || Number.isNaN(amount)) {
    return ''
  }
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(amount)
  } catch {
    // `Intl` throws on an unrecognised currency code, and the row's `currency` is free
    // text on the server. A number without its symbol beats a blank cell.
    return formatFloat(amount)
  }
}

export function formatFloat(value: unknown): string {
  const amount = Number(value)
  if (value === null || value === undefined || Number.isNaN(amount)) return ''
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(amount)
}

export function formatPercent(value: unknown): string {
  const amount = Number(value)
  if (value === null || value === undefined || Number.isNaN(amount)) return ''
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(amount)}%`
}

/**
 * `_assign` arrives as a JSON string, not an array — Frappe stores it that way and the
 * port reproduces it. Malformed values become an empty list rather than throwing, because
 * one bad row must not take out the table.
 */
export function parseAssignees(value: unknown): string[] {
  if (Array.isArray(value)) return value as string[]
  if (typeof value !== 'string' || !value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}
