import { useEffect, useState } from 'react'
import { Download, RefreshCw, Smartphone } from 'lucide-react'
import { getMobileApks, getMobileApkUrl } from '../api'

const formatBytes = (bytes) => {
  if (!bytes) return '0 MB'
  const mb = bytes / 1024 / 1024
  return `${mb.toFixed(mb >= 100 ? 0 : 1)} MB`
}

const formatDate = (timestamp) => {
  if (!timestamp) return '-'
  return new Date(timestamp * 1000).toLocaleString('pt-BR')
}

function MobileApps() {
  const [apks, setApks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadApks = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await getMobileApks()
      setApks(response.data.items || [])
    } catch (err) {
      setError(err.response?.data?.detail || 'Não foi possível carregar os APKs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadApks()
  }, [])

  const downloadApk = async (apk) => {
    setError('')
    const token = localStorage.getItem('access_token')
    window.location.href = getMobileApkUrl(apk.filename, token)
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-3">
            <Smartphone className="text-blue-400" size={28} />
            Android
          </h2>
          <p className="text-gray-400 mt-1">APKs disponíveis para instalação no celular</p>
        </div>
        <button
          onClick={loadApks}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-60 text-white"
        >
          <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          Atualizar
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 rounded p-4">
          {error}
        </div>
      )}

      <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
        {loading ? (
          <div className="p-8 text-gray-400">Carregando APKs...</div>
        ) : apks.length === 0 ? (
          <div className="p-8 text-gray-400">Nenhum APK encontrado.</div>
        ) : (
          <div className="divide-y divide-gray-700">
            {apks.map((apk) => (
              <div key={apk.filename} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-white font-semibold truncate">{apk.filename}</p>
                  <p className="text-sm text-gray-400 mt-1">
                    {formatBytes(apk.size)} • {formatDate(apk.modified_at)}
                  </p>
                </div>
                <button
                  onClick={() => downloadApk(apk)}
                  className="flex items-center justify-center gap-2 px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white"
                >
                  <Download size={18} />
                  Baixar APK
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default MobileApps
