const RESUMABLE_PROVIDER_ENGINES = new Set([
  'VEO',
  'KLING_3_0',
  'SEEDANCE',
  'LTX',
  'RUNWAY_GEN4',
])

/**
 * Return whether the application can safely continue an already-accepted
 * provider job through the existing motion endpoint.
 *
 * A provider name alone is not enough: resumption is available only when the
 * backend persisted the provider's durable job identifier. Keeping this
 * predicate shared prevents the global recovery notice and shot review from
 * offering contradictory actions for the same saved job.
 */
export function canResumeDeferredProviderJob(engine: unknown, jobId: unknown): boolean {
  return typeof engine === 'string'
    && RESUMABLE_PROVIDER_ENGINES.has(engine.trim().toUpperCase())
    && typeof jobId === 'string'
    && jobId.trim().length > 0
}
