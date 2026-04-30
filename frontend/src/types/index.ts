// API Types

export interface Citation {
  document_id: string
  document_name: string
  page_number: number
  excerpt: string
}

export interface ArbiterFlag {
  flag_type: 'contradiction' | 'unsupported' | 'vague' | 'risk'
  description: string
  related_fact_ids: string[]
}

export interface Message {
  id: string
  role: 'agent' | 'witness' | 'arbiter'
  content: string
  citations: Citation[]
  arbiter_flags: ArbiterFlag[]
  truth_score: number | null
  created_at: string
}

export interface ProfileBrief {
  id: string
  name: string
  role: string
}

export interface Session {
  id: string
  witness_name: string
  agent_mode: 'plaintiff_coach' | 'defense_cross'
  started_at: string
  ended_at: string | null
  status: 'active' | 'completed' | 'abandoned'
  profile_id: string | null
  profile: ProfileBrief | null
}

export interface ProfileDocument {
  document_id: string
  document_name: string
  familiarity_level: 'authored' | 'familiar' | 'mentioned'
}

export interface Profile {
  id: string
  name: string
  role: 'plaintiff' | 'defendant' | 'witness' | 'expert'
  relationship_to_case: string
  knowledge_areas: string[]
  limitations: string | null
  notes: string | null
  agent_intensity: number
  familiar_documents: ProfileDocument[]
  session_count: number
  created_at: string
  updated_at: string
}

export interface ProfileSummary {
  id: string
  name: string
  role: string
  relationship_to_case: string
  session_count: number
}

export interface FactEntry {
  id: string
  fact_text: string
  confidence: 'certain' | 'uncertain' | 'estimate' | 'dont_recall'
  source_type: 'witness' | 'document' | 'inference'
  citations: Citation[]
  contradicts: string[]
  created_at: string
}

export interface LedgerResponse {
  facts: FactEntry[]
  contradiction_count: number
  unsupported_count: number
}

export interface ChatResponse {
  agent_message: string
  citations: Citation[]
  arbiter_flags: ArbiterFlag[]
  new_facts: string[]
  truth_score: number
}

export interface SessionSummary {
  session_id: string
  witness_name: string
  agent_mode: string
  duration_minutes: number
  total_exchanges: number
  facts_established: number
  contradictions_found: number
  unsupported_claims: number
  key_facts: string[]
  weak_spots: string[]
  attack_vectors: string[]
  recommended_followups: string[]
}

// Question Generation Types
export interface GeneratedQuestion {
  question: string
  purpose: string
  suggested_followups: string[]
  citations: Citation[]
  topic: string
}

export interface QuestionGenerateRequest {
  count: number
  focus_area?: string
  difficulty: 'standard' | 'aggressive' | 'expert'
  include_citations: boolean
}

export interface QuestionGenerateResponse {
  session_id: string
  questions: GeneratedQuestion[]
  focus_area: string | null
  difficulty: string
  generated_count: number
}

// Clerk Agent Types
export interface ClerkMessage {
  role: 'user' | 'clerk'
  content: string
}

export interface ClerkSource {
  source_type: 'document' | 'fact_ledger'
  content: string
  document_name: string | null
  page_number: number | null
  confidence: string | null
  similarity_score: number | null
}

export interface ClerkResponse {
  answer: string
  citations: Citation[]
  sources: ClerkSource[]
  facts_referenced: number
  documents_searched: number
}
