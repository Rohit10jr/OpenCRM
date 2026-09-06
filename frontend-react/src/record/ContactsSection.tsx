import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Star } from 'lucide-react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { MissingEndpoint } from '@/components/MissingEndpoint'
import { Button } from '@/components/ui/button'
import { Avatar, Badge } from '@/components/ui/primitives'

/**
 * The Deal side panel's contacts section.
 *
 * The layout declares a `contacts_section` with no `columns` (`crm/install.py:200`) — it is
 * a custom section the page renders itself, which is why `SidePanel` leaves it empty and
 * this fills it.
 *
 * **`get_deal_contacts` is not whitelisted** (`BACKEND_GAPS.md` §3), so the list will 404.
 * `crm.api.contact.get_linked_deals` exists but is the inverse relation — deals for a
 * contact, not contacts for a deal — so it cannot stand in.
 *
 * `set_as_primary` *is* served, so the primary toggle works the moment the list does.
 */
export function ContactsSection({ dealId }: { dealId: string }) {
  const queryClient = useQueryClient()

  const contacts = useQuery({
    queryKey: ['deal-contacts', dealId],
    queryFn: () =>
      callGet<Record<string, unknown>[]>(
        'crm.fcrm.doctype.crm_deal.api.get_deal_contacts',
        { name: dealId },
      ),
    retry: false,
  })

  const setPrimary = useMutation({
    mutationFn: (contact: string) =>
      call('crm.api.contact.set_as_primary', { deal: dealId, contact }),
    onSuccess: () => {
      toast.success('Primary contact updated')
      queryClient.invalidateQueries({ queryKey: ['deal-contacts', dealId] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not set the primary contact')),
  })

  const rows = contacts.data ?? []

  return (
    <div className="flex flex-col gap-2">
      {contacts.isError ? (
        <MissingEndpoint
          what="Listing a deal's contacts"
          path="crm.fcrm.doctype.crm_deal.api.get_deal_contacts"
        />
      ) : contacts.isPending ? (
        <p className="text-sm text-ink-gray-4">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-gray-4">No contacts on this deal.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((row, index) => {
            const name = String(row.name ?? index)
            return (
              <li key={name} className="flex items-center gap-2">
                <Avatar
                  image={row.image as string}
                  label={String(row.full_name ?? name)}
                  size="md"
                />
                <div className="min-w-0 flex-1">
                  <Link
                    to="/contacts/$contactId"
                    params={{ contactId: name }}
                    className="flex items-center gap-1.5 truncate text-base text-ink-gray-8 hover:underline"
                  >
                    {String(row.full_name ?? name)}
                    {row.is_primary ? <Badge label="Primary" theme="green" /> : null}
                  </Link>
                  {row.email_id ? (
                    <p className="truncate text-sm text-ink-gray-5">{String(row.email_id)}</p>
                  ) : null}
                </div>
                {!row.is_primary ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Make primary"
                    onClick={() => setPrimary.mutate(name)}
                  >
                    <Star className="h-3.5 w-3.5" />
                  </Button>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
