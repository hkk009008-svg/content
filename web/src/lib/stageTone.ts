// Stage name -> indigo-token text-color class. Replaces the deleted
// stageColors/consoleStageColors editorial/console palette maps with a
// single token-based tone function shared by every stage-label consumer.
export function stageTone(stage: string): string {
  switch (stage) {
    case 'DONE':
    case 'COMPLETE':
    case 'VALIDATED':
      return 'text-ok'
    case 'ERROR':
    case 'IDENTITY_FAIL':
    case 'SHOT_FAILED':
    case 'CANCELLED':
      return 'text-fail'
    case 'RETRY':
    case 'WARNING':
    case 'PAUSED':
      return 'text-warn'
    default:
      return 'text-mut'
  }
}
