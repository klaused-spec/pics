import { useRef, useState, useCallback, useEffect } from 'react'
import { getThumbnailUrl } from '../api'
import { Check } from 'lucide-react'

function MediaGrid({ items, onSelect, selected, onSelectMultiple, thumbSize = 'medium', thumbnailVersion = 0 }) {
  const gridRef = useRef(null)
  const [dragRect, setDragRect] = useState(null)
  const dragState = useRef({ active: false, startX: 0, startY: 0, moved: false })
  const itemRefs = useRef({})

  const gridClass = {
    small: 'grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10',
    medium: 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6',
    large: 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-3 xl:grid-cols-4',
  }[thumbSize] || 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6'

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
    if (e.target.closest('button, input, a')) return
    e.preventDefault()
    dragState.current = { active: true, startX: e.clientX, startY: e.clientY, moved: false }
    setDragRect(null)

    function onMove(ev) {
      const { startX, startY } = dragState.current
      const dx = Math.abs(ev.clientX - startX)
      const dy = Math.abs(ev.clientY - startY)
      if (dx < 8 && dy < 8) return
      dragState.current.moved = true
      const rect = {
        x: Math.min(startX, ev.clientX),
        y: Math.min(startY, ev.clientY),
        w: Math.abs(ev.clientX - startX),
        h: Math.abs(ev.clientY - startY),
      }
      setDragRect(rect)
    }

    function onUp(ev) {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)

      const { moved } = dragState.current
      dragState.current.active = false

      if (moved) {
        // Calcula rect final
        const { startX, startY } = dragState.current
        const rect = {
          x: Math.min(startX, ev.clientX),
          y: Math.min(startY, ev.clientY),
          w: Math.abs(ev.clientX - startX),
          h: Math.abs(ev.clientY - startY),
        }
        if (rect.w > 10 && rect.h > 10) {
          const hitIds = getItemsInRect(rect)
          if (hitIds.length > 0 && onSelectMultiple) {
            onSelectMultiple(hitIds)
          }
        }
      } else {
        // Clique simples
        const el = ev.target.closest('[data-media-item]')
        if (el) {
          const id = parseInt(el.dataset.mediaId)
          const item = items.find(i => i.id === id)
          if (item) onSelect?.(item)
        }
      }
      setDragRect(null)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

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
      className={`relative grid ${gridClass} gap-2 p-4 select-none`}
      onMouseDown={handleMouseDown}
    >
      {/* Retângulo de seleção visual */}
      {dragRect && dragRect.w > 5 && (
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
            src={`${getThumbnailUrl(item.id)}&v=${thumbnailVersion}`}
            alt={item.ai_description || item.filename}
            className="w-full h-full object-cover transition-transform group-hover:scale-105"
            loading="lazy"
            draggable={false}
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
