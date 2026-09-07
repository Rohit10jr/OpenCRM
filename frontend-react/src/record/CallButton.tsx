import { useMutation, useQuery } from '@tanstack/react-query'
import { Phone } from 'lucide-react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'

/**
 * Click to call the number on a record.
 *
 * **Telephony is served.** `crm.integrations.exotel.handler.make_a_call` is whitelisted, as
 * is the whole Twilio surface. Runs 2 and 3 both listed telephony as a blocked, unmeasured
 * subsystem — it was neither, and nobody had looked.
 *
 * The button hides itself unless the server says an integration is enabled
 * (`is_call_integration_enabled`), rather than rendering and failing: a phone icon that
 * cannot dial is worse than no phone icon, and this is one of the few cases where the
 * server will tell us in advance.
 *
 * Twilio's browser-side calling needs its Voice SDK and an access token
 * (`twilio.api.generate_access_token`); that is a dependency and a call UI of its own. This
 * uses the Exotel path, which places the call server-side and rings the agent's handset —
 * no SDK, and the useful half of the feature.
 */
export function CallButton({ phone }: { phone?: unknown }) {
  const number = typeof phone === 'string' ? phone.trim() : ''

  const enabled = useQuery({
    queryKey: ['call-integration-enabled'],
    queryFn: () => callGet<unknown>('crm.integrations.api.is_call_integration_enabled'),
    staleTime: Infinity,
    retry: false,
  })

  const dial = useMutation({
    mutationFn: () =>
      call('crm.integrations.exotel.handler.make_a_call', { to_number: number }),
    onSuccess: () => toast.success(`Calling ${number}…`),
    onError: (error) => toast.error(errorMessage(error, 'Could not place the call')),
  })

  if (!number || !enabled.data) return null

  return (
    <Button
      variant="ghost"
      size="sm"
      title={`Call ${number}`}
      loading={dial.isPending}
      onClick={() => dial.mutate()}
    >
      <Phone className="h-4 w-4" />
      Call
    </Button>
  )
}
