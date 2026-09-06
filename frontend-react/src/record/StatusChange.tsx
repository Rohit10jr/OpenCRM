import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { ArrowRightLeft, ChevronDown } from 'lucide-react'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import { useDocList } from '@/api/hooks'
import { MissingEndpoint } from '@/components/MissingEndpoint'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Dialog, DialogContent } from '@/components/ui/primitives'
import { statusDotClass } from '@/list/statusColor'
import type { CrmStatus } from '@/list/useLookups'

/**
 * The status dropdown, with the one branch it cannot do silently.
 *
 * **Moving a deal to a Lost status needs a reason.** `CRMDeal.validate_lost_reason`
 * (`core_sales.py:566`) refuses the save without `lost_reason`, and refuses `"Other"`
 * without `lost_notes`. The Vue app opens `LostReasonModal.vue` for exactly this. Setting
 * the status and letting the server reject it would show the user an error for something
 * the client already knew.
 *
 * Every other status is one `set_value`, as before.
 */
export function StatusChange({
  statuses,
  current,
  colour,
  isSaving,
  onChange,
}: {
  statuses: CrmStatus[]
  current: string
  colour?: string
  isSaving?: boolean
  onChange: (patch: Record<string, unknown>) => void
}) {
  const [losing, setLosing] = useState<string | null>(null)

  const reasons = useDocList<{ name: string }>('CRM Lost Reason', {
    fields: ['name'],
    limit_page_length: 50,
  })

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="md" title="Status" loading={isSaving}>
            <span className={statusDotClass(colour)} />
            {current}
            <ChevronDown className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
          {statuses.map((option) => (
            <DropdownMenuItem
              key={option.name}
              onSelect={() => {
                if (option.type === 'Lost') setLosing(option.name)
                else onChange({ status: option.name })
              }}
            >
              <span className={statusDotClass(option.color)} />
              {option.name}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <LostReasonDialog
        status={losing}
        reasons={(reasons.data ?? []).map((row) => row.name)}
        onCancel={() => setLosing(null)}
        onConfirm={(patch) => {
          onChange({ status: losing, ...patch })
          setLosing(null)
        }}
      />
    </>
  )
}

function LostReasonDialog({
  status,
  reasons,
  onCancel,
  onConfirm,
}: {
  status: string | null
  reasons: string[]
  onCancel: () => void
  onConfirm: (patch: Record<string, unknown>) => void
}) {
  const [reason, setReason] = useState('')
  const [notes, setNotes] = useState('')

  // `"Other"` is the one reason the model insists is explained (`core_sales.py:574`).
  const needsNotes = reason === 'Other'

  return (
    <Dialog open={Boolean(status)} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent title={`Mark as ${status ?? 'Lost'}`}>
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            onConfirm({ lost_reason: reason, ...(notes ? { lost_notes: notes } : {}) })
          }}
        >
          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-ink-gray-5">Reason</span>
            <select
              required
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className="h-8 rounded border border-outline-gray-2 bg-surface-white px-2 text-base"
            >
              <option value="">Choose a reason…</option>
              {reasons.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-ink-gray-5">
              Notes{needsNotes ? ' (required for “Other”)' : ''}
            </span>
            <textarea
              rows={3}
              required={needsNotes}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              className="resize-y rounded border border-outline-gray-2 px-2 py-1.5 text-base focus:outline-none focus:ring-2 focus:ring-ink-gray-4"
            />
          </label>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="subtle" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" disabled={!reason}>
              Mark as lost
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Convert a lead into a deal.
 *
 * **Will fail.** `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal` is not whitelisted by
 * this backend (`BACKEND_GAPS.md` §5) — `conversion.py:263` implements it but nothing
 * exposes it. Built and wired to the real path on this run's instruction, with the banner
 * above so the gap is visible before the click.
 */
export function ConvertToDealButton({ leadId }: { leadId: string }) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  const convert = useMutation({
    mutationFn: () =>
      call<{ name?: string }>('crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal', {
        lead: leadId,
      }),
    onSuccess: (deal) => {
      const dealId = deal?.name
      toast.success('Lead converted')
      setOpen(false)
      if (dealId) navigate({ to: '/deals/$dealId', params: { dealId } })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not convert the lead')),
  })

  return (
    <>
      <Button variant="outline" size="md" onClick={() => setOpen(true)}>
        <ArrowRightLeft className="h-4 w-4" />
        Convert
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent title="Convert to deal">
          <MissingEndpoint
            className="mb-3"
            what="Converting a lead"
            path="crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal"
          />
          <p className="text-base text-ink-gray-6">
            This creates a deal from the lead, carrying its organization and contact across,
            and marks the lead converted.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="subtle" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="solid" loading={convert.isPending} onClick={() => convert.mutate()}>
              Convert
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
