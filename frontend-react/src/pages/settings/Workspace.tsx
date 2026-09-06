import { MissingEndpoint } from '@/components/MissingEndpoint'
import { SettingsField } from './SettingsField'
import { SettingsPage } from './SettingsLayout'
import { useSettingsDoc } from './useSettingsDoc'

/**
 * The four screens backed by `FCRM Settings` — General, Brand, Defaults, Preferences.
 *
 * One file because they are one document (`metadata.py:317`), split into four routes only
 * because fourteen switches on one page is not a settings screen, it is a control panel.
 * Splitting them into four *files* would put four copies of the same `useSettingsDoc` call
 * in four places to no benefit.
 *
 * The Vue app spreads these across `GeneralSettings.vue`, `BrandSettings.vue`,
 * `DefaultsSettings.vue` and `PreferencesSettings.vue`, which is the same shape.
 */

const TIMESTAMP_FORMATS = ['Relative', 'Absolute', 'Relative & Absolute'] as const
const SORT_ORDERS = ['Oldest First', 'Newest First'] as const

/** Frankfurter is the default and needs no key; the others do (`metadata.py:323`). */
const FX_PROVIDERS = ['frankfurter.app', 'exchangerate.host', 'exchangerate-api.com'] as const

export function GeneralSettingsPage() {
  const { doc, setField, isPending } = useSettingsDoc<Record<string, unknown>>('FCRM Settings')

  return (
    <SettingsPage
      title="General"
      description="Workspace-wide behaviour. These apply to everyone."
    >
      {isPending ? (
        <p className="text-base text-ink-gray-4">Loading…</p>
      ) : (
        <div>
          <SettingsField
            label="Sales hierarchy"
            hint="Managers see their reports' records. Read by the permission engine."
            type="checkbox"
            value={doc?.enable_sales_hierarchy}
            onCommit={(value) => setField('enable_sales_hierarchy', value)}
          />
          <SettingsField
            label="Forecasting"
            hint="Adds probability-weighted deal value."
            type="checkbox"
            value={doc?.enable_forecasting}
            onCommit={(value) => setField('enable_forecasting', value)}
          />
          <SettingsField
            label="Auto-update expected deal value"
            type="checkbox"
            value={doc?.auto_update_expected_deal_value}
            onCommit={(value) => setField('auto_update_expected_deal_value', value)}
          />
          <SettingsField
            label="Default currency"
            placeholder="USD"
            value={doc?.currency}
            onCommit={(value) => setField('currency', value)}
          />

          <SelectRow
            label="Exchange rate provider"
            hint="Used by crm.api.exchange_rate.get_exchange_rate, which this backend serves."
            options={FX_PROVIDERS}
            value={doc?.service_provider}
            onCommit={(value) => setField('service_provider', value)}
          />
          <SettingsField
            label="Provider access key"
            type="password"
            hint="Only the paid providers need one. Visible to managers only."
            value={doc?.access_key}
            onCommit={(value) => setField('access_key', value)}
          />
        </div>
      )}
    </SettingsPage>
  )
}

export function BrandSettingsPage() {
  const { doc, setField, isPending } = useSettingsDoc<Record<string, unknown>>('FCRM Settings')

  return (
    <SettingsPage title="Brand" description="What this workspace is called and how it looks.">
      {isPending ? null : (
        <>
          <SettingsField
            label="Workspace name"
            placeholder="Frappe CRM"
            value={doc?.brand_name}
            onCommit={(value) => setField('brand_name', value)}
          />
          <MissingEndpoint
            className="mt-4"
            what="Uploading a logo or favicon"
            path="upload_file"
          />
          <SettingsField
            label="Logo URL"
            hint="Paste a URL until uploads are served."
            type="url"
            value={doc?.brand_logo}
            onCommit={(value) => setField('brand_logo', value)}
          />
          <SettingsField
            label="Favicon URL"
            type="url"
            value={doc?.favicon}
            onCommit={(value) => setField('favicon', value)}
          />
        </>
      )}
    </SettingsPage>
  )
}

export function DefaultsSettingsPage() {
  const { doc, setField, isPending } = useSettingsDoc<Record<string, unknown>>('FCRM Settings')

  return (
    <SettingsPage
      title="Defaults"
      description="What happens automatically when a message arrives on a record."
    >
      {isPending ? null : (
        <div>
          <SettingsField
            label="Bump the timestamp on new communication"
            type="checkbox"
            value={doc?.update_timestamp_on_new_communication}
            onCommit={(value) => setField('update_timestamp_on_new_communication', value)}
          />
          <SettingsField
            label="Mark replied on a response"
            type="checkbox"
            value={doc?.auto_mark_replied_on_response}
            onCommit={(value) => setField('auto_mark_replied_on_response', value)}
          />
          <SettingsField
            label="Reopen on new communication"
            hint="A closed record goes back to open when someone writes in."
            type="checkbox"
            value={doc?.auto_reopen_on_new_communication}
            onCommit={(value) => setField('auto_reopen_on_new_communication', value)}
          />
        </div>
      )}
    </SettingsPage>
  )
}

export function PreferencesSettingsPage() {
  const { doc, setField, isPending } = useSettingsDoc<Record<string, unknown>>('FCRM Settings')

  return (
    <SettingsPage
      title="Preferences"
      description="How the activity timeline reads."
    >
      {isPending ? null : (
        <div>
          <SelectRow
            label="Timestamps"
            options={TIMESTAMP_FORMATS}
            value={doc?.crm_timeline_timestamp_format}
            onCommit={(value) => setField('crm_timeline_timestamp_format', value)}
          />
          <SelectRow
            label="Timeline order"
            options={SORT_ORDERS}
            value={doc?.crm_timeline_sort_order}
            onCommit={(value) => setField('crm_timeline_sort_order', value)}
          />
        </div>
      )}
    </SettingsPage>
  )
}

/**
 * A `<select>` row shaped like `SettingsField`.
 *
 * Not folded into `SettingsField` as another `type`: that component's other branches all
 * take a free value, and a select needs its option list, which would be a prop every other
 * caller ignores.
 */
function SelectRow({
  label,
  hint,
  options,
  value,
  onCommit,
}: {
  label: string
  hint?: string
  options: readonly string[]
  value: unknown
  onCommit: (value: string) => void
}) {
  return (
    <label className="flex items-start gap-4 border-b border-outline-gray-1 py-3 last:border-0">
      <div className="w-52 shrink-0 pt-1.5">
        <span className="text-base text-ink-gray-7">{label}</span>
        {hint ? <p className="mt-0.5 text-sm text-ink-gray-4">{hint}</p> : null}
      </div>
      <select
        value={String(value ?? '')}
        onChange={(event) => onCommit(event.target.value)}
        className="h-8 min-w-0 flex-1 rounded border border-outline-gray-2 bg-surface-white px-2 text-base text-ink-gray-8 focus:outline-none focus:ring-2 focus:ring-ink-gray-4"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  )
}
