import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Avatar, Tooltip } from '@/components/ui/primitives'
import { useUsers } from '@/list/useLookups'
import { cn } from '@/lib/utils'

/**
 * Who a record is assigned to, and changing it.
 *
 * The two halves use different endpoints and are not symmetrical:
 *
 *   add     `frappe.desk.form.assign_to.add` — creates a ToDo
 *   remove  `crm.api.doc.remove_assignments` — **cancels** it, rather than deleting
 *
 * That asymmetry is upstream's and is load-bearing: a cancelled ToDo grants no access but
 * keeps the audit trail, where a delete would lose it (`doc.py:266`). Worth knowing before
 * anyone "tidies" the remove path into a delete.
 */
export function AssignTo({
  doctype,
  name,
  assignees,
}: {
  doctype: string
  name: string
  assignees: string[]
}) {
  const { users, getUser } = useUsers()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['assignees', doctype, name] })
    // `_assign` is a column on the list, so the row's avatars are stale too.
    queryClient.invalidateQueries({ queryKey: ['list', doctype] })
    // An assignment is a tracked field change, so it also lands in the record's timeline.
    queryClient.invalidateQueries({ queryKey: ['activities', name] })
  }

  const assign = useMutation({
    mutationFn: (user: string) =>
      // `assign_to` is a list even for one user — that is the endpoint's shape, not a
      // convenience.
      call('frappe.desk.form.assign_to.add', { doctype, name, assign_to: [user] }),
    onSuccess: refresh,
    onError: (error) => toast.error(errorMessage(error, 'Could not assign')),
  })

  const unassign = useMutation({
    mutationFn: (user: string) =>
      call('crm.api.doc.remove_assignments', { doctype, name, assignees: [user] }),
    onSuccess: refresh,
    onError: (error) => toast.error(errorMessage(error, 'Could not unassign')),
  })

  const assigned = new Set(assignees)
  const busy = assign.isPending || unassign.isPending

  const needle = search.trim().toLowerCase()
  const matching = needle
    ? users.filter((user) =>
        `${user.full_name ?? ''} ${user.name}`.toLowerCase().includes(needle),
      )
    : users

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" title="Assigned to" disabled={busy}>
          {assignees.length ? (
            <span className="flex -space-x-1">
              {assignees.slice(0, 3).map((id) => {
                const user = getUser(id)
                return (
                  <Tooltip key={id} text={user.full_name}>
                    <span>
                      <Avatar image={user.user_image} label={user.full_name} size="md" />
                    </span>
                  </Tooltip>
                )
              })}
            </span>
          ) : (
            <>
              <Plus className="h-4 w-4" />
              Assign
            </>
          )}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="max-h-80 w-64 overflow-y-auto">
        <DropdownMenuLabel>Assign to</DropdownMenuLabel>

        {/*
          Filtered in the browser, not through `search_link` the way the Link picker is.
          `get_users` returns the CRM users — tens, not thousands — and they are already
          fetched and cached for every avatar on screen. Searching the server for a list we
          are holding would be a round trip to answer a question we can answer.

          `onKeyDown` stops Radix's typeahead stealing the keystrokes: a menu treats letters
          as jump-to-item, which would move focus off the input mid-word.
        */}
        {users.length > 8 ? (
          <div className="px-1.5 pb-1.5">
            <Input
              autoFocus
              value={search}
              placeholder="Search people…"
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => event.stopPropagation()}
            />
          </div>
        ) : null}

        {matching.map((user) => {
          const isAssigned = assigned.has(user.name)
          return (
            <button
              key={user.name}
              type="button"
              disabled={busy}
              // Not a DropdownMenuCheckboxItem: assigning several people in a row is the
              // normal case, and Radix closes the menu on select.
              onClick={() =>
                isAssigned ? unassign.mutate(user.name) : assign.mutate(user.name)
              }
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-base text-ink-gray-7 hover:bg-surface-gray-2 disabled:opacity-50"
            >
              <Avatar image={user.user_image} label={user.full_name} size="sm" />
              <span className="flex-1 truncate">{user.full_name || user.name}</span>
              <Check
                className={cn('h-4 w-4 shrink-0', isAssigned ? 'opacity-100' : 'opacity-0')}
              />
            </button>
          )
        })}
        {matching.length === 0 ? (
          <p className="px-2 py-1.5 text-sm text-ink-gray-4">
            {users.length ? 'Nobody matches that.' : 'No CRM users to assign to.'}
          </p>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
