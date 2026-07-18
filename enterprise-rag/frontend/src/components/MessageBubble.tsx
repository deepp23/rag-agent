import { useState } from 'react'
import type { ChatTurn } from '../types'

export default function MessageBubble({ turn }: { turn: ChatTurn }) {
  const [showSources, setShowSources] = useState(false)
  const isUser = turn.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-2xl flex-col gap-1.5 ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? 'bg-violet-600 text-white'
              : 'border border-neutral-800 bg-neutral-900 text-neutral-100'
          }`}
        >
          {turn.pending ? (
            <span className="inline-flex items-center gap-1.5 text-neutral-400">
              <Dot /> <Dot delay="150ms" /> <Dot delay="300ms" />
            </span>
          ) : (
            turn.content
          )}
        </div>

        {!isUser && !turn.pending && turn.retrieved_chunks && turn.retrieved_chunks.length > 0 && (
          <div>
            <button
              onClick={() => setShowSources((s) => !s)}
              className="text-xs font-medium text-neutral-500 transition hover:text-neutral-300"
            >
              {showSources ? 'Hide' : 'Show'} {turn.retrieved_chunks.length} source
              {turn.retrieved_chunks.length === 1 ? '' : 's'}
            </button>
            {showSources && (
              <div className="mt-2 space-y-2">
                {turn.retrieved_chunks.map((chunk, i) => (
                  <div
                    key={i}
                    className="max-w-lg rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-xs text-neutral-400"
                  >
                    <div className="mb-1 flex items-center justify-between text-neutral-600">
                      <span>Source {i + 1}</span>
                      <span>score {chunk.score.toFixed(3)}</span>
                    </div>
                    <p className="line-clamp-4">{chunk.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Dot({ delay = '0ms' }: { delay?: string }) {
  return (
    <span
      className="h-1.5 w-1.5 animate-bounce rounded-full bg-neutral-500"
      style={{ animationDelay: delay }}
    />
  )
}
