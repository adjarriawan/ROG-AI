import { useState } from 'react'

const STATUS_STYLE = {
  pending: 'bg-amber-50 text-amber-700',
  approved: 'bg-emerald-50 text-emerald-700',
  rejected: 'bg-slate-100 text-slate-500',
}

const STATUS_LABEL = { pending: 'Menunggu', approved: 'Aktif', rejected: 'Ditolak' }

/**
 * Review queue for the global knowledge base.
 *
 * Facts are shared by every session, so approving one changes what the
 * assistant tells everybody. The queue exists so the agent can propose without
 * being able to publish.
 */
export default function KnowledgePanel({ facts, filter, onFilter, onReview, onDelete, onAdd }) {
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    const content = draft.trim()
    if (content.length < 10 || busy) return
    setBusy(true)
    try {
      await onAdd(content)
      setDraft('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <form onSubmit={submit} className="space-y-1.5">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={2}
          maxLength={2000}
          placeholder="Tambah fakta yang berlaku di semua sesi…"
          className="w-full resize-none rounded-lg border border-slate-200 px-2 py-1.5 text-xs focus:border-blue-400 focus:outline-none"
        />
        <button
          type="submit"
          disabled={draft.trim().length < 10 || busy}
          className="w-full rounded-lg bg-slate-800 px-2 py-1.5 text-xs font-medium text-white disabled:opacity-40"
        >
          {busy ? 'Menyimpan…' : 'Tambah fakta terverifikasi'}
        </button>
      </form>

      <div className="flex gap-1 text-[11px]">
        {['pending', 'approved', 'rejected'].map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onFilter(filter === s ? null : s)}
            className={`rounded px-1.5 py-0.5 ${
              filter === s ? 'bg-slate-800 text-white' : 'bg-slate-200/70 text-slate-600'
            }`}
          >
            {STATUS_LABEL[s]}
          </button>
        ))}
      </div>

      {facts.length === 0 ? (
        <p className="px-1 py-4 text-xs text-slate-400">
          Belum ada fakta. Asisten akan mengusulkan fakta saat kamu menyatakan sesuatu
          yang layak diingat permanen.
        </p>
      ) : (
        facts.map((f) => (
          <div key={f.id} className="rounded-lg bg-white/70 px-2 py-2">
            <p className="text-xs text-slate-700">{f.content}</p>
            <div className="mt-1 flex items-center gap-1">
              <span className={`rounded px-1.5 py-0.5 text-[11px] ${STATUS_STYLE[f.status]}`}>
                {STATUS_LABEL[f.status]}
              </span>
              <span className="text-[11px] text-slate-400">
                {f.origin === 'agent' ? 'usulan asisten' : 'ditambah manual'}
              </span>
              <span className="ml-auto flex gap-1">
                {f.status !== 'approved' && (
                  <button
                    type="button"
                    onClick={() => onReview(f.id, 'approve')}
                    className="rounded px-1.5 py-0.5 text-[11px] text-emerald-700 hover:bg-emerald-50"
                  >
                    Setujui
                  </button>
                )}
                {f.status !== 'rejected' && (
                  <button
                    type="button"
                    onClick={() => onReview(f.id, 'reject')}
                    className="rounded px-1.5 py-0.5 text-[11px] text-slate-500 hover:bg-slate-100"
                  >
                    Tolak
                  </button>
                )}
                <button
                  type="button"
                  title="Hapus permanen"
                  onClick={() => onDelete(f.id)}
                  className="rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-red-50 hover:text-red-600"
                >
                  ✕
                </button>
              </span>
            </div>
          </div>
        ))
      )}
    </div>
  )
}
