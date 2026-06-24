import { useState, useEffect } from 'react';
import api from '../lib/api';
import toast from 'react-hot-toast';
import { FiTrash2, FiCode, FiToggleLeft, FiToggleRight, FiPlus, FiCopy } from 'react-icons/fi';

export default function SheetsPage() {
  const [subscriptions, setSubscriptions] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Modals state
  const [showAddModal, setShowAddModal] = useState(false);
  const [showScriptModal, setShowScriptModal] = useState(null); // stores sub id

  useEffect(() => {
    fetchSubscriptions();
  }, []);

  const fetchSubscriptions = async () => {
    try {
      const { data } = await api.get('/sheets/subscriptions');
      setSubscriptions(data);
    } catch (e) {
      toast.error('Failed to load subscriptions');
    } finally {
      setLoading(false);
    }
  };

  const toggleActive = async (sub) => {
    try {
      await api.patch(`/sheets/subscriptions/${sub.id}`, { is_active: !sub.is_active });
      setSubscriptions(subs => subs.map(s => s.id === sub.id ? { ...s, is_active: !sub.is_active } : s));
      toast.success(sub.is_active ? 'Subscription paused' : 'Subscription activated');
    } catch (e) {
      toast.error('Failed to update status');
    }
  };

  const deleteSub = async (id) => {
    if (!window.confirm('Are you sure you want to delete this subscription?')) return;
    try {
      await api.delete(`/sheets/subscriptions/${id}`);
      setSubscriptions(subs => subs.filter(s => s.id !== id));
      toast.success('Subscription deleted');
    } catch (e) {
      toast.error('Failed to delete');
    }
  };

  if (loading) {
    return <div className="text-gray-400">Loading sheets...</div>;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-100">Google Sheets</h1>
          <p className="text-gray-400">Manage your monitored sheets and get webhook scripts.</p>
        </div>
        <button 
          onClick={() => setShowAddModal(true)}
          className="btn-primary flex items-center gap-2"
        >
          <FiPlus className="w-5 h-5" />
          Add New Sheet
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {subscriptions.length === 0 ? (
          <div className="glass-card p-12 text-center flex flex-col items-center justify-center border-dashed border-2 border-dark-400/50">
            <h3 className="text-xl font-bold mb-2">No sheets connected yet</h3>
            <p className="text-gray-400 mb-6">Connect your first Google Sheet to start receiving real-time notifications.</p>
            <button onClick={() => setShowAddModal(true)} className="btn-secondary">
              Connect a Sheet
            </button>
          </div>
        ) : (
          subscriptions.map(sub => (
            <div key={sub.id} className="glass-card p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-1">
                  <h3 className="font-bold text-lg text-gray-100">{sub.spreadsheet_name || sub.spreadsheet_id}</h3>
                  <span className={`status-badge ${sub.is_active ? 'bg-primary-500/15 text-primary-400 border border-primary-500/20' : 'bg-dark-500/50 text-gray-400'}`}>
                    {sub.is_active ? 'Active' : 'Paused'}
                  </span>
                </div>
                <div className="text-sm text-gray-400 flex items-center gap-2">
                  <span className="bg-dark-600 px-2 py-0.5 rounded text-xs font-medium border border-dark-400/50">
                    Scope: {sub.track_all_sheets ? 'Entire spreadsheet' : `Tab: ${sub.sheet_name}`}
                  </span>
                  <span>•</span>
                  <span>Last row: {sub.last_known_row}</span>
                  <span>•</span>
                  <span>Polling: {sub.polling_enabled ? `${sub.polling_interval_minutes || 1} min` : 'Off'}</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {!sub.track_all_sheets && (
                  <button 
                    onClick={() => setShowScriptModal(sub.id)}
                    title="View Apps Script"
                    className="p-2.5 rounded-lg bg-dark-600 border border-dark-400/50 text-gray-200 hover:text-white hover:bg-primary-600 transition-colors"
                  >
                    <FiCode className="w-5 h-5" />
                  </button>
                )}
                <button 
                  onClick={() => toggleActive(sub)}
                  title={sub.is_active ? "Pause" : "Activate"}
                  className="p-2.5 rounded-lg bg-dark-600 border border-dark-400/50 text-gray-200 hover:text-white hover:bg-dark-500 transition-colors"
                >
                  {sub.is_active ? <FiToggleRight className="w-5 h-5 text-primary-400" /> : <FiToggleLeft className="w-5 h-5 text-gray-500" />}
                </button>
                <button 
                  onClick={() => deleteSub(sub.id)}
                  title="Delete"
                  className="p-2.5 rounded-lg bg-dark-600 border border-dark-400/50 text-gray-200 hover:text-white hover:bg-red-500/80 transition-colors"
                >
                  <FiTrash2 className="w-5 h-5 cursor-pointer text-red-400" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {showAddModal && <AddSheetModal onClose={() => setShowAddModal(false)} onAdded={fetchSubscriptions} />}
      {showScriptModal && <ScriptModal subId={showScriptModal} onClose={() => setShowScriptModal(null)} />}
    </div>
  );
}

// ============================================
// ADD SHEET MODAL
// ============================================
function AddSheetModal({ onClose, onAdded }) {
  const [spreadsheets, setSpreadsheets] = useState([]);
  const [tabs, setTabs] = useState([]);
  const [loading, setLoading] = useState(true);
  
  const [selectedSheet, setSelectedSheet] = useState('');
  const [selectedTab, setSelectedTab] = useState('');
  const [trackAllSheets, setTrackAllSheets] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get('/sheets/list').then(res => {
      setSpreadsheets(res.data);
      setLoading(false);
    }).catch(err => {
      toast.error('Failed to load Google Sheets. Plase ensure Drive API is enabled.');
      setLoading(false);
    });
  }, []);

  const handleSheetSelect = async (e) => {
    const id = e.target.value;
    setSelectedSheet(id);
    setSelectedTab('');
    
    if (!id) {
      setTabs([]);
      return;
    }
    
    try {
      const res = await api.get(`/sheets/${id}/tabs`);
      setTabs(res.data);
    } catch {
      toast.error('Failed to load tabs');
      setTabs([]);
    }
  };

  const handleSave = async () => {
    if (!selectedSheet) return toast.error('Please select a spreadsheet');
    if (!trackAllSheets && !selectedTab) return toast.error('Please select a tab or choose entire spreadsheet');
    
    setSubmitting(true);
    try {
      const sheetDetail = spreadsheets.find(s => s.id === selectedSheet);
      await api.post('/sheets/subscribe', {
        spreadsheet_id: selectedSheet,
        spreadsheet_name: sheetDetail?.name,
        spreadsheet_url: sheetDetail?.url,
        sheet_name: trackAllSheets ? undefined : selectedTab,
        polling_enabled: true,
        polling_interval_minutes: 1,
        track_all_sheets: trackAllSheets,
      });
      toast.success('Subscription created!');
      onAdded();
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to subscribe');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="glass-card w-full max-w-lg p-6 relative">
        <h2 className="text-xl font-bold mb-4">Add Google Sheet</h2>
        
        {loading ? <p className="text-gray-400">Fetching your sheets...</p> : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Select Spreadsheet</label>
              <select className="input-field w-full" value={selectedSheet} onChange={handleSheetSelect}>
                <option value="">-- Choose a spreadsheet --</option>
                {spreadsheets.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-1">Select Tab</label>
              <select className="input-field w-full" value={selectedTab} onChange={e => setSelectedTab(e.target.value)} disabled={!selectedSheet || tabs.length === 0 || trackAllSheets}>
                <option value="">-- Choose a tab --</option>
                {tabs.map(t => (
                  <option key={t.index} value={t.title}>{t.title}</option>
                ))}
              </select>
            </div>

            <label className="flex items-center gap-3 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={trackAllSheets}
                onChange={(e) => setTrackAllSheets(e.target.checked)}
                className="h-4 w-4 rounded border-dark-400 bg-dark-700 text-primary-500"
              />
              Track entire spreadsheet (all tabs) with polling every 1 minute
            </label>

            <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-dark-400/30">
              <button onClick={onClose} className="px-4 py-2 text-gray-400 hover:text-white transition-colors">Cancel</button>
              <button onClick={handleSave} disabled={submitting || !selectedSheet || (!trackAllSheets && !selectedTab)} className="btn-primary py-2">
                {submitting ? 'Saving...' : 'Subscribe'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================
// SCRIPT MODAL
// ============================================
function ScriptModal({ subId, onClose }) {
  const [scriptData, setScriptData] = useState(null);

  useEffect(() => {
    api.get(`/sheets/subscriptions/${subId}/script`).then(res => setScriptData(res.data));
  }, [subId]);

  const copyScript = () => {
    if (scriptData) {
      navigator.clipboard.writeText(scriptData.script);
      toast.success('Script copied to clipboard');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="glass-card w-full max-w-4xl max-h-[90vh] flex flex-col relative">
        <div className="p-6 border-b border-dark-400/30 flex items-center justify-between">
          <h2 className="text-xl font-bold">Install Apps Script</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>
        
        <div className="p-6 overflow-y-auto flex-1">
          <p className="text-gray-300 mb-4 text-sm">
            1. Open your Google Sheet<br/>
            2. Go to <b>Extensions &gt; Apps Script</b><br/>
            3. Paste the code below<br/>
            4. Click the Run button on the <code>setupTrigger</code> function to install it!
          </p>

          {!scriptData ? <p className="text-gray-500">Loading script...</p> : (
            <div className="relative group">
              <pre className="bg-dark-800 p-4 rounded-xl text-primary-300 text-sm overflow-x-auto border border-dark-400">
                <code>{scriptData.script}</code>
              </pre>
              <button 
                onClick={copyScript}
                className="absolute top-2 right-2 p-2 bg-dark-600 rounded-lg text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-2 text-sm shadow-xl"
              >
                <FiCopy /> Copy
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
