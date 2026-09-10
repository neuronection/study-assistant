export function isTextMaterial(material: {
  kind: string
  mime: string | null
}): boolean {
  return (
    material.kind === 'txt' ||
    material.kind === 'md' ||
    (material.mime?.startsWith('text/') ?? false)
  )
}
