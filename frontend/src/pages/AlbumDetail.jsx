import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getAlbumMedia, updateAlbum, deleteAlbum, removeMediaFromAlbum, getThumbnailUrl } from '../api'
import MediaGrid from '../components/MediaGrid'
import { ArrowLeft, Trash2, Edit2, X, Check, Play } from 'lucide-react'

function AlbumDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [album, setAlbum] = useState(null)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState(new Set())

  useEffect(() => {
    loadAlbumMedia()
  }, [id, page])

  async function loadAlbumMedia() {
    setLoading(true)
    try {
      const res = await getAlbumMedia(id, { page, per_page: 60 })
      setAlbum(res.data.album)
      setItems(res.data.items)
      setTotal(res.data.total)
    } catch (err) {
      console.error('Erro ao carregar álbum:', err)
    }
    setLoading(false)
  }

  function handleSelect(item) {
    if (selectMode) {
      const next = new Set(selected)
      if (next.has(item.id)) {
        next.delete(item.id)
      } else {
        next.add(item.id)
      }
      setSelected(next)
    } else {
      navigate(`/media/${item.id}`)
    }
  }

  async function handleRename() {
    if (!editName.trim()) return
    await updateAlbum(id, { name: editName.trim() })
    setEditing(false)
    loadAlbumMedia()
  }

  async function handleDelete() {
    if (!confirm('Remover este álbum? As fotos não serão apagadas.')) return
    await deleteAlbum(id)
    navigate('/gallery?tab=albums')
  }

  async function handleRemoveSelected() {
    if (selected.size === 0) return
    await removeMediaFromAlbum(id, [...selected])
    setSelected(new Set())
    setSelectMode(false)
    loadAlbumMedia()
  }

  if (loading && !album) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/gallery?tab=albums')} className="text-gray-400 hover:text-white">
            <ArrowLeft size={20} />
          </button>
          {editing ? (
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleRename()}
                className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white"
              />
              <button onClick={handleRename} className="text-green-400 hover:text-green-300">
                <Check size={16} />
              </button>
              <button onClick={() => setEditing(false)} className="text-gray-400 hover:text-white">
                <X size={16} />
              </button>
            </div>
          ) : (
            <div>
              <h2 className="text-lg font-semibold">{album?.name}</h2>
              <p className="text-sm text-gray-400">{total} itens</p>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {selectMode ? (
            <>
              <span className="text-sm text-gray-400">{selected.size} selecionados</span>
              <button
                onClick={handleRemoveSelected}
                disabled={selected.size === 0}
                className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm disabled:opacity-50"
              >
                Remover do álbum
              </button>
              <button
                onClick={() => { setSelectMode(false); setSelected(new Set()) }}
                className="px-3 py-1 bg-gray-700 rounded text-sm"
              >
                Cancelar
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => window.open(`/slideshow?album_id=${id}`, '_blank')}
                className="flex items-center gap-1 px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm"
              >
                <Play size={14} /> Slideshow
              </button>
              <button
                onClick={() => setSelectMode(true)}
                className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm"
              >
                Selecionar
              </button>
              <button
                onClick={() => { setEditing(true); setEditName(album?.name || '') }}
                className="p-2 text-gray-400 hover:text-white"
              >
                <Edit2 size={16} />
              </button>
              <button onClick={handleDelete} className="p-2 text-red-400 hover:text-red-300">
                <Trash2 size={16} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          <MediaGrid
            items={items}
            onSelect={handleSelect}
            selected={selectMode ? selected : null}
          />
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
  )
}

export default AlbumDetail
