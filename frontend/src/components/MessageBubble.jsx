import Markdown from 'react-markdown'

const TOOL_LABEL = {
  rag_search: 'RAG',
  image_ocr: 'OCR',
  sql_query: 'SQL',
  knowledge_search: 'Pengetahuan',
  remember_fact: 'Usulan fakta',
}

export default function MessageBubble({ role, message, toolUsed, sources = [], model }) {
  const isUser = role === 'user'
  const isError = role === 'error'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
          isUser
            ? 'bg-blue-600 text-white'
            : isError
              ? 'bg-red-50 text-red-700 border border-red-200'
              : 'bg-white text-slate-800 border border-slate-200'
        }`}
      >
        {isUser || isError ? (
          <p className="whitespace-pre-wrap">{message}</p>
        ) : (
          <div className="prose prose-sm max-w-none prose-p:my-1.5 prose-pre:bg-slate-100 prose-pre:text-slate-800">
            <Markdown>{message}</Markdown>
          </div>
        )}

        {(toolUsed || model || sources.length > 0) && (
          <div className="mt-2 flex flex-wrap gap-1.5 border-t border-slate-100 pt-2">
            {toolUsed && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                {TOOL_LABEL[toolUsed] ?? toolUsed}
              </span>
            )}
            {model && (
              <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[11px] text-violet-700">
                {model}
              </span>
            )}
            {/* Key on file + page: two pages of one document are two sources. */}
            {sources.map((s) => (
              <span
                key={`${s.filename}#${s.page ?? ''}`}
                className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-700"
              >
                Source: {s.filename}
                {s.page ? `, hal. ${s.page}` : ''}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
