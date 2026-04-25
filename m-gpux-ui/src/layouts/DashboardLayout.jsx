import React from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { Terminal, CreditCard, Key, Settings as SettingsIcon, MessageSquare, Rocket, Sun, Moon, LogOut } from 'lucide-react';

export default function DashboardLayout({ isDarkMode, toggleTheme }) {
  const location = useLocation();

  const navItems = [
    { name: 'Deploy', path: '/dashboard', icon: <Rocket className="w-5 h-5" /> },
    { name: 'Billing', path: '/dashboard/billing', icon: <CreditCard className="w-5 h-5" /> },
    { name: 'API Keys', path: '/dashboard/keys', icon: <Key className="w-5 h-5" /> },
    { name: 'Playground', path: '/dashboard/playground', icon: <MessageSquare className="w-5 h-5" /> },
    { name: 'Settings', path: '/dashboard/settings', icon: <SettingsIcon className="w-5 h-5" /> },
  ];

  return (
    <div className="flex h-screen w-full relative z-10 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border bg-surface/50 backdrop-blur-md flex flex-col hidden md:flex">
        <div className="h-16 flex items-center gap-2 px-6 border-b border-border">
          <Terminal className="text-primary w-6 h-6" />
          <Link to="/" className="font-bold text-xl tracking-tight">m-gpux</Link>
        </div>
        <nav className="flex-1 py-6 px-4 space-y-2">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path || (item.path !== '/dashboard' && location.pathname.startsWith(item.path));
            return (
              <Link
                key={item.name}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive 
                    ? 'bg-primary/10 text-primary font-medium border border-primary/20 glow' 
                    : 'text-muted hover:text-foreground hover:bg-background'
                }`}
              >
                {item.icon}
                {item.name}
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-border">
          <button className="flex items-center gap-3 px-4 py-3 w-full text-muted hover:text-red-500 rounded-lg transition-colors">
            <LogOut className="w-5 h-5" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden bg-background/50 backdrop-blur-sm">
        {/* Top Header */}
        <header className="h-16 border-b border-border flex items-center justify-end px-8 shrink-0">
          <div className="flex items-center gap-4">
            <button 
              onClick={toggleTheme}
              className="p-2 text-muted hover:text-foreground hover:bg-surface rounded-full transition-colors"
            >
              {isDarkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
            <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary/50 flex items-center justify-center text-primary font-bold cursor-pointer hover:bg-primary/30 transition-colors">
              U
            </div>
          </div>
        </header>
        
        {/* Page Content */}
        <main className="flex-1 overflow-y-auto p-8 relative">
          <div className="max-w-5xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
