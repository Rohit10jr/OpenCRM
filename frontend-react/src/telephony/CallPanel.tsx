import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { ChevronDown, ChevronUp, ListTodo, StickyNote, X } from 'lucide-react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Avatar } from '@/components/ui/primitives'
import { useSocketEvent } from '@/realtime/useSocket'
import { cn } from '@/lib/utils'
import {
  exotelCallStatus,
  formatDuration,
  type CallStatus,
  type ExotelCallPayload,
} from './callStatus'

/**
 * The live call panel — `ExotelCallUI.vue`, minus the parts that are decoration.
 *
 * A call is the one thing in this app that happens *to* the user rather than because they
 * clicked something, so this is mounted once by `AppLayout` and is invisible until the
 * `exotel_call` socket event arrives. Everything it calls is served: the event is published
 * by `exotel/handler.py:209`, and note, task and contact lookup are all whitelisted in
 * `integrations/api.py`.
 *
 * **Exotel only, and that is the whole feature here.** Twilio also publishes
 * (`twilio_call_status`), but its UI is an in-browser softphone: it needs `@twilio/voice-sdk`,
 * an access token, and mute/hold/hangup controls that talk to the SDK rather than to us.
 * That is a dependency and a second screen, and it is recorded in `BACKEND_GAPS.md` rather
 * than half-built here. Exotel rings the agent's actual handset, so the browser only has to
 * *show* the call — which is the useful half and needs nothing installed.
 *
 * **Not ported: dragging the panel around.** Upstream makes it draggable with
 * `@vueuse/core`'s `useDraggable`. It is fixed bottom-right here.
 */
export function CallPanel() {
  const [payload, setPayload] = useState<ExotelCallPayload | null>(null)
  const [status, setStatus] = useState<CallStatus>()
  const [number, setNumber] = useState('')
  const [duration, setDuration] = useState<number>()
  const [expanded, setExpanded] = useState(true)
  const [pane, setPane] = useState<'none' | 'note' | 'task'>('none')

  // The elapsed counter. `exotelCallStatus` says when to start and stop rather than
  // touching a timer itself, so the interval lives here and nowhere else.
  const [elapsed, setElapsed] = useState(0)
  const ticking = useRef<ReturnType<typeof setInterval>>()

  const stopTicking = useCallback(() => {
    if (ticking.current) clearInterval(ticking.current)
    ticking.current = undefined
  }, [])

  useEffect(() => stopTicking, [stopTicking])

  useSocketEvent('exotel_call', (data: unknown) => {
    const event = (data ?? {}) as ExotelCallPayload
    const result = exotelCallStatus(event)

    /**
     * A second call can arrive while the panel still shows the last one — a call that has
     * ended stays on screen until dismissed, and the next one does not wait for that.
     *
     * `CallSid` is what distinguishes them. Without this check the panel carried the
     * previous call's number and duration into the new one, because both are only ever
     * *written* when the payload happens to supply them: an outbound call sets `number`
     * only when it is currently empty, and `duration` is only set once a call ends. So the
     * new call would show the old contact, and could end showing the old call's length.
     *
     * Found by the Codex review of this run.
     */
    const sid = event.CallSid ?? ''
    const isNewCall = Boolean(payload) && sid !== (payload?.CallSid ?? '')
    if (isNewCall) {
      stopTicking()
      setDuration(undefined)
      setStatus(undefined)
      setElapsed(0)
    }

    setPayload(event)
    // An unrecognised payload keeps the last known status rather than blanking the panel
    // mid-call: Exotel sends intermediate events this state machine does not name.
    if (result.status) setStatus(result.status)
    if (result.phoneNumber) setNumber(result.phoneNumber)
    else if (!number || isNewCall) setNumber(event.To || event.CallFrom || event.From || '')
    if (result.durationSeconds !== undefined) setDuration(result.durationSeconds)

    if (result.timer === 'start' && !ticking.current) {
      setElapsed(0)
      ticking.current = setInterval(() => setElapsed((seconds) => seconds + 1), 1000)
    }
    if (result.timer === 'stop') stopTicking()
  })

  const contact = useQuery({
    queryKey: ['call-contact', number],
    queryFn: () =>
      callGet<CallContact>('crm.integrations.api.get_contact_by_phone_number', {
        phone_number: number,
      }),
    enabled: Boolean(number),
    retry: false,
  })

  if (!payload || !status) return null

  const sid = payload.CallSid ?? ''
  const person = contact.data
  const title = person?.full_name || number || 'Unknown caller'

  function dismiss() {
    stopTicking()
    setPayload(null)
    setStatus(undefined)
    setNumber('')
    setDuration(undefined)
    setPane('none')
  }

  return (
    <div className="fixed bottom-4 right-4 z-30 w-72 rounded-lg bg-surface-gray-10 p-3 text-ink-white shadow-2xl">
      <div className="flex items-center gap-2">
        <Avatar image={person?.image} label={title} size="md" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-base font-medium">{title}</div>
          <div className="truncate text-sm text-ink-gray-4">
            <StatusLine status={status} elapsed={elapsed} duration={duration} />
          </div>
        </div>
        <button
          type="button"
          aria-label={expanded ? 'Collapse' : 'Expand'}
          className="rounded p-1 hover:bg-surface-gray-9"
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
        </button>
        <button
          type="button"
          aria-label="Dismiss"
          className="rounded p-1 hover:bg-surface-gray-9"
          onClick={dismiss}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {expanded ? (
        <div className="mt-3 flex flex-col gap-2">
          {person?.deal || person?.lead ? (
            <Link
              to={person.deal ? '/deals/$dealId' : '/leads/$leadId'}
              params={
                person.deal ? { dealId: person.deal } : { leadId: person.lead as string }
              }
              className="text-sm text-ink-gray-4 underline underline-offset-2 hover:text-ink-white"
            >
              Open the {person.deal ? 'deal' : 'lead'}
            </Link>
          ) : null}

          <div className="flex gap-2">
            <PaneButton
              icon={StickyNote}
              label="Note"
              active={pane === 'note'}
              onClick={() => setPane(pane === 'note' ? 'none' : 'note')}
            />
            <PaneButton
              icon={ListTodo}
              label="Task"
              active={pane === 'task'}
              onClick={() => setPane(pane === 'task' ? 'none' : 'task')}
            />
          </div>

          {pane === 'note' ? <NotePane sid={sid} onDone={() => setPane('none')} /> : null}
          {pane === 'task' ? <TaskPane sid={sid} onDone={() => setPane('none')} /> : null}
        </div>
      ) : null}
    </div>
  )
}

