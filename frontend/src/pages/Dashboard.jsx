import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getStats, getJobs, startScan, startAiProcessing, startFaceDetection, startFullPipeline, startSync } from '../api'
import { Image, Video, Users, Brain, RefreshCw, Play, AlertCircle } from 'lucide-react'

function Dashboard() {
  const [stats, setStats] = useState(null)
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    loadData()
  }, [])

  // Auto-refresh enquanto houver job rodando
  useEffect(() => {
    const hasRunning = jobs.some(j => j.status === 'running')
    if (!hasRunning) return
    const interval = setInterval(loadData, 3000)
    return () => clearInterval(interval)
  }, [jobs])

  async function loadData() {
    try {
      const [statsRes, jobsRes] = await Promise.all([
        getStats(),
        getJobs({ limit: 10 }),
      ])
      setStats(statsRes.data)
      setJobs(jobsRes.data)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  async function handleAction(action) {
    try {
      await action()
      setTimeout(loadData, 1000)
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
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {/* Estatísticas */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard icon={Image} label="Fotos" value={stats.images} color="blue" onClick={() => navigate('/gallery?media_type=image')} />
          <StatCard icon={Video} label="Vídeos" value={stats.videos} color="purple" onClick={() => navigate('/gallery?media_type=video')} />
          <StatCard icon={Users} label="Pessoas" value={stats.persons} color="green" onClick={() => navigate('/persons')} />
          <StatCard icon={Brain} label="IA Processado" value={stats.ai_processed} color="yellow" />
          <StatCard icon={AlertCircle} label="Duplicatas" value={stats.duplicates_found} color="red" onClick={() => navigate('/duplicates')} />
          <StatCard icon={Users} label="Rostos" value={stats.faces_detected} color="cyan" onClick={() => navigate('/persons/review')} />
        </div>
      )}

      {/* Ações */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Ações</h2>
        <div className="flex flex-wrap gap-3">
          <ActionButton
            onClick={() => handleAction(startFullPipeline)}
            icon={Play}
            label="Pipeline Completo"
            description="Scan → Organizar → IA → Faces"
            color="blue"
          />
          <ActionButton
            onClick={() => handleAction(startScan)}
            icon={RefreshCw}
            label="Scan & Organizar"
            description="Busca novos arquivos no OneDrive"
            color="green"
          />
          <ActionButton
            onClick={() => handleAction(() => startAiProcessing(20))}
            icon={Brain}
            label="Processar IA"
            description="Analisa com Azure OpenAI"
            color="yellow"
          />
          <ActionButton
            onClick={() => handleAction(() => startFaceDetection(20))}
            icon={Users}
            label="Detectar Rostos"
            description="Identifica pessoas"
            color="purple"
          />
          <ActionButton
            onClick={() => handleAction(startSync)}
            icon={RefreshCw}
            label="Sincronizar"
            description="Atualiza movidos/apagados"
            color="gray"
          />
        </div>
      </div>

      {/* Jobs recentes */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Processamentos Recentes</h2>
        <div className="bg-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-700/50">
              <tr>
                <th className="px-4 py-2 text-left text-gray-400">Tipo</th>
                <th className="px-4 py-2 text-left text-gray-400">Status</th>
                <th className="px-4 py-2 text-left text-gray-400">Progresso</th>
                <th className="px-4 py-2 text-left text-gray-400">Data</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-t border-gray-700/50">
                  <td className="px-4 py-2">{job.job_type}</td>
                  <td className="px-4 py-2">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      job.status === 'completed' ? 'bg-green-600/30 text-green-400' :
                      job.status === 'running' ? 'bg-blue-600/30 text-blue-400' :
                      job.status === 'failed' ? 'bg-red-600/30 text-red-400' :
                      'bg-gray-600/30 text-gray-400'
                    }`}>
                      {job.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-400">
                    {job.processed_items}/{job.total_items} ({Math.round(job.progress)}%)
                  </td>
                  <td className="px-4 py-2 text-gray-400">
                    {job.created_at ? new Date(job.created_at).toLocaleString('pt-BR') : '-'}
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                    Nenhum processamento realizado ainda
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color, onClick }) {
  const colors = {
    blue: 'bg-blue-600/20 text-blue-400',
    purple: 'bg-purple-600/20 text-purple-400',
    green: 'bg-green-600/20 text-green-400',
    yellow: 'bg-yellow-600/20 text-yellow-400',
    red: 'bg-red-600/20 text-red-400',
    cyan: 'bg-cyan-600/20 text-cyan-400',
  }

  return (
    <div className={`bg-gray-800 rounded-lg p-4 ${onClick ? 'cursor-pointer hover:bg-gray-700 transition-colors' : ''}`} onClick={onClick}>
      <div className={`inline-flex p-2 rounded-lg ${colors[color]} mb-2`}>
        <Icon size={18} />
      </div>
      <p className="text-2xl font-bold">{value?.toLocaleString() || 0}</p>
      <p className="text-sm text-gray-400">{label}</p>
    </div>
  )
}

function ActionButton({ onClick, icon: Icon, label, description, color }) {
  const colors = {
    blue: 'bg-blue-600 hover:bg-blue-700',
    green: 'bg-green-600 hover:bg-green-700',
    yellow: 'bg-yellow-600 hover:bg-yellow-700',
    purple: 'bg-purple-600 hover:bg-purple-700',
  }

  return (
    <button
      onClick={onClick}
      className={`${colors[color]} rounded-lg px-4 py-3 text-left transition-colors`}
    >
      <div className="flex items-center gap-2 mb-1">
        <Icon size={16} />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <p className="text-xs text-white/70">{description}</p>
    </button>
  )
}

export default Dashboard
