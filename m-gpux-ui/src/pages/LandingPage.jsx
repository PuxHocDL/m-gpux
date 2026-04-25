import React from 'react';
import Navbar from '../components/layout/Navbar';
import Footer from '../components/layout/Footer';
import Hero from '../components/home/Hero';
import InstallationTabs from '../components/home/InstallationTabs';
import FeaturesGrid from '../components/home/FeaturesGrid';

export default function LandingPage({ isDarkMode, toggleTheme }) {
  return (
    <>
      <Navbar isDarkMode={isDarkMode} toggleTheme={toggleTheme} />
      <main className="flex-1 relative z-10">
        <Hero />
        <InstallationTabs />
        <FeaturesGrid />
      </main>
      <Footer />
    </>
  );
}
