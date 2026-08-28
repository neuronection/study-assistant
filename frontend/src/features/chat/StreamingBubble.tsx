import ReactMarkdown from 'react-markdown'

export function StreamingBubble({ text }: { text: string }) {
  return (
    <div className="flex animate-in fade-in flex-col items-start duration-200">
      <div className="bg-subtle max-w-[92%] rounded-xl px-3 py-2 text-sm">
        <ReactMarkdown>{text}</ReactMarkdown>
        <span className="chat-caret text-xs" aria-hidden />
      </div>
    </div>
  )
}
