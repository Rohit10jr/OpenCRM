import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import { keys } from '@/api/queryKeys'
import { deleteDoc, getList } from '@/api/resource'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Avatar, Checkbox, Dialog, DialogContent } from '@/components/ui/primitives'

/**
 * The other two halves of Settings → Users: pulling in accounts that already exist, and
 * the pending invitation list.
 *
 * Inviting by email is the path for someone who has never logged in. `add_existing_users`
 * (`user.py:110`) is the path for someone who has an account on this deployment but no CRM
 * role — a distinction the Vue app makes and this port had dropped.
 */

export type CrmUser = {
  name: string
  email?: string
  full_name?: string
  user_image?: string
  role?: string
}

/**
 * Grant a CRM role to accounts that already exist.
 *
 * The candidates are the first element of `get_users` (every enabled account) minus the
 * second (the ones already in CRM). The server does the same subtraction implicitly —
 * `add_existing_users` just calls `update_user_role` — so offering someone who is already
 * a member would silently be a role change, which is not what this dialog says it does.
 */
export function AddExistingUsersDialog({
  open,
  onOpenChange,
  allUsers,
  crmUsers,
  roles,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  allUsers: CrmUser[]
  crmUsers: CrmUser[]
  roles: readonly string[]
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [role, setRole] = useState('Sales User')

  const candidates = useMemo(() => {
    const members = new Set(crmUsers.map((user) => user.name))
    const needle = search.trim().toLowerCase()
    return allUsers
      .filter((user) => !members.has(user.name))
      .filter(
        (user) =>
          !needle ||
          (user.full_name ?? '').toLowerCase().includes(needle) ||
          user.name.toLowerCase().includes(needle),
      )
  }, [allUsers, crmUsers, search])

  const add = useMutation({
    // `users` is a list the server parses with `parse_json_param`, so it goes over the
    // wire as JSON rather than as a comma string.
    mutationFn: () => call('crm.api.user.add_existing_users', { users: selected, role }),
    onSuccess: () => {
      toast.success(`Added ${selected.length} ${selected.length === 1 ? 'person' : 'people'}`)
      queryClient.invalidateQueries({ queryKey: keys.users })
      setSelected([])
      setSearch('')
      onOpenChange(false)
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not add them')),
  })

  function toggle(name: string) {
    setSelected((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Add existing users">
        <div className="flex flex-col gap-3">
          <Input
            placeholder="Search people"
            value={search}
            autoFocus
            onChange={(event) => setSearch(event.target.value)}
          />

          <ul className="max-h-64 divide-y divide-outline-gray-1 overflow-auto rounded border border-outline-gray-1">
            {candidates.length === 0 ? (
              <li className="px-3 py-4 text-base text-ink-gray-4">
                Everyone with an account here is already in the CRM.
              </li>
            ) : (
              candidates.map((user) => (
                <li key={user.name}>
                  <label className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-surface-gray-1">
                    <Checkbox
                      checked={selected.includes(user.name)}
                      onCheckedChange={() => toggle(user.name)}
                    />
                    <Avatar image={user.user_image} label={user.full_name} size="sm" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-base text-ink-gray-8">
                        {user.full_name || user.name}
                      </div>
                      <div className="truncate text-sm text-ink-gray-5">{user.name}</div>
                    </div>
                  </label>
                </li>
              ))
            )}
          </ul>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-ink-gray-5">Role</span>
            <select
              className="h-8 rounded border border-outline-gray-2 bg-surface-white px-2 text-base"
              value={role}
              onChange={(event) => setRole(event.target.value)}
            >
              {roles.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <Button
            variant="solid"
            className="self-end"
            loading={add.isPending}
            disabled={selected.length === 0}
            onClick={() => add.mutate()}
          >
            {selected.length ? `Add ${selected.length}` : 'Add'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

type Invitation = { name: string; email: string; role?: string }

/**
 * Invitations that have been sent and not yet claimed.
 *
 * Read straight off `/api/resource/CRM Invitation` the way the Vue app does
 * (`InviteUserPage.vue:196`) rather than through a dedicated endpoint, because there is no
 * dedicated endpoint. Withdrawing one is a document delete; the permission query in
 * `platform_docs.py:368` decides who may see the row at all, so a user who cannot manage
 * invitations simply gets an empty list rather than an error.
 */
export function PendingInvitations() {
  const queryClient = useQueryClient()

  const invitations = useQuery({
    queryKey: ['invitations', 'pending'],
    queryFn: () =>
      getList<Invitation>('CRM Invitation', {
        filters: { status: 'Pending' },
        fields: ['name', 'email', 'role'],
        limit_page_length: 100,
      }),
    retry: false,
  })

  const withdraw = useMutation({
    mutationFn: (name: string) => deleteDoc('CRM Invitation', name),
    onSuccess: () => {
      toast.success('Invitation withdrawn')
      queryClient.invalidateQueries({ queryKey: ['invitations', 'pending'] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not withdraw it')),
  })

  const pending = invitations.data ?? []
  if (!pending.length) return null

  return (
    <section className="border-t border-outline-gray-1 px-4 py-3">
      <h2 className="text-sm font-medium uppercase tracking-wide text-ink-gray-5">
        Pending invitations
      </h2>
      <ul className="mt-2 divide-y divide-outline-gray-1">
        {pending.map((invitation) => (
          <li key={invitation.name} className="flex items-center gap-3 py-2">
            <div className="min-w-0 flex-1">
              <div className="truncate text-base text-ink-gray-8">{invitation.email}</div>
              <div className="text-sm text-ink-gray-5">{invitation.role}</div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              loading={withdraw.isPending && withdraw.variables === invitation.name}
              onClick={() => withdraw.mutate(invitation.name)}
            >
              Withdraw
            </Button>
          </li>
        ))}
      </ul>
    </section>
  )
}
