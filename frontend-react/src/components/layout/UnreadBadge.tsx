import { useQuery, useQueryClient } from '@tanstack/react-query'
import { callGet } from '@/api/client'
import { useSocketEvent } from '@/realtime/useSocket'

/**
 * The unread count on the sidebar's Notifications link — `AppSidebar.vue:45`.
 *
 * Shares `['notifications']` with the Notifications page on purpose: one fetch feeds both,
 * and marking everything read on the page makes the badge disappear without either of them
 * knowing about the other.
 *
 * `crm_notification` is published per-user by `metadata.py:217`, so the badge updates when
 * a notification arrives rather than when someone happens to navigate.
 */
export function UnreadBadge() {
  const queryClient = useQueryClient()

  const notifications = useQuery({
    queryKey: ['notifications'],
    queryFn: () => callGet<{ read?: boolean }[]>('crm.api.notifications.get_notifications'),
    retry: false,
  })

  useSocketEvent('crm_notification', () => {
    void queryClient.invalidateQueries({ queryKey: ['notifications'] })
  })

  const unread = (notifications.data ?? []).filter((row) => !row.read).length
  if (!unread) return null

  return (
    <span className="ml-auto rounded-full bg-red-600 px-1.5 text-sm font-medium text-white">
      {unread > 99 ? '99+' : unread}
    </span>
  )
}
