import React from 'react';
import { Terminal, Star, Sun, Moon } from 'lucide-react';

import { Link } from 'react-router-dom';

export default function Navbar({ isDarkMode, toggleTheme }) {
  return (
    <nav className="border-b border-border bg-background/70 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="text-primary w-6 h-6" />
          <Link to="/" className="font-bold text-xl tracking-tight">m-gpux</Link>
        </div>
        <div className="hidden md:flex items-center gap-6 text-sm text-muted font-medium">
          <a href="#" className="hover:text-foreground transition-colors">Guide</a>
          <a href="#" className="hover:text-foreground transition-colors">Architecture</a>
          <a href="#" className="hover:text-foreground transition-colors">FAQ</a>
        </div>
        <div className="flex items-center gap-4">
          <button 
            onClick={toggleTheme}
            className="p-2 text-muted hover:text-foreground hover:bg-surface rounded-full transition-colors"
            aria-label="Toggle theme"
          >
            {isDarkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
          <button className="text-muted hover:text-foreground transition-colors flex items-center gap-2 text-sm font-medium">
            <Star className="w-4 h-4" />
            <span>Star</span>
          </button>
          <Link to="/dashboard" className="bg-primary text-white px-4 py-2 rounded-md text-sm font-semibold hover:bg-orange-600 transition-colors">
            Get Started
          </Link>
        </div>
      </div>
    </nav>
  );
}
