import { NavLink, Outlet } from 'react-router-dom'
import { Home, Image, Search, Users, Play, Settings } from 'lucide-react'

function Layout() {
  const navItems = [
    { to: '/', icon: Home, label: 'Início' },
    { to: '/gallery', icon: Image, label: 'Galeria' },
    { to: '/search', icon: Search, label: 'Busca' },
    { to: '/persons', icon: Users, label: 'Pessoas' },
    { to: '/settings', icon: Settings, label: 'Config' },
  ]

  return (
    <div className="flex h-screen bg-gray-900">
      {/* Sidebar */}
      <nav className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-xl font-bold text-blue-400">📷 PICS</h1>
          <p className="text-xs text-gray-400 mt-1">Organizador de Fotos</p>
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
              {label}
            </NavLink>
          ))}
        </div>

        <div className="p-4 border-t border-gray-700">
          <p className="text-xs text-gray-500">PICS v1.0</p>
        </div>
      </nav>

      {/* Conteúdo principal */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

export default Layout
