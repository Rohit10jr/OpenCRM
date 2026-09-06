import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Send } from 'lucide-react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * WhatsApp messages against a record.
 *
 * **Served, contrary to what runs 2 and 3 assumed.** `crm.api.whatsapp.get_whatsapp_messages`,
 * `create_whatsapp_message`, `send_whatsapp_template` and `react_on_whatsapp_message` are
 * all whitelisted. The tab only appears when `is_whatsapp_enabled` says so, which is what
 * the Vue app does — the underlying config lives in the `frappe_whatsapp` app, not the CRM.
 *
 * Reactions and template sends are not built. The message list and a free-text send are the
 * useful core; templates need a picker over a doctype this port does not model, and a
 * reaction needs an emoji picker. Both are in the run report.
 */
export function WhatsAppTab({ name }: { name: string }) {
  const queryClient = useQueryClient()
  const [text, setText] = useState('')

  const messages = useQuery({
    queryKey: ['whatsapp', name],
    queryFn: () =>
      callGet<Record<string, unknown>[]>('crm.api.whatsapp.get_whatsapp_messages', {
        reference_doctype: 'CRM Lead',
        reference_name: name,
      }),
    retry: false,
  })

  const send = useMutation({
    mutationFn: () =>
      call('crm.api.whatsapp.create_whatsapp_message', {
        reference_doctype: 'CRM Lead',
        reference_name: name,
        message: text,
      }),
    onSuccess: () => {
      setText('')
      queryClient.invalidateQueries({ queryKey: ['whatsapp', name] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not send the message')),
  })

  const rows = messages.data ?? []

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-auto p-5">
        {messages.isPending ? (
          <p className="text-base text-ink-gray-4">Loading…</p>
        ) : messages.isError ? (
          <p className="text-base text-ink-gray-4">
            WhatsApp is not available on this backend.
          </p>
        ) : rows.length === 0 ? (
          <p className="text-base text-ink-gray-4">No WhatsApp messages yet.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {rows.map((row, index) => {
              const outgoing = String(row.type ?? '').toLowerCase() === 'outgoing'
              return (
                <li
                  key={String(row.name ?? index)}
                  className={cn('flex', outgoing ? 'justify-end' : 'justify-start')}
                >
                  <div
                    className={cn(
                      'max-w-[70%] rounded-lg px-3 py-2 text-base',
                      outgoing
                        ? 'bg-green-100 text-ink-gray-8'
                        : 'bg-surface-gray-2 text-ink-gray-8',
                    )}
                  >
                    <p className="whitespace-pre-wrap">{String(row.message ?? '')}</p>
                    <p className="mt-0.5 text-sm text-ink-gray-4">{timeAgo(row.creation)}</p>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <form
        className="flex items-end gap-2 border-t border-outline-gray-1 p-3"
        onSubmit={(event) => {
          event.preventDefault()
          if (text.trim()) send.mutate()
        }}
      >
        <textarea
          rows={2}
          value={text}
          placeholder="Send a WhatsApp message…"
          onChange={(event) => setText(event.target.value)}
          className="min-h-16 flex-1 resize-y rounded border border-outline-gray-2 px-2 py-1.5 text-base focus:outline-none focus:ring-2 focus:ring-ink-gray-4"
        />
        <Button type="submit" variant="solid" loading={send.isPending} disabled={!text.trim()}>
          <Send className="h-4 w-4" />
          Send
        </Button>
      </form>
    </div>
  )
}
