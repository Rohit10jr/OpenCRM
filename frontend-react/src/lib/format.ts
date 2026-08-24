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

export function formatCurrency(value: unknown, currency = 'USD'): string {
  const amount = Number(value)
  if (value === null || value === undefined || Number.isNaN(amount)) return ''
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(amount)
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
