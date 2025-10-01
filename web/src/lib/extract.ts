/**
 * Extract only the draft between <document>...</document> (case-insensitive).
 * If missing, try common fences. Fallback to whole text.
 */
export function extractDraftOnly(text: string): string {
  if (!text) return ''
  const tag = /<\s*document\s*>\s*([\s\S]*?)\s*<\s*\/\s*document\s*>/i
  const m = text.match(tag)
  if (m && m[1]) return m[1].trim()

  // tolerances: ```document ...``` fenced code blocks
  const fence = /```(?:doc|document|markdown)?\s*\n([\s\S]*?)```/i
  const f = text.match(fence)
  if (f && f[1]) return f[1].trim()

  // last resort: assume entire text is the draft
  return text.trim()
}
