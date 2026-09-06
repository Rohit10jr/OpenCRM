import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { AlertCircle, ChevronDown, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { statusDotClass } from '@/list/statusColor'
import { useStatuses } from '@/list/useLookups'
import { cn } from '@/lib/utils'
import { useDocSubscription } from '@/realtime/useSocket'
import { useQuery } from '@tanstack/react-query'
import { callGet } from '@/api/client'
import { ActivityTimeline, RecordList } from './ActivityTimeline'
import { AssignTo } from './AssignTo'
import { Attachments } from './Attachments'
import { CallButton } from './CallButton'
import { CommentBox } from './CommentBox'
import { EmailComposer } from './EmailComposer'
import { WhatsAppTab } from './WhatsAppTab'
import { SidePanel } from './SidePanel'
import { useRecord } from './useRecord'

/**
 * A whole record screen: header, tabs, side panel.
 *
 * **The record equivalent of `ListView`, and shared for the same reason.** `Deal.vue` is
 * 832 lines and `Contact.vue`/`Organization.vue` repeat most of its structure with a
 * different doctype; here they pass a doctype and a title field.
 *
 * What is deliberately not here: the email composer, the WhatsApp tab, telephony, file
 * upload and the contacts sub-panel. Each needs an endpoint or a component this
 * conversion has not reached — `get_deal_contacts` is not even served by this backend.
 * They are listed in the run report rather than stubbed, because a tab that renders an
 * empty box reads as a working feature with no data.
 */

type Tab = { id: string; label: string }

export function RecordScreen({
  doctype,
  name,
  statusDoctype,
  titleField,
  backTo,
  backLabel,
}: {
  doctype: string
  name: string
  /** e.g. `CRM Deal Status`; omitted when the doctype has no status doctype. */
  statusDoctype?: string
  /** Which field to show as the heading. Falls back to the record's name. */
  titleField?: string
  backTo: string
  backLabel: string
}) {
  const record = useRecord(doctype, name)
  // An open record is the one place realtime earns its keep: two people editing the same
  // deal is the normal case this exists for.
  useDocSubscription(doctype, name)
  const { statuses, getStatus } = useStatuses(statusDoctype)
  const [tab, setTab] = useState('activity')

  // The WhatsApp tab only exists where the workspace has WhatsApp; the server is the only
  // thing that knows.
  const whatsappEnabled = useQuery({
    queryKey: ['whatsapp-enabled'],
    queryFn: () => callGet<boolean>('crm.api.whatsapp.is_whatsapp_enabled'),
    staleTime: Infinity,
    retry: false,
  })

  const doc = record.doc as Record<string, unknown> | undefined

  // Comments arrive inside the activity feed rather than from their own endpoint
  // (`activities.py:259`), so the Comments tab is a filter over what is already fetched.
  const comments = record.activities.filter((entry) => entry.activity_type === 'comment')

  // Only deals and leads have an activity feed. A contact showing six empty tabs would
  // read as a record with no history rather than a doctype the endpoint does not serve.
  const tabs: Tab[] = record.hasActivities
    ? [
        { id: 'activity', label: 'Activity' },
        { id: 'emails', label: 'Emails' },
        { id: 'comments', label: `Comments (${comments.length})` },
        { id: 'calls', label: `Calls (${record.calls.length})` },
        { id: 'tasks', label: `Tasks (${record.tasks.length})` },
        { id: 'notes', label: `Notes (${record.notes.length})` },
        { id: 'attachments', label: `Attachments (${record.attachments.length})` },
        // Only when the server says the integration is live — the Vue app does the same,
        // and a WhatsApp tab on a workspace without WhatsApp is a dead end.
        ...(whatsappEnabled.data ? [{ id: 'whatsapp', label: 'WhatsApp' }] : []),
      ]
    : []

  function saveField(fieldname: string, value: unknown) {
    record.updateField.mutate(
      { fieldname, value },
      {
        // A silent failure here is the worst outcome: the input keeps showing the value
        // the user typed while the server still holds the old one.
        onError: (error) => toast.error(errorMessage(error, `Could not save ${fieldname}`)),
      },
    )
  }

  const tabBodies: Record<string, React.ReactNode> = {
    activity: (
      <ActivityTimeline
        activities={record.activities}
        isPending={record.activitiesPending}
      />
    ),
    comments: (
      <ActivityTimeline
        activities={comments}
        isPending={record.activitiesPending}
        emptyText="No comments yet."
      />
    ),
    calls: (
      <RecordList
        rows={record.calls}
        titleField="medium"
        subtitleField="status"
        emptyText="No calls logged against this record."
      />
    ),
    tasks: (
      <RecordList
        rows={record.tasks}
        titleField="title"
        subtitleField="status"
        emptyText="No tasks yet."
      />
    ),
    notes: (
      <RecordList
        rows={record.notes}
        titleField="title"
        subtitleField="content"
        emptyText="No notes yet."
      />
    ),
    attachments: <Attachments name={name} rows={record.attachments} />,
    emails: <EmailComposer doctype={doctype} name={name} />,
    whatsapp: <WhatsAppTab name={name} />,
  }

  if (record.error) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-ink-gray-4">
        <AlertCircle className="h-4 w-4" />
        {errorMessage(record.error, 'Could not load this record')}
      </div>
    )
  }

  if (record.isPending || !doc) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-ink-gray-4">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading…
      </div>
    )
  }

  const title = String((titleField && doc[titleField]) || doc.name || name)
  const status = doc.status ? String(doc.status) : ''

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
        <nav className="flex min-w-0 items-center gap-1.5 text-base">
          <Link to={backTo} className="text-ink-gray-5 hover:text-ink-gray-7">
            {backLabel}
          </Link>
          <span className="text-ink-gray-4">/</span>
          <span className="truncate font-semibold text-ink-gray-8">{title}</span>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <CallButton phone={doc.mobile_no ?? doc.phone} />
          <AssignTo doctype={doctype} name={name} assignees={record.assignees} />

          {statusDoctype && status ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="md"
                  title="Status"
                  loading={record.updateField.isPending}
                >
                  <span className={statusDotClass(getStatus(status)?.color)} />
                  {status}
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
                {statuses.map((option) => (
                  <DropdownMenuItem
                    key={option.name}
                    onSelect={() => saveField('status', option.name)}
                  >
                    <span className={statusDotClass(option.color)} />
                    {option.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div
            role="tablist"
            className={cn(
              'flex shrink-0 gap-5 px-5',
              tabs.length && 'border-b border-outline-gray-1',
            )}
          >
            {tabs.map((option) => (
              <button
                key={option.id}
                role="tab"
                aria-selected={tab === option.id}
                onClick={() => setTab(option.id)}
                className={cn(
                  'border-b-2 py-2.5 text-base text-ink-gray-5 hover:text-ink-gray-8',
                  tab === option.id
                    ? 'border-ink-gray-8 font-medium text-ink-gray-8'
                    : 'border-transparent',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {record.hasActivities ? (
              // A lookup rather than a ternary chain: this was five branches when it was
              // written, six once comments arrived, and a chain that long stops being
              // readable well before it stops working.
              (tabBodies[tab] ?? tabBodies.activity)
            ) : (
              <div className="flex h-full items-center justify-center p-10 text-base text-ink-gray-4">
                This doctype has no activity feed. Edit its fields in the panel.
              </div>
            )}
          </div>

          {/* Only where a comment can actually be written. */}
          {record.hasActivities && (tab === 'activity' || tab === 'comments') ? (
            <CommentBox doctype={doctype} name={name} onAdded={() => setTab('comments')} />
          ) : null}
        </div>

        <aside className="w-96 shrink-0 overflow-y-auto border-l border-outline-gray-1">
          <SidePanel
            sections={record.sections}
            doc={record.doc as never}
            onFieldChange={saveField}
            isSaving={record.updateField.isPending}
          />
        </aside>
      </div>
    </div>
  )
}
