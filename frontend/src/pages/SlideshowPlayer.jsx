import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getSlideshowRenderStatus, getSlideshowStreamUrl, deleteSlideshowRender } from '../api'

export default function SlideshowPlayer() {
  const { slug } = useParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const pollRef = useRef(null)
  const token = localStorage.getItem('token')

  useEffect(() => {
    load()
    return () => clearInterval(pollRef.current)
  }, [slug])

  async function load() {
    try {
      const r = await getSlideshowRenderStatus(slug)
      setStatus(r.data)
      if (r.data.status === 'pending' || r.data.status === 'running') {
        pollRef.current = setInterval(async () => {
          try {
            const r2 = await getSlideshowRenderStatus(slug)
            setStatus(r2.data)
            if (r2.data.status === 'done' || r2.data.status === 'failed') {
              clearInterval(pollRef.current)
            }
          } catch (_) {}
        }, 3000)
      }
    } catch (e) {
      setError('Slideshow não encontrado ou link inválido.')
    }
  }

  function copyLink() {
    navigator.clipboard.writeText(window.location.href)
      .then(() => alert('Link copiado!'))
      .catch(() => alert(window.location.href))
  }

  async function handleDelete() {
    if (!window.confirm('Apagar o vídeo? O link deixará de funcionar.')) return
    setDeleting(true)
    try {
      await deleteSlideshowRender(slug)
      navigate('/')
    } catch {
      alert('Erro ao apagar.')
      setDeleting(false)
    }
  }

  if (error) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <p className="text-white text-xl">{error}</p>
    </div>
  )

  if (!status) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <p className="text-white">Carregando…</p>
    </div>
  )

  const videoUrl = getSlideshowStreamUrl(slug)

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center p-4 gap-6">
      <h1 className="text-white text-2xl font-bold text-center">{status.album_name || 'Slideshow'}</h1>

      {(status.status === 'pending' || status.status === 'running') && (
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin text-4xl">⏳</div>
          <p className="text-gray-300">Renderizando… aguarde</p>
          <div className="w-64 bg-gray-800 rounded-full h-2">
            <div className="bg-indigo-500 h-2 rounded-full transition-all" style={{ width: `${status.progress || 0}%` }} />
          </div>
        </div>
      )}

      {status.status === 'failed' && (
        <div className="text-red-400 text-center">
          <p className="text-xl">❌ Falha na renderização</p>
          <p className="text-sm mt-2 font-mono">{status.error_message}</p>
        </div>
      )}

      {status.status === 'done' && (
        <div className="w-full max-w-2xl flex flex-col gap-4">
          <video
            src={videoUrl}
            controls
            autoPlay
            className="w-full rounded-xl shadow-2xl bg-black"
            style={{ maxHeight: '75vh' }}
          />
          <div className="flex gap-3 justify-center flex-wrap">
            <button
              onClick={copyLink}
              className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium"
            >
              🔗 Copiar link
            </button>
            <a
              href={videoUrl}
              download={status.output_filename}
              className="px-5 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm font-medium"
            >
              ⬇ Baixar MP4
            </a>
            {token && (
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="px-5 py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg text-sm font-medium disabled:opacity-50"
              >
                🗑 Apagar vídeo
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
