import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getPersons, createPerson, runClustering, getFaceThumbnailUrl } from '../api'
import { Users, Plus, Sparkles, ScanFace } from 'lucide-react'

function Persons() {
  const [persons, setPersons] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const navigate = useNavigate()
  const [thumbs, setThumbs] = useState({})

  useEffect(() => {
    loadPersons()
  }, [])

  async function loadPersons() {
    setLoading(true)
    try {
      const res = await getPersons({ per_page: 100 })
      const list = res.data.items
      setPersons(list)
      // fetch avatars via authenticated requests
      // revoke old URLs
      Object.values(thumbs).forEach(u => { try { URL.revokeObjectURL(u) } catch (e) {} })
      const results = await Promise.allSettled(list.map(p => p.avatar_face_id ? api.get(`/persons/faces/${p.avatar_face_id}/thumbnail`, { params: { size: 120 }, responseType: 'blob' }) : Promise.resolve(null)))
      const map = {}
      results.forEach((r, i) => {
        const pid = list[i].id
        if (r && r.status === 'fulfilled' && r.value && r.value.data) {
          try { map[pid] = URL.createObjectURL(r.value.data) } catch (e) { map[pid] = null }
        } else {
          map[pid] = null
        }
      })
      setThumbs(map)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  async function handleCreate(e) {
    e.preventDefault()
    if (!newName.trim()) return
    try {
      await createPerson(newName.trim())
      setNewName('')
      setShowCreate(false)
      loadPersons()
    } catch (err) {
      console.error(err)
    }
  }

  async function handleCluster() {
    try {
      const res = await runClustering()
      alert(`Criados ${res.data.new_clusters} novos agrupamentos de rostos`)
      loadPersons()
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
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Users size={24} />
            Pessoas
          </h2>
          <p className="text-sm text-gray-400 mt-1">{persons.length} pessoas identificadas</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate('/persons/review')}
            className="flex items-center gap-2 px-3 py-2 bg-yellow-600 hover:bg-yellow-700 rounded-lg text-sm"
          >
            <ScanFace size={14} />
            Revisar rostos
          </button>
          <button
            onClick={handleCluster}
            className="flex items-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm"
          >
            <Sparkles size={14} />
            Auto-agrupar
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm"
          >
            <Plus size={14} />
            Nova pessoa
          </button>
        </div>
      </div>

      {/* Formulário de criação */}
      {showCreate && (
        <form onSubmit={handleCreate} className="mb-6 p-4 bg-gray-800 rounded-lg flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Nome da pessoa"
            className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm focus:outline-none focus:border-blue-500"
            autoFocus
          />
          <button type="submit" className="px-4 py-2 bg-blue-600 rounded text-sm">
            Criar
          </button>
          <button
            type="button"
            onClick={() => setShowCreate(false)}
            className="px-4 py-2 bg-gray-700 rounded text-sm"
          >
            Cancelar
          </button>
        </form>
      )}

      {/* Grid de pessoas */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {persons.map((person) => (
          <div
            key={person.id}
            onClick={() => navigate(`/persons/${person.id}`)}
            className="bg-gray-800 rounded-lg p-4 cursor-pointer hover:bg-gray-700 transition-colors"
          >
            <div className="w-16 h-16 rounded-full bg-gray-700 flex items-center justify-center mx-auto mb-3 overflow-hidden">
              {person.avatar_face_id ? (
                <img
                  src={thumbs[person.id] || getFaceThumbnailUrl(person.avatar_face_id, 120)}
                  alt={person.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <Users size={24} className="text-gray-500" />
              )}
            </div>
            <h3 className="text-sm font-medium text-center truncate">{person.name}</h3>
            <p className="text-xs text-gray-400 text-center mt-1">
              {person.media_count} fotos · {person.face_count} aparições
            </p>
            {!person.is_confirmed && (
              <p className="text-xs text-yellow-500 text-center mt-1">Não confirmado</p>
            )}
          </div>
        ))}
      </div>

      {persons.length === 0 && (
        <div className="text-center text-gray-500 py-16">
          <Users size={48} className="mx-auto mb-4 opacity-30" />
          <p>Nenhuma pessoa identificada ainda.</p>
          <p className="text-sm mt-1">Execute a detecção facial para começar.</p>
        </div>
      )}
    </div>
  )
}

export default Persons
