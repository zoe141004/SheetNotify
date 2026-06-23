import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../lib/api';
import toast from 'react-hot-toast';

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const [name, setName] = useState(user?.name || '');
  const [loading, setLoading] = useState(false);

  // Since we don't have a specific update user endpoint yet, 
  // we'll just mock this or leave it as a placeholder for expansion.
  // The backend has `schemas.UserUpdate` but not a route. 
  // For the sake of the plan, we just show read-only or add a mock save.

  return (
    <div className="max-w-2xl space-y-8">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold text-gray-100">Settings</h1>
        <p className="text-gray-400">Manage your account preferences.</p>
      </div>

      <div className="glass-card p-6">
        <h2 className="text-xl font-bold mb-6">Profile Information</h2>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Email Address</label>
            <input 
              type="text" 
              value={user?.email || ''} 
              disabled 
              className="input-field w-full opacity-60 cursor-not-allowed" 
            />
            <p className="text-xs text-gray-500 mt-1">Bound to your Google account.</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Display Name</label>
            <input 
              type="text" 
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input-field w-full"
              disabled
            />
            <p className="text-xs text-gray-500 mt-1">Display name updating is coming soon.</p>
          </div>
        </div>
      </div>
      
      <div className="glass-card p-6">
        <h2 className="text-xl font-bold mb-6 text-red-400">Danger Zone</h2>
        <div className="p-4 border border-red-500/30 rounded-xl bg-red-500/5 flex items-center justify-between">
          <div>
            <h3 className="font-medium text-gray-200">Delete Account</h3>
            <p className="text-sm text-gray-400">Permanently delete your account and all subscriptions.</p>
          </div>
          <button className="btn-secondary text-red-400 hover:bg-red-500 hover:text-white" disabled>
            Delete Account
          </button>
        </div>
      </div>
    </div>
  );
}
