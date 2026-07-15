import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getMedia, getTimeline, getAlbums, createAlbum, addMediaToAlbum, createFolderAndMoveMedia, bulkCorrectMediaDate, getThumbnailUrl } from '../api'
import MediaGrid from '../components/MediaGrid'
import { Play, Calendar, FolderPlus, Image, CheckSquare, ChevronLeft, Clock } from 'lucide-react'

function Gallery() {
  const [items, setItems] = useState([])
  const [timeline, setTimeline] = useState([])
  const [albums, setAlbums] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [moving, setMoving] = useState(false)
  const [thumbnailVersion, setThumbnailVersion] = useState(0)
  const [searchParams, setSearchParams] = useSearchParams()
  const [showNewAlbum, setShowNewAlbum] = useState(false)
  const [newAlbumName, setNewAlbumName] = useState('')
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const [showAlbumPicker, setShowAlbumPicker] = useState(false)
  const [pickerNewAlbumName, setPickerNewAlbumName] = useState('')
  const [showFolderCreator, setShowFolderCreator] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [showDateCorrection, setShowDateCorrection] = useState(false)
  const [correctedDate, setCorrectedDate] = useState('')
  const [writeMetadata, setWriteMetadata] = useState(true)
  const [renameVideos, setRenameVideos] = useState(true)
  const [dateCorrectionResult, setDateCorrectionResult] = useState(null)
  const [perPage, setPerPage] = useState(() => {
    const saved = localStorage.getItem('gallery_per_page')
    return saved ? parseInt(saved) : 60
  })
  const [thumbSize, setThumbSize] = useState(() => localStorage.getItem('gallery_thumb_size') || 'medium')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem('gallery_sidebar_collapsed') === 'true'
  })
  const navigate = useNavigate()

  const tab = searchParams.get('tab') || 'data'
  const year = searchParams.get('year')
  const month = searchParams.get('month')
  const folder = searchParams.get('folder')
  const mediaType = searchParams.get('media_type')

  useEffect(() => {
    if (tab === 'data') {
      loadMedia()
    } else {
      loadAlbums()
    }
  }, [page, perPage, year, month, folder, tab, mediaType])

  useEffect(() => {
    if (tab === 'data') {
      loadTimeline()
    }
  }, [tab, mediaType])

  async function loadMedia() {
    setLoading(true)
    try {
      const params = { page, per_page: perPage }
      if (year) params.year = parseInt(year)
      if (month) params.month = parseInt(month)
      if (folder) params.folder = folder
      if (mediaType) params.media_type = mediaType

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
      const params = {}
      if (mediaType) params.media_type = mediaType
      const fastRes = await getTimeline({ ...params, include_folders: false })
      setTimeline(fastRes.data)

      const fullRes = await getTimeline({ ...params, include_folders: true })
      setTimeline(fullRes.data)
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

  function handleSelectMultiple(ids) {
    const next = new Set(selected)
    ids.forEach(id => next.add(id))
    setSelected(next)
  }

  async function handleAddToAlbum(albumId) {
    if (selected.size === 0) return
    await addMediaToAlbum(albumId, [...selected])
    setSelected(new Set())
    setSelectMode(false)
    setShowAlbumPicker(false)
  }

  async function handleCreateAlbumAndMove(e) {
    e.preventDefault()
    if (selected.size === 0 || !pickerNewAlbumName.trim()) return
    try {
      const res = await createAlbum(pickerNewAlbumName.trim())
      const album = res.data
      await addMediaToAlbum(album.id, [...selected])
      setSelected(new Set())
      setSelectMode(false)
      setShowAlbumPicker(false)
      setPickerNewAlbumName('')
      loadAlbums()
    } catch (err) {
      console.error('Erro ao criar álbum e adicionar mídia:', err)
    }
  }

  async function handleCreateFolder(e) {
    e.preventDefault()
    if (moving || selected.size === 0 || !year || !month || !newFolderName.trim()) return

    await handleMoveToFolder(newFolderName.trim())
  }

  async function handleMoveToFolder(folderName) {
    if (moving || selected.size === 0 || !year || !month || !folderName.trim()) return

    setMoving(true)
    setLoading(true)
    try {
      const res = await createFolderAndMoveMedia(parseInt(year), parseInt(month), folderName.trim(), [...selected])
      if (res.data.errors?.length) {
        console.error('Erros ao mover arquivos:', res.data.errors)
      }
      setThumbnailVersion(Date.now())
      await Promise.all([loadMedia(), loadTimeline()])
      if (!res.data.errors?.length) {
        setSelected(new Set())
        setSelectMode(false)
        setShowFolderCreator(false)
        setNewFolderName('')
      }
    } catch (err) {
      console.error('Erro ao mover arquivos para pasta:', err)
    } finally {
      setMoving(false)
      setLoading(false)
    }
  }

  async function handleBulkDateCorrection(e) {
    e.preventDefault()
    if (moving || !correctedDate || !year || !month) return

    const mediaIds = selected.size > 0 ? [...selected] : items.map((item) => item.id)
    if (mediaIds.length === 0) return

    setDateCorrectionResult(null)
    setMoving(true)
    setLoading(true)
    try {
      const isoDate = new Date(correctedDate).toISOString()
      const res = await bulkCorrectMediaDate({
        date_taken: isoDate,
        media_ids: mediaIds,
        source_year: parseInt(year),
        source_month: parseInt(month),
        source_folder: folder || null,
        write_metadata: writeMetadata,
        move_files: true,
        keep_folder: true,
        rename_videos: renameVideos,
      })
      setDateCorrectionResult(res.data)
      setThumbnailVersion(Date.now())
      setSelected(new Set())
      setSelectMode(false)
      setShowDateCorrection(false)
      setShowFolderCreator(false)
      setShowAlbumPicker(false)

      const nextDate = new Date(correctedDate)
      const nextParams = { tab: 'data', year: nextDate.getFullYear(), month: nextDate.getMonth() + 1 }
      if (folder) nextParams.folder = folder
      setSearchParams(nextParams)
      setPage(1)
      await loadTimeline()
    } catch (err) {
      setDateCorrectionResult({ errors: [err.response?.data?.detail || 'Erro ao corrigir datas'] })
      console.error('Erro ao corrigir datas:', err)
    } finally {
      setMoving(false)
      setLoading(false)
    }
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

  const currentMonthEntry = (() => {
    if (!year || !month) return null
    const y = parseInt(year)
    const m = parseInt(month)
    return timeline.find((t) => t.year === y && t.month === m) || null
  })()

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className={`transition-all duration-200 ${sidebarCollapsed ? 'w-12' : 'w-48'} bg-gray-800/50 border-r border-gray-700 overflow-hidden flex flex-col`}>
        <div className="flex items-center justify-between p-2 border-b border-gray-700">
          {!sidebarCollapsed && (
            <div className="text-xs font-semibold uppercase text-gray-400">Filtros</div>
          )}
          <button
            onClick={() => {
              const next = !sidebarCollapsed
              setSidebarCollapsed(next)
              window.localStorage.setItem('gallery_sidebar_collapsed', String(next))
            }}
            className="p-2 rounded hover:bg-gray-700 text-gray-300"
            aria-label={sidebarCollapsed ? 'Expandir painel de filtros' : 'Recolher painel de filtros'}
          >
            <ChevronLeft className={`${sidebarCollapsed ? 'rotate-180' : ''} transition-transform`} size={16} />
          </button>
        </div>
        {!sidebarCollapsed && (
          <>    
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
              <div key={`${t.year}-${t.month}`}>
                <button
                  onClick={() => filterByMonth(t.year, t.month)}
                  className={`w-full text-left px-2 py-1 text-sm rounded ${
                    year == t.year && month == t.month && !folder
                      ? 'bg-blue-600/30 text-blue-400'
                      : 'text-gray-400 hover:text-white'
                  }`}
                >
                  {monthNames[t.month]} {t.year} ({t.count})
                </button>
                {t.folders && t.folders.length > 0 && (
                  <div className="pl-4 mt-1">
                    {t.folders.map((sub) => (
                      <button
                        key={sub.name}
                        onClick={() => {
                          setSearchParams({ tab: 'data', year: t.year, month: t.month, folder: sub.name })
                          setPage(1)
                        }}
                        className={`w-full text-left px-2 py-1 text-xs rounded ${
                          year == t.year && month == t.month && folder === sub.name
                            ? 'bg-blue-600/30 text-blue-400'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        └ {sub.name} ({sub.count})
                      </button>
                    ))}
                  </div>
                )}
              </div>
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
          </>
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
                  {mediaType === 'video' ? 'Vídeos' : mediaType === 'image' ? 'Fotos' : year ? `${monthNames[parseInt(month)] || ''} ${year}` : 'Todas as mídias'}
                </h2>
                <p className="text-sm text-gray-400">
                  {total} itens
                  {folder && (
                    <span className="ml-2 text-blue-400">
                      Pasta: {folder}
                      <button onClick={() => { const p = new URLSearchParams(searchParams); p.delete('folder'); setSearchParams(p); setPage(1) }} className="ml-2 text-blue-400 hover:text-blue-300">✕ limpar pasta</button>
                    </span>
                  )}
                  {mediaType && (
                    <button onClick={() => { const p = new URLSearchParams(searchParams); p.delete('media_type'); setSearchParams(p); setPage(1) }} className="ml-2 text-blue-400 hover:text-blue-300">✕ limpar filtro</button>
                  )}
                  {dateCorrectionResult && (
                    <span className={dateCorrectionResult.errors?.length ? 'ml-2 text-amber-400' : 'ml-2 text-green-400'}>
                      Datas corrigidas: {dateCorrectionResult.corrected || 0}, movidos: {dateCorrectionResult.moved || 0}
                      {dateCorrectionResult.metadata_written ? `, EXIF: ${dateCorrectionResult.metadata_written}` : ''}
                      {dateCorrectionResult.errors?.length ? `, erros: ${dateCorrectionResult.errors.length}` : ''}
                    </span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {selectMode ? (
                  <>
                    <span className="text-sm text-gray-400">{selected.size} selecionados</span>
                    <div className="relative">
                      <button
                        onClick={async () => { const res = await getAlbums(); setAlbums(res.data); setShowAlbumPicker(!showAlbumPicker) }}
                        disabled={selected.size === 0}
                        className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm disabled:opacity-50"
                      >
                        Adicionar ao álbum
                      </button>
                      {showAlbumPicker && (
                        <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded p-2 min-w-[220px] max-h-64 overflow-auto z-50">
                          <form onSubmit={handleCreateAlbumAndMove} className="mb-2 flex gap-2">
                            <input
                              value={pickerNewAlbumName}
                              onChange={(e) => setPickerNewAlbumName(e.target.value)}
                              placeholder="Novo álbum..."
                              className="flex-1 px-2 py-1 text-sm bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-500"
                            />
                            <button
                              type="submit"
                              className="px-2 py-1 bg-green-600 hover:bg-green-700 rounded text-sm disabled:opacity-50"
                            >
                              Criar
                            </button>
                          </form>
                          {albums.length === 0 ? (
                            <p className="text-xs text-gray-500 p-1">Nenhum álbum criado. Crie um agora.</p>
                          ) : (
                            albums.map((a) => (
                              <button
                                key={a.id}
                                onClick={() => handleAddToAlbum(a.id)}
                                className="block w-full text-left px-2 py-1 text-sm text-gray-300 hover:bg-gray-700 rounded"
                              >
                                {a.name} ({a.media_count})
                              </button>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                    <div className="relative">
                      <button
                        onClick={() => setShowFolderCreator(f => !f)}
                        disabled={moving || selected.size === 0 || !year || !month}
                        className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm disabled:opacity-50"
                      >
                        {moving ? 'Movendo...' : 'Mover para pasta'}
                      </button>
                      {showFolderCreator && (
                        <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded p-2 min-w-[260px] z-50">
                          <div className="mb-2 text-sm font-semibold text-gray-200">Mover para pasta</div>
                          {currentMonthEntry && currentMonthEntry.folders && currentMonthEntry.folders.length > 0 ? (
                            <div className="mb-2 border border-gray-700 rounded p-2 bg-gray-900 text-sm">
                              <div className="mb-1 text-xs uppercase text-gray-500">Pastas existentes</div>
                              {currentMonthEntry.folders.map((sub) => (
                                <button
                                  key={sub.name}
                                  type="button"
                                  onClick={() => handleMoveToFolder(sub.name)}
                                  className="block w-full text-left px-2 py-1 mb-1 rounded text-gray-300 hover:bg-gray-700"
                                >
                                  {sub.name} ({sub.count})
                                </button>
                              ))}
                            </div>
                          ) : (
                            <div className="mb-2 text-xs text-gray-500">Nenhuma pasta existente neste mês.</div>
                          )}
                          <form onSubmit={handleCreateFolder} className="space-y-2">
                            <input
                              autoFocus
                              value={newFolderName}
                              onChange={(e) => setNewFolderName(e.target.value)}
                              placeholder="Nova pasta..."
                              className="w-full px-2 py-1 text-sm bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-500"
                            />
                            <button
                              type="submit"
                              disabled={moving}
                              className="w-full px-2 py-1 bg-blue-500 hover:bg-blue-600 rounded text-sm disabled:opacity-50"
                            >
                              {moving ? 'Movendo...' : 'Criar e mover'}
                            </button>
                          </form>
                        </div>
                      )}
                    </div>
                    <div className="relative">
                      <button
                        onClick={() => setShowDateCorrection(f => !f)}
                        disabled={moving || !year || !month || (selected.size === 0 && items.length === 0)}
                        className="px-3 py-1 bg-amber-600 hover:bg-amber-700 rounded text-sm disabled:opacity-50"
                      >
                        {moving ? 'Aplicando...' : 'Corrigir data'}
                      </button>
                      {showDateCorrection && (
                        <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded p-3 min-w-[300px] z-50">
                          <div className="mb-2 text-sm font-semibold text-gray-200">Corrigir data em massa</div>
                          <form onSubmit={handleBulkDateCorrection} className="space-y-3">
                            <input
                              autoFocus
                              type="datetime-local"
                              value={correctedDate}
                              onChange={(e) => setCorrectedDate(e.target.value)}
                              className="w-full px-2 py-1 text-sm bg-gray-700 border border-gray-600 rounded text-white"
                            />
                            <label className="flex items-center gap-2 text-sm text-gray-300">
                              <input
                                type="checkbox"
                                checked={writeMetadata}
                                onChange={(e) => setWriteMetadata(e.target.checked)}
                                className="rounded border-gray-600 bg-gray-700"
                              />
                              Gravar EXIF quando possível
                            </label>
                            <label className="flex items-center gap-2 text-sm text-gray-300">
                              <input
                                type="checkbox"
                                checked={renameVideos}
                                onChange={(e) => setRenameVideos(e.target.checked)}
                                className="rounded border-gray-600 bg-gray-700"
                              />
                              Renomear vídeos com data correta
                            </label>
                            <div className="text-xs text-gray-500">
                              {selected.size > 0 ? `${selected.size} selecionados` : `${items.length} itens desta página`} serão movidos para a data correta mantendo a pasta.
                            </div>
                            <button
                              type="submit"
                              disabled={moving || !correctedDate}
                              className="w-full flex items-center justify-center gap-2 px-2 py-1 bg-amber-500 hover:bg-amber-600 rounded text-sm disabled:opacity-50"
                            >
                              <Clock size={14} />
                              {moving ? 'Aplicando...' : 'Aplicar e mover'}
                            </button>
                          </form>
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => { setSelectMode(false); setSelected(new Set()); setShowAlbumPicker(false); setShowFolderCreator(false); setShowDateCorrection(false) }}
                      disabled={moving}
                      className="px-3 py-1 bg-gray-700 rounded text-sm"
                    >
                      Cancelar
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => setSelectMode(true)}
                      className="flex items-center gap-1 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-colors"
                    >
                      <CheckSquare size={16} />
                      Selecionar
                    </button>
                    <button
                      onClick={startSlideshow}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm transition-colors"
                    >
                      <Play size={16} />
                      Slideshow
                    </button>
                    <div className="flex items-center gap-1 bg-gray-700 rounded-lg p-0.5">
                      {[['small', 'P'], ['medium', 'M'], ['large', 'G']].map(([size, label]) => (
                        <button
                          key={size}
                          onClick={() => { setThumbSize(size); localStorage.setItem('gallery_thumb_size', size) }}
                          className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                            thumbSize === size ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
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
                {/* Se não há itens na raiz do mês mas existem subpastas, mostra-as como pastas clicáveis */}
                {(!folder && year && month && items.length === 0 && timeline) ? (
                  (() => {
                    const y = parseInt(year)
                    const m = parseInt(month)
                    const entry = timeline.find(t => t.year === y && t.month === m)
                    if (entry && entry.folders && entry.folders.length > 0) {
                      return (
                        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                          {entry.folders.map(sub => (
                            <button
                              key={sub.name}
                              onClick={() => { setSearchParams({ tab: 'data', year: y, month: m, folder: sub.name }); setPage(1) }}
                              className="flex flex-col items-start gap-2 p-4 bg-gray-800 border border-gray-700 rounded hover:bg-gray-750"
                            >
                              <div className="text-sm text-blue-300 font-semibold">{sub.name}</div>
                              <div className="text-xs text-gray-400">{sub.count} itens</div>
                            </button>
                          ))}
                        </div>
                      )
                    }
                    return <MediaGrid items={items} onSelect={handleSelect} selected={selectMode ? selected : null} onSelectMultiple={handleSelectMultiple} thumbSize={thumbSize} thumbnailVersion={thumbnailVersion} />
                  })()
                ) : (
                  <>
                    <MediaGrid items={items} onSelect={handleSelect} selected={selectMode ? selected : null} onSelectMultiple={handleSelectMultiple} thumbSize={thumbSize} thumbnailVersion={thumbnailVersion} />
                    {total > perPage && (
                      <div className="flex items-center justify-center gap-3 p-4">
                        <button
                          disabled={page <= 1}
                          onClick={() => setPage(p => p - 1)}
                          className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
                        >
                          Anterior
                        </button>
                        <span className="px-3 py-1 text-sm text-gray-400">
                          Página {page} de {Math.ceil(total / perPage)}
                        </span>
                        <button
                          disabled={page >= Math.ceil(total / perPage)}
                          onClick={() => setPage(p => p + 1)}
                          className="px-3 py-1 bg-gray-700 rounded disabled:opacity-50 text-sm"
                        >
                          Próxima
                        </button>
                        <select
                          value={perPage}
                          onChange={e => { const v = parseInt(e.target.value); setPerPage(v); localStorage.setItem('gallery_per_page', v); setPage(1) }}
                          className="px-2 py-1 bg-gray-700 rounded text-sm text-gray-300 border border-gray-600"
                        >
                          <option value={30}>30/pág</option>
                          <option value={60}>60/pág</option>
                          <option value={120}>120/pág</option>
                          <option value={200}>200/pág</option>
                        </select>
                      </div>
                    )}
                  </>
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
