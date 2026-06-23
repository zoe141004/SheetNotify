import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../lib/api';
import { FiGrid, FiMessageSquare, FiClock, FiCheckCircle } from 'react-icons/fi';
import { Link } from 'react-router-dom';

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [subsCount, setSubsCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const [statsRes, subsRes] = await Promise.all([
          api.get('/logs/stats'),
          api.get('/sheets/subscriptions')
        ]);
        setStats(statsRes.data);
        setSubsCount(subsRes.data.length);
      } catch (error) {
        console.error('Failed to load dashboard data', error);
      } finally {
        setLoading(false);
      }
    };
    fetchDashboardData();
  }, []);

  if (loading) {
    return <div className="text-gray-400">Loading dashboard...</div>;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold text-gray-100">Welcome, {user?.name || 'User'}!</h1>
        <p className="text-gray-400">Here's an overview of your SheetNotify system today.</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="glass-card p-6 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h3 className="text-gray-400 font-medium">Connected Sheets</h3>
            <div className="w-10 h-10 rounded-xl bg-primary-500/10 flex items-center justify-center text-primary-400">
              <FiGrid className="w-5 h-5" />
            </div>
          </div>
          <div className="text-3xl font-bold">{subsCount}</div>
        </div>

        <div className="glass-card p-6 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h3 className="text-gray-400 font-medium">Total Sent</h3>
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-400">
              <FiCheckCircle className="w-5 h-5" />
            </div>
          </div>
          <div className="text-3xl font-bold">{stats?.sent || 0}</div>
        </div>

        <div className="glass-card p-6 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h3 className="text-gray-400 font-medium">Notifications Today</h3>
            <div className="w-10 h-10 rounded-xl bg-accent-500/10 flex items-center justify-center text-accent-400">
              <FiClock className="w-5 h-5" />
            </div>
          </div>
          <div className="text-3xl font-bold">{stats?.today || 0}</div>
        </div>

        <div className="glass-card p-6 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h3 className="text-gray-400 font-medium">Telegram Status</h3>
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${user?.telegram_chat_id ? 'bg-primary-500/10 text-primary-400' : 'bg-red-500/10 text-red-400'}`}>
              <FiMessageSquare className="w-5 h-5" />
            </div>
          </div>
          <div className="text-xl font-bold">
            {user?.telegram_chat_id ? 'Linked' : 'Not Linked'}
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {!user?.telegram_chat_id && (
          <div className="glass-card p-6 border-red-500/30 bg-red-500/5">
            <h2 className="text-xl font-bold mb-2">Connect Telegram</h2>
            <p className="text-gray-400 mb-6 text-sm">
              You need to link your Telegram account to start receiving notifications.
            </p>
            <Link to="/telegram" className="btn-primary inline-flex">
              Link Telegram Now
            </Link>
          </div>
        )}
        
        <div className="glass-card p-6 border-primary-500/30">
          <h2 className="text-xl font-bold mb-2">Add New Sheet</h2>
          <p className="text-gray-400 mb-6 text-sm">
            Select a Google Sheet from your Drive to monitor for new rows.
          </p>
          <Link to="/sheets" className="btn-secondary inline-flex">
            Manage Sheets
          </Link>
        </div>
      </div>
    </div>
  );
}
