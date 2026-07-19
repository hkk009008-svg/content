import type { AppConfig } from '../types/project'

/**
 * Pod (RunPod GPU) gating helpers.
 *
 * `config.billing_providers` ships PROVIDER-keyed from the backend
 * (domain/scene_decomposer.py:154 BILLING_PROVIDERS), e.g.
 *   { RUNPOD_GPU: ['FLUX_DEV', 'HIDREAM_I1', 'SD3_5_LARGE', 'SUPIR_V0Q', 'CCSR'], ... }
 * — a provider bucket listing the engine keys it bills — NOT engine-keyed
 * (never `{ FLUX_DEV: 'RUNPOD_GPU' }`). isPodGated below reads the real shape;
 * see the task-7 report for why.
 */
const POD_PROVIDER = 'RUNPOD_GPU'

/** Non-engine features that also require the pod (not represented in api_registry). */
export const POD_FEATURES = ['lora_training', 'comfyui_keyframe'] as const
export type PodFeature = (typeof POD_FEATURES)[number]

export function isPodGated(engineKey: string, config: AppConfig | null): boolean {
  return !!config?.billing_providers?.[POD_PROVIDER]?.includes(engineKey)
}
