export default function ModelPicker({ models, value, onChange, disabled }) {
  const fmtSize = (b) => `${(b / 1e9).toFixed(1)} GB`

  return (
    <label className="flex items-center gap-2 text-xs text-slate-500">
      Model
      <select
        value={value ?? ''}
        disabled={disabled || models.length === 0}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 outline-none focus:border-blue-400 disabled:opacity-50"
      >
        {models.map((m) => (
          // A model without tool support cannot drive the agent at all, so it
          // is shown but not selectable rather than silently failing later.
          <option key={m.name} value={m.name} disabled={!m.supports_tools}>
            {m.name} · {fmtSize(m.size)}
            {m.supports_tools ? '' : ' — tanpa dukungan tools'}
          </option>
        ))}
      </select>
    </label>
  )
}
