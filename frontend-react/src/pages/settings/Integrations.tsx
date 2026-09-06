import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/primitives'
import { SettingsField } from './SettingsField'
import { SettingsPage } from './SettingsLayout'
import { useSettingsDoc } from './useSettingsDoc'

/**
 * WhatsApp and ERPNext — both served, both listed as blocked by earlier runs.
 *
 * `crm.api.whatsapp.*` and `crm.fcrm.doctype.erpnext_crm_settings.*` are whitelisted. The
 * ERPNext screen in particular has more server behind it than any other settings page:
 * product sync, sync-issue triage, quotation prefill.
 */

export function WhatsAppSettingsPage() {
  const installed = useQuery({
    queryKey: ['whatsapp-installed'],
    queryFn: () => callGet<boolean>('crm.api.whatsapp.is_whatsapp_installed'),
    retry: false,
  })
  const enabled = useQuery({
    queryKey: ['whatsapp-enabled'],
    queryFn: () => callGet<boolean>('crm.api.whatsapp.is_whatsapp_enabled'),
    retry: false,
  })

  return (
    <SettingsPage
      title="WhatsApp"
      description="Messages against a record, and template sends."
      actions={
        enabled.data ? (
          <Badge label="Enabled" theme="green" />
        ) : installed.data ? (
          <Badge label="Installed, not enabled" theme="orange" />
        ) : (
          <Badge label="Not installed" theme="gray" />
        )
      }
    >
      {/*
        Configuration lives in the `frappe_whatsapp` app rather than in the CRM, which is
        why there is no settings document to edit here. What the CRM serves is the
        messaging surface — `get_whatsapp_messages`, `create_whatsapp_message`,
        `send_whatsapp_template`, `react_on_whatsapp_message` — and those are on the record
        screen, not here.
      */}
      <p className="text-base text-ink-gray-6">
        WhatsApp is configured in the <code className="text-ink-gray-8">frappe_whatsapp</code>{' '}
        app, not here. Once it reports as installed and enabled, the WhatsApp tab appears on
        deal and lead records.
      </p>

      <dl className="mt-4 divide-y divide-outline-gray-1 border-t border-outline-gray-1">
        <Row label="Installed" value={installed.data ? 'Yes' : 'No'} />
        <Row label="Enabled" value={enabled.data ? 'Yes' : 'No'} />
      </dl>
    </SettingsPage>
  )
}

export function ERPNextSettingsPage() {
  const queryClient = useQueryClient()
  const { doc, setField } = useSettingsDoc<Record<string, unknown>>('ERPNext CRM Settings')

  const installed = useQuery({
    queryKey: ['erpnext-installed'],
    queryFn: () =>
      callGet<boolean>(
        'crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.is_erpnext_installed',
      ),
    retry: false,
  })

  const syncIssues = useQuery({
    queryKey: ['erpnext-sync-issues'],
    queryFn: () =>
      callGet<Record<string, unknown>[]>(
        'crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_open_sync_issues',
      ),
    retry: false,
  })

  const runSync = useMutation({
    mutationFn: () =>
      call('crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.run_product_sync'),
    onSuccess: () => {
      toast.success('Product sync started')
      queryClient.invalidateQueries({ queryKey: ['erpnext-sync-issues'] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not start the sync')),
  })

  const dismiss = useMutation({
    mutationFn: (name: string) =>
      call(
        'crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.dismiss_sync_issue',
        { name },
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['erpnext-sync-issues'] }),
    onError: (error) => toast.error(errorMessage(error, 'Could not dismiss')),
  })

  const issues = syncIssues.data ?? []

  return (
    <SettingsPage
      title="ERPNext"
      description="Push won deals into ERPNext as customers, and pull products back."
      actions={
        <>
          {installed.data ? (
            <Badge label="Installed" theme="green" />
          ) : (
            <Badge label="Not detected" theme="gray" />
          )}
          <Button variant="outline" loading={runSync.isPending} onClick={() => runSync.mutate()}>
            Sync products
          </Button>
        </>
      }
    >
      <div>
        <SettingsField
          label="Enabled"
          type="checkbox"
          value={doc?.enabled}
          onCommit={(value) => setField('enabled', value)}
        />
        <SettingsField
          label="ERPNext site URL"
          type="url"
          placeholder="https://erp.example.com"
          value={doc?.erpnext_site_url}
          onCommit={(value) => setField('erpnext_site_url', value)}
        />
        <SettingsField
          label="API key"
          value={doc?.api_key}
          onCommit={(value) => setField('api_key', value)}
        />
        <SettingsField
          label="API secret"
          type="password"
          value={doc?.api_secret}
          onCommit={(value) => setField('api_secret', value)}
        />
      </div>

      <section className="mt-8">
        <h3 className="mb-2 text-base font-medium text-ink-gray-8">
          Open sync issues{issues.length ? ` (${issues.length})` : ''}
        </h3>
        {issues.length === 0 ? (
          <p className="text-base text-ink-gray-4">
            {syncIssues.isError
              ? 'Could not read sync issues from this backend.'
              : 'Nothing outstanding.'}
          </p>
        ) : (
          <ul className="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
            {issues.map((issue, index) => (
              <li
                key={String(issue.name ?? index)}
                className="flex items-start gap-3 py-2.5"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-base text-ink-gray-8">
                    {String(issue.title ?? issue.name ?? 'Sync issue')}
                  </p>
                  {issue.error ? (
                    <p className="truncate text-sm text-ink-gray-5">{String(issue.error)}</p>
                  ) : null}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => dismiss.mutate(String(issue.name))}
                >
                  Dismiss
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </SettingsPage>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-4 py-2.5">
      <dt className="w-52 shrink-0 text-base text-ink-gray-7">{label}</dt>
      <dd className="text-base text-ink-gray-8">{value}</dd>
    </div>
  )
}
