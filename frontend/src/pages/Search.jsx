import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { searchMedia } from '../api'
import MediaGrid from '../components/MediaGrid'
import { Search as SearchIcon, Play } from 'lucide-react'

function Search() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSearch(e) {
    e.preventDefault()
    if (!query.trim() || query.trim().length < 2) return

    setLoading(true)
    try {
      const res = await searchMedia(query)
      setResults(res.data)
    } catch (err) {
      console.error('Erro na busca:', err)
    }
    setLoading(false)
  }

  function handleSelect(item) {
    navigate(`/media/${item.id}`)
  }

  function startSlideshow() {
    if (results && results.items.length > 0) {
      const ids = results.items.map(i => i.id).join(',')
      window.open(`/slideshow?ids=${ids}`, '_blank')
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Barra de busca */}
      <div className="p-6 border-b border-gray-700">
        <form onSubmit={handleSearch} className="max-w-2xl mx-auto">
          <div className="relative">
            <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" size={20} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar fotos... (ex: praia, aniversário, família no parque)"
              className="w-full pl-12 pr-4 py-3 bg-gray-800 border border-gray-600 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <p className="mt-2 text-xs text-gray-500 text-center">
            Busca por descrição IA, localização e tags. Ex: "passeio na praia", "aniversário", "paisagem com montanha"
          </p>
        </form>
      </div>

      {/* Resultados */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
          </div>
        ) : results ? (
          <div>
            <div className="flex items-center justify-between p-4 border-b border-gray-700/50">
              <p className="text-sm text-gray-400">
                {results.total} resultado{results.total !== 1 ? 's' : ''} para "{results.query}"
              </p>
              {results.items.length > 0 && (
                <button
                  onClick={startSlideshow}
                  className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm"
                >
                  <Play size={14} />
                  Slideshow
                </button>
              )}
            </div>
            <MediaGrid items={results.items} onSelect={handleSelect} />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <SearchIcon size={48} className="mb-4 opacity-30" />
            <p>Digite algo para buscar nas suas fotos</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default Search
