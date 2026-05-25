import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getMedia, getTimeline, getAlbums, createAlbum, getThumbnailUrl } from '../api'
import MediaGrid from '../components/MediaGrid'
import { Play, Calendar, FolderPlus, Image } from 'lucide-react'

function Gallery() {
  const [items, setItems] = useState([])
  const [timeline, setTimeline] = useState([])
  const [albums, setAlbums] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [searchParams, setSearchParams] = useSearchParams()
  const [showNewAlbum, setShowNewAlbum] = useState(false)
  const [newAlbumName, setNewAlbumName] = useState('')
  const navigate = useNavigate()

  const tab = searchParams.get('tab') || 'data'
  const year = searchParams.get('year')
  const month = searchParams.get('month')

  useEffect(() => {
    if (tab === 'data') {
      loadMedia()
      loadTimeline()
    } else {
      loadAlbums()
    }
  }, [page, year, month, tab])

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

  async function loadAlbums() {
    setLoading(true)
    try {
      const res = await getAlbums()
      setAlbums(res.data)
    } catch (err) {
      console.error('Erro ao carregar álbuns:', err)
    }
    setLoading(false)
  }

  async function handleCreateAlbum(e) {
    e.preventDefault()
    if (!newAlbumName.trim()) return
    try {
      await createAlbum(newAlbumName.trim())
      setNewAlbumName('')
      setShowNewAlbum(false)
      loadAlbums()
    } catch (err) {
      console.error('Erro ao criar álbum:', err)
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
    setSearchParams({ tab: 'data', year: y, month: m })
    setPage(1)
  }

  function clearFilter() {
    setSearchParams({ tab: 'data' })
    setPage(1)
  }

  function switchTab(t) {
    setSearchParams({ tab: t })
    setPage(1)
  }

  const monthNames = [
    '', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
    'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'
  ]

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-48 bg-gray-800/50 border-r border-gray-700 overflow-auto flex flex-col">
        {/* Abas */}
        <div className="flex border-b border-gray-700">
          <button
            onClick={() => switchTab('data')}
            className={`flex-1 px-3 py-2 text-xs font-semibold ${
              tab === 'data' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400 hover:text-white'
            }`}
          >
            <Calendar size={12} className="inline mr-1" />
            Data
          </button>
          <button
            onClick={() => switchTab('albums')}
            className={`flex-1 px-3 py-2 text-xs font-semibold ${
              tab === 'albums' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400 hover:text-white'
            }`}
          >
            <Image size={12} className="inline mr-1" />
            Álbuns
          </button>
        </div>

        {/* Conteúdo da sidebar */}
        {tab === 'data' ? (
          <div className="p-2 flex-1 overflow-auto">
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
        ) : (
          <div className="p-2 flex-1 overflow-auto">
            <button
              onClick={() => setShowNewAlbum(true)}
              className="w-full flex items-center gap-1 px-2 py-1 text-sm text-green-400 hover:text-green-300 rounded hover:bg-gray-700/50"
            >
              <FolderPlus size={14} />
              Novo álbum
            </button>
            {showNewAlbum && (
              <form onSubmit={handleCreateAlbum} className="mt-1">
                <input
                  autoFocus
                  value={newAlbumName}
                  onChange={(e) => setNewAlbumName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Escape' && setShowNewAlbum(false)}
                  placeholder="Nome do álbum"
                  className="w-full px-2 py-1 text-sm bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-500"
                />
              </form>
            )}
            {albums.map((a) => (
              <button
                key={a.id}
                onClick={() => navigate(`/albums/${a.id}`)}
                className="w-full text-left px-2 py-1 text-sm rounded text-gray-400 hover:text-white hover:bg-gray-700/50"
              >
                {a.name} ({a.media_count})
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Conteúdo principal */}
      <div className="flex-1 flex flex-col">
        {tab === 'data' ? (
          <>
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
          </>
        ) : (
          <>
            {/* Header Álbuns */}
            <div className="flex items-center justify-between p-4 border-b border-gray-700">
              <div>
                <h2 className="text-lg font-semibold">Álbuns</h2>
                <p className="text-sm text-gray-400">{albums.length} álbuns</p>
              </div>
              <button
                onClick={() => setShowNewAlbum(true)}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg text-sm transition-colors"
              >
                <FolderPlus size={16} />
                Novo álbum
              </button>
            </div>

            {/* Grid de álbuns */}
            {loading ? (
              <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
              </div>
            ) : (
              <div className="flex-1 overflow-auto p-4">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                  {albums.map((album) => (
                    <div
                      key={album.id}
                      onClick={() => navigate(`/albums/${album.id}`)}
                      className="cursor-pointer group"
                    >
                      <div className="aspect-square bg-gray-800 rounded-lg overflow-hidden border border-gray-700 group-hover:border-blue-500 transition-colors">
                        {album.cover_media_id ? (
                          <img
                            src={getThumbnailUrl(album.cover_media_id, 300)}
                            alt={album.name}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <Image size={48} className="text-gray-600" />
                          </div>
                        )}
                      </div>
                      <p className="mt-2 text-sm font-medium truncate">{album.name}</p>
                      <p className="text-xs text-gray-400">{album.media_count} itens</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default Gallery
