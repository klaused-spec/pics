import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDuplicates, deleteMedia, deleteAllDuplicates, getThumbnailUrl } from '../api'
import { Trash2, ArrowLeft, CheckCircle } from 'lucide-react'

export default function Duplicates() {
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    loadDuplicates()
  }, [])

  async function loadDuplicates() {
    setLoading(true)
    try {
      const res = await getDuplicates()
      setGroups(res.data)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  async function handleDelete(mediaId) {
    if (!confirm('Mover este arquivo para .trash?')) return
    try {
      await deleteMedia(mediaId)
      loadDuplicates()
    } catch (err) {
      alert('Erro: ' + (err.response?.data?.detail || err.message))
    }
  }

  async function handleDeleteAll() {
    const total = groups.reduce((sum, g) => sum + g.duplicates.length, 0)
    if (!confirm(`Mover TODAS ${total} duplicatas para .trash? (originais serão mantidos)`)) return
    try {
      const res = await deleteAllDuplicates()
      alert(`${res.data.deleted} duplicatas removidas.${res.data.errors.length ? '\nErros: ' + res.data.errors.join(', ') : ''}`)
      loadDuplicates()
    } catch (err) {
      alert('Erro: ' + (err.response?.data?.detail || err.message))
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/')} className="text-gray-400 hover:text-white">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-2xl font-bold">Duplicatas</h1>
        <span className="text-sm text-gray-400">({groups.length} grupos)</span>
        {groups.length > 0 && (
          <button
            onClick={handleDeleteAll}
            className="ml-auto flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium"
          >
            <Trash2 size={16} />
            Apagar todas duplicatas
          </button>
        )}
      </div>

      {groups.length === 0 ? (
        <div className="text-center text-gray-400 py-16">
          <CheckCircle size={48} className="mx-auto mb-4 text-green-500" />
          <p className="text-lg">Nenhuma duplicata encontrada!</p>
        </div>
      ) : (
        <div className="space-y-6">
          {groups.map((group, gi) => (
            <div key={gi} className="bg-gray-800 rounded-xl p-4">
              <p className="text-xs text-gray-400 mb-3">Grupo {gi + 1} — {group.duplicates.length + 1} arquivos</p>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {/* Original */}
                <DuplicateCard
                  media={group.original}
                  isOriginal
                  onView={() => navigate(`/media/${group.original.id}`)}
                  onDelete={() => handleDelete(group.original.id)}
                />
                {/* Duplicatas */}
                {group.duplicates.map((dupe) => (
                  <DuplicateCard
                    key={dupe.id}
                    media={dupe}
                    onView={() => navigate(`/media/${dupe.id}`)}
                    onDelete={() => handleDelete(dupe.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DuplicateCard({ media, isOriginal, onView, onDelete }) {
  const path = media.organized_path || ''
  const folder = path.split('/').slice(-2, -1)[0] || ''

  return (
    <div className={`relative rounded-lg overflow-hidden bg-gray-900 border ${isOriginal ? 'border-green-600' : 'border-gray-700'}`}>
      <div className="aspect-square cursor-pointer" onClick={onView}>
        <img
          src={getThumbnailUrl(media.id, 300)}
          alt={media.filename}
          className="w-full h-full object-cover"
        />
      </div>
      <div className="p-2 space-y-1">
        {isOriginal && (
          <span className="inline-block text-[10px] px-1.5 py-0.5 bg-green-600 rounded text-white font-semibold">ORIGINAL</span>
        )}
        {!isOriginal && (
          <span className="inline-block text-[10px] px-1.5 py-0.5 bg-red-600/50 rounded text-red-300 font-semibold">DUPLICATA</span>
        )}
        <p className="text-xs text-gray-300 truncate" title={media.filename}>{media.filename}</p>
        <p className="text-[10px] text-gray-500 break-all" title={path}>{path}</p>
        {media.width && media.height && (
          <p className="text-[10px] text-gray-500">{media.width}x{media.height}</p>
        )}
        {media.date_taken && (
          <p className="text-[10px] text-gray-500">{new Date(media.date_taken).toLocaleDateString('pt-BR')}</p>
        )}
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete() }}
        className="absolute top-2 right-2 p-1.5 bg-red-600 hover:bg-red-700 rounded-full text-white opacity-0 group-hover:opacity-100 hover:opacity-100 transition-opacity"
        style={{ opacity: 1 }}
        title="Mover para .trash"
      >
        <Trash2 size={14} />
      </button>
    </div>
  )
}
