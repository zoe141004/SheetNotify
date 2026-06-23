import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { 
  FiGrid, 
  FiFileText, 
  FiMessageSquare, 
  FiClock, 
  FiSettings,
  FiLogOut 
} from 'react-icons/fi';

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const location = useLocation();

  const navigation = [
    { name: 'Dashboard', href: '/', icon: FiGrid },
    { name: 'Google Sheets', href: '/sheets', icon: FiFileText },
    { name: 'Telegram Bot', href: '/telegram', icon: FiMessageSquare },
    { name: 'Logs', href: '/logs', icon: FiClock },
    { name: 'Settings', href: '/settings', icon: FiSettings },
  ];

  return (
    <div className="min-h-screen bg-dark-900 flex text-gray-100 font-sans">
      {/* Sidebar */}
      <aside className="w-64 glass-card border-l-0 border-y-0 rounded-none flex flex-col z-10 hidden md:flex">
        <div className="p-6">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-accent-400 flex items-center justify-center text-white font-bold text-xl">
              S
            </div>
            <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-gray-100 to-gray-400">
              SheetNotify
            </span>
          </Link>
        </div>

        <nav className="flex-1 px-4 space-y-2 mt-4">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                to={item.href}
                className={isActive ? 'sidebar-link-active' : 'sidebar-link'}
              >
                <Icon className={`w-5 h-5 ${isActive ? 'text-primary-400' : 'text-gray-500'}`} />
                {item.name}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-dark-400/30">
          <div className="flex items-center gap-3 px-4 py-3 mb-2 rounded-xl bg-dark-800/50">
            {user?.avatar_url ? (
              <img src={user.avatar_url} alt="Avatar" className="w-8 h-8 rounded-full" />
            ) : (
              <div className="w-8 h-8 rounded-full bg-dark-400 flex items-center justify-center">
                {user?.email?.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="flex-1 overflow-hidden">
              <p className="text-sm font-medium truncate">{user?.name || 'User'}</p>
              <p className="text-xs text-gray-500 truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-400 hover:bg-dark-600 rounded-lg transition-colors"
          >
            <FiLogOut className="w-4 h-4" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden gradient-bg relative">
        {/* Mobile Header */}
        <header className="md:hidden glass-card rounded-none border-t-0 border-x-0 p-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-accent-400 flex items-center justify-center text-white font-bold">
              S
            </div>
          </div>
          <button onClick={logout} className="text-gray-400">
            <FiLogOut className="w-5 h-5" />
          </button>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8">
          <div className="max-w-6xl mx-auto animate-fade-in">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
