import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../lib/api';
import toast from 'react-hot-toast';
import { FiMessageSquare, FiExternalLink, FiCopy, FiCheckCircle } from 'react-icons/fi';

export default function TelegramPage() {
  const { user, refreshUser } = useAuth();
  const [linkData, setLinkData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchLinkData = async () => {
      try {
        const { data } = await api.get('/telegram/link-url');
        setLinkData(data);
      } catch (error) {
        toast.error('Failed to load Telegram link data');
      } finally {
        setLoading(false);
      }
    };
    fetchLinkData();
    
    // Poll user info occasionally to see if they linked
    const interval = setInterval(() => {
      if (!user?.telegram_chat_id) {
        refreshUser();
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [user?.telegram_chat_id, refreshUser]);

  const handleCopyLink = () => {
    if (linkData?.link_url) {
      navigator.clipboard.writeText(linkData.link_url);
      toast.success('Link copied to clipboard');
    }
  };

  const handleUnlink = async () => {
    if (!window.confirm('Are you sure you want to unlink Telegram? You will stop receiving notifications.')) return;
    
    try {
      await api.post('/telegram/unlink');
      toast.success('Telegram account unlinked');
      refreshUser();
    } catch (e) {
      toast.error('Failed to unlink Telegram');
    }
  };

  if (loading) {
    return <div className="text-gray-400">Loading Telegram info...</div>;
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold text-gray-100">Telegram Setup</h1>
        <p className="text-gray-400">Link your Telegram account to receive instant notifications.</p>
      </div>

      {user?.telegram_chat_id ? (
        <div className="glass-card p-8 border-emerald-500/30 flex flex-col md:flex-row items-center gap-8 text-center md:text-left">
          <div className="w-24 h-24 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-400 shrink-0">
            <FiCheckCircle className="w-12 h-12" />
          </div>
          <div className="flex-1">
            <h2 className="text-2xl font-bold mb-2">Account Linked!</h2>
            <p className="text-gray-400 mb-2">
              Your SheetNotify account is securely linked to Telegram.
            </p>
            {user.telegram_username && (
              <p className="font-medium text-gray-200 mb-6">
                Connected as: <span className="text-primary-400">@{user.telegram_username}</span>
              </p>
            )}
            <button onClick={handleUnlink} className="btn-danger inline-block">
              Unlink Telegram
            </button>
          </div>
        </div>
      ) : (
        <div className="glass-card p-6 md:p-8">
          <h2 className="text-xl font-bold mb-6">How to link your account</h2>
          
          <div className="space-y-8">
            <div className="flex gap-4">
              <div className="w-8 h-8 rounded-full bg-dark-500 text-gray-200 flex items-center justify-center shrink-0 font-bold">1</div>
              <div>
                <h3 className="font-medium text-gray-200 mb-1">Open the Telegram App</h3>
                <p className="text-sm text-gray-400">Click the button below to open our official Telegram bot.</p>
                <a 
                  href={linkData?.link_url} 
                  target="_blank" 
                  rel="noreferrer"
                  className="mt-4 btn-primary inline-flex items-center gap-2"
                >
                  <FiExternalLink className="w-4 h-4" />
                  Open in Telegram
                </a>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="w-8 h-8 rounded-full bg-dark-500 text-gray-200 flex items-center justify-center shrink-0 font-bold">2</div>
              <div className="flex-1">
                <h3 className="font-medium text-gray-200 mb-1">Or send the command manually</h3>
                <p className="text-sm text-gray-400 mb-4">
                  If the button above doesn't work, open Telegram, search for <b>@{linkData?.bot_username}</b>, and send this exact message:
                </p>
                <div className="flex items-center gap-2 bg-dark-800 border border-dark-400 p-3 rounded-lg overflow-x-auto">
                  <code className="text-primary-400 text-sm flex-1 whitespace-nowrap">
                    /start {user?.telegram_link_token}
                  </code>
                  <button 
                    onClick={handleCopyLink} 
                    className="p-2 hover:bg-dark-600 rounded-md text-gray-400 transition-colors"
                  >
                    <FiCopy className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
            
            <div className="flex gap-4">
              <div className="w-8 h-8 rounded-full bg-dark-500 text-gray-200 flex items-center justify-center shrink-0 font-bold">3</div>
              <div>
                <h3 className="font-medium text-gray-200 mb-1">Wait for confirmation</h3>
                <p className="text-sm text-gray-400">
                  Once you send the message, the bot will confirm successful linking. This page will update automatically.
                </p>
              </div>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
