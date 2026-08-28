import { apiFetch } from '@/lib/api'

export async function exportMarkdownWithDrawings(
  markdown: string,
  drawings: Array<{ id: number; png_sha: string | null }>
): Promise<string> {
  let resolved = markdown
  for (const drawing of drawings) {
    if (!drawing.png_sha) {
      continue
    }
    const response = await apiFetch(`/api/v1/blobs/${drawing.png_sha}`)
    if (!response.ok) {
      continue
    }
    const buffer = new Uint8Array(await response.arrayBuffer())
    let binary = ''
    for (let index = 0; index < buffer.length; index += 1) {
      binary += String.fromCharCode(buffer[index])
    }
    resolved = resolved.replaceAll(
      `ca-drawing://${drawing.id}`,
      `data:image/png;base64,${btoa(binary)}`
    )
  }
  return resolved
}