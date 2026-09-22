import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  timeout: 180000, // local LLM inference is slow on CPU
})

function errMessage(err) {
  return err.response?.data?.detail ?? err.message ?? 'Terjadi kesalahan.'
}

export async function sendChat(sessionId, message, model) {
  try {
    const { data } = await client.post('/chat', { session_id: sessionId, message, model })
    return data
  } catch (err) {
    throw new Error(errMessage(err))
  }
}

export async function uploadFile(sessionId, file) {
  const form = new FormData()
  form.append('file', file)
  try {
    const { data } = await client.post('/upload', form, {
      params: { session_id: sessionId },
    })
    return data
  } catch (err) {
    throw new Error(errMessage(err))
  }
}

export async function fetchHistory(sessionId) {
  try {
    const { data } = await client.get('/chat/history', { params: { session_id: sessionId } })
    return data
  } catch {
    return [] // history is best-effort; never block the UI on it
  }
}

export async function fetchHealth() {
  const { data } = await client.get('/health', { timeout: 10000 })
  return data
}

export async function fetchModels() {
  const { data } = await client.get('/models', { timeout: 20000 })
  return data
}

export async function fetchDocuments() {
  const { data } = await client.get('/documents', { timeout: 10000 })
  return data
}

export async function deleteDocument(filename) {
  try {
    const { data } = await client.delete(`/documents/${encodeURIComponent(filename)}`)
    return data
  } catch (err) {
    throw new Error(errMessage(err))
  }
}

export async function fetchSessions() {
  const { data } = await client.get('/sessions', { timeout: 10000 })
  return data
}

export async function clearHistory(sessionId) {
  await client.delete('/chat/history', { params: { session_id: sessionId } })
}
