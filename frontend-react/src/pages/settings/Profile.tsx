import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { updateDoc } from '@/api/resource'
import { useSession } from '@/auth/session'
import { Button } from '@/components/ui/button'
import { ErrorMessage, FormControl } from '@/components/ui/input'
import { Avatar, Dialog, DialogContent } from '@/components/ui/primitives'
import { MissingEndpoint } from '@/components/MissingEndpoint'
import { SettingsField } from './SettingsField'
import { SettingsPage } from './SettingsLayout'

/**
 * Your own profile — name, signature, password.
 *
 * The signature comes from `crm.api.get_user_signature`, which is served; writing it back is
 * an ordinary `User` field. The avatar is the one thing that needs an upload
 * (`BACKEND_GAPS.md` §2), so it renders read-only with a banner.
 */
export function ProfileSettingsPage() {
  const { user } = useSession()
  const queryClient = useQueryClient()
  const [changingPassword, setChangingPassword] = useState(false)

  const profile = useQuery({
    queryKey: ['user-info'],
    queryFn: () => callGet<Record<string, unknown>>('crm.api.session.get_user_info'),
  })

  const signature = useQuery({
    queryKey: ['user-signature'],
    queryFn: () => callGet<string>('crm.api.get_user_signature'),
  })

  const saveField = useMutation({
    mutationFn: ({ fieldname, value }: { fieldname: string; value: unknown }) =>
      updateDoc('User', user as string, { [fieldname]: value }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-info'] })
      queryClient.invalidateQueries({ queryKey: ['user-signature'] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not save')),
  })

  const me = (profile.data ?? {}) as Record<string, unknown>
  const set = (fieldname: string, value: unknown) => saveField.mutate({ fieldname, value })

  return (
    <SettingsPage
      title="Profile"
      description="How you appear to everyone else in this workspace."
      actions={
        <Button variant="outline" onClick={() => setChangingPassword(true)}>
          Change password
        </Button>
      }
    >
      <div className="mb-5 flex items-center gap-4">
        <Avatar
          image={me.user_image as string}
          label={(me.full_name as string) ?? user}
          size="md"
          className="h-14 w-14 text-lg"
        />
        <MissingEndpoint
          className="flex-1"
          what="Changing your photo"
          path="upload_file"
        />
      </div>

      <div>
        <SettingsField
          label="First name"
          value={me.first_name}
          onCommit={(value) => set('first_name', value)}
        />
        <SettingsField
          label="Last name"
          value={me.last_name}
          onCommit={(value) => set('last_name', value)}
        />
        <SettingsField
          label="Email"
          type="email"
          value={me.email ?? user}
          disabled
          hint="Your email is your login and cannot be changed here."
          onCommit={() => {}}
        />
        <SettingsField
          label="Signature"
          type="textarea"
          hint="Appended to emails you send."
          value={signature.data ?? ''}
          onCommit={(value) => set('email_signature', value)}
        />
      </div>

      <ChangePasswordDialog open={changingPassword} onOpenChange={setChangingPassword} />
    </SettingsPage>
  )
}

/** `crm.api.user.change_password` — served, and takes the old password as confirmation. */
function ChangePasswordDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')

  const change = useMutation({
    mutationFn: () =>
      call('crm.api.user.change_password', {
        old_password: oldPassword,
        new_password: newPassword,
      }),
    onSuccess: () => {
      toast.success('Password changed')
      setOldPassword('')
      setNewPassword('')
      setConfirm('')
      onOpenChange(false)
    },
    onError: (e) => setError(errorMessage(e, 'Could not change your password')),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Change password">
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            setError('')
            // Checked here because it is a typing mistake, not a policy: the server has no
            // second field to compare against. The rules themselves stay server-side.
            if (newPassword !== confirm) {
              setError('The two passwords do not match')
              return
            }
            change.mutate()
          }}
        >
          <FormControl
            label="Current password"
            type="password"
            autoComplete="current-password"
            required
            value={oldPassword}
            onChange={(event) => setOldPassword(event.target.value)}
          />
          <FormControl
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
          <FormControl
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
          <ErrorMessage message={error} />
          <Button
            type="submit"
            variant="solid"
            className="self-end"
            loading={change.isPending}
          >
            Change password
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
