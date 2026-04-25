import React, { useState } from 'react';
import { Rocket, Server, Cpu, Box, Play } from 'lucide-react';

export default function Deploy() {
  const [isDeploying, setIsDeploying] = useState(false);

  const handleDeploy = (e) => {
    e.preventDefault();
    setIsDeploying(true);
    setTimeout(() => setIsDeploying(false), 3000);
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Deploy Model</h1>
        <p className="text-muted">Spin up a new LLM endpoint on Modal infrastructure.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Deployment Form */}
        <div className="lg:col-span-2 bg-surface border border-border rounded-xl p-6">
          <form onSubmit={handleDeploy} className="space-y-6">
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted flex items-center gap-2">
                <Box className="w-4 h-4" /> HuggingFace Model ID
              </label>
              <input 
                type="text" 
                defaultValue="Qwen/Qwen2.5-7B-Instruct"
                className="w-full bg-background border border-border rounded-lg px-4 py-3 text-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted flex items-center gap-2">
                <Cpu className="w-4 h-4" /> GPU Hardware
              </label>
              <select className="w-full bg-background border border-border rounded-lg px-4 py-3 text-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors appearance-none">
                <option value="L4">NVIDIA L4 (Recommended)</option>
                <option value="A100">NVIDIA A100 40GB</option>
                <option value="A100-80">NVIDIA A100 80GB</option>
                <option value="T4">NVIDIA T4</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted flex items-center gap-2">
                <Server className="w-4 h-4" /> Keep Warm (Min Containers)
              </label>
              <div className="flex items-center gap-4">
                <input type="range" min="0" max="5" defaultValue="1" className="flex-1 accent-primary" />
                <span className="bg-background border border-border px-4 py-2 rounded-lg font-mono">1</span>
              </div>
            </div>

            <button 
              type="submit" 
              disabled={isDeploying}
              className="w-full bg-primary text-white font-bold py-3 px-4 rounded-lg hover:bg-orange-600 transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-primary/20"
            >
              {isDeploying ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  Deploying to Modal...
                </>
              ) : (
                <>
                  <Rocket className="w-5 h-5" /> Deploy Server
                </>
              )}
            </button>
          </form>
        </div>

        {/* Active Deployments Mock */}
        <div className="space-y-4">
          <h2 className="font-bold text-lg flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
            </span>
            Active Endpoints
          </h2>
          
          <div className="bg-surface border border-border rounded-xl p-4 hover:border-primary/50 transition-colors cursor-pointer group">
            <div className="flex items-center justify-between mb-3">
              <span className="font-medium">Qwen2.5-7B</span>
              <span className="text-xs bg-green-500/10 text-green-500 px-2 py-1 rounded-full border border-green-500/20">Running</span>
            </div>
            <div className="text-xs text-muted font-mono truncate mb-4">
              workspace--m-gpux-llm.modal.run
            </div>
            <div className="flex gap-2">
              <button className="flex-1 bg-background border border-border rounded-md py-1.5 text-xs font-medium hover:text-primary transition-colors flex items-center justify-center gap-1">
                <Play className="w-3 h-3" /> Test
              </button>
              <button className="flex-1 bg-background border border-border rounded-md py-1.5 text-xs font-medium text-red-500 hover:bg-red-500/10 transition-colors">
                Stop
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
