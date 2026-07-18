import { useCallback, useEffect, useState } from 'react'
import Sidebar from '../components/Sidebar'
import ChatWindow from '../components/ChatWindow'
import UploadDialog from '../components/UploadDialog'
import { conversationsApi } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'
import type { ChatTurn, ConversationResponse } from '../types'

export default function ChatPage() {
  const [conversations, setConversations] = useState<ConversationResponse[]>([])
  const [conversationsLoading, setConversationsLoading] = useState(true)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [sending, setSending] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshConversations = useCallback(async () => {
    setConversationsLoading(true)
    try {
      const list = await conversationsApi.list()
      setConversations(list)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setConversationsLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

  const selectConversation = useCallback(async (id: string) => {
    setActiveId(id)
    setLoadingMessages(true)
    setError(null)
    try {
      const messages = await conversationsApi.messages(id)
      setTurns(
        messages.map((m) => ({ id: m.id, role: m.role, content: m.content }))
      )
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setLoadingMessages(false)
    }
  }, [])

  function handleNewChat() {
    setActiveId(null)
    setTurns([])
    setError(null)
  }

  async function handleSend(query: string) {
    setError(null)
    setSending(true)

    const userTurn: ChatTurn = { id: `local-${Date.now()}`, role: 'user', content: query }
    const pendingTurn: ChatTurn = { id: `pending-${Date.now()}`, role: 'assistant', content: '', pending: true }
    setTurns((prev) => [...prev, userTurn, pendingTurn])

    try {
      let conversationId = activeId
      if (!conversationId) {
        const conv = await conversationsApi.create()
        conversationId = conv.id
        setActiveId(conv.id)
      }

      const res = await conversationsApi.sendMessage(conversationId, query)

      setTurns((prev) =>
        prev.map((t) =>
          t.id === pendingTurn.id
            ? { id: `assistant-${Date.now()}`, role: 'assistant', content: res.response, retrieved_chunks: res.retrieved_chunks }
            : t
        )
      )
      refreshConversations()
    } catch (err) {
      setTurns((prev) => prev.filter((t) => t.id !== pendingTurn.id && t.id !== userTurn.id))
      setError(extractErrorMessage(err))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={selectConversation}
        onNewChat={handleNewChat}
        onUploadClick={() => setUploadOpen(true)}
        loading={conversationsLoading}
      />
      <div className="flex flex-1 flex-col">
        {error && (
          <div className="border-b border-red-900/50 bg-red-950/40 px-6 py-2 text-sm text-red-400">
            {error}
          </div>
        )}
        <ChatWindow turns={turns} onSend={handleSend} sending={sending} loadingMessages={loadingMessages} />
      </div>
      {uploadOpen && <UploadDialog onClose={() => setUploadOpen(false)} />}
    </div>
  )
}
