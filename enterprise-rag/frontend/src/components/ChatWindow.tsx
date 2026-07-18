import { useEffect, useRef, useState, type FormEvent } from 'react'
import MessageBubble from './MessageBubble'
import type { ChatTurn } from '../types'

interface Props {
  turns: ChatTurn[]
  onSend: (query: string) => void
  sending: boolean
  loadingMessages: boolean
}

export default function ChatWindow({ turns, onSend, sending, loadingMessages }: Props) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const query = input.trim()
    if (!query || sending) return
    setInput('')
    onSend(query)
  }

  return (
    <div className="flex h-full flex-1 flex-col bg-neutral-950">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {loadingMessages ? (
          <p className="mt-10 text-center text-sm text-neutral-600">Loading conversation…</p>
        ) : turns.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-5">
            {turns.map((t) => (
              <MessageBubble key={t.id} turn={t} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-neutral-800 px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
            placeholder="Ask a question about your documents…"
            rows={1}
            maxLength={2000}
            className="max-h-40 flex-1 resize-none rounded-xl border border-neutral-800 bg-neutral-900 px-4 py-3 text-sm text-neutral-100 placeholder-neutral-600 outline-none transition focus:border-violet-500 focus:ring-1 focus:ring-violet-500"
          />
          <button
            type="submit"
            disabled={!input.trim() || sending}
            className="flex h-11 shrink-0 items-center justify-center rounded-xl bg-violet-600 px-4 text-sm font-medium text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 pt-16 text-center">
      <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-600 text-xl text-white">
        💬
      </div>
      <h2 className="text-lg font-medium text-neutral-200">Ask anything about your documents</h2>
      <p className="max-w-sm text-sm text-neutral-600">
        Upload a document from the sidebar, then ask a question here to get an answer grounded
        in your workspace's content.
      </p>
    </div>
  )
}
