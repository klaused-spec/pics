import { useEffect, useState } from 'react'
import { UserPlus, Trash2, KeyRound, Users as UsersIcon, Loader2 } from 'lucide-react'
import { getUsers, createUser, updateUserPassword, deleteUser } from '../api'

function Users() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [creating, setCreating] = useState(false)

  const currentEmail = (localStorage.getItem('userEmail') || '').toLowerCase()

  const loadUsers = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await getUsers()
      setUsers(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Falha ao carregar usuários')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
  }, [])

  const clearFeedback = () => {
    setError('')
    setNotice('')
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    clearFeedback()
    if (!email.trim() || password.length < 6) {
      setError('Informe um e-mail válido e senha com pelo menos 6 caracteres.')
      return
    }
    setCreating(true)
    try {
      await createUser(email.trim(), password)
      setEmail('')
      setPassword('')
      setNotice('Usuário criado com sucesso.')
      await loadUsers()
    } catch (err) {
      setError(err.response?.data?.detail || 'Falha ao criar usuário')
    } finally {
      setCreating(false)
    }
  }

  const handleResetPassword = async (user) => {
    clearFeedback()
    const newPassword = window.prompt(`Nova senha para ${user.email} (mínimo 6 caracteres):`)
    if (newPassword === null) return
    if (newPassword.length < 6) {
      setError('A senha deve ter pelo menos 6 caracteres.')
      return
    }
    try {
      await updateUserPassword(user.id, newPassword)
      setNotice(`Senha de ${user.email} atualizada.`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Falha ao atualizar senha')
    }
  }

  const handleDelete = async (user) => {
    clearFeedback()
    if (!window.confirm(`Remover o usuário ${user.email}?`)) return
    try {
      await deleteUser(user.id)
      setNotice(`Usuário ${user.email} removido.`)
      await loadUsers()
    } catch (err) {
      setError(err.response?.data?.detail || 'Falha ao remover usuário')
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <UsersIcon className="text-blue-400" size={28} />
        <div>
          <h1 className="text-2xl font-bold text-white">Usuários</h1>
          <p className="text-sm text-gray-400">Crie contas e gerencie senhas de acesso.</p>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}
      {notice && (
        <div className="mb-4 rounded-lg border border-green-500/40 bg-green-500/10 px-4 py-3 text-sm text-green-300">
          {notice}
        </div>
      )}

      <form onSubmit={handleCreate} className="mb-8 rounded-xl border border-gray-700 bg-gray-800 p-5">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
          <UserPlus size={18} className="text-blue-400" />
          Criar novo usuário
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-400">E-mail</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="usuario@email.com"
              autoComplete="off"
              className="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-400">Senha</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="mínimo 6 caracteres"
              autoComplete="new-password"
              className="w-full rounded-lg border border-gray-600 bg-gray-900 px-3 py-2 text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={creating}
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white transition-colors hover:bg-blue-500 disabled:opacity-60"
        >
          {creating ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
          {creating ? 'Criando...' : 'Criar usuário'}
        </button>
      </form>

      <div className="rounded-xl border border-gray-700 bg-gray-800">
        <div className="border-b border-gray-700 px-5 py-3 text-sm font-semibold text-gray-300">
          Contas cadastradas ({users.length})
        </div>
        {loading ? (
          <div className="flex items-center justify-center gap-2 px-5 py-8 text-gray-400">
            <Loader2 size={18} className="animate-spin" />
            Carregando...
          </div>
        ) : users.length === 0 ? (
          <div className="px-5 py-8 text-center text-gray-400">Nenhum usuário cadastrado.</div>
        ) : (
          <ul className="divide-y divide-gray-700">
            {users.map((user) => {
              const isCurrent = user.email.toLowerCase() === currentEmail
              return (
                <li key={user.id} className="flex items-center gap-4 px-5 py-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 font-bold text-white">
                    {user.email.slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-white">
                      {user.email}
                      {isCurrent && <span className="ml-2 rounded bg-blue-500/20 px-2 py-0.5 text-xs text-blue-300">você</span>}
                    </p>
                    <p className="text-xs text-gray-400">
                      Criado em {new Date(user.created_at).toLocaleDateString('pt-BR')}
                    </p>
                  </div>
                  <button
                    onClick={() => handleResetPassword(user)}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-600 px-3 py-1.5 text-sm text-gray-200 transition-colors hover:bg-gray-700"
                    title="Alterar senha"
                  >
                    <KeyRound size={15} />
                    Senha
                  </button>
                  <button
                    onClick={() => handleDelete(user)}
                    disabled={isCurrent}
                    className="inline-flex items-center gap-1 rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-red-300 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-40"
                    title={isCurrent ? 'Você não pode remover a própria conta' : 'Remover usuário'}
                  >
                    <Trash2 size={15} />
                    Remover
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

export default Users
