import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { call, client, errorMessage } from '@/api/client'
import { MissingEndpoint } from '@/components/MissingEndpoint'
import { Button } from '@/components/ui/button'
import { timeAgo } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * Files on a record.
 *
 * Listing and deleting work — `get_activities` returns the attachments and
 * `crm.api.delete_attachment` is served. **Adding does not:** `upload_file` is not
 * whitelisted and there is no multipart route at all (`BACKEND_GAPS.md` §2), so the drop
 * zone posts to the path the Vue client uses and 404s.
 *
 * Kept as a real multipart POST rather than a disabled button, on this run's instruction:
 * the failure is the information. When an upload route lands, this component should work
 * unchanged.
 */
export function Attachments({
  name,
  rows,
}: {
  /** The record's name — attachments are keyed to it. */
  name: string
  rows: Record<string, unknown>[]
}) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['activities', name] })

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      form.append('is_private', '1')
      form.append('attached_to_name', name)
      // The axios instance carries the bearer token; the browser sets the multipart
      // boundary itself, so no Content-Type here.
      const response = await client.post('/api/method/upload_file', form)
      return response.data
    },
    onSuccess: () => {
      toast.success('File attached')
      refresh()
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not attach the file')),
  })

  const remove = useMutation({
    mutationFn: (fileName: string) =>
      call('crm.api.delete_attachment', { filename: fileName }),
    onSuccess: () => {
      toast.success('Attachment removed')
      refresh()
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not remove the attachment')),
  })

  return (
    <div className="p-5">
      <MissingEndpoint className="mb-4" what="Uploading a file" path="upload_file" />

      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          const file = event.dataTransfer.files?.[0]
          if (file) upload.mutate(file)
        }}
        className={cn(
          'mb-4 flex flex-col items-center gap-2 rounded-lg border-2 border-dashed p-6 text-center',
          dragging ? 'border-ink-gray-5 bg-surface-gray-1' : 'border-outline-gray-2',
        )}
      >
        <Upload className="h-5 w-5 text-ink-gray-4" />
        <p className="text-base text-ink-gray-6">Drop a file here, or</p>
        <Button
          variant="subtle"
          size="sm"
          loading={upload.isPending}
          onClick={() => inputRef.current?.click()}
        >
          Choose a file
        </Button>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) upload.mutate(file)
            // Reset, so choosing the same file twice fires twice.
            event.target.value = ''
          }}
        />
      </div>

      {rows.length === 0 ? (
        <p className="text-base text-ink-gray-4">No attachments.</p>
      ) : (
        <ul className="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
          {rows.map((row, index) => (
            <li key={String(row.name ?? index)} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                {row.file_url ? (
                  <a
                    href={String(row.file_url)}
                    target="_blank"
                    rel="noreferrer"
                    className="truncate text-base text-ink-gray-8 hover:underline"
                  >
                    {String(row.file_name ?? row.name)}
                  </a>
                ) : (
                  <span className="truncate text-base text-ink-gray-8">
                    {String(row.file_name ?? row.name)}
                  </span>
                )}
                {row.creation ? (
                  <div className="text-sm text-ink-gray-4">{timeAgo(row.creation)}</div>
                ) : null}
              </div>
              <Button
                variant="ghost"
                size="icon"
                title="Remove"
                onClick={() => remove.mutate(String(row.name))}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
