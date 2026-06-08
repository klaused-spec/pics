import { useState, useEffect, useRef } from 'react'
import { Settings as SettingsIcon, Database, FolderOpen, Download, Upload, Save, AlertTriangle, Trash2, Plus, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { getSettings, updateSettings, backupDatabase, restoreDatabase } from '../api'
import api from '../api'

export default function Settings() {
  const navigate = useNavigate()
  const [paths, setPaths] = useState({ source_dir: '', organized_dir: '', database_path: '', organization_pattern: 'year/month', library_folders: [], allow_library_modify: false })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null) // { type, text, section }

  const [newFolder, setNewFolder] = useState('')
  const [restoreConfirm, setRestoreConfirm] = useState(false)
  const [restoreFile, setRestoreFile] = useState(null)
  const [resetConfirm, setResetConfirm] = useState(0) // 0=idle, 1=first confirm, 2=confirmed
  const fileRef = useRef()

  useEffect(() => {
    getSettings().then(r => setPaths(r.data))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      await updateSettings({
        source_dir: paths.source_dir,
        organized_dir: paths.organized_dir,
        organization_pattern: paths.organization_pattern,
        library_folders: paths.library_folders,
        allow_library_modify: paths.allow_library_modify,
      })
      setMessage({ type: 'success', text: 'Configurações salvas!', section: 'paths' })
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || 'Erro ao salvar', section: 'paths' })
    }
    setSaving(false)
  }

  const addLibraryFolder = () => {
    const folder = newFolder.trim()
    if (folder && !paths.library_folders.includes(folder)) {
      setPaths(p => ({ ...p, library_folders: [...p.library_folders, folder] }))
      setNewFolder('')
    }
  }

  const removeLibraryFolder = (index) => {
    setPaths(p => ({ ...p, library_folders: p.library_folders.filter((_, i) => i !== index) }))
  }

  const handleBackup = async () => {
    try {
      const res = await backupDatabase()
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `pics_backup_${new Date().toISOString().slice(0, 10)}.zip`
      a.click()
      window.URL.revokeObjectURL(url)
      setMessage({ type: 'success', text: 'Backup baixado!', section: 'db' })
    } catch {
      setMessage({ type: 'error', text: 'Erro ao fazer backup', section: 'db' })
    }
  }

  const handleFileSelect = (e) => {
    const file = e.target.files[0]
    if (!file) return
    setRestoreFile(file)
    setRestoreConfirm(true)
    e.target.value = ''
  }

  const handleRestoreConfirm = async () => {
    if (!restoreFile) return
    setRestoreConfirm(false)
    try {
      await restoreDatabase(restoreFile)
      setMessage({ type: 'success', text: 'Banco restaurado! Reinicie o backend.', section: 'db' })
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Erro ao restaurar', section: 'db' })
    }
    setRestoreFile(null)
  }

  const handleRestoreCancel = () => {
    setRestoreConfirm(false)
    setRestoreFile(null)
  }

  const handleResetClick = () => {
    if (resetConfirm === 0) {
      setResetConfirm(1)
    } else if (resetConfirm === 1) {
      setResetConfirm(2)
      handleResetExecute()
    }
  }

  const handleResetExecute = async () => {
    try {
      const res = await api.post('/settings/reset')
      setMessage({ type: 'success', text: res.data.message, section: 'reset' })
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Erro ao resetar', section: 'reset' })
    }
    setResetConfirm(0)
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <SettingsIcon className="w-6 h-6" /> Configurações
      </h1>

      {/* Diretórios */}
      <section className="bg-white rounded-xl shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <FolderOpen className="w-5 h-5" /> Diretórios
        </h2>

        <div className="space-y-3">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Source (origem das fotos)</span>
            <input
              type="text"
              value={paths.source_dir}
              onChange={e => setPaths(p => ({ ...p, source_dir: e.target.value }))}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Organizadas (destino principal)</span>
            <input
              type="text"
              value={paths.organized_dir}
              onChange={e => setPaths(p => ({ ...p, organized_dir: e.target.value }))}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </label>
        </div>

        <div className="flex items-center gap-2 pt-2 text-xs text-amber-600">
          <AlertTriangle className="w-4 h-4" />
          <span>Premissa: arquivos NUNCA são deletados. Movidos para .trash dentro de cada pasta.</span>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {saving ? 'Salvando...' : 'Salvar'}
        </button>

        {message?.section === 'paths' && (
          <div className={`p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {message.text}
          </div>
        )}
      </section>

      {/* Padrão de Organização */}
      <section className="bg-white rounded-xl shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <FolderOpen className="w-5 h-5" /> Padrão de Organização
        </h2>

        <div className="space-y-3">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Estrutura de pastas</span>
            <select
              value={paths.organization_pattern}
              onChange={e => setPaths(p => ({ ...p, organization_pattern: e.target.value }))}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="year/month">Hierárquico: YYYY/MM/ (ex: 2021/05/foto.jpg)</option>
              <option value="year_month">Flat: YYYY_MM/ (ex: 2021_05/foto.jpg)</option>
            </select>
          </label>

          <div className="text-xs text-gray-500 bg-gray-50 p-3 rounded-lg">
            <p className="font-medium mb-1">Padrão "Flat" (YYYY_MM):</p>
            <p>Permite pastas manuais com descrição, ex: <code className="bg-gray-200 px-1 rounded">2021_05_aniversario_fulano/</code></p>
            <p className="mt-1">Pastas como <code className="bg-gray-200 px-1 rounded">2021_05/</code> e <code className="bg-gray-200 px-1 rounded">2021_05_aniversario_fulano/</code> coexistem separadas.</p>
          </div>
        </div>
      </section>

      {/* Pastas de Biblioteca */}
      <section className="bg-white rounded-xl shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <FolderOpen className="w-5 h-5" /> Pastas de Biblioteca Adicionais
        </h2>
        <p className="text-sm text-gray-600">
          Pastas extras que o sistema indexa e monitora (além da pasta "Organizadas" principal).
          Cada pasta segue o padrão de organização escolhido.
        </p>

        <div className="space-y-2">
          {paths.library_folders.map((folder, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="text"
                value={folder}
                onChange={e => {
                  const updated = [...paths.library_folders]
                  updated[i] = e.target.value
                  setPaths(p => ({ ...p, library_folders: updated }))
                }}
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <button
                onClick={() => removeLibraryFolder(i)}
                className="p-2 text-red-500 hover:bg-red-50 rounded-lg"
                title="Remover"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <input
            type="text"
            value={newFolder}
            onChange={e => setNewFolder(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addLibraryFolder()}
            placeholder="/mnt/g/fotos/pasta1"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <button
            onClick={addLibraryFolder}
            className="flex items-center gap-1 px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm"
          >
            <Plus className="w-4 h-4" /> Adicionar
          </button>
        </div>

        <label className="flex items-center gap-3 pt-2">
          <input
            type="checkbox"
            checked={paths.allow_library_modify || false}
            onChange={e => setPaths(p => ({ ...p, allow_library_modify: e.target.checked }))}
            className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-sm text-gray-700">Permitir modificar biblioteca (excluir, transcodificar arquivos nas pastas acima)</span>
        </label>

        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {saving ? 'Salvando...' : 'Salvar'}
        </button>

        {message?.section === 'paths' && (
          <div className={`p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {message.text}
          </div>
        )}
      </section>

      {/* Banco de dados */}
      <section className="bg-white rounded-xl shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Database className="w-5 h-5" /> Banco de Dados
        </h2>

        <p className="text-sm text-gray-600">
          Banco: <code className="bg-gray-100 px-1 rounded">{paths.database_path}</code>
        </p>
        <p className="text-xs text-gray-500">
          O banco contém: registros de mídias, faces/pessoas (com embeddings), descrições da IA e cache.
          Faça backup regularmente para não perder esse conhecimento.
        </p>

        <div className="flex flex-col gap-3">
          <div className="flex gap-3">
            <button
              onClick={handleBackup}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
            >
              <Download className="w-4 h-4" /> Backup
            </button>

            <button
              onClick={() => fileRef.current.click()}
              className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700"
            >
              <Upload className="w-4 h-4" /> Restaurar
            </button>
            <input ref={fileRef} type="file" accept=".db,.zip" className="hidden" onChange={handleFileSelect} />
          </div>

          {restoreConfirm && (
            <div className="p-3 bg-amber-50 border border-amber-300 rounded-lg space-y-2">
              <p className="text-sm text-amber-800 font-medium">
                ⚠️ ATENÇÃO: Isso vai substituir o banco atual. O banco atual será salvo como backup.
              </p>
              <p className="text-xs text-amber-700">Arquivo: {restoreFile?.name}</p>
              <div className="flex gap-2">
                <button
                  onClick={handleRestoreConfirm}
                  className="px-3 py-1 bg-amber-600 text-white rounded text-sm hover:bg-amber-700"
                >
                  Confirmar Restauração
                </button>
                <button
                  onClick={handleRestoreCancel}
                  className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300"
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}

          {message?.section === 'db' && (
            <div className={`p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
              {message.text}
            </div>
          )}
        </div>
      </section>

      {/* Reset */}
      <section className="bg-white rounded-xl shadow p-6 space-y-4 border border-red-200">
        <h2 className="text-lg font-semibold flex items-center gap-2 text-red-600">
          <Trash2 className="w-5 h-5" /> Zerar Tudo
        </h2>
        <p className="text-sm text-gray-600">
          Apaga todo o banco (faces, descrições IA, albums, media) e move os arquivos organizados de volta para o source.
          Use antes de reprocessar tudo do zero.
        </p>
        {resetConfirm === 0 && (
          <button
            onClick={handleResetClick}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            <Trash2 className="w-4 h-4" /> Resetar Tudo
          </button>
        )}
        {resetConfirm === 1 && (
          <div className="p-3 bg-red-50 border border-red-300 rounded-lg space-y-2">
            <p className="text-sm text-red-800 font-medium">
              ⚠️ Isso vai ZERAR todo o banco e mover arquivos de volta ao source. Tem certeza?
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleResetClick}
                className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700"
              >
                Sim, Resetar Tudo
              </button>
              <button
                onClick={() => setResetConfirm(0)}
                className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}

        {message?.section === 'reset' && (
          <div className={`p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            {message.text}
          </div>
        )}
      </section>

      {/* Manutenção */}
      <section className="bg-white rounded-xl shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Database className="w-5 h-5" /> Manutenção
        </h2>
        <p className="text-sm text-gray-600">
          Acesse a página de manutenção para diagnosticar problemas e executar operações de sincronização.
        </p>
        <button
          onClick={() => navigate('/maintenance')}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Database className="w-4 h-4" />
          Ir para Manutenção
        </button>
      </section>
    </div>
  )
}
