import { AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * "This screen needs something the backend does not serve yet."
 *
 * Run 5 builds UI for endpoints this Django port has not whitelisted — a deliberate
 * reversal of runs 1–4, which refused to. The reversal is only safe if the gap is visible
 * *before* someone clicks, so every affected component renders one of these and names the
 * exact dotted path.
 *
 * The path is shown rather than described because it is the thing you would grep for, in
 * both the Vue source and `frappe_core/whitelist.py`.
 *
 * Full list and what would unblock each: `docs/react-spike/BACKEND_GAPS.md`.
 */
export function MissingEndpoint({
  path,
  what,
  className,
}: {
  /** The dotted path the Vue client calls, e.g. `frappe.core.doctype.communication.email.make`. */
  path: string
  /** What stops working, in the user's terms. */
  what: string
  className?: string
}) {
  return (
    <div
      role="note"
      className={cn(
        'flex items-start gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0">
        <p>
          <span className="font-medium">{what}</span> — this backend does not serve it yet.
        </p>
        <code className="mt-0.5 block truncate text-xs text-amber-800">{path}</code>
      </div>
    </div>
  )
}
