import { useState, useEffect, useRef } from 'react'
import { Settings as SettingsIcon, Database, FolderOpen, Download, Upload, Save, AlertTriangle, Trash2, Plus, X } from 'lucide-react'
import { getSettings, updateSettings, backupDatabase, restoreDatabase } from '../api'

export default function Settings() {
  const [paths, setPaths] = useState({ source_dir: '', organized_dir: '', trash_dir: '', database_path: '', organization_pattern: 'year/month', library_folders: [] })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [newFolder, setNewFolder] = useState('')
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
        trash_dir: paths.trash_dir,
        organization_pattern: paths.organization_pattern,
        library_folders: paths.library_folders,
      })
      setMessage({ type: 'success', text: 'Configurações salvas!' })
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || 'Erro ao salvar' })
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
      a.download = `pics_backup_${new Date().toISOString().slice(0, 10)}.db`
      a.click()
      window.URL.revokeObjectURL(url)
      setMessage({ type: 'success', text: 'Backup baixado!' })
    } catch {
      setMessage({ type: 'error', text: 'Erro ao fazer backup' })
    }
  }

  const handleRestore = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    if (!confirm('ATENÇÃO: Isso vai substituir o banco atual. O banco atual será salvo como backup. Continuar?')) return
    try {
      await restoreDatabase(file)
      setMessage({ type: 'success', text: 'Banco restaurado! Reinicie o backend.' })
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Erro ao restaurar' })
    }
    e.target.value = ''
  }

  const handleReset = async () => {
    if (!confirm('⚠️ ATENÇÃO: Isso vai ZERAR todo o banco (faces, AI, albums) e mover os arquivos de volta para o source. Tem certeza?')) return
    if (!confirm('Última chance! Isso é irreversível. Continuar?')) return
    try {
      const res = await fetch('/api/settings/reset', { method: 'POST' })
      const data = await res.json()
      setMessage({ type: 'success', text: data.message })
    } catch {
      setMessage({ type: 'error', text: 'Erro ao resetar' })
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <SettingsIcon className="w-6 h-6" /> Configurações
      </h1>

      {message && (
        <div className={`p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {message.text}
        </div>
      )}

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
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Organizadas (destino principal)</span>
            <input
              type="text"
              value={paths.organized_dir}
              onChange={e => setPaths(p => ({ ...p, organized_dir: e.target.value }))}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-gray-700">Trash (lixeira)</span>
            <input
              type="text"
              value={paths.trash_dir}
              onChange={e => setPaths(p => ({ ...p, trash_dir: e.target.value }))}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </label>
        </div>

        <div className="flex items-center gap-2 pt-2 text-xs text-amber-600">
          <AlertTriangle className="w-4 h-4" />
          <span>Premissa: arquivos NUNCA são deletados. Apenas movidos entre source → organized → trash.</span>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {saving ? 'Salvando...' : 'Salvar'}
        </button>
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
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <button
            onClick={addLibraryFolder}
            className="flex items-center gap-1 px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm"
          >
            <Plus className="w-4 h-4" /> Adicionar
          </button>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {saving ? 'Salvando...' : 'Salvar'}
        </button>
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
          <input ref={fileRef} type="file" accept=".db,.zip" className="hidden" onChange={handleRestore} />
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
        <button
          onClick={handleReset}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
        >
          <Trash2 className="w-4 h-4" /> Resetar Tudo
        </button>
      </section>
    </div>
  )
}
