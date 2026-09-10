import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

function Fallback({ error }: { error: Error }) {
  const { t } = useTranslation()
  return (
    <div
      style={{
        padding: 40,
        fontFamily: 'ui-monospace, monospace',
        color: '#b91c1c',
        background: '#fef2f2',
      }}
    >
      <h1 style={{ fontSize: 18, marginBottom: 8 }}>{t('errorBoundary.title')}</h1>
      <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>
        {error.message}
        {'\n\n'}
        {error.stack}
      </pre>
      <button
        style={{ marginTop: 12, padding: '6px 14px', cursor: 'pointer' }}
        onClick={() => window.location.reload()}
      >
        {t('errorBoundary.reload')}
      </button>
    </div>
  )
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Study Assistant render error:', error, info)
  }

  render(): ReactNode {
    if (this.state.error) {
      return <Fallback error={this.state.error} />
    }
    return this.props.children
  }
}
