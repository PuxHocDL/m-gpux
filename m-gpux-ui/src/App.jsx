import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import DashboardLayout from './layouts/DashboardLayout';
import Deploy from './pages/dashboard/Deploy';
import Billing from './pages/dashboard/Billing';
import ApiKeys from './pages/dashboard/ApiKeys';
import Settings from './pages/dashboard/Settings';
import Playground from './pages/dashboard/Playground';

function App() {
  const [isDarkMode, setIsDarkMode] = useState(true);

  // Sync theme to HTML document
  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  const toggleTheme = () => setIsDarkMode(!isDarkMode);

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background text-foreground relative overflow-hidden flex flex-col transition-colors duration-300">
        {/* Background Grid - Global */}
        <div className="absolute inset-0 bg-grid-pattern [mask-image:linear-gradient(to_bottom,black,transparent)] pointer-events-none opacity-20 z-0 fixed"></div>

        <Routes>
          {/* Public Landing Page */}
          <Route path="/" element={<LandingPage isDarkMode={isDarkMode} toggleTheme={toggleTheme} />} />
          
          {/* Dashboard Layout */}
          <Route path="/dashboard" element={<DashboardLayout isDarkMode={isDarkMode} toggleTheme={toggleTheme} />}>
            <Route index element={<Deploy />} />
            <Route path="billing" element={<Billing />} />
            <Route path="keys" element={<ApiKeys />} />
            <Route path="settings" element={<Settings />} />
            <Route path="playground" element={<Playground />} />
          </Route>
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
