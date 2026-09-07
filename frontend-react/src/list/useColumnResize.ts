import { useCallback, useRef, useState } from 'react'
import type { ListColumn } from '@/api/types'

/** Narrow enough to stay readable, wide enough not to clip a date. */
const MIN_WIDTH = 64

/**
 * Drag a column's right edge to resize it.
 *
 * **The width is local while dragging and saved once, on release.** Every column write is a
 * round trip to `CRM View Settings`, so persisting per mousemove would be one request per
 * pixel — the same lesson `FieldInput` learned about committing on blur rather than on
 * keystroke.
 *
 * Listeners go on `window`, not the handle, because a fast drag outruns the element and the
 * pointer ends up over the page; bound to the handle, the column would stop following the
 * cursor and stick.
 *
 * Widths are stored as `rem` strings to match what the server already holds (`"16rem"`),
 * and measured in pixels, so the conversion happens here and nowhere else.
 */
export function useColumnResize(
  columns: ListColumn[],
  onCommit: (columns: ListColumn[]) => void,
) {
  /** Pixel widths mid-drag, keyed by column. Empty except while dragging. */
  const [pending, setPending] = useState<Record<string, number>>({})
  const drag = useRef<{ key: string; startX: number; startWidth: number }>()

  const start = useCallback(
    (key: string, event: React.PointerEvent) => {
      event.preventDefault()
      event.stopPropagation()

      // Measure the header cell rather than reading `column.width`: the stored value may be
      // absent, and a column with no width is whatever the table gave it.
      const th = (event.currentTarget as HTMLElement).closest('th')
      const startWidth = th?.getBoundingClientRect().width ?? MIN_WIDTH
      drag.current = { key, startX: event.clientX, startWidth }

      const move = (moveEvent: PointerEvent) => {
        if (!drag.current) return
        const delta = moveEvent.clientX - drag.current.startX
        const width = Math.max(MIN_WIDTH, drag.current.startWidth + delta)
        setPending({ [drag.current.key]: width })
      }

      const end = () => {
        window.removeEventListener('pointermove', move)
        window.removeEventListener('pointerup', end)

        const current = drag.current
        drag.current = undefined
        if (!current) return

        setPending((widths) => {
          const width = widths[current.key]
          // A click with no movement is not a resize, and saving one would write the
          // measured width over a stored value the user never touched.
          if (width && Math.round(width) !== Math.round(current.startWidth)) {
            onCommit(
              columns.map((column) =>
                column.key === current.key
                  ? { ...column, width: `${(width / 16).toFixed(2)}rem` }
                  : column,
              ),
            )
          }
          return {}
        })
      }

      window.addEventListener('pointermove', move)
      window.addEventListener('pointerup', end)
    },
    [columns, onCommit],
  )

  /** The width to render: the drag's if one is in flight, else the stored one. */
  const widthOf = useCallback(
    (column: ListColumn) =>
      pending[column.key] ? `${pending[column.key]}px` : column.width,
    [pending],
  )

  return { start, widthOf }
}
