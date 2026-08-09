import { useState, useEffect, useRef, useCallback } from 'react'
import { Terminal, RefreshCw, Trash2, ChevronDown } from 'lucide-react'
import { getWorkerLogs, getWorkerLog, getLogsStreamUrl } from '../api'

const LEVEL_COLOR = {
  ERROR:    'text-red-400',
  WARNING:  'text-yellow-400',
  WARN:     'text-yellow-400',
  INFO:     'text-green-400',
  DEBUG:    'text-gray-500',
}

function levelOf(line) {
  if (line.includes('[ERROR]'))   return 'ERROR'
  if (line.includes('[WARNING]') || line.includes('[WARN]')) return 'WARNING'
  if (line.includes('[INFO]'))    return 'INFO'
  if (line.includes('[DEBUG]'))   return 'DEBUG'
  return 'INFO'
}

function LogLine({ line }) {
  const level = levelOf(line)
  return (
    <div className={`font-mono text-xs leading-5 whitespace-pre-wrap break-all ${LEVEL_COLOR[level] ?? 'text-gray-300'}`}>
      {line}
    </div>
  )
}

// ── Aba Backend (SSE) ─────────────────────────────────────────────────────────
function BackendLogs() {
  const [lines, setLines] = useState([])
  const [filter, setFilter] = useState('ALL')
  const [paused, setPaused] = useState(false)
  const bottomRef = useRef(null)
  const esRef = useRef(null)
  const pausedRef = useRef(false)
  pausedRef.current = paused

  useEffect(() => {
    const url = getLogsStreamUrl()
    const es = new EventSource(url)
    esRef.current = es

    es.onmessage = (e) => {
      if (pausedRef.current) return
      setLines((prev) => {
        const next = [...prev, e.data]
        return next.length > 600 ? next.slice(-600) : next
      })
    }
    es.onerror = () => {
      // reconecta automaticamente pelo browser
    }
    return () => es.close()
  }, [])

  useEffect(() => {
    if (!paused) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, paused])

  const filtered = filter === 'ALL' ? lines : lines.filter((l) => levelOf(l) === filter)

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center gap-2 flex-wrap">
        {['ALL', 'INFO', 'WARNING', 'ERROR'].map((lv) => (
          <button
            key={lv}
            onClick={() => setFilter(lv)}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
              filter === lv ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            {lv}
          </button>
        ))}
        <button
          onClick={() => setPaused((p) => !p)}
          className={`ml-auto px-3 py-1 rounded text-xs font-medium flex items-center gap-1 transition-colors ${
            paused ? 'bg-yellow-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          {paused ? '▶ Retomar' : '⏸ Pausar'}
        </button>
        <button
          onClick={() => setLines([])}
          className="px-3 py-1 rounded text-xs font-medium bg-gray-700 text-gray-300 hover:bg-red-700 flex items-center gap-1"
        >
          <Trash2 size={12} /> Limpar
        </button>
      </div>

      <div className="flex-1 overflow-y-auto bg-gray-950 rounded-lg p-3 border border-gray-700 min-h-0">
        {filtered.length === 0 && (
          <p className="text-gray-500 text-xs italic">Aguardando logs…</p>
        )}
        {filtered.map((line, i) => <LogLine key={i} line={line} />)}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Aba Workers (arquivos de log do slideshow) ────────────────────────────────
function WorkerLogs() {
  const [files, setFiles] = useState([])
  const [selected, setSelected] = useState(null)
  const [lines, setLines] = useState([])
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  const loadFiles = useCallback(async () => {
    try {
      const r = await getWorkerLogs()
      setFiles(r.data.files || [])
    } catch (_) {}
  }, [])

  useEffect(() => { loadFiles() }, [loadFiles])

  useEffect(() => {
    if (!selected) return
    setLoading(true)
    getWorkerLog(selected, 500)
      .then((r) => { setLines(r.data.lines || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [selected])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  function fmt(mtime) {
    return new Date(mtime * 1000).toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    })
  }

  return (
    <div className="flex gap-3 h-full min-h-0">
      {/* Lista de arquivos */}
      <div className="w-56 flex-shrink-0 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400 font-medium">Arquivos</span>
          <button onClick={loadFiles} className="text-gray-500 hover:text-white p-1 rounded">
            <RefreshCw size={13} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto bg-gray-950 rounded-lg border border-gray-700 p-1">
          {files.length === 0 && <p className="text-gray-500 text-xs p-2 italic">Nenhum log encontrado</p>}
          {files.map((f) => (
            <button
              key={f.name}
              onClick={() => setSelected(f.name)}
              className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors mb-0.5 ${
                selected === f.name
                  ? 'bg-blue-600/30 text-blue-300'
                  : 'text-gray-300 hover:bg-gray-800'
              }`}
            >
              <div className="font-mono truncate">{f.name}</div>
              <div className="text-gray-500 text-[10px]">{fmt(f.mtime)}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Conteúdo do log */}
      <div className="flex-1 flex flex-col min-w-0">
        {selected && (
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs text-gray-400 font-mono truncate">{selected}</span>
            <button
              onClick={() => getWorkerLog(selected, 500).then((r) => setLines(r.data.lines || []))}
              className="ml-auto text-gray-500 hover:text-white p-1 rounded flex-shrink-0"
            >
              <RefreshCw size={13} />
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto bg-gray-950 rounded-lg p-3 border border-gray-700 min-h-0">
          {!selected && <p className="text-gray-500 text-xs italic">Selecione um arquivo à esquerda</p>}
          {loading && <p className="text-gray-500 text-xs italic">Carregando…</p>}
          {!loading && lines.map((line, i) => <LogLine key={i} line={line} />)}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function Logs() {
  const [tab, setTab] = useState('backend')

  return (
    <div className="flex flex-col h-full p-4 gap-4 min-h-0">
      <div className="flex items-center gap-3">
        <Terminal size={20} className="text-green-400" />
        <h1 className="text-xl font-bold text-white">Logs</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-700">
        {[
          { key: 'backend', label: '⚙️ Backend' },
          { key: 'workers', label: '🎬 Workers (Slideshow)' },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === key
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0">
        {tab === 'backend' ? <BackendLogs /> : <WorkerLogs />}
      </div>
    </div>
  )
}
