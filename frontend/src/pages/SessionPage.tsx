import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Send, AlertTriangle, FileText, Clock, Sparkles, Download, X, Copy, Check, BookOpen } from 'lucide-react'
import { useSession, useEndSession } from '../hooks/useSession'
import { useMessages, useSendMessage } from '../hooks/useChat'
import { useLedger } from '../hooks/useLedger'
import { useGenerateQuestions, useExportQuestions } from '../hooks/useQuestions'
import TruthOMeter from '../components/TruthOMeter'
import type { Message, ArbiterFlag, Citation, FactEntry, GeneratedQuestion } from '../types'

export default function SessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()

  const { data: session } = useSession(sessionId!)
  const { data: messages } = useMessages(sessionId!)
  const { data: ledger } = useLedger(sessionId!)
  const sendMessage = useSendMessage(sessionId!)
  const endSession = useEndSession()

  const [input, setInput] = useState('')
  const [showQuestions, setShowQuestions] = useState(false)
  const [questions, setQuestions] = useState<GeneratedQuestion[]>([])
  const [questionCount, setQuestionCount] = useState(5)
  const [difficulty, setDifficulty] = useState<'standard' | 'aggressive' | 'expert'>('standard')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const generateQuestions = useGenerateQuestions()
  const exportQuestions = useExportQuestions()

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || sendMessage.isPending) return

    const message = input.trim()
    setInput('')

    await sendMessage.mutateAsync(message)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleEndSession = async () => {
    if (!sessionId) return
    await endSession.mutateAsync(sessionId)
    navigate('/')
  }

  const handleGenerateQuestions = async () => {
    if (!sessionId) return
    const result = await generateQuestions.mutateAsync({
      sessionId,
      request: { count: questionCount, difficulty },
    })
    setQuestions(result.questions)
    setShowQuestions(true)
  }

  const handleExportQuestions = async () => {
    if (!sessionId) return
    const content = await exportQuestions.mutateAsync({ sessionId, format: 'markdown' })
    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `questions_${sessionId}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-500">Loading session...</div>
      </div>
    )
  }

  const isCoach = session.agent_mode === 'plaintiff_coach'

  // Truth-O-Meter score is sourced from the most recent agent-role message.
  // Arbiter analysis runs against the witness response but its outputs
  // (arbiter_flags + truth_score) are persisted on the agent message that
  // follows it (see app/services/chat.py:99-105). Null = no score yet.
  const latestAgentScore =
    messages?.filter((m) => m.role === 'agent').slice(-1)[0]?.truth_score ?? null

  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      {/* Header */}
      <header className={`py-4 px-6 ${isCoach ? 'bg-coach-green' : 'bg-defense-red'} text-white`}>
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/')}
              className="p-2 hover:bg-white/20 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1 className="font-semibold">{session.witness_name}</h1>
              <p className="text-sm opacity-80">
                {isCoach ? "Plaintiff's Coach" : 'Defense Cross-Examination'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm opacity-80">
              <Clock className="w-4 h-4" />
              <span>
                {Math.round(
                  (Date.now() - new Date(session.started_at).getTime()) / 60000
                )}m
              </span>
            </div>
            <button
              onClick={() => navigate(`/clerk?session=${sessionId}`)}
              className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
            >
              <BookOpen className="w-4 h-4" />
              Ask Clerk
            </button>
            <button
              onClick={handleGenerateQuestions}
              disabled={generateQuestions.isPending}
              className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
            >
              <Sparkles className="w-4 h-4" />
              {generateQuestions.isPending ? 'Generating...' : 'Generate Questions'}
            </button>
            <button
              onClick={handleEndSession}
              disabled={endSession.isPending}
              className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg text-sm font-medium transition-colors"
            >
              {endSession.isPending ? 'Ending...' : 'End Session'}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex max-w-7xl mx-auto w-full">
        {/* Chat Panel */}
        <div className="flex-1 flex flex-col">
          {/* Truth-O-Meter — aggregated arbiter confidence for the latest agent message. */}
          <div className="px-6 pt-4">
            <TruthOMeter score={latestAgentScore} className="mb-4" />
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4 chat-scroll">
            {/* Welcome message */}
            {(!messages || messages.length === 0) && (
              <div className="text-center py-12 text-gray-500">
                <p className="text-lg font-medium mb-2">
                  {isCoach
                    ? "Let's begin. Tell me about the situation with your kitchen renovation."
                    : "I'll be cross-examining you today. Let's start with the basics."}
                </p>
                <p className="text-sm">Type your response below to begin.</p>
              </div>
            )}

            {messages?.map((message) => (
              <MessageBubble key={message.id} message={message} isCoach={isCoach} />
            ))}

            {sendMessage.isPending && (
              <div className="flex justify-start">
                <div className="bg-gray-200 rounded-2xl px-4 py-3 animate-pulse">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-4 bg-white border-t">
            <div className="flex gap-3">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your response..."
                rows={2}
                className="flex-1 px-4 py-3 border border-gray-300 rounded-xl resize-none focus:ring-2 focus:ring-legal-navy focus:border-transparent"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || sendMessage.isPending}
                className={`px-6 rounded-xl font-medium text-white transition-colors disabled:opacity-50 ${
                  isCoach
                    ? 'bg-coach-green hover:bg-opacity-90'
                    : 'bg-defense-red hover:bg-opacity-90'
                }`}
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>

        {/* Ledger Sidebar */}
        <aside className="w-80 bg-white border-l overflow-y-auto">
          <div className="p-4 border-b">
            <h2 className="font-semibold text-gray-900">Fact Ledger</h2>
            {ledger && (
              <div className="flex gap-4 mt-2 text-sm">
                <span className="text-gray-600">
                  {ledger.facts.length} facts
                </span>
                {ledger.contradiction_count > 0 && (
                  <span className="text-defense-red font-medium">
                    {ledger.contradiction_count} contradictions
                  </span>
                )}
                {ledger.unsupported_count > 0 && (
                  <span className="text-yellow-600">
                    {ledger.unsupported_count} unsupported
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="p-4 space-y-3">
            {ledger?.facts.map((fact) => (
              <FactCard key={fact.id} fact={fact} />
            ))}

            {(!ledger || ledger.facts.length === 0) && (
              <p className="text-gray-500 text-sm text-center py-8">
                Facts will appear here as you testify
              </p>
            )}
          </div>
        </aside>
      </main>

      {/* Questions Modal */}
      {showQuestions && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            {/* Modal Header */}
            <div className="p-6 border-b flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold text-gray-900">Generated Questions</h2>
                <p className="text-sm text-gray-500 mt-1">
                  {questions.length} questions • {difficulty} difficulty
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleExportQuestions}
                  disabled={exportQuestions.isPending}
                  className="px-4 py-2 bg-legal-navy text-white rounded-lg text-sm font-medium hover:bg-opacity-90 flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  {exportQuestions.isPending ? 'Exporting...' : 'Download'}
                </button>
                <button
                  onClick={() => setShowQuestions(false)}
                  className="p-2 text-gray-400 hover:text-gray-600"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Settings */}
            <div className="p-4 bg-gray-50 border-b flex items-center gap-4">
              <div className="flex items-center gap-2">
                <label className="text-sm text-gray-600">Count:</label>
                <select
                  value={questionCount}
                  onChange={(e) => setQuestionCount(parseInt(e.target.value))}
                  className="px-3 py-1 border rounded-lg text-sm"
                >
                  {[5, 10, 15, 20].map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-2">
                <label className="text-sm text-gray-600">Difficulty:</label>
                <select
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value as typeof difficulty)}
                  className="px-3 py-1 border rounded-lg text-sm"
                >
                  <option value="standard">Standard</option>
                  <option value="aggressive">Aggressive</option>
                  <option value="expert">Expert</option>
                </select>
              </div>
              <button
                onClick={handleGenerateQuestions}
                disabled={generateQuestions.isPending}
                className="px-4 py-1 bg-coach-green text-white rounded-lg text-sm font-medium hover:bg-opacity-90"
              >
                {generateQuestions.isPending ? 'Generating...' : 'Regenerate'}
              </button>
            </div>

            {/* Questions List */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {questions.map((q, i) => (
                <QuestionCard key={i} question={q} index={i + 1} />
              ))}

              {questions.length === 0 && !generateQuestions.isPending && (
                <div className="text-center py-12 text-gray-500">
                  <Sparkles className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>Click "Generate Questions" to create prep questions</p>
                </div>
              )}

              {generateQuestions.isPending && (
                <div className="text-center py-12 text-gray-500">
                  <div className="animate-spin w-8 h-8 border-4 border-legal-navy border-t-transparent rounded-full mx-auto mb-4" />
                  <p>Generating questions based on your session...</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MessageBubble({ message, isCoach }: { message: Message; isCoach: boolean }) {
  const isWitness = message.role === 'witness'

  return (
    <div className={`flex ${isWitness ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isWitness
            ? 'bg-legal-navy text-white'
            : isCoach
              ? 'bg-green-100 text-gray-900'
              : 'bg-red-100 text-gray-900'
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>

        {/* Citations */}
        {message.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-white/20 space-y-2">
            {message.citations.map((cite, i) => (
              <CitationBadge key={i} citation={cite} />
            ))}
          </div>
        )}

        {/* Arbiter Flags */}
        {message.arbiter_flags.length > 0 && (
          <div className="mt-3 pt-3 border-t border-white/20 space-y-2">
            {message.arbiter_flags.map((flag, i) => (
              <FlagBadge key={i} flag={flag} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function CitationBadge({ citation }: { citation: Citation }) {
  return (
    <div className="flex items-start gap-2 text-xs opacity-80">
      <FileText className="w-3 h-3 mt-0.5 flex-shrink-0" />
      <span>
        {citation.document_name}, p.{citation.page_number}
      </span>
    </div>
  )
}

function FlagBadge({ flag }: { flag: ArbiterFlag }) {
  const colors = {
    contradiction: 'bg-red-500',
    unsupported: 'bg-yellow-500',
    vague: 'bg-orange-500',
    risk: 'bg-purple-500',
  }

  return (
    <div className="flex items-start gap-2 text-xs">
      <AlertTriangle className={`w-3 h-3 mt-0.5 flex-shrink-0 ${colors[flag.flag_type]}`} />
      <span>{flag.description}</span>
    </div>
  )
}

function FactCard({ fact }: { fact: FactEntry }) {
  const confidenceColors = {
    certain: 'bg-green-100 text-green-800',
    uncertain: 'bg-yellow-100 text-yellow-800',
    estimate: 'bg-orange-100 text-orange-800',
    dont_recall: 'bg-gray-100 text-gray-800',
  }

  const hasContradiction = fact.contradicts.length > 0
  const hasSupport = fact.citations.length > 0

  return (
    <div
      className={`p-3 rounded-lg border ${
        hasContradiction
          ? 'border-red-300 bg-red-50'
          : hasSupport
            ? 'border-green-200 bg-green-50'
            : 'border-yellow-200 bg-yellow-50'
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <span
          className={`px-2 py-0.5 rounded text-xs font-medium ${
            confidenceColors[fact.confidence]
          }`}
        >
          {fact.confidence.replace('_', ' ')}
        </span>
        {hasContradiction && (
          <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />
        )}
      </div>

      <p className="text-sm text-gray-900">{fact.fact_text}</p>

      {hasSupport && (
        <div className="mt-2 text-xs text-gray-500">
          📄 {fact.citations[0].document_name}, p.{fact.citations[0].page_number}
        </div>
      )}

      {!hasSupport && (
        <div className="mt-2 text-xs text-yellow-600">⚠️ No documentary support</div>
      )}
    </div>
  )
}

function QuestionCard({ question, index }: { question: GeneratedQuestion; index: number }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(question.question)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="px-2 py-0.5 bg-legal-navy/10 text-legal-navy text-xs font-medium rounded">
              #{index}
            </span>
            <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded capitalize">
              {question.topic}
            </span>
          </div>
          <p className="text-gray-900 font-medium">{question.question}</p>
          <p className="text-sm text-gray-500 mt-2 italic">{question.purpose}</p>
        </div>
        <button
          onClick={handleCopy}
          className="p-2 text-gray-400 hover:text-gray-600 flex-shrink-0"
          title="Copy question"
        >
          {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>

      {question.suggested_followups.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <p className="text-xs font-medium text-gray-500 mb-2">Follow-up questions:</p>
          <ul className="space-y-1">
            {question.suggested_followups.map((fu, i) => (
              <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                <span className="text-gray-400">→</span>
                {fu}
              </li>
            ))}
          </ul>
        </div>
      )}

      {question.citations.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <p className="text-xs text-gray-400">
            📄 {question.citations.map((c) => `${c.document_name}, p.${c.page_number}`).join(' • ')}
          </p>
        </div>
      )}
    </div>
  )
}
