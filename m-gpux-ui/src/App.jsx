import Navbar from "./components/layout/Navbar";
import Footer from "./components/layout/Footer";
import { ClickSpark } from "./components/reactbits";
import Hero from "./components/sections/Hero";
import StatsBand from "./components/sections/StatsBand";
import TutorialSection from "./components/sections/TutorialSection";
import CommandShowcase from "./components/sections/CommandShowcase";
import ExtensionShowcase from "./components/sections/ExtensionShowcase";
import FeaturesSection from "./components/sections/FeaturesSection";
import CTASection from "./components/sections/CTASection";

export default function App() {
  return (
    <div className="relative min-h-screen overflow-x-clip">
      <ClickSpark />
      <Navbar />
      <main>
        <Hero />
        <StatsBand />
        <TutorialSection />
        <CommandShowcase />
        <ExtensionShowcase />
        <FeaturesSection />
        <CTASection />
      </main>
      <Footer />
    </div>
  );
}
