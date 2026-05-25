import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getPendingFaces, getFaceThumbnailUrl, assignFace, confirmFace, ignoreFace, unassignFace, getPersons, createPerson } from '../api'
import { ArrowLeft, Check, X, EyeOff, UserPlus } from 'lucide-react'

function FaceReview() {
  const [faces, setFaces] = useState([])
  const [persons, setPersons] = useState([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [editingFace, setEditingFace] = useState(null)
  const [newPersonName, setNewPersonName] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [facesRes, personsRes] = await Promise.all([
        getPendingFaces({ per_page: 100 }),
        getPersons({ per_page: 200 }),
      ])
      setFaces(facesRes.data.items)
      setTotal(facesRes.data.total)
      setPersons(personsRes.data.items || personsRes.data)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  async function handleConfirm(faceId) {
    try {
      await confirmFace(faceId)
      setFaces(prev => prev.filter(f => f.id !== faceId))
      setTotal(prev => prev - 1)
    } catch (err) {
      console.error(err)
    }
  }

  async function handleIgnore(faceId) {
    try {
      await ignoreFace(faceId)
      setFaces(prev => prev.filter(f => f.id !== faceId))
      setTotal(prev => prev - 1)
    } catch (err) {
      console.error(err)
    }
  }

  async function handleReject(faceId) {
    try {
      await unassignFace(faceId)
      // Recarrega para atualizar sugestão
      const res = await getPendingFaces({ per_page: 100 })
      setFaces(res.data.items)
      setTotal(res.data.total)
    } catch (err) {
      console.error(err)
    }
  }

  async function handleAssign(faceId, personId) {
    try {
      await assignFace(faceId, personId)
      setFaces(prev => prev.filter(f => f.id !== faceId))
      setTotal(prev => prev - 1)
      setEditingFace(null)
      setNewPersonName('')
    } catch (err) {
      console.error(err)
    }
  }

  async function handleCreateAndAssign(faceId) {
    const name = newPersonName.trim()
    if (!name) return
    try {
      const res = await createPerson(name)
      const personId = res.data.id
      await assignFace(faceId, personId)
      setFaces(prev => prev.filter(f => f.id !== faceId))
      setTotal(prev => prev - 1)
      setEditingFace(null)
      setNewPersonName('')
      // Atualiza lista de pessoas
      const pRes = await getPersons({ per_page: 200 })
      setPersons(pRes.data.items || pRes.data)
    } catch (err) {
      console.error(err)
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
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/persons')}
            className="text-gray-400 hover:text-white"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h2 className="text-xl font-semibold">Revisar Rostos</h2>
            <p className="text-sm text-gray-400">{total} rostos pendentes</p>
          </div>
        </div>
      </div>

      {faces.length === 0 ? (
        <div className="text-center text-gray-500 py-16">
          <Check size={48} className="mx-auto mb-4 opacity-30" />
          <p>Todos os rostos foram revisados!</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {faces.map((face) => (
            <div
              key={face.id}
              className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700 hover:border-gray-500 transition-colors"
            >
              {/* Thumbnail do rosto */}
              <div
                className="aspect-square bg-gray-900 flex items-center justify-center cursor-pointer"
                onDoubleClick={() => navigate(`/media/${face.media_id}`)}
                title="Duplo clique para abrir foto"
              >
                <img
                  src={getFaceThumbnailUrl(face.id, 200)}
                  alt={`Rosto ${face.id}`}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              </div>

              {/* Info e ações */}
              <div className="p-2">
                {/* Sugestão */}
                {face.person_name ? (
                  <p className="text-sm text-yellow-400 truncate mb-1" title={face.person_name}>
                    {face.person_name} ({Math.round((face.confidence || 0) * 100)}%)
                  </p>
                ) : (
                  <p className="text-xs text-gray-500 mb-1">Não identificado</p>
                )}

                {/* Nome do arquivo */}
                <p className="text-xs text-gray-500 truncate mb-2" title={face.media_filename}>
                  {face.media_filename}
                </p>

                {/* Botões de ação */}
                {editingFace === face.id ? (
                  <div className="space-y-1">
                    <div className="max-h-28 overflow-auto space-y-0.5">
                      {persons.map((p) => (
                        <button
                          key={p.id}
                          onClick={() => handleAssign(face.id, p.id)}
                          className="w-full text-left px-2 py-1 text-xs hover:bg-gray-600 rounded truncate"
                        >
                          {p.name}
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-1">
                      <input
                        type="text"
                        value={newPersonName}
                        onChange={(e) => setNewPersonName(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleCreateAndAssign(face.id)}
                        placeholder="Nova pessoa..."
                        className="flex-1 px-1.5 py-1 text-xs bg-gray-900 border border-gray-600 rounded text-white placeholder-gray-500"
                      />
                      <button
                        onClick={() => handleCreateAndAssign(face.id)}
                        className="px-1.5 py-1 text-xs bg-green-600 rounded hover:bg-green-700"
                      >
                        +
                      </button>
                    </div>
                    <button
                      onClick={() => { setEditingFace(null); setNewPersonName('') }}
                      className="w-full text-xs text-gray-400 hover:text-white py-0.5"
                    >
                      Cancelar
                    </button>
                  </div>
                ) : (
                  <div className="flex gap-1">
                    {/* Aprovar sugestão */}
                    {face.person_name && (
                      <button
                        onClick={() => handleConfirm(face.id)}
                        className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-green-600 hover:bg-green-700 rounded text-xs"
                        title="Aprovar"
                      >
                        <Check size={12} />
                      </button>
                    )}
                    {/* Rejeitar sugestão */}
                    {face.person_name && (
                      <button
                        onClick={() => handleReject(face.id)}
                        className="px-2 py-1.5 bg-red-600 hover:bg-red-700 rounded text-xs"
                        title="Rejeitar sugestão"
                      >
                        <X size={12} />
                      </button>
                    )}
                    {/* Identificar / Trocar */}
                    <button
                      onClick={() => setEditingFace(face.id)}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-xs"
                      title="Identificar"
                    >
                      <UserPlus size={12} />
                    </button>
                    {/* Ignorar */}
                    <button
                      onClick={() => handleIgnore(face.id)}
                      className="px-2 py-1.5 bg-gray-600 hover:bg-gray-700 rounded text-xs"
                      title="Ignorar"
                    >
                      <EyeOff size={12} />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default FaceReview
