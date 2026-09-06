import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatFloat } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * The dashboard.
 *
 * `crm.api.dashboard.get_dashboard` returns the *layout* with a `data` key filled in per
 * tile (`dashboard.py:485`), so the client renders whatever tiles the server sends rather
 * than hardcoding ten of them — the same metadata-driven shape as the record side panel.
 * A tile's `type` picks the renderer: `number`, `donut`, `bar`.
 *
 * **Charts are drawn with plain SVG and CSS, not a charting library.** Three shapes are
 * needed and each is a dozen lines; pulling in Recharts to draw a donut and a bar chart
 * would be a dependency and a bundle for something the browser already does. If a fourth
 * shape arrives, revisit that.
 */

type Tile = {
  name: string
  type: string
  width?: number
  title?: string
  data?: unknown
}

export function DashboardPage() {
  const queryClient = useQueryClient()
  const [range, setRange] = useState<{ from: string; to: string }>({ from: '', to: '' })

  const dashboard = useQuery({
    queryKey: ['dashboard', range],
    queryFn: () =>
      callGet<{ layout?: Tile[] } | Tile[]>('crm.api.dashboard.get_dashboard', {
        ...(range.from ? { from_date: range.from } : {}),
        ...(range.to ? { to_date: range.to } : {}),
      }),
  })

  const reset = useMutation({
    mutationFn: () => call('crm.api.dashboard.reset_to_default'),
    onSuccess: () => {
      toast.success('Dashboard reset')
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not reset')),
  })

  // The endpoint has returned both shapes across versions; accept either rather than
  // depending on which one this build sends.
  const payload = dashboard.data
  const tiles: Tile[] = Array.isArray(payload) ? payload : (payload?.layout ?? [])

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
        <h1 className="text-lg font-semibold text-ink-gray-8">Dashboard</h1>
        <div className="ml-auto flex items-center gap-2">
          <Input
            type="date"
            aria-label="From"
            className="w-40"
            value={range.from}
            onChange={(event) => setRange((r) => ({ ...r, from: event.target.value }))}
          />
          <Input
            type="date"
            aria-label="To"
            className="w-40"
            value={range.to}
            onChange={(event) => setRange((r) => ({ ...r, to: event.target.value }))}
          />
          <Button variant="ghost" size="sm" loading={reset.isPending} onClick={() => reset.mutate()}>
            <RotateCcw className="h-4 w-4" />
            Reset
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {dashboard.isPending ? (
          <p className="text-base text-ink-gray-4">Loading…</p>
        ) : dashboard.isError ? (
          <p className="text-base text-ink-gray-4">
            {errorMessage(dashboard.error, 'Could not load the dashboard')}
          </p>
        ) : (
          <div className="grid grid-cols-4 gap-4">
            {tiles.map((tile) => (
              <div
                key={tile.name}
                className={cn(
                  'rounded-lg border border-outline-gray-1 bg-surface-white p-4',
                  (tile.width ?? 1) >= 2 ? 'col-span-2' : 'col-span-1',
                )}
              >
                <h2 className="mb-2 truncate text-sm font-medium text-ink-gray-5">
                  {tile.title ?? humanise(tile.name)}
                </h2>
                <TileBody tile={tile} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function TileBody({ tile }: { tile: Tile }) {
  const series = toSeries(tile.data)

  if (tile.type === 'number') {
    const value =
      typeof tile.data === 'number'
        ? tile.data
        : Number((tile.data as { value?: unknown })?.value ?? 0)
    return <p className="text-2xl font-semibold text-ink-gray-9">{formatFloat(value)}</p>
  }

  if (!series.length) {
    return <p className="text-base text-ink-gray-4">No data in this range.</p>
  }

  return tile.type === 'donut' ? <Donut series={series} /> : <Bars series={series} />
}

type Point = { label: string; value: number }

/**
 * The tiles do not agree on a shape — some send `[{label, value}]`, some `{a: 1, b: 2}`,
 * some `[{name, count}]`. Normalising here rather than in each renderer keeps the branch
 * in one place, where it can be read against the server.
 */
function toSeries(data: unknown): Point[] {
  if (Array.isArray(data)) {
    return data
      .map((row) => {
        const entry = row as Record<string, unknown>
        const label = entry.label ?? entry.name ?? entry.title
        const value = entry.value ?? entry.count ?? entry.total
        return { label: String(label ?? ''), value: Number(value ?? 0) }
      })
      .filter((point) => point.label !== '')
  }
  if (data && typeof data === 'object') {
    return Object.entries(data as Record<string, unknown>).map(([label, value]) => ({
      label,
      value: Number(value ?? 0),
    }))
  }
  return []
}

/** A palette rather than one hue, so adjacent slices are distinguishable without a legend swatch lookup. */
const COLOURS = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2', '#65a30d']

function Donut({ series }: { series: Point[] }) {
  const total = series.reduce((sum, point) => sum + point.value, 0)
  if (!total) return <p className="text-base text-ink-gray-4">Nothing to show.</p>

  // One circle per slice, drawn with a dash offset — cheaper than arc paths and exact.
  const circumference = 2 * Math.PI * 40
  let offset = 0

  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 100 100" className="h-28 w-28 shrink-0 -rotate-90">
        {series.map((point, index) => {
          const length = (point.value / total) * circumference
          const circle = (
            <circle
              key={point.label}
              cx="50"
              cy="50"
              r="40"
              fill="none"
              strokeWidth="16"
              stroke={COLOURS[index % COLOURS.length]}
              strokeDasharray={`${length} ${circumference - length}`}
              strokeDashoffset={-offset}
            />
          )
          offset += length
          return circle
        })}
      </svg>

      <ul className="min-w-0 flex-1 space-y-1">
        {series.map((point, index) => (
          <li key={point.label} className="flex items-center gap-2 text-sm">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: COLOURS[index % COLOURS.length] }}
            />
            <span className="min-w-0 flex-1 truncate text-ink-gray-6">{point.label}</span>
            <span className="tabular-nums text-ink-gray-8">{formatFloat(point.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Bars({ series }: { series: Point[] }) {
  const max = Math.max(...series.map((point) => point.value), 1)

  return (
    <ul className="space-y-2">
      {series.map((point) => (
        <li key={point.label} className="text-sm">
          <div className="mb-0.5 flex items-baseline gap-2">
            <span className="min-w-0 flex-1 truncate text-ink-gray-6">{point.label}</span>
            <span className="tabular-nums text-ink-gray-8">{formatFloat(point.value)}</span>
          </div>
          <div className="h-2 rounded bg-surface-gray-2">
            <div
              className="h-2 rounded bg-blue-600"
              style={{ width: `${(point.value / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

/** `deals_by_stage_donut` -> `Deals by stage donut`, for tiles the server sends untitled. */
function humanise(name: string) {
  const spaced = name.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}
