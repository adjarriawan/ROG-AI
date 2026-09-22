import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  timeout: 180000, // local LLM inference is slow on CPU
})

function errMessage(err) {
  return err.response?.data?.detail ?? err.message ?? 'Terjadi kesalahan.'
}

export async function sendChat(sessionId, message) {
  try {
    const { data } = await client.post('/chat', { session_id: sessionId, message })
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
