import { describe, expect, it } from 'vitest'
import { canResumeDeferredProviderJob } from './providerRecovery'

describe('canResumeDeferredProviderJob', () => {
  it.each([
    'VEO',
    'veo',
    'KLING_3_0',
    ' kling_3_0 ',
    'SEEDANCE',
    'seedance',
    'LTX',
    'ltx',
    'RUNWAY_GEN4',
    ' runway_gen4 ',
  ])(
    'accepts a durable saved job for %s',
    (engine) => {
      expect(canResumeDeferredProviderJob(engine, 'job-123')).toBe(true)
    },
  )

  it.each([
    ['VEO_NATIVE', 'operations/123'],
    ['LTX', ''],
    ['RUNWAY_GEN4', '   '],
    ['RUNWAY_GEN4', undefined],
    [undefined, 'job-123'],
  ])('rejects a non-resumable or identifier-free pair %#', (engine, jobId) => {
    expect(canResumeDeferredProviderJob(engine, jobId)).toBe(false)
  })
})
