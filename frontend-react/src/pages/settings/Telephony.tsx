import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { callGet } from '@/api/client'
import { Badge } from '@/components/ui/primitives'
import { cn } from '@/lib/utils'
import { SettingsField } from './SettingsField'
import { SettingsPage } from './SettingsLayout'
import { useSettingsDoc } from './useSettingsDoc'

/**
 * Telephony — Twilio and Exotel.
 *
 * **This backend serves telephony.** `crm.integrations.twilio.api.*` and
 * `crm.integrations.exotel.handler.*` are whitelisted, including `make_a_call`. Runs 2 and 3
 * listed telephony as an unmeasured blocked subsystem; it was neither.
 *
 * Credentials are encrypted at rest and restricted to managers (`telephony.py:190`), so a
 * Sales User loading this screen gets a document with the secret fields missing rather than
 * an error. That is the server's decision, and the inputs simply come back empty.
 */

const PROVIDERS = [
  { id: 'twilio', label: 'Twilio', doctype: 'CRM Twilio Settings' },
  { id: 'exotel', label: 'Exotel', doctype: 'CRM Exotel Settings' },
] as const

export function TelephonySettingsPage() {
  const [provider, setProvider] = useState<'twilio' | 'exotel'>('twilio')

  // Which provider the server thinks is live, rather than which tab is open.
  const enabled = useQuery({
    queryKey: ['call-integration-enabled'],
    queryFn: () => callGet<unknown>('crm.api.is_call_integration_enabled'),
    retry: false,
  })

  return (
    <SettingsPage
      title="Telephony"
      description="Click-to-call from a record, and call logging back into the timeline."
      actions={
        enabled.data ? <Badge label="A provider is enabled" theme="green" /> : null
      }
    >
      <div className="mb-4 flex gap-1">
        {PROVIDERS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => setProvider(option.id)}
            className={cn(
              'rounded px-3 py-1.5 text-base text-ink-gray-6 hover:bg-surface-gray-2',
              provider === option.id && 'bg-surface-gray-3 font-medium text-ink-gray-8',
            )}
          >
            {option.label}
          </button>
        ))}
      </div>

      {provider === 'twilio' ? <TwilioSettings /> : <ExotelSettings />}
    </SettingsPage>
  )
}

function TwilioSettings() {
  const { doc, setField } = useSettingsDoc<Record<string, unknown>>('CRM Twilio Settings')

  return (
    <div>
      <SettingsField
        label="Enabled"
        type="checkbox"
        value={doc?.enabled}
        onCommit={(value) => setField('enabled', value)}
      />
      <SettingsField
        label="Account SID"
        value={doc?.account_sid}
        onCommit={(value) => setField('account_sid', value)}
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
      <SettingsField
        label="Auth token"
        type="password"
        value={doc?.auth_token}
        onCommit={(value) => setField('auth_token', value)}
      />
      <SettingsField
        label="TwiML app SID"
        value={doc?.twiml_sid}
        onCommit={(value) => setField('twiml_sid', value)}
      />
      <SettingsField
        label="App name"
        value={doc?.app_name}
        onCommit={(value) => setField('app_name', value)}
      />
      <SettingsField
        label="Record calls"
        type="checkbox"
        value={doc?.record_calls}
        onCommit={(value) => setField('record_calls', value)}
      />
    </div>
  )
}

function ExotelSettings() {
  const { doc, setField } = useSettingsDoc<Record<string, unknown>>('CRM Exotel Settings')

  return (
    <div>
      <SettingsField
        label="Enabled"
        type="checkbox"
        value={doc?.enabled}
        onCommit={(value) => setField('enabled', value)}
      />
      <SettingsField
        label="Account SID"
        value={doc?.account_sid}
        onCommit={(value) => setField('account_sid', value)}
      />
      <SettingsField
        label="API key"
        value={doc?.api_key}
        onCommit={(value) => setField('api_key', value)}
      />
      <SettingsField
        label="API token"
        type="password"
        value={doc?.api_token}
        onCommit={(value) => setField('api_token', value)}
      />
      <SettingsField
        label="Subdomain"
        placeholder="yourcompany"
        value={doc?.subdomain}
        onCommit={(value) => setField('subdomain', value)}
      />
      <SettingsField
        label="Webhook verify token"
        type="password"
        hint="Proves an inbound call event really came from Exotel. Treat as a secret."
        value={doc?.webhook_verify_token}
        onCommit={(value) => setField('webhook_verify_token', value)}
      />
      <SettingsField
        label="Record calls"
        type="checkbox"
        value={doc?.record_call}
        onCommit={(value) => setField('record_call', value)}
      />
    </div>
  )
}
