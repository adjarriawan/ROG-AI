import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'
import UploadButton from './UploadButton'
import { fetchHistory, sendChat, uploadFile } from '../services/api'

function getSessionId() {
  let id = localStorage.getItem('session_id')
  if (!id) {
    id = `session-${crypto.randomUUID().slice(0, 8)}`
    localStorage.setItem('session_id', id)
  }
  return id
}

export default function ChatBox() {
  const [sessionId] = useState(getSessionId)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const endRef = useRef(null)

  useEffect(() => {
    fetchHistory(sessionId).then((rows) =>
      setMessages(rows.map((r) => ({ role: r.role, message: r.message }))),
    )
  }, [sessionId])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  const push = (m) => setMessages((prev) => [...prev, m])

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return

    setInput('')
    push({ role: 'user', message: text })
    setBusy(true)
    try {
      const res = await sendChat(sessionId, text)
      push({
        role: 'assistant',
        message: res.answer,
        toolUsed: res.tool_used,
        sources: res.sources,
      })
    } catch (err) {
      push({ role: 'error', message: err.message })
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
    } catch (err) {
      push({ role: 'error', message: err.message })
    } finally {
      setBusy(false)
      setStatus('')
    }
  }

  return (
    <div className="flex h-dvh flex-col bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-4 py-3 text-center">
        <h1 className="font-semibold text-slate-800">Agentic RAG Assistant</h1>
        <p className="text-xs text-slate-400">{sessionId}</p>
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
  )
}
