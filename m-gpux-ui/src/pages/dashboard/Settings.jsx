import React from 'react';
import { User, CheckCircle2 } from 'lucide-react';

export default function Settings() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Account Settings</h1>
        <p className="text-muted">Manage your m-gpux profiles and Modal tokens.</p>
      </div>

      <div className="bg-surface border border-border rounded-xl p-6">
        <h3 className="font-bold mb-6 text-lg">Configured Profiles</h3>
        
        <div className="space-y-4">
          <div className="border border-primary/50 bg-primary/5 rounded-lg p-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="bg-primary/20 p-2 rounded-full text-primary">
                <User className="w-5 h-5" />
              </div>
              <div>
                <div className="font-bold flex items-center gap-2">
                  personal-dev 
                  <span className="text-xs bg-primary text-white px-2 py-0.5 rounded-full flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> Active
                  </span>
                </div>
                <div className="text-sm text-muted font-mono mt-1">Token ID: ak-****************</div>
              </div>
            </div>
            <button className="text-sm font-medium text-muted hover:text-foreground transition-colors border border-border bg-background px-4 py-2 rounded-md">
              Edit
            </button>
          </div>

          <div className="border border-border bg-background rounded-lg p-4 flex items-center justify-between opacity-70 hover:opacity-100 transition-opacity">
            <div className="flex items-center gap-4">
              <div className="bg-surface p-2 rounded-full text-muted">
                <User className="w-5 h-5" />
              </div>
              <div>
                <div className="font-bold">company-prod</div>
                <div className="text-sm text-muted font-mono mt-1">Token ID: ak-****************</div>
              </div>
            </div>
            <button className="text-sm font-medium text-muted hover:text-foreground transition-colors border border-border bg-surface px-4 py-2 rounded-md">
              Switch
            </button>
          </div>
        </div>

        <button className="mt-6 text-sm font-medium text-primary hover:text-orange-400 transition-colors">
          + Add New Profile
        </button>
      </div>
    </div>
  );
}
