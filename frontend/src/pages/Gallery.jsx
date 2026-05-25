import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getMedia, getTimeline } from '../api'
import MediaGrid from '../components/MediaGrid'
import { Play, Calendar } from 'lucide-react'

function Gallery() {
  const [items, setItems] = useState([])
  const [timeline, setTimeline] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const year = searchParams.get('year')
  const month = searchParams.get('month')

  useEffect(() => {
    loadMedia()
    loadTimeline()
  }, [page, year, month])

  async function loadMedia() {
    setLoading(true)
    try {
      const params = { page, per_page: 60 }
      if (year) params.year = parseInt(year)
      if (month) params.month = parseInt(month)

      const res = await getMedia(params)
      setItems(res.data.items)
      setTotal(res.data.total)
    } catch (err) {
      console.error('Erro ao carregar mídia:', err)
    }
    setLoading(false)
  }

  async function loadTimeline() {
    try {
      const res = await getTimeline()
      setTimeline(res.data)
    } catch (err) {
      console.error('Erro ao carregar timeline:', err)
    }
  }

  function handleSelect(item) {
    navigate(`/media/${item.id}`)
  }

  function startSlideshow() {
    const params = new URLSearchParams()
    if (year) params.set('year', year)
    if (month) params.set('month', month)
    window.open(`/slideshow?${params.toString()}`, '_blank')
  }

  function filterByMonth(y, m) {
    setSearchParams({ year: y, month: m })
    setPage(1)
  }

  function clearFilter() {
    setSearchParams({})
    setPage(1)
  }

  const monthNames = [
    '', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
    'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'
  ]

  return (
    <div className="flex h-full">
      {/* Sidebar Timeline */}
      <div className="w-48 bg-gray-800/50 border-r border-gray-700 overflow-auto">
        <div className="p-3 border-b border-gray-700">
          <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
            <Calendar size={14} />
            Timeline
          </h3>
        </div>
        <div className="p-2">
          <button
            onClick={clearFilter}
            className={`w-full text-left px-2 py-1 text-sm rounded ${
              !year ? 'bg-blue-600/30 text-blue-400' : 'text-gray-400 hover:text-white'
            }`}
          >
            Todas ({total})
          </button>
          {timeline.map((t) => (
            <button
              key={`${t.year}-${t.month}`}
              onClick={() => filterByMonth(t.year, t.month)}
              className={`w-full text-left px-2 py-1 text-sm rounded ${
                year == t.year && month == t.month
                  ? 'bg-blue-600/30 text-blue-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {monthNames[t.month]} {t.year} ({t.count})
            </button>
          ))}
        </div>
      </div>

      {/* Conteúdo */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div>
            <h2 className="text-lg font-semibold">
              {year ? `${monthNames[parseInt(month)] || ''} ${year}` : 'Todas as fotos'}
            </h2>
            <p className="text-sm text-gray-400">{total} itens</p>
          </div>
          <button
            onClick={startSlideshow}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm transition-colors"
          >
            <Play size={16} />
            Slideshow
          </button>
        </div>

        {/* Grid */}
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
          </div>
        ) : (
          <div className="flex-1 overflow-auto">
            <MediaGrid items={items} onSelect={handleSelect} />

            {/* Paginação */}
            {total > 60 && (
              <div className="flex justify-center gap-2 p-4">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(p => p - 1)}
                  className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
                >
                  Anterior
                </button>
                <span className="px-3 py-1 text-sm text-gray-400">
                  Página {page} de {Math.ceil(total / 60)}
                </span>
                <button
                  disabled={page >= Math.ceil(total / 60)}
                  onClick={() => setPage(p => p + 1)}
                  className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
                >
                  Próxima
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default Gallery
