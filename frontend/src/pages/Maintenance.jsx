import { useState, useEffect, useRef } from 'react'
import { AlertTriangle, RotateCcw, Zap, Trash2, Database, Activity, ChevronDown, ChevronUp, X, Cloud } from 'lucide-react'
import { startSync, startScan, startAiProcessing, startFaceDetection, startFullPipeline, startPurgeMissing, startRcloneDownload, getRcloneLog, databaseAudit, getJobs, startThumbnailWarmup, deleteJob, deleteAllJobs, resumeInterruptedJobs, resumeJob, rebootServer, restartApp, updateAndRestart, backfillDimensions } from '../api'

export default function Maintenance() {
  const [audit, setAudit] = useState(null)
  const [loading, setLoading] = useState(true)
  const [executing, setExecuting] = useState(null)
  const [jobs, setJobs] = useState([])
  const [expanded, setExpanded] = useState(true)
  const [message, setMessage] = useState(null)
  const [resumingJobId, setResumingJobId] = useState(null)
  const [rcloneLog, setRcloneLog] = useState([])
  const rcloneLogRef = useRef(null)

  useEffect(() => {
    // Mantém o log rolado para a última linha conforme chegam novas.
    if (rcloneLogRef.current) {
      rcloneLogRef.current.scrollTop = rcloneLogRef.current.scrollHeight
    }
  }, [rcloneLog])

  useEffect(() => {
    loadAudit()
    loadJobs()
    loadRcloneLog()
  }, [])

  async function loadRcloneLog() {
    try {
      const res = await getRcloneLog()
      setRcloneLog(res.data.lines || [])
    } catch (err) {
      // silencioso: rclone pode estar desativado
    }
  }

  async function loadAudit() {
    try {
      const res = await databaseAudit()
      setAudit(res.data)
      setLoading(false)
    } catch (err) {
      console.error(err)
      setLoading(false)
      setMessage({ type: 'error', text: 'Erro ao carregar diagnóstico' })
    }
  }

  async function loadJobs() {
    try {
      const res = await getJobs({ limit: 10 })
      setJobs(res.data)
    } catch (err) {
      console.error(err)
    }
  }

  async function handleAction(action, name) {
    setExecuting(action)
    setMessage(null)
    try {
      if (action === 'sync') await startSync()
      else if (action === 'scan') await startScan()
      else if (action === 'ai') await startAiProcessing()
      else if (action === 'faces') await startFaceDetection()
      else if (action === 'full') await startFullPipeline()
      else if (action === 'purge') await startPurgeMissing()
      else if (action === 'rclone') await startRcloneDownload()
      else if (action === 'reboot') {
        await rebootServer()
        setMessage({ type: 'success', text: 'Reinicialização iniciada. O servidor ficará offline em instantes.' })
      }
      else if (action === 'restart_app') {
        await restartApp()
        setMessage({ type: 'success', text: 'Reiniciando backend + Caddy. Aguarde ~15 segundos e recarregue a página.' })
      }
      else if (action === 'update_and_restart') {
        await updateAndRestart()
        setMessage({ type: 'success', text: 'Atualização iniciada: git pull + APK + restart. Aguarde ~2 minutos e recarregue a página.' })
      }
      else if (action === 'warmup_cache') {
        await startThumbnailWarmup()
        setMessage({ type: 'success', text: 'Cache de thumbnails iniciado em segundo plano.' })
        loadJobs()
      }
      else if (action === 'backfill_dimensions') {
        const res = await backfillDimensions()
        setMessage({ type: 'success', text: res.data.message })
      }
      else if (action === 'clear_jobs') {
        await deleteAllJobs()
        setMessage({ type: 'success', text: 'Histórico de jobs limpo com sucesso.' })
        loadJobs()
      }
      else if (action === 'resume_interrupted') {
        const res = await resumeInterruptedJobs()
        if (res.data.count > 0) {
          setMessage({ type: 'success', text: `Retomando ${res.data.count} job(s) interrompido(s)` })
          loadJobs()
        } else {
          setMessage({ type: 'success', text: 'Nenhum job interrompido para retomar' })
        }
      }
      else {
        setMessage({ type: 'success', text: `${name} iniciado em background` })
        loadJobs()
      }
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || `Erro ao iniciar ${name}` })
    }
    setExecuting(null)
  }

  async function handleDeleteJob(jobId) {
    try {
      await deleteJob(jobId)
      setMessage({ type: 'success', text: 'Job removido do histórico' })
      loadJobs()
    } catch (err) {
      setMessage({ type: 'error', text: 'Erro ao remover job' })
    }
  }

  async function handleResumeJob(jobId) {
    setResumingJobId(jobId)
    try {
      await resumeJob(jobId)
      setMessage({ type: 'success', text: 'Job agendado para retomada' })
      loadJobs()
    } catch (err) {
      setMessage({ type: 'error', text: 'Erro ao retomar job' })
    }
    setResumingJobId(null)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    )
  }

  const getHealthColor = () => {
    if (!audit) return 'gray'
    const missing = audit.missing || 0
    const orphan = audit.orphan_faces || 0
    if (missing > 100 || orphan > 1000) return 'red'
    if (missing > 10 || orphan > 100) return 'yellow'
    return 'green'
  }

  const healthColor = getHealthColor()
  const healthClass = {
    green: 'bg-green-50 border-green-200 text-green-700',
    yellow: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    red: 'bg-red-50 border-red-200 text-red-700',
    gray: 'bg-gray-50 border-gray-200 text-gray-700'
  }[healthColor]

  const jobLabels = {
    scan_organize: 'Scan / Organização',
    ai_process: 'Processamento IA',
    face_detect: 'Detecção Facial',
    sync: 'Sync',
    purge_missing: 'Limpar Missing',
    thumbnail_warmup: 'Warmup de Thumbnails',
    rclone_download: 'Download OneDrive (rclone)',
  }

  const maintenanceActions = [
    {
      action: 'sync',
      icon: <RotateCcw className="w-4 h-4" />,
      label: 'Sincronizar',
      description: 'Detecta arquivos deletados/movidos',
      name: 'Sync',
    },
    {
      action: 'scan',
      icon: <Zap className="w-4 h-4" />,
      label: 'Escanear',
      description: 'Encontra e indexa novos arquivos',
      name: 'Scan',
    },
    {
      action: 'rclone',
      icon: <Cloud className="w-4 h-4" />,
      label: 'Baixar do OneDrive',
      description: 'Baixa remotes via rclone para o source',
      name: 'Download rclone',
    },
    {
      action: 'ai',
      icon: <Database className="w-4 h-4" />,
      label: 'Descrever (IA)',
      description: 'Processa imagens com Azure OpenAI',
      name: 'IA processing',
    },
    {
      action: 'faces',
      icon: <AlertTriangle className="w-4 h-4" />,
      label: 'Detectar Rostos',
      description: 'Identifica e agrupa faces',
      name: 'Face detection',
    },
    {
      action: 'purge',
      icon: <Trash2 className="w-4 h-4" />,
      label: 'Limpar Missing',
      description: 'Remove arquivos marcados como deletados',
      name: 'Purge missing',
      destructive: true,
      confirm: true,
    },
    {
      action: 'full',
      icon: <Zap className="w-4 h-4" />,
      label: 'Pipeline Completo',
      description: 'Executa: Sync → Scan → IA → Faces',
      name: 'Full pipeline',
    },
    {
      action: 'warmup_cache',
      icon: <Database className="w-4 h-4" />,
      label: 'Cache de Thumbnails',
      description: 'Gera TODAS as thumbnails em paralelo (rápido)',
      name: 'Thumbnail cache warmup',
    },
    {
      action: 'backfill_dimensions',
      icon: <Activity className="w-4 h-4" />,
      label: 'Corrigir Dimensões de Vídeo',
      description: 'Preenche largura/altura/duração de vídeos com dados faltando (necessário para badge 8K/4K/FHD/HD)',
      name: 'Backfill video dimensions',
    },
    {
      action: 'resume_interrupted',
      icon: <RotateCcw className="w-4 h-4" />,
      label: 'Retomar Interrompidos',
      description: 'Continua jobs que foram interrompidos',
      name: 'Resume interrupted',
    },
    {
      action: 'update_and_restart',
      icon: <RotateCcw className="w-4 h-4" />,
      label: 'Atualizar + Reiniciar',
      description: 'git pull → baixa APK do GitHub Actions → reinicia backend',
      name: 'Update and restart',
      destructive: true,
      confirm: true,
      confirmMessage: 'Isso vai fazer git pull, baixar o APK mais recente e reiniciar o backend. Continuar?',
    },
    {
      action: 'restart_app',
      icon: <RotateCcw className="w-4 h-4" />,
      label: 'Reiniciar Aplicação',
      description: 'Mata e reinicia backend + Caddy (sem reboot do PC)',
      name: 'Restart app',
      destructive: true,
      confirm: true,
      confirmMessage: 'Tem certeza? Backend e Caddy serão reiniciados. A página ficará offline por ~15 segundos.',
    },
    {
      action: 'reboot',
      icon: <AlertTriangle className="w-4 h-4" />,
      label: 'Reiniciar PC',
      description: 'Força reinicialização imediata do servidor',
      name: 'Reboot',
      destructive: true,
      confirm: true,
      confirmMessage: 'Tem certeza? O servidor será reiniciado imediatamente (shutdown -r -t 0).',
    },
    {
      action: 'clear_jobs',
      icon: <Trash2 className="w-4 h-4" />,
      label: 'Limpar histórico de jobs',
      description: 'Remove jobs anteriores do histórico do backend',
      name: 'Clear jobs',
      destructive: true,
      confirm: true,
      confirmMessage: 'Apagar o histórico de jobs concluídos/erro? Jobs em execuão não serão removidos.',
      allowWhileRunning: true,
    },
  ]

  const runningJobs = jobs.filter((job) => job.status === 'running')
  const hasRunningJobs = runningJobs.length > 0

  const formatJobDate = (isoDate) => {
    if (!isoDate) return null
    return new Date(isoDate).toLocaleString()
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 p-6">
      <h1 className="text-3xl font-bold flex items-center gap-2">
        <Database className="w-8 h-8" />
        Manutenção e Diagnóstico
      </h1>

      {message && (
        <div className={`p-4 rounded-lg text-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {message.text}
        </div>
      )}

      {/* Status Geral */}
      {audit && (
        <div className={`border rounded-xl p-6 space-y-4 ${healthClass}`}>
          <div className="flex items-center gap-3">
            <Activity className="w-6 h-6" />
            <div>
              <h2 className="text-lg font-semibold">Status do Banco de Dados</h2>
              <p className="text-sm opacity-75">Última auditoria</p>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="opacity-75">Total no banco</p>
              <p className="text-2xl font-bold">{audit.total_media?.toLocaleString()}</p>
            </div>
            <div>
              <p className="opacity-75">✅ Visíveis</p>
              <p className="text-2xl font-bold text-green-600">{audit.visible_count?.toLocaleString()}</p>
            </div>
            <div>
              <p className="opacity-75">Duplicatas</p>
              <p className="text-2xl font-bold text-blue-600">{audit.duplicates?.toLocaleString()}</p>
            </div>
            <div>
              <p className="opacity-75">⚠️ Missing</p>
              <p className="text-2xl font-bold text-red-600">{audit.missing?.toLocaleString()}</p>
            </div>
          </div>

          <div className="bg-white bg-opacity-30 rounded-lg p-3 space-y-2 text-sm">
            <p><strong>Não organizados:</strong> {audit.organized || 0} organizados, {audit.total_media - audit.organized || 0} pendentes</p>
            <p><strong>Rostos órfãos:</strong> {audit.orphan_faces || 0} (sem mídia vinculada)</p>
          </div>
        </div>
      )}

      {/* Ações Rápidas */}
      <div className="bg-white rounded-xl shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Zap className="w-5 h-5" /> Ações Rápidas
        </h2>
        <p className="text-sm text-gray-600">Execute operações de manutenção necessárias</p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {maintenanceActions.map((item) => (
            <ActionButton
              key={item.action}
              icon={item.icon}
              label={item.label}
              description={item.description}
              action={item.action}
              executing={executing}
              onClick={() => {
                if (item.confirm && !window.confirm(item.confirmMessage || `Remover ${audit?.missing || 0} arquivos missing do banco?`)) {
                  return
                }
                handleAction(item.action, item.name)
              }}
              destructive={item.destructive}
              disabled={hasRunningJobs && !item.allowWhileRunning}
            />
          ))}
        </div>
        {hasRunningJobs && (
          <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-900 mt-4">
            <strong>{runningJobs.length} job(s) em execução:</strong> {runningJobs.map((job) => jobLabels[job.job_type] || job.job_type).join(', ')}. Aguarde a conclusão para iniciar outra ação.
          </div>
        )}
      </div>

      {/* Jobs em Execução */}
      <div className="bg-white rounded-xl shadow p-6 space-y-4">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between hover:bg-gray-50 p-3 rounded-lg"
        >
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Activity className="w-5 h-5" /> Histórico de Jobs
          </h2>
          {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>

        {expanded && (
          <div className="space-y-2">
            {jobs.length === 0 ? (
              <div className="border rounded-lg p-4 bg-gray-50 text-sm text-gray-600">
                Nenhum job registrado ainda. Execute uma ação para que apareça no histórico.
              </div>
            ) : (
              jobs.map((job) => (
                <div key={job.id} className="border rounded-lg p-3 bg-white text-gray-900">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <p className="font-medium text-sm text-gray-900">{jobLabels[job.job_type] || job.job_type}</p>
                      <p className="text-xs text-gray-500">
                        {job.status} · {formatJobDate(job.started_at || job.created_at)}
                        {job.completed_at ? ` · finalizado ${formatJobDate(job.completed_at)}` : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <p className="text-xs text-gray-500">
                        {job.total_items > 0 ? `${Math.round(job.progress || 0)}%` : job.status === 'running' ? 'Em execução' : job.status === 'completed' ? 'Concluído' : 'Aguardando'}
                      </p>
                      {job.status === 'interrupted' && (
                        <button
                          onClick={() => handleResumeJob(job.id)}
                          disabled={resumingJobId === job.id}
                          className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded hover:bg-yellow-200 disabled:opacity-50"
                          title="Retomar este job"
                        >
                          {resumingJobId === job.id ? 'Retomando...' : 'Retomar'}
                        </button>
                      )}
                      {job.status !== 'running' && (
                        <button
                          onClick={() => handleDeleteJob(job.id)}
                          className="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200"
                          title="Remover do histórico"
                        >
                          Excluir
                        </button>
                      )}
                    </div>
                  </div>
                  {job.total_items > 0 ? (
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full transition-all ${
                          job.status === 'completed' ? 'bg-green-500' :
                          job.status === 'failed' ? 'bg-red-500' :
                          'bg-blue-500'
                        }`}
                        style={{ width: `${Math.min(100, Math.round(job.progress || 0))}%` }}
                      ></div>
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500">Progresso não disponível para este tipo de job.</p>
                  )}
                  {job.error_message && (
                    <p className="text-xs text-red-600 mt-2">{job.error_message}</p>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Log do rclone (OneDrive) - antes das Recomendações */}
      {rcloneLog.length > 0 && (
        <div className="bg-white rounded-xl shadow p-6 space-y-3">
          <h2 className="text-lg font-semibold flex items-center gap-2 text-gray-900">
            <Cloud className="w-5 h-5" /> Log do Download (OneDrive)
          </h2>
          <pre
            ref={rcloneLogRef}
            className="bg-gray-900 text-green-300 text-xs rounded-lg p-4 h-40 overflow-auto whitespace-pre-wrap font-mono"
          >
            {rcloneLog.join('\n')}
          </pre>
        </div>
      )}

      {/* Recomendações */}
      {audit && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-6 space-y-3">
          <h2 className="font-semibold text-blue-900 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" /> Recomendações
          </h2>
          <ul className="text-sm text-blue-800 space-y-2">
            {(audit.missing || 0) > 0 && (
              <li>✓ {audit.missing} arquivos missing - clique <strong>Limpar Missing</strong> para remover do banco</li>
            )}
            {(audit.orphan_faces || 0) > 100 && (
              <li>✓ {audit.orphan_faces} rostos órfãos - execute <strong>Pipeline Completo</strong></li>
            )}
            {(audit.total_media - audit.organized) > 1000 && (
              <li>✓ {audit.total_media - audit.organized} arquivos não organizados - execute <strong>Escanear</strong></li>
            )}
            {(audit.duplicates || 0) > 5000 && (
              <li>✓ {audit.duplicates} duplicatas no banco - isso é normal se tiver cópias</li>
            )}
            {(audit.missing || 0) === 0 && (audit.orphan_faces || 0) < 100 && (
              <li>✓ Banco de dados está saudável!</li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}

function ActionButton({ icon, label, description, action, executing, onClick, destructive = false, disabled = false }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || (executing !== null && executing !== action)}
      className={`p-4 rounded-lg text-left transition-all ${
        destructive
          ? 'bg-red-50 border-2 border-red-200 hover:bg-red-100 disabled:opacity-50'
          : 'bg-gray-50 border-2 border-gray-200 hover:bg-blue-50 hover:border-blue-300 disabled:opacity-50'
      }`}
    >
      <div className="flex items-center gap-3">
        <div className={destructive ? 'text-red-600' : 'text-blue-600'}>
          {executing === action ? (
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-current"></div>
          ) : (
            icon
          )}
        </div>
        <div>
          <p className="font-medium text-sm text-gray-900">{label}</p>
          <p className="text-xs text-gray-600">{description}</p>
        </div>
      </div>
    </button>
  )
}
