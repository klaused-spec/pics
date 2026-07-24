import { useState, useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Home, Image, Search, Users, UserCog, Settings, Database, ChevronLeft, ChevronRight, LogOut, Smartphone, HardDriveOff } from 'lucide-react'
import { api } from '../api'

function Layout() {
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem('layout_sidebar_collapsed') === 'true'
  })
  const [unavailableDirs, setUnavailableDirs] = useState([])

  useEffect(() => {
    let cancelled = false
    async function checkStorage() {
      try {
        const res = await api.get('/health')
        if (!cancelled) {
          setUnavailableDirs(res.data?.storage?.unavailable || [])
        }
      } catch {
        // backend fora do ar — não mostrar aviso de storage
      }
    }
    checkStorage()
    const interval = setInterval(checkStorage, 15000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  const toggleCollapsed = () => {
    const next = !collapsed
    window.localStorage.setItem('layout_sidebar_collapsed', String(next))
    setCollapsed(next)
  }

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('userEmail')
    navigate('/login')
  }

  const userEmail = localStorage.getItem('userEmail') || 'Usuário'

  const navItems = [
    { to: '/', icon: Home, label: 'Início' },
    { to: '/gallery', icon: Image, label: 'Galeria' },
    { to: '/search', icon: Search, label: 'Busca' },
    { to: '/persons', icon: Users, label: 'Pessoas' },
    { to: '/maintenance', icon: Database, label: 'Manutenção' },
    { to: '/mobile', icon: Smartphone, label: 'Android' },
    { to: '/users', icon: UserCog, label: 'Usuários' },
    { to: '/settings', icon: Settings, label: 'Config' },
  ]

  return (
    <div className="flex h-screen bg-gray-900">
      {/* Sidebar */}
      <nav className={`transition-all duration-200 ${collapsed ? 'w-20' : 'w-64'} bg-gray-800 border-r border-gray-700 flex flex-col`}>
        <div className="p-4 border-b border-gray-700 flex items-center justify-between gap-2">
          <div className="space-y-1">
            <h1 className={`text-xl font-bold text-blue-400 ${collapsed ? 'sr-only' : ''}`}>📷 PICS</h1>
            {!collapsed && <p className="text-xs text-gray-400 mt-1">Organizador de Fotos</p>}
          </div>
          <button
            onClick={toggleCollapsed}
            className="p-2 rounded hover:bg-gray-700 text-gray-300"
            aria-label={collapsed ? 'Expandir barra lateral' : 'Recolher barra lateral'}
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        <div className="flex-1 py-4">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-400 border-r-2 border-blue-400'
                    : 'text-gray-300 hover:bg-gray-700/50 hover:text-white'
                }`
              }
              end={to === '/'}
            >
              <Icon size={18} />
              {!collapsed && label}
            </NavLink>
          ))}
        </div>

        {/* User Info & Logout */}
        <div className="p-4 border-t border-gray-700 space-y-3">
          {!collapsed && (
            <div className="text-xs">
              <p className="text-gray-400">Logado como:</p>
              <p className="text-blue-300 font-semibold truncate">{userEmail}</p>
              <p className="text-gray-500 mt-1">v{__APP_VERSION__}</p>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-red-500/20 rounded transition-colors"
          >
            <LogOut size={16} />
            {!collapsed && 'Sair'}
          </button>
        </div>
      </nav>

      {/* Conteúdo principal */}
      <main className="flex-1 overflow-auto flex flex-col">
        {unavailableDirs.length > 0 && (
          <div className="bg-red-900/80 border-b border-red-700 px-4 py-3 flex items-start gap-3 shrink-0">
            <HardDriveOff size={18} className="text-red-400 mt-0.5 shrink-0" />
            <div className="text-sm">
              <span className="font-semibold text-red-300">Unidade(s) indisponível(is) — operações de arquivo bloqueadas.</span>
              <ul className="mt-1 space-y-0.5">
                {unavailableDirs.map(d => (
                  <li key={d} className="text-red-400 font-mono text-xs">{d}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
        <div className="flex-1 overflow-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

export default Layout
