import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { UserPlus } from 'lucide-react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { keys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { ErrorMessage, FormControl } from '@/components/ui/input'
import { Avatar, Badge, Dialog, DialogContent } from '@/components/ui/primitives'
import { useSession } from '@/auth/session'

/**
 * Settings → Users. The first settings screen, and the third kind of screen in this app
 * after lists and records.
 *
 * Chosen because it is entirely served: `crm.api.session.get_users` (`session.py:62`),
 * `crm.api.user.update_user_role` (`user.py:128`) and `crm.api.invite_by_email`
 * (`misc.py:74`) all exist. Several other settings screens in the Vue app depend on
 * endpoints this port does not serve; picking one that does is the difference between a
 * settings screen and a mock of one.
 *
 * Deliberately *not* built on `ListView`: this is not a `get_data` list. It has no
 * filters, no saved views and no columns from the server, and forcing it through the list
 * engine would mean teaching that engine about a payload shape only this screen has.
 */

type CrmUser = {
  name: string
  email?: string
  full_name?: string
  user_image?: string
  role?: string
  enabled?: boolean
  session_user?: boolean
}

/** `user.py:18`. The server enforces this; the dropdown just does not offer more. */
const ASSIGNABLE_ROLES = ['System Manager', 'Sales Manager', 'Sales User'] as const

export function UsersSettingsPage() {
  const queryClient = useQueryClient()
  const { user: sessionUser } = useSession()
  const [inviting, setInviting] = useState(false)

  const users = useQuery({
    queryKey: keys.users,
    // The tuple's second element is the CRM users — the ones with a CRM role. The first
    // is every enabled account, which this screen does not want.
    queryFn: () => callGet<[CrmUser[], CrmUser[]]>('crm.api.session.get_users'),
  })

  const setRole = useMutation({
    mutationFn: (args: { user: string; new_role: string }) =>
      call('crm.api.user.update_user_role', args),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.users }),
    // The server refuses some changes for reasons the client cannot know — demoting a
    // user who has reports would orphan a hierarchy subtree (`user.py:133`) — so its
    // message is shown rather than a generic one.
    onError: (error) => toast.error(errorMessage(error, 'Could not change the role')),
  })

  const [, crmUsers = []] = users.data ?? []

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
        <h1 className="text-lg font-semibold text-ink-gray-8">Users</h1>
        <div className="ml-auto">
          <Button variant="solid" size="md" onClick={() => setInviting(true)}>
            <UserPlus className="h-4 w-4" />
            Invite
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        {users.isPending ? (
          <p className="p-5 text-base text-ink-gray-4">Loading…</p>
        ) : (
          <ul className="divide-y divide-outline-gray-1">
            {crmUsers.map((user) => (
              <li key={user.name} className="flex items-center gap-3 px-4 py-3">
                <Avatar image={user.user_image} label={user.full_name} size="md" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-base text-ink-gray-8">
                      {user.full_name || user.name}
                    </span>
                    {user.name === sessionUser ? (
                      <Badge label="You" theme="blue" />
                    ) : null}
                  </div>
                  <div className="truncate text-sm text-ink-gray-5">{user.email}</div>
                </div>

                <select
                  aria-label={`Role for ${user.full_name || user.name}`}
                  className="h-8 rounded border border-outline-gray-2 bg-surface-white px-2 text-base"
                  value={user.role ?? ''}
                  disabled={setRole.isPending}
                  onChange={(event) =>
                    setRole.mutate({ user: user.name, new_role: event.target.value })
                  }
                >
                  {/* A role the server reports but does not let you assign still has to
                      appear, or the select would silently show the wrong one. */}
                  {user.role && !ASSIGNABLE_ROLES.includes(user.role as never) ? (
                    <option value={user.role}>{user.role}</option>
                  ) : null}
                  {ASSIGNABLE_ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </li>
            ))}
          </ul>
        )}
      </div>

      <InviteDialog open={inviting} onOpenChange={setInviting} />
    </div>
  )
}

/**
 * Invite by email.
 *
 * `invite_by_email` answers with a three-way split — already members, already invited,
 * newly invited (`misc.py:78`) — and all three are reported, because "invited 1 of 3" is
 * the answer the user needs and a bare success would hide it.
 */
function InviteDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [emails, setEmails] = useState('')
  const [role, setRole] = useState<string>('Sales User')
  const [error, setError] = useState('')

  const invite = useMutation({
    mutationFn: (args: { emails: string; role: string }) =>
      call<Record<string, string[]>>('crm.api.invite_by_email', args),
  })

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    invite.mutate(
      { emails, role },
      {
        onSuccess: (result) => {
          const parts = Object.entries(result ?? {})
            .filter(([, list]) => Array.isArray(list) && list.length)
            .map(([key, list]) => `${key.replace(/_/g, ' ')}: ${list.length}`)
          toast.success(parts.length ? parts.join(', ') : 'Invitations sent')
          setEmails('')
          onOpenChange(false)
        },
        onError: (e) => setError(errorMessage(e, 'Could not send the invitations')),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Invite people">
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <FormControl
            label="Email addresses, comma separated"
            name="emails"
            type="text"
            required
            autoFocus
            value={emails}
            onChange={(event) => setEmails(event.target.value)}
          />
          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-ink-gray-5">Role</span>
            <select
              className="h-8 rounded border border-outline-gray-2 bg-surface-white px-2 text-base"
              value={role}
              onChange={(event) => setRole(event.target.value)}
            >
              {ASSIGNABLE_ROLES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <ErrorMessage message={error} />
          <Button
            type="submit"
            variant="solid"
            className="self-end"
            loading={invite.isPending}
          >
            Send invitations
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
