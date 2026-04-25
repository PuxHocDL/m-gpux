import React from 'react';
import { Key, Plus, Trash2, Copy } from 'lucide-react';

export default function ApiKeys() {
  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-2">API Keys</h1>
          <p className="text-muted">Manage access keys for your deployed LLM endpoints.</p>
        </div>
        <button className="bg-primary text-white px-4 py-2 rounded-md text-sm font-semibold hover:bg-orange-600 transition-colors flex items-center gap-2">
          <Plus className="w-4 h-4" /> Create New Key
        </button>
      </div>

      <div className="bg-surface border border-border rounded-xl overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-background border-b border-border">
            <tr>
              <th className="px-6 py-4 font-medium text-muted">Name</th>
              <th className="px-6 py-4 font-medium text-muted">Key</th>
              <th className="px-6 py-4 font-medium text-muted">Created</th>
              <th className="px-6 py-4 font-medium text-muted text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            <tr className="hover:bg-background/50 transition-colors">
              <td className="px-6 py-4 font-medium">Production App</td>
              <td className="px-6 py-4 font-mono text-muted flex items-center gap-2">
                sk-live-********************a9f2
                <button className="p-1 hover:text-foreground transition-colors"><Copy className="w-3 h-3" /></button>
              </td>
              <td className="px-6 py-4 text-muted">Oct 24, 2026</td>
              <td className="px-6 py-4 text-right">
                <button className="p-2 text-muted hover:text-red-500 rounded-lg transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
              </td>
            </tr>
            <tr className="hover:bg-background/50 transition-colors">
              <td className="px-6 py-4 font-medium">Local Testing</td>
              <td className="px-6 py-4 font-mono text-muted flex items-center gap-2">
                sk-test-********************b1c4
                <button className="p-1 hover:text-foreground transition-colors"><Copy className="w-3 h-3" /></button>
              </td>
              <td className="px-6 py-4 text-muted">Oct 25, 2026</td>
              <td className="px-6 py-4 text-right">
                <button className="p-2 text-muted hover:text-red-500 rounded-lg transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
