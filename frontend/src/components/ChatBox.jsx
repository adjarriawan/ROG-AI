import { useCallback, useEffect, useRef, useState } from 'react'
import HealthBadge from './HealthBadge'
import MessageBubble from './MessageBubble'
import ModelPicker from './ModelPicker'
import Sidebar from './Sidebar'
import UploadButton from './UploadButton'
import {
  addFact,
  deleteDocument,
  deleteFact,
  fetchDocuments,
  fetchKnowledge,
  fetchHealth,
  fetchHistory,
  fetchModels,
  fetchSessions,
  reviewFact,
  sendChat,
  uploadFile,
} from '../services/api'

function newSessionId() {
  return `session-${crypto.randomUUID().slice(0, 8)}`
}

function initialSession() {
  let id = localStorage.getItem('session_id')
  if (!id) {
    id = newSessionId()
    localStorage.setItem('session_id', id)
  }
  return id
}

export default function ChatBox() {
  const [sessionId, setSessionId] = useState(initialSession)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')

  const [health, setHealth] = useState(null)
  const [models, setModels] = useState([])
  const [model, setModel] = useState(localStorage.getItem('model') ?? '')
  const [sessions, setSessions] = useState([])
  const [documents, setDocuments] = useState([])
  const [facts, setFacts] = useState([])
  // Pending is what needs a human; show that first.
  const [factFilter, setFactFilter] = useState('pending')

  const endRef = useRef(null)

  const refreshHealth = useCallback(() => {
    fetchHealth().then(setHealth).catch(() => setHealth(null))
  }, [])

  const refreshFacts = useCallback(() => {
    fetchKnowledge(factFilter).then(setFacts).catch(() => {})
  }, [factFilter])

  const refreshSidebar = useCallback(() => {
    fetchSessions().then(setSessions).catch(() => {})
    fetchDocuments().then(setDocuments).catch(() => {})
  }, [])

  useEffect(refreshFacts, [refreshFacts])

  useEffect(() => {
    refreshHealth()
    refreshSidebar()
    fetchModels()
      .then((data) => {
        setModels(data.models)
        // Keep the stored choice only if it still exists and can run tools.
        const stored = localStorage.getItem('model')
        const usable = data.models.find((m) => m.name === stored && m.supports_tools)
        setModel(usable ? stored : data.current)
      })
      .catch(() => {})
  }, [refreshHealth, refreshSidebar])

  useEffect(() => {
    fetchHistory(sessionId).then((rows) =>
      setMessages(rows.map((r) => ({ role: r.role, message: r.message }))),
    )
  }, [sessionId])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  const push = (m) => setMessages((prev) => [...prev, m])

  function chooseModel(name) {
    setModel(name)
    localStorage.setItem('model', name)
  }

  function selectSession(id) {
    if (id === sessionId) return
    setSessionId(id)
    localStorage.setItem('session_id', id)
  }

  function startNewSession() {
    const id = newSessionId()
    setMessages([])
    selectSession(id)
  }

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return

    setInput('')
    push({ role: 'user', message: text })
    setBusy(true)
    try {
      const res = await sendChat(sessionId, text, model || undefined)
      push({
        role: 'assistant',
        message: res.answer,
        toolUsed: res.tool_used,
        sources: res.sources,
        model: res.model,
      })
      refreshSidebar()
    } catch (err) {
      push({ role: 'error', message: err.message })
      refreshHealth() // a failure is often a dependency being down
    } finally {
      setBusy(false)
    }
  }

  async function handleFile(file) {
    setBusy(true)
    setStatus(`Mengunggah ${file.name}...`)
    try {
      const res = await uploadFile(sessionId, file)
      push({
        role: 'assistant',
        message:
          res.kind === 'image'
            ? `Gambar **${res.filename}** siap. Silakan tanyakan isinya.`
            : `Dokumen **${res.filename}** diproses menjadi ${res.chunks} chunk dan masuk ke knowledge base.`,
      })
      refreshSidebar()
    } catch (err) {
      push({ role: 'error', message: err.message })
    } finally {
      setBusy(false)
      setStatus('')
    }
  }

  async function handleReviewFact(id, decision) {
    try {
      await reviewFact(id, decision)
      refreshFacts()
    } catch (err) {
      push({ role: 'error', message: err.message })
    }
  }

  async function handleDeleteFact(id) {
    if (!confirm('Hapus fakta ini secara permanen?')) return
    try {
      await deleteFact(id)
      refreshFacts()
    } catch (err) {
      push({ role: 'error', message: err.message })
    }
  }

  async function handleAddFact(content) {
    try {
      await addFact(content)
      // A manually added fact is approved, so show the list it landed in.
      setFactFilter('approved')
    } catch (err) {
      push({ role: 'error', message: err.message })
    }
  }

  async function handleDeleteDocument(filename) {
    if (!confirm(`Hapus "${filename}" dari knowledge base?`)) return
    try {
      await deleteDocument(filename)
      refreshSidebar()
      refreshHealth()
    } catch (err) {
      push({ role: 'error', message: err.message })
    }
  }

  return (
    <div className="flex h-dvh bg-slate-50">
      <Sidebar
        sessions={sessions}
        documents={documents}
        currentSession={sessionId}
        onSelectSession={selectSession}
        onNewSession={startNewSession}
        onDeleteDocument={handleDeleteDocument}
        facts={facts}
        factFilter={factFilter}
        onFactFilter={setFactFilter}
        onReviewFact={handleReviewFact}
        onDeleteFact={handleDeleteFact}
        onAddFact={handleAddFact}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-2.5">
          <div className="min-w-0">
            <h1 className="truncate font-semibold text-slate-800">Agentic RAG Assistant</h1>
            <p className="truncate text-xs text-slate-400">{sessionId}</p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <ModelPicker models={models} value={model} onChange={chooseModel} disabled={busy} />
            <HealthBadge health={health} onRefresh={refreshHealth} />
          </div>
        </header>

        <main className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 && (
            <p className="mt-10 text-center text-sm text-slate-400">
              Unggah dokumen atau gambar, lalu ajukan pertanyaan.
            </p>
          )}
          {messages.map((m, i) => (
            <MessageBubble key={i} {...m} />
          ))}
          {busy && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="h-2 w-2 animate-pulse rounded-full bg-slate-400" />
              {status || 'Agent sedang berpikir...'}
            </div>
          )}
          <div ref={endRef} />
        </main>

        <form
          onSubmit={handleSend}
          className="flex items-center gap-1 border-t border-slate-200 bg-white p-3"
        >
          <UploadButton onFile={handleFile} disabled={busy} />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Tulis pertanyaan..."
            disabled={busy}
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400 disabled:bg-slate-50"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  )
}
