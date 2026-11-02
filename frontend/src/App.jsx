import React, { useEffect, useState } from 'react';
import { Zap, DollarSign, AlertTriangle, RefreshCw, CheckCircle2, Clock, XCircle } from 'lucide-react';

export default function App() {
  const [data, setData] = useState({ total_revenue: 0, open_tickets: 0, tickets: [], payments: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:3000/api/dashboard-data');
      if (!res.ok) throw new Error('Failed to fetch dashboard data');
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 10000);
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = (status) => {
    switch (status) {
      case 'PAID':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 flex items-center gap-1"><CheckCircle2 size={12}/> PAID</span>;
      case 'PENDING':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 flex items-center gap-1"><Clock size={12}/> PENDING</span>;
      case 'CANCELLED':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 flex items-center gap-1"><XCircle size={12}/> CANCELLED</span>;
      case 'OPEN':
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-orange-100 text-orange-800 flex items-center gap-1"><AlertTriangle size={12}/> OPEN</span>;
      default:
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-800">{status}</span>;
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* Header */}
      <header className="bg-emerald-700 text-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <div className="flex items-center space-x-3">
            <div className="bg-white p-2 rounded-xl text-emerald-700 shadow">
              <Zap size={24} />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">M-Paya Energy</h1>
              <p className="text-xs text-emerald-200">Landlord & Tenant Sub-Meter Management Dashboard</p>
            </div>
          </div>
          <button 
            onClick={fetchDashboardData}
            disabled={loading}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition shadow-sm disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8 space-y-8">
        {error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-xl text-sm shadow-sm">
            Connection error: {error}. Ensure FastAPI backend is running at http://127.0.0.1:3000.
          </div>
        )}

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500">Total Revenue</p>
              <h3 className="text-2xl font-bold text-slate-800 mt-1">KES {data.total_revenue.toLocaleString()}</h3>
            </div>
            <div className="bg-emerald-50 p-3 rounded-xl text-emerald-600">
              <DollarSign size={24} />
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500">Open Tickets</p>
              <h3 className="text-2xl font-bold text-slate-800 mt-1">{data.open_tickets}</h3>
            </div>
            <div className="bg-amber-50 p-3 rounded-xl text-amber-600">
              <AlertTriangle size={24} />
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500">Total Transactions</p>
              <h3 className="text-2xl font-bold text-slate-800 mt-1">{data.payments.length}</h3>
            </div>
            <div className="bg-blue-50 p-3 rounded-xl text-blue-600">
              <Zap size={24} />
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500">Total Fault Reports</p>
              <h3 className="text-2xl font-bold text-slate-800 mt-1">{data.tickets.length}</h3>
            </div>
            <div className="bg-purple-50 p-3 rounded-xl text-purple-600">
              <AlertTriangle size={24} />
            </div>
          </div>
        </div>

        {/* Tables Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Recent Payments */}
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <h2 className="font-semibold text-slate-800">Recent Payments &amp; Tokens</h2>
              <span className="text-xs bg-slate-200 text-slate-700 px-2.5 py-1 rounded-full font-medium">Last 50</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 font-medium border-b border-slate-100">
                    <th className="px-6 py-3">Phone</th>
                    <th className="px-6 py-3">Meter</th>
                    <th className="px-6 py-3">Amount</th>
                    <th className="px-6 py-3">Status</th>
                    <th className="px-6 py-3">Receipt</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.payments.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="px-6 py-8 text-center text-slate-400">No payment records found.</td>
                    </tr>
                  ) : (
                    data.payments.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-50/80 transition">
                        <td className="px-6 py-4 font-medium text-slate-700">{p.phone}</td>
                        <td className="px-6 py-4 text-slate-600">{p.meter_number}</td>
                        <td className="px-6 py-4 font-semibold text-slate-800">KES {p.amount}</td>
                        <td className="px-6 py-4">{getStatusBadge(p.status)}</td>
                        <td className="px-6 py-4 font-mono text-xs text-slate-500">{p.mpesa_receipt || '—'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Recent Fault Tickets */}
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <h2 className="font-semibold text-slate-800">Recent Fault Tickets</h2>
              <span className="text-xs bg-slate-200 text-slate-700 px-2.5 py-1 rounded-full font-medium">Last 50</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 font-medium border-b border-slate-100">
                    <th className="px-6 py-3">ID</th>
                    <th className="px-6 py-3">Phone</th>
                    <th className="px-6 py-3">Meter</th>
                    <th className="px-6 py-3">Fault</th>
                    <th className="px-6 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.tickets.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="px-6 py-8 text-center text-slate-400">No fault tickets reported.</td>
                    </tr>
                  ) : (
                    data.tickets.map((t) => (
                      <tr key={t.id} className="hover:bg-slate-50/80 transition">
                        <td className="px-6 py-4 font-mono text-xs font-bold text-slate-600">#TKT-{t.id}</td>
                        <td className="px-6 py-4 font-medium text-slate-700">{t.phone}</td>
                        <td className="px-6 py-4 text-slate-600">{t.meter_number}</td>
                        <td className="px-6 py-4 font-medium text-slate-800">{t.fault_type}</td>
                        <td className="px-6 py-4">{getStatusBadge(t.status)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
