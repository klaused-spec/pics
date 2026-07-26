import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getPendingFaces, getFaceThumbnailUrl, assignFace, confirmFace, ignoreFace, unassignFace, getPersons, createPerson, getHighConfidenceFaces, bulkApproveFaces, bulkApproveAllFaces, cleanupLowConfidenceFaces, refreshFaceSuggestions } from '../api'
import { ArrowLeft, Check, X, EyeOff, UserPlus, Zap, Trash2, RefreshCw, CheckCheck } from 'lucide-react'

function FaceReview() {
  const [faces, setFaces] = useState([])
  const [persons, setPersons] = useState([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [editingFace, setEditingFace] = useState(null)
  const [newPersonName, setNewPersonName] = useState('')
  const [thumbUrls, setThumbUrls] = useState({})
  const [highConfidenceMode, setHighConfidenceMode] = useState(false)
  const [approvingBulk, setApprovingBulk] = useState(false)
  const [approvingAll, setApprovingAll] = useState(false)
  const [cleaningUp, setCleaningUp] = useState(false)
  const [refreshingSuggestions, setRefreshingSuggestions] = useState(false)
  const [hcPage, setHcPage] = useState(1)
  const [loadingMore, setLoadingMore] = useState(false)
  const thumbFetchRef = useRef(0)
  const navigate = useNavigate()

  useEffect(() => {
    setHcPage(1)
    setFaces([])
    setThumbUrls({})
    loadData(1, true)
  }, [highConfidenceMode])

  // Batch thumbnail fetch: processes faces in groups of 20 to avoid overwhelming the backend
  async function fetchThumbsBatch(facesList, existingMap = {}) {
    const token = ++thumbFetchRef.current
    const BATCH = 20
    const newMap = { ...existingMap }
    for (let i = 0; i < facesList.length; i += BATCH) {
      if (thumbFetchRef.current !== token) return // cancelled by newer load
      const batch = facesList.slice(i, i + BATCH)
      const results = await Promise.allSettled(
        batch.map(f => api.get(`/persons/faces/${f.id}/thumbnail`, { params: { size: 160 }, responseType: 'blob' }))
      )
      results.forEach((r, idx) => {
        const fid = batch[idx].id
        if (r.status === 'fulfilled') {
          try { newMap[fid] = URL.createObjectURL(r.value.data) } catch { newMap[fid] = null }
        } else {
          newMap[fid] = null
        }
      })
      setThumbUrls(prev => ({ ...prev, ...newMap }))
    }
  }

  async function loadData(page = 1, reset = false) {
    if (page === 1) setLoading(true)
    else setLoadingMore(true)
    try {
      let facesRes
      if (highConfidenceMode) {
        facesRes = await getHighConfidenceFaces({ per_page: 100, page, min_confidence: 0.75 })
      } else {
        facesRes = await getPendingFaces({ per_page: 100 })
      }
      
      const [personsRes] = await Promise.all([
        page === 1 ? getPersons({ per_page: 200 }) : Promise.resolve(null),
      ])

      const newFaces = facesRes.data.items
      const prevFaces = reset ? [] : faces
      const merged = reset ? newFaces : [...prevFaces, ...newFaces]

      setFaces(merged)
      setTotal(facesRes.data.total)
      if (personsRes) setPersons(personsRes.data.items || personsRes.data)

      // Revoke old blob URLs only on full reset
      if (reset) {
        Object.values(thumbUrls).forEach(url => { try { URL.revokeObjectURL(url) } catch {} })
        setThumbUrls({})
      }
      fetchThumbsBatch(newFaces, reset ? {} : thumbUrls)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
    setLoadingMore(false)
  }

  async function handleLoadMore() {
    const nextPage = hcPage + 1
    setHcPage(nextPage)
    await loadData(nextPage, false)
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
      setFaces(prev => prev.filter(f => f.id !== faceId))
      setTotal(prev => prev - 1)
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

  async function handleBulkApprove() {
    if (!window.confirm(`Aprovar ${faces.length} rostos carregados com >= 75% de confiança?`)) return
    
    setApprovingBulk(true)
    try {
      const faceIds = faces.map(f => f.id)
      await bulkApproveFaces(faceIds)
      setHcPage(1)
      await loadData(1, true)
    } catch (err) {
      console.error(err)
      alert('Erro ao aprovar em massa: ' + err.message)
    }
    setApprovingBulk(false)
  }

  async function handleApproveAll() {
    if (!window.confirm(`Aprovar TODOS os ${total} rostos com >= 75% de confiança no banco? Esta ação não pode ser desfeita.`)) return

    setApprovingAll(true)
    try {
      const res = await bulkApproveAllFaces(0.75)
      alert(`${res.data.approved_count} rostos aprovados.`)
      setHcPage(1)
      await loadData(1, true)
    } catch (err) {
      console.error(err)
      alert('Erro ao aprovar todos: ' + err.message)
    }
    setApprovingAll(false)
  }

  async function handleRefreshSuggestions() {
    setRefreshingSuggestions(true)
    try {
      const res = await refreshFaceSuggestions()
      await loadData()
      alert(`Sugestões recalculadas:\n- Atualizadas: ${res.data.suggested}\n- Ambíguas limpas: ${res.data.cleared}\n- Referências confirmadas: ${res.data.confirmed_references}`)
    } catch (err) {
      console.error(err)
      alert('Erro ao recalcular sugestões: ' + err.message)
    }
    setRefreshingSuggestions(false)
  }

  async function handleCleanup() {
    if (!window.confirm('Remover faces não confirmadas com baixa confiança? Esta ação é irreversível!')) return
    
    setCleaningUp(true)
    try {
      const res = await cleanupLowConfidenceFaces(0.40)
      alert(`Limpeza concluída:\n- Ignorados: ${res.data.ignored_removed}\n- Baixa confiança: ${res.data.low_confidence_removed}\n- Não identificados: ${res.data.unidentified_removed}\n- Total removido: ${res.data.total_removed}`)
      await loadData()
    } catch (err) {
      console.error(err)
      alert('Erro ao fazer limpeza: ' + err.message)
    }
    setCleaningUp(false)
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
      {/* Cabeçalho */}
      <div className="flex items-center gap-3 mb-4">
        <button onClick={() => navigate('/persons')} className="text-gray-400 hover:text-white">
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1">
          <h2 className="text-xl font-semibold">Revisar Rostos</h2>
          <p className="text-sm text-gray-400">{total} rostos pendentes</p>
        </div>
        {/* Ações em massa — discreta, à direita */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setHighConfidenceMode(!highConfidenceMode)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              highConfidenceMode ? 'bg-yellow-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
            title="Filtrar só rostos com >= 75% de confiança"
          >
            <Zap size={14} />
            {highConfidenceMode ? 'Alta confiança' : 'Todos'}
          </button>

          {highConfidenceMode && (
            <>
              <button
                onClick={handleApproveAll}
                disabled={approvingAll || approvingBulk || total === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-500 rounded text-sm font-medium text-white disabled:opacity-40"
                title={`Aprovar todos os ${total} rostos com >= 75% de confiança`}
              >
                <CheckCheck size={14} />
                {approvingAll ? 'Aprovando...' : `Aprovar tudo (${total})`}
              </button>
            </>
          )}

          <button
            onClick={handleCleanup}
            disabled={cleaningUp}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-red-700 rounded text-sm font-medium text-gray-300 hover:text-white disabled:opacity-40 transition-colors"
            title="Remover faces não confirmadas com baixa confiança"
          >
            <Trash2 size={14} />
            {cleaningUp ? 'Limpando...' : 'Limpeza'}
          </button>

          <button
            onClick={handleRefreshSuggestions}
            disabled={refreshingSuggestions}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-blue-700 rounded text-sm font-medium text-gray-300 hover:text-white disabled:opacity-40 transition-colors"
            title="Recalcular sugestões usando rostos confirmados"
          >
            <RefreshCw size={14} className={refreshingSuggestions ? 'animate-spin' : ''} />
            {refreshingSuggestions ? 'Recalculando...' : 'Reaprender'}
          </button>
        </div>
      </div>

      {faces.length === 0 ? (
        <div className="text-center text-gray-500 py-16">
          <Check size={48} className="mx-auto mb-4 opacity-30" />
          <p>
            {highConfidenceMode
              ? 'Nenhum rosto com >= 75% de confiança'
              : 'Todos os rostos foram revisados!'}
          </p>
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
                  src={thumbUrls[face.id] || getFaceThumbnailUrl(face.id, 200)}
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

      {/* Carregar mais (alta confiança, paginado) */}
      {highConfidenceMode && faces.length > 0 && faces.length < total && (
        <div className="flex justify-center mt-6">
          <button
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="px-6 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium text-white disabled:opacity-50"
          >
            {loadingMore ? 'Carregando...' : `Carregar mais (${faces.length} de ${total})`}
          </button>
        </div>
      )}
    </div>
  )
}

export default FaceReview
