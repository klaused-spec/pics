import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getPersonMedia, updatePerson, deletePerson, getFaceThumbnailUrl } from '../api'
import MediaGrid from '../components/MediaGrid'
import { ArrowLeft, Edit2, Play, Image, Trash2 } from 'lucide-react'

function PersonDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [showAvatarPicker, setShowAvatarPicker] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    loadData()
  }, [id])

  async function loadData() {
    setLoading(true)
    try {
      const res = await getPersonMedia(id, { per_page: 100 })
      setData(res.data)
      setName(res.data.person.name)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  async function handleRename(e) {
    e.preventDefault()
    try {
      await updatePerson(id, { name: name.trim() })
      setEditing(false)
      loadData()
    } catch (err) {
      console.error(err)
    }
  }

  async function handleSetAvatar(faceId) {
    try {
      await updatePerson(id, { avatar_face_id: faceId })
      setShowAvatarPicker(false)
      loadData()
    } catch (err) {
      console.error(err)
    }
  }

  async function handleDelete() {
    setDeleting(true)
    try {
      await deletePerson(id)
      navigate('/persons')
    } catch (err) {
      console.error(err)
      alert('Erro ao deletar pessoa')
    }
    setDeleting(false)
  }

  function startSlideshow() {
    if (data && data.items.length > 0) {
      const ids = data.items.map(i => i.id).join(',')
      window.open(`/slideshow?ids=${ids}`, '_blank')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    )
  }

  if (!data) {
    return <div className="p-8 text-gray-400">Pessoa não encontrada</div>
  }

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/persons')}
            className="text-gray-400 hover:text-white"
          >
            <ArrowLeft size={20} />
          </button>

          {/* Avatar */}
          <div
            className="w-10 h-10 rounded-full bg-gray-700 overflow-hidden cursor-pointer flex items-center justify-center"
            onClick={() => setShowAvatarPicker(true)}
            title="Clique para trocar foto"
          >
            {data.person.avatar_face_id ? (
              <img src={getFaceThumbnailUrl(data.person.avatar_face_id, 80)} alt="" className="w-full h-full object-cover" />
            ) : (
              <Image size={16} className="text-gray-500" />
            )}
          </div>

          {editing ? (
            <form onSubmit={handleRename} className="flex gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-sm"
                autoFocus
              />
              <button type="submit" className="px-3 py-1 bg-blue-600 rounded text-sm">Salvar</button>
              <button type="button" onClick={() => setEditing(false)} className="px-3 py-1 bg-gray-700 rounded text-sm">Cancelar</button>
            </form>
          ) : (
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">{data.person.name}</h2>
              <button onClick={() => setEditing(true)} className="text-gray-400 hover:text-white">
                <Edit2 size={14} />
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">{data.total} fotos</span>
          <button
            onClick={startSlideshow}
            className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm"
          >
            <Play size={14} />
            Slideshow
          </button>
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded-lg text-sm"
            title="Deletar esta pessoa"
          >
            <Trash2 size={14} />
            Deletar
          </button>
        </div>

        {showDeleteConfirm && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-gray-800 rounded-lg p-6 max-w-sm mx-4 border border-red-600">
              <h3 className="text-lg font-semibold mb-2">Deletar "{data.person.name}"?</h3>
              <p className="text-sm text-gray-300 mb-4">
                Os {data.person.face_count} rostos serão desassociados (não serão deletados). 
                Você poderá reagrupá-los depois.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded-lg text-sm font-medium"
                >
                  {deleting ? 'Deletando...' : 'Sim, deletar'}
                </button>
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium"
                >
                  Cancelar
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        {/* Picker de avatar */}
        {showAvatarPicker && data.person.face_ids && data.person.face_ids.length > 0 && (
          <div className="p-4 bg-gray-800 border-b border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm text-gray-300">Escolha a foto de perfil:</p>
              <button onClick={() => setShowAvatarPicker(false)} className="text-xs text-gray-400 hover:text-white">Fechar</button>
            </div>
            <div className="flex gap-2 flex-wrap">
              {data.person.face_ids.map((fid) => (
                <div
                  key={fid}
                  onClick={() => handleSetAvatar(fid)}
                  className={`w-16 h-16 rounded-lg overflow-hidden cursor-pointer border-2 transition-colors ${
                    data.person.avatar_face_id === fid ? 'border-blue-500' : 'border-gray-600 hover:border-gray-400'
                  }`}
                >
                  <img src={getFaceThumbnailUrl(fid, 120)} alt="" className="w-full h-full object-cover" />
                </div>
              ))}
            </div>
          </div>
        )}
        <MediaGrid items={data.items} onSelect={(item) => navigate(`/media/${item.id}`)} />
      </div>
    </div>
  )
}

export default PersonDetail
