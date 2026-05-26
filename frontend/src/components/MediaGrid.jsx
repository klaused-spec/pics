import { useRef, useState, useCallback, useEffect } from 'react'
import { getThumbnailUrl } from '../api'
import { Check } from 'lucide-react'

function MediaGrid({ items, onSelect, selected, onSelectMultiple }) {
  const gridRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState(null)
  const [dragRect, setDragRect] = useState(null)
  const dragDidMove = useRef(false)
  const itemRefs = useRef({})

  // Calcula quais itens estão dentro do retângulo de seleção
  const getItemsInRect = useCallback((rect) => {
    if (!rect || !gridRef.current) return []
    const hits = []

    for (const [id, el] of Object.entries(itemRefs.current)) {
      if (!el) continue
      const r = el.getBoundingClientRect()
      if (
        r.left < rect.x + rect.w &&
        r.right > rect.x &&
        r.top < rect.y + rect.h &&
        r.bottom > rect.y
      ) {
        hits.push(parseInt(id))
      }
    }
    return hits
  }, [])

  function handleMouseDown(e) {
    if (!selected || e.button !== 0) return
    // Ignora botões e inputs interativos
    if (e.target.closest('button, input, a')) return
    e.preventDefault()
    setIsDragging(true)
    dragDidMove.current = false
    setDragStart({ x: e.clientX, y: e.clientY })
    setDragRect(null)
  }

  function handleMouseMove(e) {
    if (!isDragging || !dragStart) return
    e.preventDefault()
    const dx = Math.abs(e.clientX - dragStart.x)
    const dy = Math.abs(e.clientY - dragStart.y)
    // Só começa o arrasto visual após mover pelo menos 8px
    if (dx < 8 && dy < 8) return
    dragDidMove.current = true
    const rect = {
      x: Math.min(dragStart.x, e.clientX),
      y: Math.min(dragStart.y, e.clientY),
      w: Math.abs(e.clientX - dragStart.x),
      h: Math.abs(e.clientY - dragStart.y),
    }
    setDragRect(rect)
  }

  function handleMouseUp(e) {
    if (!isDragging) return
    setIsDragging(false)

    if (dragDidMove.current && dragRect && dragRect.w > 10 && dragRect.h > 10) {
      // Arrasto: seleciona todos os itens na área de uma vez
      const hitIds = getItemsInRect(dragRect)
      if (hitIds.length > 0 && onSelectMultiple) {
        onSelectMultiple(hitIds)
      }
    } else if (!dragDidMove.current) {
      // Clique simples: busca o item sob o cursor
      const el = e.target.closest('[data-media-item]')
      if (el) {
        const id = parseInt(el.dataset.mediaId)
        const item = items.find(i => i.id === id)
        if (item) onSelect?.(item)
      }
    }

    setDragStart(null)
    setDragRect(null)
    dragDidMove.current = false
  }

  // Cancela drag se o mouse sair da janela
  useEffect(() => {
    function handleGlobalUp() {
      if (isDragging) {
        setIsDragging(false)
        setDragStart(null)
        setDragRect(null)
        dragDidMove.current = false
      }
    }
    window.addEventListener('mouseup', handleGlobalUp)
    return () => window.removeEventListener('mouseup', handleGlobalUp)
  }, [isDragging])

  if (!items || items.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        Nenhuma mídia encontrada.
      </div>
    )
  }

  return (
    <div
      ref={gridRef}
      className="relative grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2 p-4 select-none"
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
    >
      {/* Retângulo de seleção visual */}
      {isDragging && dragRect && dragRect.w > 5 && (
        <div
          className="fixed border-2 border-blue-400 bg-blue-400/20 rounded pointer-events-none z-50"
          style={{ left: dragRect.x, top: dragRect.y, width: dragRect.w, height: dragRect.h }}
        />
      )}

      {items.map((item) => {
        const isSelected = selected && selected.has(item.id)
        return (
        <div
          key={item.id}
          data-media-item
          data-media-id={item.id}
          ref={(el) => { itemRefs.current[item.id] = el }}
          className={`relative group cursor-pointer aspect-square overflow-hidden rounded-lg bg-gray-800 ${
            isSelected ? 'ring-2 ring-blue-500' : ''
          }`}
          onClick={(e) => {
            // Em modo seleção, o handleMouseUp já cuida do clique
            if (selected) return
            onSelect?.(item)
          }}
        >
          <img
            src={getThumbnailUrl(item.id)}
            alt={item.ai_description || item.filename}
            className="w-full h-full object-cover transition-transform group-hover:scale-105"
            loading="lazy"
          />

          {/* Checkbox de seleção */}
          {selected && (
            <div className={`absolute top-2 left-2 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
              isSelected ? 'bg-blue-500 border-blue-500' : 'border-white/70 bg-black/30'
            }`}>
              {isSelected && <Check size={12} className="text-white" />}
            </div>
          )}

          {/* Overlay com informações */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
            <div className="absolute bottom-0 left-0 right-0 p-2">
              <p className="text-xs text-white truncate">{item.filename}</p>
              {item.date_taken && (
                <p className="text-xs text-gray-300">
                  {new Date(item.date_taken).toLocaleDateString('pt-BR')}
                </p>
              )}
            </div>
          </div>

          {/* Badge de vídeo */}
          {item.media_type === 'video' && (
            <div className="absolute top-2 right-2 bg-black/60 rounded-full p-1">
              <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            </div>
          )}

          {/* Badge de transcodificação pendente */}
          {item.needs_transcode && !item.is_transcoded && (
            <div className="absolute bottom-2 right-2 bg-yellow-600/90 rounded px-1.5 py-0.5">
              <p className="text-xs text-white font-medium">Converter</p>
            </div>
          )}

          {/* Badge de localização IA */}
          {item.ai_location && item.ai_location !== 'desconhecido' && (
            <div className="absolute top-2 left-2 bg-blue-600/80 rounded px-1.5 py-0.5">
              <p className="text-xs text-white truncate max-w-[100px]">{item.ai_location}</p>
            </div>
          )}
        </div>
        )
      })}
    </div>
  )
}

export default MediaGrid
