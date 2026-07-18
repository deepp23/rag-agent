export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserResponse {
  id: string
  email: string
  workspace_id: string
  created_at: string
}

export interface ConversationResponse {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface RetrievedChunk {
  text: string
  score: number
  metadata: Record<string, unknown>
}

export interface MessageResponse {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ChatResponse {
  conversation_id: string
  response: string
  retrieved_chunks: RetrievedChunk[]
}

export interface IngestResponse {
  message: string
  file_name: string
  total_chunks: number
}

// Client-side only, used to render an in-flight or just-sent turn
// before the server response round-trips back.
export interface ChatTurn {
  id: string
  role: 'user' | 'assistant'
  content: string
  retrieved_chunks?: RetrievedChunk[]
  pending?: boolean
}
