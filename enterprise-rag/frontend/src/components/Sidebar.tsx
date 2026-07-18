import { useAuth } from '../context/AuthContext'
import type { ConversationResponse } from '../types'

interface Props {
  conversations: ConversationResponse[]
  activeId: string | null
  onSelect: (id: string) => void
  onNewChat: () => void
  onUploadClick: () => void
  loading: boolean
}

export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onUploadClick,
  loading,
}: Props) {
  const { user, logout } = useAuth()

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-neutral-800 bg-neutral-950">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 text-sm font-semibold text-white">
          R
        </div>
        <span className="text-sm font-semibold text-neutral-200">Enterprise RAG</span>
      </div>

      <div className="flex flex-col gap-2 px-3">
        <button
          onClick={onNewChat}
          className="flex items-center justify-center gap-2 rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm font-medium text-neutral-200 transition hover:bg-neutral-800"
        >
          <span className="text-base leading-none">+</span> New chat
        </button>
        <button
          onClick={onUploadClick}
          className="flex items-center justify-center gap-2 rounded-lg border border-violet-800/60 bg-violet-950/40 px-3 py-2 text-sm font-medium text-violet-300 transition hover:bg-violet-900/40"
        >
          <span className="text-base leading-none">↑</span> Upload document
        </button>
      </div>

      <div className="mt-4 flex-1 overflow-y-auto px-3">
        <p className="mb-2 px-1 text-xs font-medium uppercase tracking-wide text-neutral-600">
          Conversations
        </p>
        {loading && (
          <p className="px-1 text-sm text-neutral-600">Loading…</p>
        )}
        {!loading && conversations.length === 0 && (
          <p className="px-1 text-sm text-neutral-600">No conversations yet.</p>
        )}
        <div className="space-y-1">
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => onSelect(c.id)}
              className={`block w-full truncate rounded-lg px-3 py-2 text-left text-sm transition ${
                activeId === c.id
                  ? 'bg-neutral-800 text-neutral-100'
                  : 'text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200'
              }`}
              title={c.title ?? 'Untitled conversation'}
            >
              {c.title || 'New conversation'}
            </button>
          ))}
        </div>
      </div>

      <div className="border-t border-neutral-800 px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-neutral-200">{user?.email}</p>
            <p className="text-xs text-neutral-600">Personal workspace</p>
          </div>
          <button
            onClick={logout}
            className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-300"
          >
            Log out
          </button>
        </div>
      </div>
    </aside>
  )
}
