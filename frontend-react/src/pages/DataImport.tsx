import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Upload } from 'lucide-react'
import { MissingEndpoint } from '@/components/MissingEndpoint'
import { Button } from '@/components/ui/button'
import { useDocList } from '@/api/hooks'
import { timeAgo } from '@/lib/format'

/**
 * Data import — the list of past imports, and starting a new one.
 *
 * **Starting one cannot work here.** An import is a CSV upload followed by a column-mapping
 * step, and `upload_file` is not served (`BACKEND_GAPS.md` §2), so there is nowhere to put
 * the file. The Vue app's `DataImport.vue` is mostly the mapping UI that comes *after* the
 * upload, which is unreachable until then.
 *
 * What is built: the history list, which reads `Data Import` rows through the ordinary
 * resource API, and the upload step with its banner. The mapping step is not built —
 * building a column mapper against an upload that cannot happen would be guessing at a
 * payload nobody has seen.
 */
export function DataImportPage() {
  const navigate = useNavigate()
  const [doctype, setDoctype] = useState('CRM Lead')

  const imports = useDocList<Record<string, unknown>>('Data Import', {
    fields: ['name', 'reference_doctype', 'status', 'creation'],
    limit_page_length: 50,
    order_by: 'creation desc',
  })

  const rows = imports.data ?? []

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
        <h1 className="text-lg font-semibold text-ink-gray-8">Data import</h1>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-3xl">
          <MissingEndpoint
            className="mb-4"
            what="Uploading an import file"
            path="upload_file"
          />

          <section className="mb-8 rounded-lg border border-outline-gray-1 p-4">
            <h2 className="mb-2 text-base font-medium text-ink-gray-8">New import</h2>
            <div className="flex items-end gap-2">
              <label className="flex flex-col gap-1.5">
                <span className="text-sm text-ink-gray-5">Import into</span>
                <select
                  value={doctype}
                  onChange={(event) => setDoctype(event.target.value)}
                  className="h-8 rounded border border-outline-gray-2 bg-surface-white px-2 text-base"
                >
                  {['CRM Lead', 'CRM Deal', 'Contact', 'CRM Organization'].map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              <Button variant="solid" disabled title="Needs upload_file">
                <Upload className="h-4 w-4" />
                Choose a CSV
              </Button>
            </div>
            <p className="mt-2 text-sm text-ink-gray-4">
              The column-mapping step is not built either — it comes after an upload, and
              building a mapper against a payload nobody has seen would be guesswork.
            </p>
          </section>

          <section>
            <h2 className="mb-2 text-base font-medium text-ink-gray-8">Past imports</h2>
            {imports.isPending ? (
              <p className="text-base text-ink-gray-4">Loading…</p>
            ) : imports.isError ? (
              <p className="text-base text-ink-gray-4">
                This backend does not serve the <code>Data Import</code> doctype.
              </p>
            ) : rows.length === 0 ? (
              <p className="text-base text-ink-gray-4">Nothing imported yet.</p>
            ) : (
              <ul className="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
                {rows.map((row) => (
                  <li
                    key={String(row.name)}
                    className="flex cursor-pointer items-center gap-3 py-3 hover:bg-surface-gray-1"
                    onClick={() =>
                      navigate({
                        to: '/data-import/$importName',
                        params: { importName: String(row.name) },
                      })
                    }
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-base text-ink-gray-8">
                        {String(row.reference_doctype ?? row.name)}
                      </p>
                      <p className="text-sm text-ink-gray-5">
                        {[row.status, row.creation ? timeAgo(row.creation) : null]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
