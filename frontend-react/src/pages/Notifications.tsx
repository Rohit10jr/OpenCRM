import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { CheckCheck } from 'lucide-react'
import { call, callGet } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Avatar } from '@/components/ui/primitives'
import { timeAgo } from '@/lib/format'
import { useUsers } from '@/list/useLookups'
import { cn } from '@/lib/utils'
import { useSocketEvent } from '@/realtime/useSocket'

/**
 * Notifications.
 *
 * The server rewrites `reference_doctype` on the way out — the client receives `"deal"` or
 * `"lead"`, never the doctype name, and anything that is not a CRM Deal falls to the lead
 * spelling (`notifications.py:37`). That is upstream's ternary, so the link building below
 * reads those two words rather than a doctype.
 *
 * `crm_notification` arrives over the socket, which is what the realtime layer was ported
 * for; a new notification refetches the list rather than being appended, because the server
 * also owns the unread count and the ordering.
 */
export function NotificationsPage() {
  const queryClient = useQueryClient()
  const { getUser } = useUsers()

  const notifications = useQuery({
    queryKey: ['notifications'],
    queryFn: () => callGet<Record<string, unknown>[]>('crm.api.notifications.get_notifications'),
  })

  useSocketEvent('crm_notification', () => {
    queryClient.invalidateQueries({ queryKey: ['notifications'] })
  })

  const markRead = useMutation({
    mutationFn: () => call('crm.api.notifications.mark_as_read'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const rows = notifications.data ?? []
  const unread = rows.filter((row) => !row.read).length

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
        <h1 className="text-lg font-semibold text-ink-gray-8">
          Notifications{unread ? ` (${unread})` : ''}
        </h1>
        {unread ? (
          <Button
            className="ml-auto"
            variant="ghost"
            size="sm"
            loading={markRead.isPending}
            onClick={() => markRead.mutate()}
          >
            <CheckCheck className="h-4 w-4" />
            Mark all read
          </Button>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        {notifications.isPending ? (
          <p className="p-5 text-base text-ink-gray-4">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="p-5 text-base text-ink-gray-4">Nothing to catch up on.</p>
        ) : (
          <ul className="divide-y divide-outline-gray-1">
            {rows.map((row, index) => {
              const from = getUser(row.from_user as string)
              return (
                <li
                  key={String(row.name ?? index)}
                  className={cn('px-4 py-3', !row.read && 'bg-surface-gray-1')}
                >
                  <NotificationBody row={row} fromName={from.full_name} image={from.user_image} />
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

function NotificationBody({
  row,
  fromName,
  image,
}: {
  row: Record<string, unknown>
  fromName?: string
  image?: string
}) {
  const kind = String(row.reference_doctype ?? '')
  const name = String(row.reference_name ?? '')
  // Only the two the server emits. Anything else renders unlinked rather than guessing a
  // route that does not exist.
  const to = kind === 'deal' ? '/deals/$dealId' : kind === 'lead' ? '/leads/$leadId' : null

  const text = (
    <>
      <span className="font-medium text-ink-gray-8">{fromName}</span>{' '}
      {String(row.notification_text ?? row.message ?? 'sent you a notification')}
    </>
  )

  return (
    <div className="flex items-start gap-3">
      <Avatar image={image} label={fromName} size="md" />
      <div className="min-w-0 flex-1 text-base text-ink-gray-7">
        {to ? (
          <Link
            to={to}
            params={kind === 'deal' ? { dealId: name } : { leadId: name }}
            className="hover:underline"
          >
            {text}
          </Link>
        ) : (
          text
        )}
        <div className="text-sm text-ink-gray-4">{timeAgo(row.creation)}</div>
      </div>
    </div>
  )
}
