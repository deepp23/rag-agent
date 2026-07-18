import { client } from './client'
import type {
  ChatResponse,
  ConversationResponse,
  IngestResponse,
  MessageResponse,
  TokenResponse,
  UserResponse,
} from '../types'

export const authApi = {
  signup: (email: string, password: string) =>
    client.post<TokenResponse>('/auth/signup', { email, password }).then((r) => r.data),

  login: (email: string, password: string) =>
    client.post<TokenResponse>('/auth/login', { email, password }).then((r) => r.data),

  me: () => client.get<UserResponse>('/auth/me').then((r) => r.data),
}

export const conversationsApi = {
  list: () => client.get<ConversationResponse[]>('/conversations').then((r) => r.data),

  create: () => client.post<ConversationResponse>('/conversations').then((r) => r.data),

  messages: (conversationId: string) =>
    client
      .get<MessageResponse[]>(`/conversations/${conversationId}/messages`)
      .then((r) => r.data),

  sendMessage: (conversationId: string, query: string) =>
    client
      .post<ChatResponse>(`/conversations/${conversationId}/messages`, { query })
      .then((r) => r.data),
}

export const ingestApi = {
  upload: (file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post<IngestResponse>('/ingest', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (onProgress && evt.total) {
            onProgress(Math.round((evt.loaded / evt.total) * 100))
          }
        },
      })
      .then((r) => r.data)
  },
}
