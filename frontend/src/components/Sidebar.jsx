import { useState } from 'react'
import KnowledgePanel from './KnowledgePanel'

function Tab({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 rounded-lg px-2 py-1.5 text-xs font-medium ${
        active ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'
      }`}
    >
      {children}
    </button>
  )
}

export default function Sidebar({
  sessions,
  documents,
  currentSession,
  onSelectSession,
  onNewSession,
  onDeleteDocument,
  facts,
  factFilter,
  onFactFilter,
  onReviewFact,
  onDeleteFact,
  onAddFact,
}) {
  const [tab, setTab] = useState('sessions')

  const fmtDate = (d) =>
    new Date(d).toLocaleString('id-ID', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-slate-100/60">
      <div className="p-3">
        <button
          type="button"
          onClick={onNewSession}
          className="mb-3 w-full rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700"
        >
          + Chat baru
        </button>
        <div className="flex gap-1 rounded-lg bg-slate-200/70 p-1">
          <Tab active={tab === 'sessions'} onClick={() => setTab('sessions')}>
            Riwayat ({sessions.length})
          </Tab>
          <Tab active={tab === 'docs'} onClick={() => setTab('docs')}>
            Dokumen ({documents.length})
          </Tab>
          <Tab active={tab === 'knowledge'} onClick={() => setTab('knowledge')}>
            Fakta ({facts.length})
          </Tab>
        </div>
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto px-3 pb-3">
        {tab === 'sessions' &&
          (sessions.length === 0 ? (
            <p className="px-1 py-4 text-xs text-slate-400">Belum ada riwayat chat.</p>
          ) : (
            sessions.map((s) => (
              <button
                key={s.session_id}
                type="button"
                onClick={() => onSelectSession(s.session_id)}
                className={`w-full rounded-lg px-2 py-2 text-left text-xs ${
                  s.session_id === currentSession
                    ? 'bg-white shadow-sm'
                    : 'hover:bg-white/70'
                }`}
              >
                <p className="truncate font-medium text-slate-700">{s.last_message}</p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  {s.messages} pesan · {fmtDate(s.updated_at)}
                </p>
              </button>
            ))
          ))}

        {tab === 'docs' &&
          (documents.length === 0 ? (
            <p className="px-1 py-4 text-xs text-slate-400">
              Belum ada dokumen. Unggah PDF atau TXT untuk mengisi knowledge base.
            </p>
          ) : (
            documents.map((d) => (
              <div
                key={d.filename}
                className="group flex items-center gap-1 rounded-lg px-2 py-2 hover:bg-white/70"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-slate-700">{d.filename}</p>
                  <p className="text-[11px] text-slate-400">
                    {d.chunks} chunk · {fmtDate(d.uploaded_at)}
                  </p>
                </div>
                <button
                  type="button"
                  title={`Hapus ${d.filename} dari knowledge base`}
                  onClick={() => onDeleteDocument(d.filename)}
                  className="rounded px-1.5 py-0.5 text-xs text-slate-300 opacity-0 hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                >
                  ✕
                </button>
              </div>
            ))
          ))}

        {tab === 'knowledge' && (
          <KnowledgePanel
            facts={facts}
            filter={factFilter}
            onFilter={onFactFilter}
            onReview={onReviewFact}
            onDelete={onDeleteFact}
            onAdd={onAddFact}
          />
        )}
      </div>
    </aside>
  )
}
