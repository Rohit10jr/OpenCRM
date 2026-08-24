import type { DocRow, ListColumn } from '@/api/types'
import { Avatar, Badge, Tooltip } from '@/components/ui/primitives'
import {
  formatCurrency,
  formatDate,
  formatFloat,
  formatPercent,
  parseAssignees,
  timeAgo,
} from '@/lib/format'
import { useUsers, type CrmUser } from './useLookups'
import { statusDotClass } from './statusColor'

/**
 * One list cell, rendered from the column's `type` — Frappe's fieldtype.
 *
 * The Vue app does this in `parseRows()` inside **each page** (`Deals.vue:383`,
 * and again in Leads, Contacts, Organizations…), which is why the same Datetime and
 * `_assign` handling appears seven times. Doing it once, keyed on fieldtype, is the
 * difference between screen two costing 600 lines and costing 2,000.
 *
 * Anything genuinely per-doctype goes through `overrides` rather than into this switch.
 */

export type CellOverride = (row: DocRow, column: ListColumn) => React.ReactNode | undefined

export function Cell({
  row,
  column,
  getStatusColor,
  overrides,
}: {
  row: DocRow
  column: ListColumn
  /** Status colours live per doctype (`CRM Deal Status` vs `CRM Lead Status`). */
  getStatusColor?: (value: string) => string | undefined
  overrides?: Record<string, CellOverride>
}) {
  const { getUser } = useUsers()

  const override = overrides?.[column.key]?.(row, column)
  if (override !== undefined) return <>{override}</>

  const value = row[column.key]

  // `_assign` before the fieldtype switch: the server types it as Text, but it is a JSON
  // array of user ids and rendering it as text shows the user a JSON literal.
  if (column.key === '_assign') {
    const assignees = parseAssignees(value)
    if (!assignees.length) return null
    return (
      <div className="flex -space-x-1">
        {assignees.slice(0, 3).map((id) => {
          const user = getUser(id)
          return (
            <Tooltip key={id} text={user.full_name}>
              <span>
                <Avatar image={user.user_image} label={user.full_name} size="sm" />
              </span>
            </Tooltip>
          )
        })}
      </div>
    )
  }

  if (column.key === 'status') {
    if (!value) return null
    return (
      <span className="flex items-center gap-2 truncate">
        <span className={statusDotClass(getStatusColor?.(String(value)))} />
        <span className="truncate">{String(value)}</span>
      </span>
    )
  }

  if (column.key === 'sla_status') {
    if (!value) return null
    const theme =
      value === 'Failed' ? 'red' : value === 'Fulfilled' ? 'green' : 'orange'
    return <Badge label={String(value)} theme={theme} />
  }

  // `modified` and `creation` read as "3 days ago" with the exact timestamp on hover.
  // Every other Datetime shows the date, matching `parseRows`'s carve-out.
  if (column.key === 'modified' || column.key === 'creation') {
    if (!value) return null
    return (
      <Tooltip text={formatDate(value, true)}>
        <span className="truncate">{timeAgo(value)}</span>
      </Tooltip>
    )
  }

  switch (column.type) {
    case 'Datetime':
      return <span className="truncate">{formatDate(value, true)}</span>
    case 'Date':
      return <span className="truncate">{formatDate(value)}</span>
    case 'Currency':
      // The row carries its own `currency` — a deal in EUR next to one in USD is normal
      // in this CRM, so formatting every amount as the site default would misreport it.
      return (
        <span className="truncate tabular-nums">
          {formatCurrency(value, (row.currency as string) || undefined)}
        </span>
      )
    case 'Float':
      return <span className="truncate tabular-nums">{formatFloat(value)}</span>
    case 'Percent':
      return <span className="truncate tabular-nums">{formatPercent(value)}</span>
    case 'Check':
      return <span className="truncate">{value ? 'Yes' : 'No'}</span>
    case 'Link':
      return <LinkCell value={value} options={column.options} getUser={getUser} />
    default:
      return <span className="truncate">{value == null ? '' : String(value)}</span>
  }
}

/**
 * A Link column holds a document name. For `User` that name is an email address, and the
 * list shows the person instead — the one Link target the CRM cares about often enough
 * to special-case.
 */
function LinkCell({
  value,
  options,
  getUser,
}: {
  value: unknown
  options?: string
  getUser: (name?: string | null) => CrmUser
}) {
  if (!value) return null
  if (options !== 'User') return <span className="truncate">{String(value)}</span>

  const user = getUser(String(value))
  return (
    <span className="flex items-center gap-2 truncate">
      <Avatar image={user.user_image} label={user.full_name} size="sm" />
      <span className="truncate">{user.full_name}</span>
    </span>
  )
}
