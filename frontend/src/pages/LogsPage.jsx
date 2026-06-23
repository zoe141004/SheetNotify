import { useState, useEffect } from 'react';
import api from '../lib/api';
import { FiCheckCircle, FiXCircle, FiSkipForward } from 'react-icons/fi';

export default function LogsPage() {
  const [logs, setLogs] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, total: 0, pages: 0, per_page: 20 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLogs(1);
  }, []);

  const fetchLogs = async (page) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/logs?page=${page}&per_page=20`);
      setLogs(data.items);
      setPagination({
        page: data.page,
        total: data.total,
        pages: data.pages,
        per_page: data.per_page
      });
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (status) => {
    if (status === 'sent') return <FiCheckCircle className="text-emerald-400 w-5 h-5" />;
    if (status === 'failed') return <FiXCircle className="text-red-400 w-5 h-5" />;
    return <FiSkipForward className="text-yellow-400 w-5 h-5" />;
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-100">Notification Logs</h1>
        <p className="text-gray-400">History of all data received from your Google Sheets.</p>
      </div>

      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-dark-800/50 border-b border-dark-400/50 text-sm text-gray-400">
                <th className="p-4 font-medium">Status</th>
                <th className="p-4 font-medium">Sheet & Tab</th>
                <th className="p-4 font-medium">Row</th>
                <th className="p-4 font-medium">Time (UTC)</th>
                <th className="p-4 font-medium">Data Excerpt</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dark-400/30 text-sm">
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan="5" className="p-8 text-center text-gray-500">Loading logs...</td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan="5" className="p-8 text-center text-gray-500">No logs found.</td>
                </tr>
              ) : (
                logs.map(log => (
                  <tr key={log.id} className="hover:bg-dark-600/30 transition-colors">
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(log.status)}
                        <span className="capitalize text-gray-300">{log.status}</span>
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="font-medium text-gray-200">{log.spreadsheet_name || 'Unknown'}</div>
                      <div className="text-xs text-gray-500">{log.sheet_name}</div>
                    </td>
                    <td className="p-4 text-gray-300">{log.row_number || '-'}</td>
                    <td className="p-4 text-gray-400">
                      {new Date(log.received_at).toLocaleString()}
                    </td>
                    <td className="p-4">
                      <div className="max-w-[250px] truncate text-gray-400 font-mono text-xs bg-dark-800 p-1 rounded border border-dark-400/50">
                        {JSON.stringify(log.row_data).substring(0, 50)}...
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {pagination.pages > 1 && (
          <div className="p-4 border-t border-dark-400/50 flex items-center justify-between">
            <span className="text-sm text-gray-400">
              Showing {(pagination.page - 1) * pagination.per_page + 1} to {Math.min(pagination.page * pagination.per_page, pagination.total)} of {pagination.total}
            </span>
            <div className="flex items-center gap-2">
              <button 
                onClick={() => fetchLogs(pagination.page - 1)}
                disabled={pagination.page === 1}
                className="px-3 py-1 bg-dark-600 rounded text-sm disabled:opacity-50"
              >
                Prev
              </button>
              <button 
                onClick={() => fetchLogs(pagination.page + 1)}
                disabled={pagination.page === pagination.pages}
                className="px-3 py-1 bg-dark-600 rounded text-sm disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
