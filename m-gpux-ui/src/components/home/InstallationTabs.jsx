import React, { useState } from 'react';
import { motion } from 'framer-motion';

export default function InstallationTabs() {
  const [activeTab, setActiveTab] = useState('install');

  const tabs = [
    { id: 'install', label: '1. Install' },
    { id: 'hub', label: '2. Hub' },
    { id: 'serve', label: '3. Serve' },
    { id: 'vision', label: '4. Vision' },
  ];

  const content = {
    install: `pip install m-gpux\nm-gpux account add`,
    hub: `# Spin up a Jupyter lab on a T4 GPU\nm-gpux hub`,
    serve: `# Deploy Qwen2.5-7B on L4\nm-gpux serve deploy`,
    vision: `# Train a ResNet model from a local folder\nm-gpux vision train`
  };

  return (
    <section className="py-24 px-6 bg-surface/50 border-y border-border relative">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-5xl font-bold mb-4">Start orchestrating today</h2>
          <p className="text-muted text-lg">Four simple commands to power up your workflows.</p>
        </div>

        <div className="bg-[#111111] border border-border rounded-xl overflow-hidden shadow-2xl">
          <div className="flex overflow-x-auto border-b border-[#2a2a2a] bg-[#0a0a0a] no-scrollbar">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-6 py-4 text-sm font-medium whitespace-nowrap transition-colors relative ${
                  activeTab === tab.id ? 'text-primary' : 'text-muted hover:text-foreground'
                }`}
              >
                {tab.label}
                {activeTab === tab.id && (
                  <motion.div
                    layoutId="activeTabIndicator"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
                  />
                )}
              </button>
            ))}
          </div>
          <div className="p-6 md:p-8 font-mono text-sm leading-relaxed text-neutral-300 min-h-[160px] flex items-center">
            <pre className="w-full overflow-x-auto">
              <code className="block">
                {content[activeTab].split('\\n').map((line, i) => (
                  <div key={i} className={line.startsWith('#') ? 'text-neutral-500' : 'text-white'}>
                    {!line.startsWith('#') && <span className="text-muted select-none mr-4">{i + 1}</span>}
                    {line}
                  </div>
                ))}
              </code>
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}
