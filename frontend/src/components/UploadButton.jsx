import { useRef } from 'react'

const ACCEPT = '.pdf,.txt,.md,.png,.jpg,.jpeg,.webp,.bmp'

export default function UploadButton({ onFile, disabled }) {
  const inputRef = useRef(null)

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFile(file)
          e.target.value = '' // allow re-uploading the same file
        }}
      />
      <button
        type="button"
        title="Unggah dokumen atau gambar"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className="rounded-lg px-3 py-2 text-lg text-slate-500 hover:bg-slate-100 disabled:opacity-40"
      >
        📎
      </button>
    </>
  )
}
