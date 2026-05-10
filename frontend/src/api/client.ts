import type {
  Session,
  Message,
  ChatResponse,
  LedgerResponse,
  SessionSummary,
  Profile,
  ProfileSummary,
  QuestionGenerateRequest,
  QuestionGenerateResponse,
  ClerkMessage,
  ClerkResponse,
} from '../types'

const API_BASE = '/api/v1'

// Clerk token getter — registered by ClerkTokenSync in main.tsx
let _clerkGetToken: (() => Promise<string | null>) | null = null

export function initClerkAuth(fn: () => Promise<string | null>): void {
  _clerkGetToken = fn
}

async function fetchAPI<T>(
  endpoint: string,
  options: RequestInit = {},
  requireAuth: boolean = true
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }

  if (requireAuth && _clerkGetToken) {
    const token = await _clerkGetToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    window.location.href = '/login'
    throw new Error('Session expired. Please log in again.')
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// Sessions
export async function createSession(
  witnessName: string,
  agentMode: 'plaintiff_coach' | 'defense_cross',
  profileId?: string
): Promise<Session> {
  return fetchAPI<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify({
      witness_name: witnessName,
      agent_mode: agentMode,
      profile_id: profileId || null,
    }),
  })
}

export async function getSessions(): Promise<Session[]> {
  return fetchAPI<Session[]>('/sessions')
}

export async function getSession(sessionId: string): Promise<Session> {
  return fetchAPI<Session>(`/sessions/${sessionId}`)
}

export async function endSession(sessionId: string): Promise<SessionSummary> {
  return fetchAPI<SessionSummary>(`/sessions/${sessionId}/end`, {
    method: 'POST',
  })
}

// Chat
export async function sendMessage(
  sessionId: string,
  message: string
): Promise<ChatResponse> {
  return fetchAPI<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message }),
  })
}

export async function getMessages(sessionId: string): Promise<Message[]> {
  return fetchAPI<Message[]>(`/sessions/${sessionId}/messages`)
}

// Ledger
export async function getLedger(sessionId: string): Promise<LedgerResponse> {
  return fetchAPI<LedgerResponse>(`/sessions/${sessionId}/ledger`)
}

// Health
export async function checkHealth(): Promise<{ status: string; database: string }> {
  return fetchAPI('/health')
}

// Profiles
export async function getProfiles(): Promise<ProfileSummary[]> {
  return fetchAPI<ProfileSummary[]>('/profiles')
}

export async function getProfile(profileId: string): Promise<Profile> {
  return fetchAPI<Profile>(`/profiles/${profileId}`)
}

export async function createProfile(data: {
  name: string
  role: 'plaintiff' | 'defendant' | 'witness' | 'expert'
  relationship_to_case: string
  knowledge_areas?: string[]
  limitations?: string
  notes?: string
  agent_intensity?: number
  familiar_document_ids?: string[]
}): Promise<Profile> {
  return fetchAPI<Profile>('/profiles', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateProfile(
  profileId: string,
  data: Partial<{
    name: string
    role: 'plaintiff' | 'defendant' | 'witness' | 'expert'
    relationship_to_case: string
    knowledge_areas: string[]
    limitations: string
    notes: string
    agent_intensity: number
  }>
): Promise<Profile> {
  return fetchAPI<Profile>(`/profiles/${profileId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteProfile(profileId: string): Promise<void> {
  await fetchAPI(`/profiles/${profileId}`, {
    method: 'DELETE',
  })
}

export async function addDocumentToProfile(
  profileId: string,
  documentId: string,
  familiarityLevel: 'authored' | 'familiar' | 'mentioned' = 'familiar'
): Promise<void> {
  await fetchAPI(`/profiles/${profileId}/documents`, {
    method: 'POST',
    body: JSON.stringify({ document_id: documentId, familiarity_level: familiarityLevel }),
  })
}

export async function removeDocumentFromProfile(
  profileId: string,
  documentId: string
): Promise<void> {
  await fetchAPI(`/profiles/${profileId}/documents/${documentId}`, {
    method: 'DELETE',
  })
}

// Question Generation
export async function generateQuestions(
  sessionId: string,
  request: Partial<QuestionGenerateRequest> = {}
): Promise<QuestionGenerateResponse> {
  return fetchAPI<QuestionGenerateResponse>(`/sessions/${sessionId}/generate-questions`, {
    method: 'POST',
    body: JSON.stringify({
      count: request.count || 5,
      focus_area: request.focus_area || null,
      difficulty: request.difficulty || 'standard',
      include_citations: request.include_citations ?? true,
    }),
  })
}

// Clerk Agent (legal research — different from Clerk auth)
export async function askClerk(
  query: string,
  sessionId?: string,
  conversationHistory: ClerkMessage[] = []
): Promise<ClerkResponse> {
  return fetchAPI<ClerkResponse>('/clerk/ask', {
    method: 'POST',
    body: JSON.stringify({
      query,
      session_id: sessionId || null,
      conversation_history: conversationHistory,
    }),
  })
}

export async function exportQuestions(
  sessionId: string,
  format: 'text' | 'markdown' = 'markdown'
): Promise<string> {
  const token = _clerkGetToken ? await _clerkGetToken() : null
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/export-questions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      format,
      include_citations: true,
      include_followups: true,
      include_purpose: false,
    }),
  })

  if (!response.ok) {
    throw new Error('Failed to export questions')
  }

  return response.text()
}
