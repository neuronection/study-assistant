import { Mail } from 'lucide-react'
import { AboutPanel } from '@neuronection/assistant-ui'

const GitHubGlyph = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
    <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.55 0-.27-.01-1.17-.02-2.12-3.2.7-3.88-1.36-3.88-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.19 1.76 1.19 1.03 1.75 2.69 1.25 3.35.95.1-.74.4-1.25.72-1.53-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.1 11.1 0 0 1 5.8 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.12 3.05.74.81 1.18 1.83 1.18 3.09 0 4.42-2.69 5.39-5.25 5.67.41.35.77 1.05.77 2.12 0 1.53-.01 2.76-.01 3.14 0 .3.2.67.8.55A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
  </svg>
)

const LinkedInGlyph = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.225 0z" />
  </svg>
)

export function AboutPage() {
  return (
    <div className="mx-auto w-full max-w-4xl p-6 pb-20">
      <AboutPanel
        appName="Study Assistant"
        familyCurrent="study"
        tagline="Local-first, open-source study workbench"
        description="Study Assistant is an open-source, local-first study workbench that runs in your browser or as a desktop app: course library, handwriting notes, AI chat with tools, practice builder — math-first, subject-agnostic. Your files never leave your machine."
        license={{
          name: 'Apache License 2.0',
          href: 'https://www.apache.org/licenses/LICENSE-2.0',
        }}
        linksTitle="Contact & Connect"
        links={[
          { group: 'Project', href: 'https://github.com/neuronection/study-assistant', label: 'GitHub', subtitle: 'neuronection/study-assistant', icon: GitHubGlyph },
          { group: 'Family', href: 'https://neuronection.com', label: 'neuronection.com', subtitle: 'The Neuronection family hub', icon: GitHubGlyph },
          { group: 'Family', href: 'https://github.com/neuronection/assistant-ui', label: 'assistant-ui', subtitle: 'Shared UI library', icon: GitHubGlyph },
          { group: 'Creator', href: 'https://www.linkedin.com/in/ilias-chatzopoulos-aabb22163/', label: 'LinkedIn', subtitle: 'Ilias Chatzopoulos', icon: LinkedInGlyph },
          { group: 'Creator', copyValue: 'constliakos@gmail.com', label: 'constliakos@gmail.com', subtitle: 'Click to copy', icon: Mail },
        ]}
        creator={{
          name: 'Ilias Chatzopoulos',
          role: 'Founder & Lead Architect',
          href: 'https://github.com/constLiakos',
        }}
        tech={[
          'Python + FastAPI',
          'pywebview desktop shell',
          'React SPA',
          'Tiptap editor',
          'LangChain AI gateway',
          'structured outputs',
          'Whisper STT',
          'MCP tools',
          'content-addressed blob store',
          'Apache-2.0',
        ]}
        copyright="© 2026 Neuronection"
      />
    </div>
  )
}
