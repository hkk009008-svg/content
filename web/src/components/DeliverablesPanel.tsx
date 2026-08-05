import { useCallback, useEffect, useMemo, useState } from 'react'

interface ArtifactRecord {
  artifact_id: string
  sequence: number
  version: number
  logical_name: string
  sha256: string
  byte_size: number
  media_type: string
  provider: string | null
  model: string | null
  parameters: Record<string, unknown>
  source_hashes: Record<string, string>
  dependency_hashes: Record<string, string>
  distribution_class: 'internal' | 'client_deliverable'
  reproducibility: {
    status: 'provider_replay_only' | 'recipe_captured' | 'output_hash_only'
    bit_exact: false
    note: string
  }
}

interface ArtifactSnapshot {
  current: ArtifactRecord[]
  records: ArtifactRecord[]
  has_more: boolean
  next_before_sequence: number | null
}

interface PackageResult {
  sha256: string
  byte_size: number
  artifact_ids: string[]
  entry_count: number
  filename: string
  download_url: string
}

interface Props {
  projectId: string
}

function sizeLabel(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function replayLabel(status: ArtifactRecord['reproducibility']['status']): string {
  if (status === 'provider_replay_only') return 'Provider replay'
  if (status === 'recipe_captured') return 'Recipe captured'
  return 'Output hash only'
}

function evidenceJson(artifact: ArtifactRecord): string {
  return JSON.stringify({
    parameters: artifact.parameters,
    source_hashes: artifact.source_hashes,
    dependency_hashes: artifact.dependency_hashes,
    provider: artifact.provider,
    model: artifact.model,
  }, null, 2)
}

export default function DeliverablesPanel({ projectId }: Props) {
  const [snapshot, setSnapshot] = useState<ArtifactSnapshot | null>(null)
  const [packageResult, setPackageResult] = useState<PackageResult | null>(null)
  const [status, setStatus] = useState('')
  const [packaging, setPackaging] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [selectedByLogicalName, setSelectedByLogicalName] = useState<Record<string, string>>({})

  const load = useCallback(async (options: {
    signal?: AbortSignal
    before?: number
    append?: boolean
  } = {}) => {
    try {
      const query = new URLSearchParams({ limit: '50' })
      if (options.before) query.set('before', String(options.before))
      const response = await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/artifacts?${query.toString()}`,
        { signal: options.signal },
      )
      const body = await response.json() as ArtifactSnapshot & { error?: string }
      if (!response.ok) throw new Error(body.error || `Artifact query failed (${response.status})`)
      if (!Array.isArray(body?.current) || !Array.isArray(body?.records)) {
        throw new Error('Artifact query returned an invalid response')
      }
      setSnapshot((previous) => {
        if (!options.append || !previous) return body
        const byId = new Map<string, ArtifactRecord>()
        for (const record of [...previous.records, ...body.records]) {
          byId.set(record.artifact_id, record)
        }
        return {
          ...body,
          current: body.current,
          records: Array.from(byId.values()).sort((left, right) => right.sequence - left.sequence),
        }
      })
      return true
    } catch (error) {
      if ((error as { name?: string })?.name !== 'AbortError') {
        setStatus(error instanceof Error ? error.message : 'Artifact history is unavailable.')
      }
      return false
    }
  }, [projectId])

  useEffect(() => {
    const controller = new AbortController()
    load({ signal: controller.signal })
    return () => controller.abort()
  }, [load])

  const allArtifacts = useMemo(() => {
    const byId = new Map<string, ArtifactRecord>()
    for (const record of [...(snapshot?.current || []), ...(snapshot?.records || [])]) {
      byId.set(record.artifact_id, record)
    }
    return Array.from(byId.values()).sort((left, right) => right.sequence - left.sequence)
  }, [snapshot])

  const currentArtifactIds = useMemo(
    () => new Set((snapshot?.current || []).map((record) => record.artifact_id)),
    [snapshot],
  )

  const deliverableGroups = useMemo(() => {
    const groups = new Map<string, ArtifactRecord[]>()
    for (const record of allArtifacts) {
      if (record.distribution_class !== 'client_deliverable') continue
      const versions = groups.get(record.logical_name) || []
      versions.push(record)
      groups.set(record.logical_name, versions)
    }
    return Array.from(groups.entries())
      .map(([logicalName, versions]) => ({
        logicalName,
        versions: versions.sort((left, right) => right.version - left.version),
      }))
      .sort((left, right) => left.logicalName.localeCompare(right.logicalName))
  }, [allArtifacts])

  useEffect(() => {
    setSelectedByLogicalName((previous) => {
      const next: Record<string, string> = {}
      for (const group of deliverableGroups) {
        const previousId = previous[group.logicalName]
        const current = group.versions.find((record) => currentArtifactIds.has(record.artifact_id))
        next[group.logicalName] = group.versions.some((record) => record.artifact_id === previousId)
          ? previousId
          : (current || group.versions[0]).artifact_id
      }
      return next
    })
  }, [currentArtifactIds, deliverableGroups])

  const selectedDeliverables = useMemo(
    () => deliverableGroups.flatMap((group) => {
      const selectedId = selectedByLogicalName[group.logicalName]
      // Derive the same current/default selection synchronously that the
      // selector renders.  The normalization effect runs after paint; without
      // this fallback an operator could click during that frame and package
      // the server default instead of the visibly selected immutable version.
      const selected = group.versions.find((record) => record.artifact_id === selectedId)
        || group.versions.find((record) => currentArtifactIds.has(record.artifact_id))
        || group.versions[0]
      return selected ? [selected] : []
    }),
    [currentArtifactIds, deliverableGroups, selectedByLogicalName],
  )

  const packageDeliverables = async () => {
    if (packaging) return
    setPackaging(true)
    setStatus('Building a verified client package…')
    try {
      const response = await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/deliverables/package`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: selectedDeliverables.length > 0
            ? JSON.stringify({ artifact_ids: selectedDeliverables.map((record) => record.artifact_id) })
            : '{}',
        },
      )
      const body = await response.json() as PackageResult & { error?: string }
      if (!response.ok) throw new Error(body.error || `Packaging failed (${response.status})`)
      if (!body.download_url || !body.filename || !body.sha256) {
        throw new Error('Packaging returned an invalid response')
      }
      setPackageResult(body)
      await load()
      setStatus(`Verified package ready · ${sizeLabel(body.byte_size)}`)

      // The fixed, project-scoped URL streams with Content-Disposition. A
      // temporary anchor starts the download without buffering a large ZIP in
      // browser memory and without navigating away from the production UI.
      const link = document.createElement('a')
      link.href = body.download_url
      link.download = body.filename
      link.hidden = true
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Packaging failed.')
    } finally {
      setPackaging(false)
    }
  }

  const loadOlder = async () => {
    if (loadingOlder || !snapshot?.has_more || !snapshot.next_before_sequence) return
    setLoadingOlder(true)
    setStatus('Loading older artifact versions…')
    const loaded = await load({ before: snapshot.next_before_sequence, append: true })
    setLoadingOlder(false)
    if (loaded) setStatus('')
  }

  return (
    <section className="mb-4 rounded border border-line bg-app/60 p-3" aria-labelledby="deliverables-title">
      <div className="flex items-center justify-between gap-2">
        <h3 id="deliverables-title" className="font-mono text-[10px] uppercase tracking-wider text-dim">
          Client delivery
        </h3>
        <span className="font-mono text-[10px] text-dim">
          {deliverableGroups.length} deliverables · {allArtifacts.length} versions
        </span>
      </div>
      {deliverableGroups.length > 0 ? (
        <ul className="mt-2 space-y-1.5" aria-label="Versioned client deliverables">
          {deliverableGroups.map((group) => {
            const artifact = group.versions.find(
              (record) => record.artifact_id === selectedByLogicalName[group.logicalName],
            ) || group.versions[0]
            return (
            <li key={group.logicalName} className="text-[10px] leading-4 text-mut">
              <div className="flex justify-between gap-2">
                <span className="truncate text-tx">{group.logicalName}</span>
                <label className="shrink-0 font-mono">
                  <span className="sr-only">Version for {group.logicalName}</span>
                  <select
                    aria-label={`Version for ${group.logicalName}`}
                    value={artifact.artifact_id}
                    onChange={(event) => {
                      setSelectedByLogicalName((previous) => ({
                        ...previous,
                        [group.logicalName]: event.target.value,
                      }))
                      setPackageResult(null)
                    }}
                    className="rounded border border-line bg-app px-1 py-0.5 text-[10px] text-tx"
                  >
                    {group.versions.map((version) => (
                      <option key={version.artifact_id} value={version.artifact_id}>
                        v{version.version}{currentArtifactIds.has(version.artifact_id) ? ' · current' : ' · archived'}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="flex justify-between gap-2 font-mono text-dim">
                <span>{replayLabel(artifact.reproducibility.status)} · not bit-exact</span>
                <span title={artifact.sha256}>sha256:{artifact.sha256.slice(0, 8)}</span>
              </div>
              <details className="mt-1">
                <summary className="cursor-pointer font-mono text-[9px] text-dim">
                  Inspect recipe and provenance
                </summary>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-bg p-2 font-mono text-[9px] text-mut">
                  {evidenceJson(artifact)}
                </pre>
              </details>
            </li>
          )})}
        </ul>
      ) : (
        <p className="mt-2 text-[10px] leading-4 text-mut">
          No versioned delivery yet. An existing final export will be adopted with output-hash-only provenance when packaged.
        </p>
      )}
      <button
        type="button"
        onClick={packageDeliverables}
        disabled={packaging}
        aria-busy={packaging}
        className="mt-3 w-full rounded bg-pri px-2 py-2 font-mono text-[10px] uppercase tracking-wide text-app hover:brightness-110 disabled:opacity-50"
      >
        {packaging ? 'Packaging…' : (
          selectedDeliverables.length > 0 ? 'Package selected versions' : 'Package client deliverables'
        )}
      </button>
      {status && <p role="status" className="mt-2 text-[10px] leading-4 text-mut">{status}</p>}
      {packageResult && (
        <p className="mt-1 break-all font-mono text-[9px] text-dim" title={packageResult.sha256}>
          {packageResult.filename} · sha256:{packageResult.sha256.slice(0, 12)}
        </p>
      )}
      <details className="mt-3 border-t border-line pt-2">
        <summary className="cursor-pointer font-mono text-[10px] text-dim">
          All production artifact versions ({allArtifacts.length})
        </summary>
        {allArtifacts.length > 0 ? (
          <ul className="mt-2 max-h-48 space-y-1 overflow-auto" aria-label="All production artifact versions">
            {allArtifacts.map((artifact) => (
              <li key={artifact.artifact_id} className="font-mono text-[9px] text-dim">
                <details>
                  <summary className="flex cursor-pointer justify-between gap-2">
                    <span className="truncate">
                      {artifact.logical_name} · v{artifact.version} · {artifact.distribution_class === 'client_deliverable' ? 'client' : 'internal'}
                    </span>
                    <span className="shrink-0" title={artifact.sha256}>sha256:{artifact.sha256.slice(0, 8)}</span>
                  </summary>
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-bg p-2 text-mut">
                    {evidenceJson(artifact)}
                  </pre>
                </details>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[10px] text-mut">No indexed production artifacts yet.</p>
        )}
      </details>
      {snapshot?.has_more && (
        <button
          type="button"
          onClick={loadOlder}
          disabled={loadingOlder}
          className="mt-2 w-full rounded border border-line px-2 py-1.5 font-mono text-[10px] text-mut hover:text-tx disabled:opacity-50"
        >
          {loadingOlder ? 'Loading…' : 'Load older versions'}
        </button>
      )}
    </section>
  )
}