type CallContact = {
  full_name?: string
  mobile_no?: string
  image?: string
  deal?: string
  lead?: string
}

function StatusLine({
  status,
  elapsed,
  duration,
}: {
  status: CallStatus
  elapsed: number
  duration?: number
}) {
  if (status === 'In progress') return <>In progress · {formatDuration(elapsed)}</>
  if (status === 'Call ended' && duration !== undefined) {
    return <>Call ended · {formatDuration(duration)}</>
  }
  return <>{status}</>
}

function PaneButton({
  icon: Icon,
  label,
  active,
  onClick,
}: {
  icon: typeof StickyNote
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1.5 text-sm',
        active ? 'bg-surface-gray-8' : 'bg-surface-gray-9 hover:bg-surface-gray-8',
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  )
}

/**
 * Attach a note to the call log.
 *
 * The server links whatever it creates to the `CRM Call Log` row for this `CallSid`
 * (`integrations/api.py:116`), so the note is reachable from the call afterwards. It needs
 * a call log to exist — a note taken before Exotel's webhook has landed will 404, which is
 * upstream's behaviour too.
 */
function NotePane({ sid, onDone }: { sid: string; onDone: () => void }) {
  const [content, setContent] = useState('')

  const save = useMutation({
    mutationFn: () =>
      call('crm.integrations.api.add_note_to_call_log', {
        call_sid: sid,
        note: { title: 'Call Note', content },
      }),
    onSuccess: () => {
      toast.success('Note saved to the call')
      setContent('')
      onDone()
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not save the note')),
  })

  return (
    <div className="flex flex-col gap-2">
      <textarea
        className="min-h-20 rounded border border-outline-gray-2 bg-surface-white p-2 text-base text-ink-gray-8"
        placeholder="What was said"
        autoFocus
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <Button
        variant="solid"
        size="sm"
        className="self-end"
        loading={save.isPending}
        disabled={!content.trim()}
        onClick={() => save.mutate()}
      >
        Save note
      </Button>
    </div>
  )
}

/** Attach a task to the call log. Same shape as the note, one field wider. */
function TaskPane({ sid, onDone }: { sid: string; onDone: () => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')

  const save = useMutation({
    mutationFn: () =>
      call('crm.integrations.api.add_task_to_call_log', {
        call_sid: sid,
        task: { title, description, status: 'Backlog', priority: 'Medium' },
      }),
    onSuccess: () => {
      toast.success('Task added to the call')
      setTitle('')
      setDescription('')
      onDone()
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not add the task')),
  })

  return (
    <div className="flex flex-col gap-2">
      <Input
        placeholder="Follow up on…"
        autoFocus
        value={title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <textarea
        className="min-h-16 rounded border border-outline-gray-2 bg-surface-white p-2 text-base text-ink-gray-8"
        placeholder="Details"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />
      <Button
        variant="solid"
        size="sm"
        className="self-end"
        loading={save.isPending}
        disabled={!title.trim()}
        onClick={() => save.mutate()}
      >
        Add task
      </Button>
    </div>
  )
}
