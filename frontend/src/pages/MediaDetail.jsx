import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getMediaById, getMediaNeighbors, getFileUrl, getStreamUrl, assignFace, unassignFace, confirmFace, ignoreFace, getPersons, createPerson, createManualFace, getAlbums, addMediaToAlbum, forceTranscode, getTranscodeStatus, deleteOriginalVideo, deleteMedia, getSettings } from '../api'
import { ArrowLeft, ChevronLeft, ChevronRight, MapPin, Tag, User, Calendar, Camera, FolderPlus, Trash2 } from 'lucide-react'

const FACE_COLORS = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316']

function MediaDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [media, setMedia] = useState(null)
  const [loading, setLoading] = useState(true)
  const [persons, setPersons] = useState([])
  const [showAssign, setShowAssign] = useState(null)
  const [newPersonName, setNewPersonName] = useState('')
  const [showFaceBoxes, setShowFaceBoxes] = useState(true)
  const [highlightFace, setHighlightFace] = useState(null)
  const imgRef = useRef(null)
  const [imgSize, setImgSize] = useState({ width: 0, height: 0, naturalWidth: 1, naturalHeight: 1 })
  const [selectingFace, setSelectingFace] = useState(false)
  const [selectionStart, setSelectionStart] = useState(null)
  const [selectionRect, setSelectionRect] = useState(null)
  const [neighbors, setNeighbors] = useState({ prev_id: null, next_id: null })
  const [albums, setAlbums] = useState([])
  const [showAlbumPicker, setShowAlbumPicker] = useState(false)
  const [allowLibraryModify, setAllowLibraryModify] = useState(false)

  useEffect(() => {
    loadMedia()
    loadPersons()
    loadNeighbors()
    getSettings().then(r => setAllowLibraryModify(r.data.allow_library_modify))
  }, [id])

  async function loadMedia() {
    setLoading(true)
    try {
      const res = await getMediaById(id)
      setMedia(res.data)
    } catch (err) {
      console.error('Erro ao carregar mídia:', err)
    }
    setLoading(false)
  }

  async function loadNeighbors() {
    try {
      const res = await getMediaNeighbors(id)
      setNeighbors(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  const goToPrev = useCallback(() => {
    if (neighbors.prev_id) navigate(`/media/${neighbors.prev_id}`)
  }, [neighbors.prev_id, navigate])

  const goToNext = useCallback(() => {
    if (neighbors.next_id) navigate(`/media/${neighbors.next_id}`)
  }, [neighbors.next_id, navigate])

  // Teclado: setas esquerda/direita
  useEffect(() => {
    function handleKey(e) {
      if (e.target.tagName === 'INPUT') return
      if (e.key === 'ArrowLeft') goToPrev()
      if (e.key === 'ArrowRight') goToNext()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [goToPrev, goToNext])

  async function loadPersons() {
    try {
      const res = await getPersons({ per_page: 200 })
      setPersons(res.data.items)
    } catch (err) {
      console.error(err)
    }
  }

  async function handleAssignFace(faceId, personId) {
    try {
      await assignFace(faceId, personId)
      setShowAssign(null)
      setNewPersonName('')
      loadMedia()
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
      setShowAssign(null)
      setNewPersonName('')
      // Atualiza lista de pessoas
      const pRes = await getPersons()
      setPersons(pRes.data.items || pRes.data)
      loadMedia()
    } catch (err) {
      console.error(err)
    }
  }

  // Seleção manual de rosto
  function handleMouseDown(e) {
    if (!selectingFace) return
    const rect = imgRef.current.getBoundingClientRect()
    setSelectionStart({ x: e.clientX - rect.left, y: e.clientY - rect.top })
    setSelectionRect(null)
  }

  function handleMouseMove(e) {
    if (!selectingFace || !selectionStart) return
    const rect = imgRef.current.getBoundingClientRect()
    const curX = e.clientX - rect.left
    const curY = e.clientY - rect.top
    setSelectionRect({
      x: Math.min(selectionStart.x, curX),
      y: Math.min(selectionStart.y, curY),
      w: Math.abs(curX - selectionStart.x),
      h: Math.abs(curY - selectionStart.y),
    })
  }

  async function handleMouseUp() {
    if (!selectingFace || !selectionRect || selectionRect.w < 10 || selectionRect.h < 10) {
      setSelectionStart(null)
      setSelectionRect(null)
      return
    }
    // Converte coordenadas da tela para coordenadas da imagem original
    const scaleX = imgSize.naturalWidth / imgSize.width
    const scaleY = imgSize.naturalHeight / imgSize.height
    const bbox = {
      bbox_x: Math.round(selectionRect.x * scaleX),
      bbox_y: Math.round(selectionRect.y * scaleY),
      bbox_width: Math.round(selectionRect.w * scaleX),
      bbox_height: Math.round(selectionRect.h * scaleY),
    }
    try {
      await createManualFace(media.id, bbox)
      loadMedia()
    } catch (err) {
      console.error('Erro ao criar rosto manual:', err)
    }
    setSelectingFace(false)
    setSelectionStart(null)
    setSelectionRect(null)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    )
  }

  if (!media) {
    return <div className="p-8 text-gray-400">Mídia não encontrada</div>
  }

  // Filtra rostos ignorados
  const visibleFaces = media.faces ? media.faces.filter(f => !f.is_ignored) : []

  return (
    <div className="h-full flex flex-col lg:flex-row">
      {/* Área da mídia */}
      <div className="flex-1 flex flex-col bg-black">
        <div className="p-3">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 text-gray-400 hover:text-white text-sm"
          >
            <ArrowLeft size={16} />
            Voltar
          </button>
        </div>

        <div className="flex-1 flex items-center justify-center p-4 relative">
          {/* Seta esquerda */}
          {neighbors.prev_id && (
            <button
              onClick={goToPrev}
              className="absolute left-2 top-1/2 -translate-y-1/2 z-10 p-2 bg-black/50 hover:bg-black/80 rounded-full text-white transition-colors"
              title="Foto anterior (←)"
            >
              <ChevronLeft size={24} />
            </button>
          )}
          {/* Seta direita */}
          {neighbors.next_id && (
            <button
              onClick={goToNext}
              className="absolute right-2 top-1/2 -translate-y-1/2 z-10 p-2 bg-black/50 hover:bg-black/80 rounded-full text-white transition-colors"
              title="Próxima foto (→)"
            >
              <ChevronRight size={24} />
            </button>
          )}
          {media.media_type === 'image' ? (
            <div
              className="relative inline-block max-w-full max-h-full"
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              style={{ cursor: selectingFace ? 'crosshair' : 'default' }}
            >
              <img
                ref={imgRef}
                src={getFileUrl(media.id)}
                alt={media.ai_description || media.filename}
                className="max-w-full max-h-[calc(100vh-120px)] object-contain select-none"
                draggable={false}
                onLoad={(e) => {
                  const { width, height, naturalWidth, naturalHeight } = e.target
                  setImgSize({ width, height, naturalWidth, naturalHeight })
                }}
              />
              {/* Retângulo de seleção manual */}
              {selectingFace && selectionRect && (
                <div
                  className="absolute border-2 border-dashed border-yellow-400 bg-yellow-400/10 pointer-events-none"
                  style={{
                    left: `${selectionRect.x}px`,
                    top: `${selectionRect.y}px`,
                    width: `${selectionRect.w}px`,
                    height: `${selectionRect.h}px`,
                  }}
                />
              )}
              {/* Banner de modo seleção */}
              {selectingFace && (
                <div className="absolute top-2 left-1/2 -translate-x-1/2 bg-yellow-600 px-3 py-1 rounded text-sm font-medium">
                  Selecione o rosto arrastando na imagem
                  <button
                    onClick={() => { setSelectingFace(false); setSelectionRect(null); setSelectionStart(null) }}
                    className="ml-2 text-xs underline"
                  >
                    Cancelar
                  </button>
                </div>
              )}
              {/* Overlay de rostos */}
              {showFaceBoxes && visibleFaces.length > 0 && imgSize.width > 0 && (
                <div className="absolute inset-0 pointer-events-none">
                  {visibleFaces.map((face, idx) => {
                    const scaleX = imgSize.width / imgSize.naturalWidth
                    const scaleY = imgSize.height / imgSize.naturalHeight
                    const color = FACE_COLORS[idx % FACE_COLORS.length]
                    const isHighlighted = highlightFace === face.id

                    return (
                      <div
                        key={face.id}
                        className="absolute pointer-events-auto cursor-pointer transition-all"
                        style={{
                          left: `${face.bbox.x * scaleX}px`,
                          top: `${face.bbox.y * scaleY}px`,
                          width: `${face.bbox.w * scaleX}px`,
                          height: `${face.bbox.h * scaleY}px`,
                          border: `2px solid ${color}`,
                          borderRadius: '4px',
                          boxShadow: isHighlighted ? `0 0 12px ${color}` : 'none',
                          opacity: isHighlighted ? 1 : 0.7,
                        }}
                        onMouseEnter={() => setHighlightFace(face.id)}
                        onMouseLeave={() => setHighlightFace(null)}
                        onClick={() => setShowAssign(face.id)}
                      >
                        {/* Label do rosto */}
                        <div
                          className="absolute -top-6 left-0 px-1.5 py-0.5 rounded text-xs whitespace-nowrap"
                          style={{ backgroundColor: color, color: 'white' }}
                        >
                          {face.person_name || `Rosto ${idx + 1}`}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          ) : media.needs_transcode && media.is_transcoded === false && media.transcode_status === 'transcoding' ? (
            <TranscodeProgress mediaId={media.id} onDone={loadMedia} />
          ) : (
            <div className="relative flex flex-col items-center">
              <video
                src={getStreamUrl(media.id)}
                controls
                className="max-w-full max-h-[calc(100vh-160px)]"
                autoPlay
              />
              <div className="flex gap-2 mt-3">
                <button
                  onClick={async () => {
                    try {
                      await forceTranscode(media.id)
                      loadMedia()
                    } catch (err) {
                      console.error(err)
                    }
                  }}
                  className="px-3 py-1.5 bg-yellow-700 hover:bg-yellow-600 rounded text-sm text-white"
                >
                  ⚠️ Não toca? Converter
                </button>
                {media.is_transcoded && (
                  <button
                    onClick={async () => {
                      if (!confirm('Apagar vídeo original? (mantém apenas a versão convertida)')) return
                      try {
                        const res = await deleteOriginalVideo(media.id)
                        alert(res.data.message)
                        loadMedia()
                      } catch (err) {
                        alert('Erro: ' + (err.response?.data?.detail || err.message))
                      }
                    }}
                    className="px-3 py-1.5 bg-red-700 hover:bg-red-600 rounded text-sm text-white"
                  >
                    🗑️ Apagar original
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Toggle de face boxes */}
          {media.media_type === 'image' && (
            <div className="absolute top-2 right-2 flex gap-1">
              {media.faces && media.faces.length > 0 && (
                <button
                  onClick={() => setShowFaceBoxes(!showFaceBoxes)}
                  className={`px-2 py-1 rounded text-xs ${
                    showFaceBoxes ? 'bg-blue-600' : 'bg-gray-700'
                  }`}
                >
                  {showFaceBoxes ? 'Ocultar rostos' : 'Mostrar rostos'}
                </button>
              )}
              <button
                onClick={() => setSelectingFace(true)}
                className="px-2 py-1 rounded text-xs bg-yellow-600 hover:bg-yellow-700"
              >
                + Rosto manual
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Painel lateral de detalhes */}
      <div className="w-full lg:w-80 bg-gray-800 border-l border-gray-700 overflow-auto">
        <div className="p-4 space-y-4">
          <h3 className="font-semibold text-lg truncate">{media.filename}</h3>

          {/* Data */}
          {media.date_taken && (
            <div className="flex items-center gap-2 text-sm text-gray-300">
              <Calendar size={14} className="text-blue-400" />
              {new Date(media.date_taken).toLocaleString('pt-BR')}
            </div>
          )}

          {/* Localização IA */}
          {media.ai_location && media.ai_location !== 'desconhecido' && (
            <div className="flex items-center gap-2 text-sm text-gray-300">
              <MapPin size={14} className="text-green-400" />
              {media.ai_location}
            </div>
          )}

          {/* Câmera */}
          {media.camera_model && (
            <div className="flex items-center gap-2 text-sm text-gray-300">
              <Camera size={14} className="text-yellow-400" />
              {media.camera_make} {media.camera_model}
            </div>
          )}

          {/* Descrição IA */}
          {media.ai_description && (
            <div className="bg-gray-700/50 rounded-lg p-3">
              <h4 className="text-xs font-semibold text-blue-400 mb-1">Descrição IA</h4>
              <p className="text-sm text-gray-300">{media.ai_description}</p>
            </div>
          )}

          {/* Tags */}
          {media.tags && media.tags.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-400 mb-2 flex items-center gap-1">
                <Tag size={12} /> Tags
              </h4>
              <div className="flex flex-wrap gap-1">
                {media.tags.map((tag) => (
                  <span
                    key={tag.id}
                    className="px-2 py-0.5 bg-gray-700 rounded-full text-xs text-gray-300"
                  >
                    {tag.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Adicionar ao álbum */}
          <div>
            <button
              onClick={async () => { const res = await getAlbums(); setAlbums(res.data); setShowAlbumPicker(!showAlbumPicker) }}
              className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
            >
              <FolderPlus size={12} /> Adicionar ao álbum
            </button>
            {showAlbumPicker && (
              <div className="mt-1 bg-gray-800 border border-gray-700 rounded p-2 max-h-32 overflow-auto">
                {albums.length === 0 ? (
                  <p className="text-xs text-gray-500">Nenhum álbum. Crie na Galeria.</p>
                ) : (
                  albums.map((a) => (
                    <button
                      key={a.id}
                      onClick={async () => { await addMediaToAlbum(a.id, [media.id]); setShowAlbumPicker(false) }}
                      className="block w-full text-left px-2 py-1 text-xs text-gray-300 hover:bg-gray-700 rounded"
                    >
                      {a.name} ({a.media_count})
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Rostos detectados */}
          {visibleFaces.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-400 mb-2 flex items-center gap-1">
                <User size={12} /> Pessoas ({visibleFaces.length})
              </h4>
              <div className="space-y-2">
                {visibleFaces.map((face, idx) => {
                  const color = FACE_COLORS[idx % FACE_COLORS.length]
                  return (
                  <div
                    key={face.id}
                    className="flex items-center justify-between bg-gray-700/50 rounded p-2 transition-all"
                    style={{
                      borderLeft: `3px solid ${color}`,
                      backgroundColor: highlightFace === face.id ? 'rgba(59,130,246,0.15)' : undefined,
                    }}
                    onMouseEnter={() => setHighlightFace(face.id)}
                    onMouseLeave={() => setHighlightFace(null)}
                  >
                    <div>
                      <p className="text-sm">
                        {face.person_name || `Rosto ${idx + 1}`}
                      </p>
                      {face.confidence && !face.is_confirmed && face.person_name && (
                        <p className="text-xs text-yellow-400">
                          Sugestão ({Math.round(face.confidence * 100)}%)
                        </p>
                      )}
                      {face.is_confirmed && face.person_name && (
                        <p className="text-xs text-green-400">✓ Confirmado</p>
                      )}
                    </div>
                    <div className="flex gap-1">
                      {/* Sugestão pendente: aprovar ou rejeitar */}
                      {face.person_name && !face.is_confirmed && (
                        <>
                          <button
                            onClick={async () => { await confirmFace(face.id); loadMedia() }}
                            className="text-xs px-2 py-1 bg-green-600 rounded hover:bg-green-700"
                            title="Aprovar sugestão"
                          >
                            ✓
                          </button>
                          <button
                            onClick={async () => { await unassignFace(face.id); loadMedia() }}
                            className="text-xs px-2 py-1 bg-red-600 rounded hover:bg-red-700"
                            title="Rejeitar sugestão"
                          >
                            ✕
                          </button>
                        </>
                      )}
                      {/* Já confirmado: pode remover ou trocar */}
                      {face.person_name && face.is_confirmed && (
                        <button
                          onClick={async () => { await unassignFace(face.id); loadMedia() }}
                          className="text-xs px-2 py-1 bg-red-600 rounded hover:bg-red-700"
                          title="Remover identificação"
                        >
                          ✕
                        </button>
                      )}
                      <button
                        onClick={() => setShowAssign(face.id)}
                        className="text-xs px-2 py-1 bg-blue-600 rounded hover:bg-blue-700"
                      >
                        {face.person_name ? 'Trocar' : 'Identificar'}
                      </button>
                      <button
                        onClick={async () => { await ignoreFace(face.id); loadMedia() }}
                        className="text-xs px-2 py-1 bg-gray-600 rounded hover:bg-gray-700"
                        title="Descartar rosto (detecção errada)"
                      >
                        🗑
                      </button>
                    </div>
                  </div>
                  )
                })}
              </div>

              {/* Modal de atribuição */}
              {showAssign && (
                <div className="mt-2 bg-gray-700 rounded-lg p-3">
                  <p className="text-sm mb-2">Selecione a pessoa:</p>
                  <div className="max-h-40 overflow-auto space-y-1">
                    {persons.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => handleAssignFace(showAssign, p.id)}
                        className="w-full text-left px-2 py-1 text-sm hover:bg-gray-600 rounded"
                      >
                        {p.name}
                      </button>
                    ))}
                  </div>
                  <div className="mt-2 flex gap-1">
                    <input
                      type="text"
                      value={newPersonName}
                      onChange={(e) => setNewPersonName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleCreateAndAssign(showAssign)}
                      placeholder="Nova pessoa..."
                      className="flex-1 px-2 py-1 text-sm bg-gray-800 border border-gray-600 rounded text-white placeholder-gray-500"
                    />
                    <button
                      onClick={() => handleCreateAndAssign(showAssign)}
                      className="px-2 py-1 text-sm bg-green-600 rounded hover:bg-green-700"
                    >
                      +
                    </button>
                  </div>
                  <button
                    onClick={() => { setShowAssign(null); setNewPersonName('') }}
                    className="mt-2 text-xs text-gray-400 hover:text-white"
                  >
                    Cancelar
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Metadados técnicos */}
          <div className="border-t border-gray-700 pt-3">
            <h4 className="text-xs font-semibold text-gray-400 mb-2">Detalhes</h4>
            <div className="space-y-1 text-xs text-gray-400">
              {media.width && media.height && (
                <p>Resolução: {media.width}x{media.height}</p>
              )}
              {media.duration_seconds && (
                <p>Duração: {Math.round(media.duration_seconds)}s</p>
              )}
              <p className="truncate" title={media.organized_path}>
                Caminho: {media.organized_path}
              </p>
            </div>
          </div>

          {/* Botão Excluir */}
          {allowLibraryModify && (
            <div className="border-t border-gray-700 pt-3">
              <button
                onClick={async () => {
                  if (!confirm('Mover este arquivo para .trash? (pode ser recuperado)')) return
                  try {
                    await deleteMedia(media.id)
                    navigate(-1)
                  } catch (err) {
                    alert('Erro: ' + (err.response?.data?.detail || err.message))
                  }
                }}
                className="flex items-center gap-2 px-3 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm text-white w-full justify-center"
              >
                <Trash2 size={14} /> Excluir arquivo
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Componente de progresso de transcodificação com polling
function TranscodeProgress({ mediaId, onDone }) {
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState('transcoding')
  const triggered = useRef(false)

  useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const res = await getTranscodeStatus(mediaId)
        if (!active) return
        setProgress(res.data.progress)
        setStatus(res.data.status)

        if (res.data.status === 'done') {
          onDone?.()
        } else if (res.data.status === 'error') {
          // parar de pollar
        } else {
          setTimeout(poll, 2000)
        }
      } catch {
        if (active) setTimeout(poll, 5000)
      }
    }
    poll()
    return () => { active = false }
  }, [mediaId])

  return (
    <div className="flex flex-col items-center justify-center gap-3">
      {status === 'error' ? (
        <>
          <p className="text-red-400 font-medium">Erro na conversão</p>
          <button onClick={onDone} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm">
            Voltar
          </button>
        </>
      ) : (
        <>
          <div className="relative w-48 h-48 flex items-center justify-center">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="45" fill="none" stroke="#374151" strokeWidth="8" />
              <circle cx="50" cy="50" r="45" fill="none" stroke="#facc15" strokeWidth="8"
                strokeDasharray={`${progress * 2.83} 283`} strokeLinecap="round"
                className="transition-all duration-1000"
              />
            </svg>
            <span className="absolute text-2xl font-bold text-yellow-400">{progress}%</span>
          </div>
          <p className="text-yellow-400 font-medium">Convertendo vídeo...</p>
          <p className="text-sm text-gray-400">Isso acontece apenas na primeira vez</p>
        </>
      )}
    </div>
  )
}

export default MediaDetail
