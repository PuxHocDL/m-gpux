import React, { useState, useEffect } from 'react';
import Navbar from './components/layout/Navbar';
import Footer from './components/layout/Footer';
import Hero from './components/home/Hero';
import InstallationTabs from './components/home/InstallationTabs';
import FeaturesGrid from './components/home/FeaturesGrid';

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
    <div className="min-h-screen bg-background text-foreground relative overflow-hidden flex flex-col transition-colors duration-300">
      {/* Background Grid */}
      <div className="absolute inset-0 bg-grid-pattern [mask-image:linear-gradient(to_bottom,black,transparent)] pointer-events-none opacity-20 z-0"></div>

      <Navbar isDarkMode={isDarkMode} toggleTheme={toggleTheme} />
      
      <main className="flex-1 relative z-10">
        <Hero />
        <InstallationTabs />
        <FeaturesGrid />
      </main>

      <Footer />
    </div>
  );
}

export default App;
