import { useState, useEffect } from 'react';
import { getHealth, getDashboardStats } from '../api/client';
import { useNavigate } from 'react-router-dom';
import { Activity, Server, HeartHandshake, ShieldCheck, AlertTriangle, AlertCircle, XCircle } from 'lucide-react';

export default function Dashboard() {
  const navigate = useNavigate();
  const [health, setHealth] = useState({ loading: true, online: false });
  const [stats, setStats] = useState({
    loading: true,
    total_inventory_items: 0,
    safe_count: 0,
    near_expiry_count: 0,
    critical_count: 0,
    donation_count: 0,
    expired_count: 0,
    ngo_candidates: 0,
    donation_units_count: 0,
    error: null,
  });

  useEffect(() => {
    getHealth()
      .then(() => setHealth({ loading: false, online: true }))
      .catch(() => setHealth({ loading: false, online: false }));

    getDashboardStats()
      .then((res) => setStats({ loading: false, ...res, error: null }))
      .catch((err) => setStats((prev) => ({ ...prev, loading: false, error: err.message })));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-muted">Real-time inventory status, shelf-life analytics & NGO relief routing.</p>
        </div>
      </div>

      <div className="stats-grid mb-8">
        {/* System Health */}
        <div className="card stat-card">
          <div className="flex items-center gap-2 mb-2">
            <Server className="text-accent" size={20} />
            <span className="stat-label">System Health</span>
          </div>
          {health.loading ? (
            <div className="stat-value text-muted">Checking...</div>
          ) : (
            <div className={`stat-value ${health.online ? 'text-success' : 'text-danger'}`}>
              {health.online ? 'Online' : 'Offline'}
            </div>
          )}
        </div>

        {/* Total Inventory Items */}
        <div className="card stat-card">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="text-accent" size={20} />
            <span className="stat-label">Total Batches</span>
          </div>
          {stats.loading ? (
            <div className="stat-value text-muted">...</div>
          ) : stats.error ? (
            <div className="stat-value text-danger" style={{ fontSize: '1rem' }}>Error</div>
          ) : (
            <div className="stat-value">{stats.total_inventory_items}</div>
          )}
        </div>

        {/* NGO Candidates Card - Clickable */}
        <div
          className="card stat-card cursor-pointer hover:border-amber-400 transition-all shadow-md hover:shadow-lg"
          onClick={() => navigate('/ngo-donations')}
          style={{ cursor: 'pointer', border: '1px solid rgba(245, 158, 11, 0.4)' }}
          title="Click to view & dispatch NGO donation candidates"
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <HeartHandshake className="text-amber-400" size={22} />
              <span className="stat-label text-amber-300 font-semibold">NGO Candidates</span>
            </div>
            <span className="text-xs bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-mono">
              Action Required
            </span>
          </div>
          {stats.loading ? (
            <div className="stat-value text-muted">...</div>
          ) : (
            <div>
              <div className="stat-value text-amber-400">
                {stats.ngo_candidates} <span className="text-sm font-normal text-muted">batches</span>
              </div>
              <div className="text-xs text-muted mt-1">
                {stats.donation_units_count} units available within 6h expiry
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Expiry Breakdown Grid */}
      <h2 className="text-lg font-semibold mb-4">Inventory Expiry Status Breakdown</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card p-4 border-l-4 border-emerald-500">
          <div className="flex items-center gap-2 mb-1">
            <ShieldCheck className="text-emerald-400" size={18} />
            <span className="text-xs font-semibold text-muted">SAFE (&gt; 7 days)</span>
          </div>
          <div className="text-2xl font-bold text-emerald-400">
            {stats.loading ? '...' : stats.safe_count}
          </div>
        </div>

        <div className="card p-4 border-l-4 border-yellow-500">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="text-yellow-400" size={18} />
            <span className="text-xs font-semibold text-muted">NEAR EXPIRY (2-7 days)</span>
          </div>
          <div className="text-2xl font-bold text-yellow-400">
            {stats.loading ? '...' : stats.near_expiry_count}
          </div>
        </div>

        <div className="card p-4 border-l-4 border-orange-500">
          <div className="flex items-center gap-2 mb-1">
            <AlertCircle className="text-orange-400" size={18} />
            <span className="text-xs font-semibold text-muted">CRITICAL (6h - 2 days)</span>
          </div>
          <div className="text-2xl font-bold text-orange-400">
            {stats.loading ? '...' : stats.critical_count}
          </div>
        </div>

        <div className="card p-4 border-l-4 border-rose-500">
          <div className="flex items-center gap-2 mb-1">
            <XCircle className="text-rose-400" size={18} />
            <span className="text-xs font-semibold text-muted">EXPIRED</span>
          </div>
          <div className="text-2xl font-bold text-rose-400">
            {stats.loading ? '...' : stats.expired_count}
          </div>
        </div>
      </div>
    </div>
  );
}
