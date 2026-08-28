import { FileText, FileType2, ImageIcon, Sheet } from 'lucide-react'

export function KindIcon({ kind, className }: { kind: string; className?: string }) {
  if (kind === 'image') {
    return <ImageIcon className={className} aria-hidden />
  }
  if (kind === 'pdf') {
    return <Sheet className={className} aria-hidden />
  }
  if (kind === 'md' || kind === 'txt') {
    return <FileType2 className={className} aria-hidden />
  }
  return <FileText className={className} aria-hidden />
}
