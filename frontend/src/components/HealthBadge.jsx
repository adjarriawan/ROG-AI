const DOT = {
  ok: 'bg-emerald-500',
  degraded: 'bg-amber-500',
  error: 'bg-red-500',
}

export default function HealthBadge({ health, onRefresh }) {
  const status = health?.status ?? 'error'
  const detail = health
    ? `DB ${health.database} · Ollama ${health.ollama} · ${health.documents} dokumen`
    : 'Backend tidak terjangkau'

  return (
    <button
      type="button"
      onClick={onRefresh}
      title={detail}
      className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
    >
      <span className={`h-2 w-2 rounded-full ${DOT[status] ?? DOT.error}`} />
      {status === 'ok' ? 'Sistem normal' : status === 'degraded' ? 'Sebagian bermasalah' : 'Tidak terhubung'}
    </button>
  )
}
