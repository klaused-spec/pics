import { getThumbnailUrl } from '../api'
import { Check } from 'lucide-react'

function MediaGrid({ items, onSelect, selected }) {
  if (!items || items.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        Nenhuma mídia encontrada.
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2 p-4">
      {items.map((item) => {
        const isSelected = selected && selected.has(item.id)
        return (
        <div
          key={item.id}
          className={`relative group cursor-pointer aspect-square overflow-hidden rounded-lg bg-gray-800 ${
            isSelected ? 'ring-2 ring-blue-500' : ''
          }`}
          onClick={() => onSelect?.(item)}
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
