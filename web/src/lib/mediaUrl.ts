/**
 * Media-URL resolver — shared by every surface that renders project-relative
 * media (keyframes, take stills, video). Extracted from the two Filmstrips +
 * HeroShot/TakeStrip, which each carried a private copy of the same logic.
 *
 * Resolves a project-relative asset `path` to the backend `file?path=` endpoint
 * so the browser fetches it through the API proxy. When `projectId` is falsy the
 * raw `path` is returned unchanged — mirrors the original resolvers' behavior so
 * previews still render (best-effort) before a project id is known.
 */
export function fileUrl(
  apiBase: string | undefined,
  projectId: string | null | undefined,
  path: string,
): string {
  if (!projectId) return path
  return `${apiBase ?? '/api'}/projects/${projectId}/file?path=${encodeURIComponent(path)}`
}
