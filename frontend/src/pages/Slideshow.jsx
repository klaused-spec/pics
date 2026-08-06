import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getMedia, searchMedia, getAlbumMedia, getFileUrl, getStreamUrl } from '../api'
import { ChevronLeft, ChevronRight, X, Pause, Play } from 'lucide-react'

function Slideshow() {
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [loading, setLoading] = useState(true)
  const intervalRef = useRef(null)
  const videoRef = useRef(null)

  // Intervalo entre slides (ms)
  const SLIDE_INTERVAL = 5000

  useEffect(() => {
    loadItems()
  }, [])

  useEffect(() => {
    if (playing && items.length > 0) {
      const current = items[currentIndex]
      // Para vídeos, não avança automaticamente
      if (current?.media_type === 'video') {
        return
      }
      intervalRef.current = setInterval(() => {
        setCurrentIndex((i) => (i + 1) % items.length)
      }, SLIDE_INTERVAL)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [playing, currentIndex, items])

  async function loadItems() {
    setLoading(true)
    try {
      const ids = searchParams.get('ids')
      const year = searchParams.get('year')
      const month = searchParams.get('month')
      const q = searchParams.get('q')
      const albumId = searchParams.get('album_id')

      if (albumId) {
        // Slideshow de um álbum
        const res = await getAlbumMedia(albumId, { per_page: 200 })
        setItems(res.data.items)
      } else if (ids) {
        // IDs específicos (de busca ou pessoa)
        const idList = ids.split(',').map(Number)
        // Carrega em batches (a API não suporta IDs diretamente, então carregamos por listagem)
        const params = { per_page: 200 }
        if (year) params.year = parseInt(year)
        if (month) params.month = parseInt(month)
        const res = await getMedia(params)
        const filtered = res.data.items.filter(i => idList.includes(i.id))
        setItems(filtered.length > 0 ? filtered : res.data.items)
      } else if (q) {
        const res = await searchMedia(q, 100)
        setItems(res.data.items)
      } else {
        const params = { per_page: 100 }
        if (year) params.year = parseInt(year)
        if (month) params.month = parseInt(month)
        const res = await getMedia(params)
        setItems(res.data.items)
      }
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  const goNext = useCallback(() => {
    setCurrentIndex((i) => (i + 1) % items.length)
  }, [items.length])

  const goPrev = useCallback(() => {
    setCurrentIndex((i) => (i - 1 + items.length) % items.length)
  }, [items.length])

  const togglePlay = useCallback(() => {
    setPlaying((p) => !p)
  }, [])

  // Atalhos de teclado
  useEffect(() => {
    function handleKey(e) {
      switch (e.key) {
        case 'ArrowRight':
        case ' ':
          goNext()
          break
        case 'ArrowLeft':
          goPrev()
          break
        case 'Escape':
          window.close()
          break
        case 'p':
          togglePlay()
          break
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [goNext, goPrev, togglePlay])

  // Quando vídeo termina, avança para próximo
  function handleVideoEnd() {
    if (playing) goNext()
  }

  if (loading) {
    return (
      <div className="h-screen w-screen bg-black flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-400"></div>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="h-screen w-screen bg-black flex items-center justify-center text-gray-400">
        Nenhum conteúdo para exibir
      </div>
    )
  }

  const current = items[currentIndex]

  return (
    <div className="h-screen w-screen bg-black relative select-none">
      {/* Conteúdo */}
      <div className="absolute inset-0 flex items-center justify-center">
        {current.media_type === 'image' ? (
          <img
            key={current.id}
            src={getFileUrl(current.id)}
            alt={current.ai_description || ''}
            className="max-w-full max-h-full object-contain animate-fade-in"
          />
        ) : (
          <video
            ref={videoRef}
            key={current.id}
            src={getStreamUrl(current.id)}
            className="max-w-full max-h-full"
            autoPlay
            onEnded={handleVideoEnd}
          />
        )}
      </div>

      {/* Controles (aparecem no hover) */}
      <div className="absolute inset-0 opacity-0 hover:opacity-100 transition-opacity duration-300">
        {/* Barra superior */}
        <div className="absolute top-0 left-0 right-0 bg-gradient-to-b from-black/70 to-transparent p-4 flex items-center justify-between">
          <div>
            <p className="text-sm text-white">{current.filename}</p>
            {current.ai_description && (
              <p className="text-xs text-gray-300 mt-1 max-w-lg">{current.ai_description}</p>
            )}
          </div>
          <button onClick={() => window.close()} className="text-white/70 hover:text-white">
            <X size={24} />
          </button>
        </div>

        {/* Botões laterais */}
        <button
          onClick={goPrev}
          className="absolute left-4 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/80 rounded-full p-3 text-white"
        >
          <ChevronLeft size={32} />
        </button>
        <button
          onClick={goNext}
          className="absolute right-4 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/80 rounded-full p-3 text-white"
        >
          <ChevronRight size={32} />
        </button>

        {/* Barra inferior */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={togglePlay}
                className="bg-white/20 hover:bg-white/30 rounded-full p-2 text-white"
              >
                {playing ? <Pause size={20} /> : <Play size={20} />}
              </button>
              <span className="text-sm text-white/70">
                {currentIndex + 1} / {items.length}
              </span>
            </div>
            {current.date_taken && (
              <span className="text-sm text-white/70">
                {new Date(current.date_taken).toLocaleDateString('pt-BR', {
                  day: 'numeric', month: 'long', year: 'numeric'
                })}
              </span>
            )}
          </div>

          {/* Barra de progresso */}
          <div className="mt-2 h-1 bg-white/20 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-400 transition-all duration-300"
              style={{ width: `${((currentIndex + 1) / items.length) * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default Slideshow
