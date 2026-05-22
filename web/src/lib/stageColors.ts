// Consolidated stage name → Tailwind text color map.
// This is the canonical 27-key superset; Notes.tsx and GenerationPanel.tsx
// both import from here so they stay in sync.
export const stageColors: Record<string, string> = {
  STYLE: 'text-purple-400',
  AUDIO: 'text-blue-400',
  SCENE: 'text-editorial-brass',
  DECOMPOSE: 'text-cyan-400',
  DIALOGUE: 'text-pink-400',
  GENERATE: 'text-yellow-400',
  VIDEO: 'text-orange-400',
  VALIDATED: 'text-editorial-ready',
  IDENTITY_FAIL: 'text-editorial-curtain',
  RETRY: 'text-editorial-warn',
  ASSEMBLY: 'text-indigo-400',
  COMPLETE: 'text-editorial-ready',
  DONE: 'text-editorial-ready',
  ERROR: 'text-editorial-curtain',
  CANCELLED: 'text-editorial-ivory-mute',
  WARNING: 'text-editorial-warn',
  KEYFRAME: 'text-yellow-400',
  KEYFRAME_READY: 'text-editorial-ready',
  KEYFRAME_REVIEW: 'text-editorial-brass',
  MOTION: 'text-orange-400',
  MOTION_READY: 'text-editorial-ready',
  PERFORMANCE: 'text-pink-400',
  REVIEW: 'text-editorial-brass',
  PLAN_REVIEW: 'text-cyan-400',
  DIRECTOR: 'text-purple-400',
  SHOT_FAILED: 'text-editorial-curtain',
  PAUSED: 'text-editorial-warn',
  RESUMED: 'text-editorial-ready',
}

// Warm-sepia variant for the Director's Console surface.
// Collapses the editorial palette's brass/ready/curtain/warn hues into the
// console palette's two-tone gold (active/success) + accent (fail/warn) +
// ink-mute (neutral/cancelled). The console palette has no separate warn
// color, so RETRY/PAUSED/WARNING share the accent hue with errors.
export const consoleStageColors: Record<string, string> = {
  STYLE: 'text-console-ink-mute',
  AUDIO: 'text-console-ink-mute',
  SCENE: 'text-console-gold',
  DECOMPOSE: 'text-console-ink-mute',
  DIALOGUE: 'text-console-ink-mute',
  GENERATE: 'text-console-ink-mute',
  VIDEO: 'text-console-ink-mute',
  VALIDATED: 'text-console-gold',
  IDENTITY_FAIL: 'text-console-accent',
  RETRY: 'text-console-accent',
  ASSEMBLY: 'text-console-ink-mute',
  COMPLETE: 'text-console-gold',
  DONE: 'text-console-gold',
  ERROR: 'text-console-accent',
  CANCELLED: 'text-console-ink-mute',
  WARNING: 'text-console-accent',
  KEYFRAME: 'text-console-ink-mute',
  KEYFRAME_READY: 'text-console-gold',
  KEYFRAME_REVIEW: 'text-console-gold',
  MOTION: 'text-console-ink-mute',
  MOTION_READY: 'text-console-gold',
  PERFORMANCE: 'text-console-ink-mute',
  REVIEW: 'text-console-gold',
  PLAN_REVIEW: 'text-console-ink-mute',
  DIRECTOR: 'text-console-ink-mute',
  SHOT_FAILED: 'text-console-accent',
  PAUSED: 'text-console-accent',
  RESUMED: 'text-console-gold',
}
