import React from 'react';
import { motion } from 'framer-motion';

export default function TerminalMockup() {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, delay: 0.2 }}
      className="mt-16 text-left max-w-3xl mx-auto"
    >
      <div className="bg-[#111111] border border-border rounded-xl overflow-hidden shadow-2xl glow">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[#2a2a2a] bg-[#0a0a0a]">
          <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/50"></div>
          <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/50"></div>
          <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/50"></div>
          <span className="text-xs text-neutral-400 ml-2 font-mono">Terminal</span>
        </div>
        <div className="p-6 font-mono text-sm leading-relaxed text-neutral-300">
          <div className="flex items-center gap-2 text-primary mb-2">
            <span className="text-green-400">➜</span>
            <span>~</span>
            <span className="text-white">m-gpux serve deploy</span>
          </div>
          <div className="text-neutral-400">✔ Pick an LLM: <span className="text-blue-400">Qwen/Qwen2.5-7B-Instruct</span></div>
          <div className="text-neutral-400">✔ Select GPU: <span className="text-blue-400">L4</span></div>
          <div className="text-neutral-400">✔ Keep warm (min containers): <span className="text-blue-400">1</span></div>
          <br/>
          <div className="text-yellow-400">Deploying LLM API server to Modal...</div>
          <div className="text-green-400">✨ Successfully deployed in 12s!</div>
          <div className="mt-2 text-neutral-500">Endpoint: https://workspace--m-gpux-llm-api.modal.run/v1</div>
        </div>
      </div>
    </motion.div>
  );
}
