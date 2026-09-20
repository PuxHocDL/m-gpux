import Navbar from "./components/layout/Navbar";
import DocsSection from "./components/sections/DocsSection";

export default function DocsApp() {
  return (
    <div className="relative min-h-screen overflow-x-clip">
      <Navbar />
      <main className="pt-[68px]">
        <DocsSection />
      </main>
    </div>
  );
}
