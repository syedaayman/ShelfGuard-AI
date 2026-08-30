import { useState, useEffect } from 'react';
import { 
  getHealth, 
  getDashboardStats, 
  getDashboardCategories, 
  getDashboardTrends 
} from '../api/client';
import { useNavigate } from 'react-router-dom';
import { 
  Server, 
  HeartHandshake, 
  Package, 
  TrendingUp, 
  PieChart as PieIcon, 
  ArrowUpRight, 
  CheckCircle2,
  RefreshCw
} from 'lucide-react';
import AnimatedCounter from '../components/AnimatedCounter';

// Import Chart.js and react-chartjs-2
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
  PointElement,
  LineElement,
  Filler,
} from 'chart.js';
import { Bar, Doughnut, Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
  PointElement,
  LineElement,
  Filler
);

const CATEGORY_COLORS = [
  '#E0A83E', // Gold
  '#2E9C8F', // Teal
  '#2F4A44', // Forest Green
  '#8FCFC6', // Soft Teal
  '#F3D999', // Soft Gold
  '#D9752E', // Amber Orange
  '#4A7C59', // Sage Green
  '#C15C4A', // Coral
  '#6B7D74', // Slate
  '#3E8E7E', // Emerald Teal
  '#B57F1E', // Dark Gold
  '#5C6B73', // Steel
];

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

  // State to hold category counts from full database aggregation
  const [categoryData, setCategoryData] = useState({ labels: [], data: [], totalBatches: 0 });

  // State to hold dynamic ML discount & demand velocity trends
  const [trendsData, setTrendsData] = useState({
    labels: [],
    discount_rates: [],
    demand_velocities: [],
    summary_insight: '',
  });

  const fetchAllDashboardData = () => {
    getHealth()
      .then(() => setHealth({ loading: false, online: true }))
      .catch(() => setHealth({ loading: false, online: false }));

    getDashboardStats()
      .then((res) => setStats({ loading: false, ...res, error: null }))
      .catch((err) => setStats((prev) => ({ ...prev, loading: false, error: err.message })));

    // Fetch full-database aggregated category share
    getDashboardCategories()
      .then((res) => {
        if (res.items && res.items.length > 0) {
          const labels = res.items.map((item) => item.category);
          const data = res.items.map((item) => item.count);
          setCategoryData({ labels, data, totalBatches: res.total_batches || 0 });
        } else {
          setCategoryData({ labels: [], data: [], totalBatches: 0 });
        }
      })
      .catch(() => setCategoryData({ labels: [], data: [], totalBatches: 0 }));

    // Fetch dynamic XGBoost dynamic discount & demand velocity profile
    getDashboardTrends()
      .then((res) => {
        if (res.labels && res.labels.length > 0) {
          setTrendsData({
            labels: res.labels,
            discount_rates: res.discount_rates,
            demand_velocities: res.demand_velocities,
            summary_insight: res.summary_insight,
          });
        } else {
          setTrendsData({
            labels: [],
            discount_rates: [],
            demand_velocities: [],
            summary_insight: '',
          });
        }
      })
      .catch(() =>
        setTrendsData({
          labels: [],
          discount_rates: [],
          demand_velocities: [],
          summary_insight: '',
        })
      );
  };

  useEffect(() => {
    fetchAllDashboardData();
    // 6-second auto-refresh interval for live inventory state sync
    const interval = setInterval(fetchAllDashboardData, 6000);
    return () => clearInterval(interval);
  }, []);

  // 1. Vertical Bar Chart Options & Data (Expiry Lifecycle Distribution)
  const barChartData = {
    labels: ['Safe (>7d)', 'Near Expiry', 'Critical (6h-2d)', 'Donation (≤6h)', 'Expired'],
    datasets: [
      {
        label: 'Batches',
        data: [
          stats.safe_count, 
          stats.near_expiry_count, 
          stats.critical_count, 
          stats.donation_count, 
          stats.expired_count
        ],
        backgroundColor: [
          '#3E8E7E', // Safe Teal
          '#E0A83E', // Gold
          '#D9752E', // Critical Orange
          '#B57F1E', // Donation Amber
          '#C15C4A', // Expired Coral
        ],
        borderRadius: 8,
        borderSkipped: false,
      },
    ],
  };

  const barChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#2F4A44',
        titleFont: { family: 'Manrope', size: 13, weight: 'bold' },
        bodyFont: { family: 'Inter', size: 12 },
        padding: 10,
        cornerRadius: 10,
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { font: { family: 'Manrope', size: 11, weight: '600' }, color: '#6B7D74' },
      },
      y: {
        grid: { color: '#DCE6E0' },
        ticks: { font: { family: 'JetBrains Mono', size: 11 }, color: '#6B7D74' },
      },
    },
  };

  // 2. Donut Chart Options & Data (Real Full-Database Category Share)
  const donutChartData = {
    labels: categoryData.labels,
    datasets: [
      {
        data: categoryData.data,
        backgroundColor: categoryData.labels.map((_, i) => CATEGORY_COLORS[i % CATEGORY_COLORS.length]),
        borderWidth: 2,
        borderColor: '#FFFFFF',
      },
    ],
  };

  const donutChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '68%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          font: { family: 'Manrope', size: 11, weight: '600' },
          color: '#223229',
          usePointStyle: true,
          pointStyle: 'circle',
          padding: 12,
        },
      },
      tooltip: {
        backgroundColor: '#2F4A44',
        cornerRadius: 10,
        callbacks: {
          label: (context) => {
            const count = context.parsed;
            const total = categoryData.totalBatches || categoryData.data.reduce((a, b) => a + b, 0);
            const pct = total > 0 ? ((count / total) * 100).toFixed(1) : 0;
            return ` ${context.label}: ${count} batches (${pct}%)`;
          },
        },
      },
    },
  };

  // 3. Dynamic XGBoost Dynamic Markdown & Demand Velocity Profile
  const lineChartData = {
    labels: trendsData.labels,
    datasets: [
      {
        label: 'Average Dynamic Markdown (%)',
        data: trendsData.discount_rates,
        borderColor: '#E0A83E',
        backgroundColor: 'rgba(224, 168, 62, 0.15)',
        fill: true,
        tension: 0.35,
        pointBackgroundColor: '#E0A83E',
        pointRadius: 5,
        pointHoverRadius: 7,
      },
      {
        label: 'Average Demand Velocity (units/day)',
        data: trendsData.demand_velocities,
        borderColor: '#2E9C8F',
        backgroundColor: 'rgba(46, 156, 143, 0.08)',
        fill: true,
        tension: 0.35,
        pointBackgroundColor: '#2E9C8F',
        pointRadius: 5,
        pointHoverRadius: 7,
      },
    ],
  };

  const lineChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        align: 'end',
        labels: {
          font: { family: 'Manrope', size: 11, weight: '600' },
          color: '#6B7D74',
          usePointStyle: true,
        },
      },
      tooltip: {
        backgroundColor: '#2F4A44',
        titleFont: { family: 'Manrope', size: 12, weight: 'bold' },
        bodyFont: { family: 'JetBrains Mono', size: 12 },
        padding: 12,
        cornerRadius: 12,
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { font: { family: 'Manrope', size: 11, weight: '600' }, color: '#6B7D74' },
      },
      y: {
        grid: { color: '#DCE6E0' },
        ticks: { font: { family: 'JetBrains Mono', size: 11 }, color: '#6B7D74' },
      },
    },
  };

  return (
    <div>
      {/* PAGE HEADER */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1>Operations Dashboard</h1>
          <p className="text-sm text-muted">Perishable stock expiry analytics, ML pricing velocity, and relief dispatch.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="status-pill font-mono text-xs text-muted flex items-center gap-1.5 bg-card border border-subtle">
            <RefreshCw size={11} className="text-teal" /> Auto-sync (6s)
          </span>
        </div>
      </div>

      {/* TOP ROW METRIC CARDS — EQUAL HEIGHT & ALIGNED INTERNAL PADDING */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.25rem' }}>
        
        {/* CARD 1: NGO CANDIDATES */}
        <div 
          className="card card-gold stat-card cursor-pointer"
          onClick={() => navigate('/ngo')}
          title="Click to view and dispatch NGO relief candidates"
          style={{ minHeight: '160px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}
        >
          <div className="flex items-center justify-between">
            <span className="stat-label" style={{ color: '#223229', opacity: 0.85 }}>NGO Relief Candidates</span>
            <span className="status-pill font-mono" style={{ background: 'rgba(34, 50, 41, 0.15)', color: '#223229' }}>
              Action Needed
            </span>
          </div>

          <div className="my-1">
            <div className="stat-value" style={{ color: '#223229', fontSize: '2.2rem' }}>
              <AnimatedCounter value={stats.ngo_candidates} /> <span className="text-sm font-normal opacity-80">batches</span>
            </div>
            <div className="text-xs font-mono mt-1 font-semibold" style={{ color: '#223229' }}>
              <AnimatedCounter value={stats.donation_units_count} /> units eligible for dispatch (&le;6h)
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t" style={{ borderColor: 'rgba(34, 50, 41, 0.15)' }}>
            <span className="text-xs font-bold flex items-center gap-1">
              Dispatch Relief Items <ArrowUpRight size={14} />
            </span>
            <HeartHandshake size={20} style={{ opacity: 0.8 }} />
          </div>
        </div>

        {/* CARD 2: TOTAL BATCHES TRACKED */}
        <div 
          className="card card-forest stat-card"
          style={{ minHeight: '160px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}
        >
          <div className="flex items-center justify-between">
            <span className="stat-label" style={{ color: '#A9BDB4' }}>Total Active Batches</span>
            <Package size={20} style={{ color: 'var(--accent-gold)' }} />
          </div>

          <div className="my-1">
            <div className="stat-value" style={{ color: '#FFFFFF', fontSize: '2.2rem' }}>
              {stats.loading ? '...' : <AnimatedCounter value={stats.total_inventory_items} />}
            </div>
            <div className="text-xs text-muted mt-1 font-mono" style={{ color: '#A9BDB4' }}>
              Live SQLite product inventory records
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t" style={{ borderColor: 'rgba(255, 255, 255, 0.1)' }}>
            <span className="text-xs text-muted" style={{ color: '#A9BDB4' }}>Tracked & Evaluated</span>
            <span className="status-pill status-safe" style={{ fontSize: '10px' }}>Active</span>
          </div>
        </div>

        {/* CARD 3: SYSTEM HEALTH */}
        <div 
          className="card stat-card"
          style={{ minHeight: '160px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}
        >
          <div className="flex items-center justify-between">
            <span className="stat-label">System Status</span>
            <Server size={20} className="text-teal" />
          </div>

          <div className="my-1">
            <div className={`stat-value ${health.online ? 'text-success' : 'text-danger'}`} style={{ fontSize: '1.85rem' }}>
              {health.loading ? 'Checking...' : (health.online ? 'Operational' : 'Offline')}
            </div>
            <div className="text-xs text-muted mt-1 font-mono">
              FastAPI Engine & Database Engine
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-subtle">
            <span className="text-xs text-muted flex items-center gap-1">
              <CheckCircle2 size={13} className="text-success" /> API Connected
            </span>
            <span className="text-xs font-mono text-muted">v1.0</span>
          </div>
        </div>

      </div>

      {/* CHARTS GRID */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-8" style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.5rem' }}>
        
        {/* CHART 1: VERTICAL BAR CHART — LIFECYCLE STATISTICS */}
        <div className="card lg:col-span-8" style={{ gridColumn: 'span 7' }}>
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2>Expiry Lifecycle Statistics</h2>
              <p className="text-xs text-muted">Batch count distribution across dynamic expiry stages</p>
            </div>
            <span className="status-pill status-safe font-mono text-xs">IST Clock</span>
          </div>
          <div style={{ height: '260px', position: 'relative' }}>
            <Bar data={barChartData} options={barChartOptions} />
          </div>
        </div>

        {/* CHART 2: DONUT CHART — CATEGORY SHARE */}
        <div className="card lg:col-span-4" style={{ gridColumn: 'span 5' }}>
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2>Category Share</h2>
              <p className="text-xs text-muted">Inventory distribution by product category</p>
            </div>
            <PieIcon size={18} className="text-teal" />
          </div>
          <div style={{ height: '260px', position: 'relative' }}>
            {categoryData.labels.length > 0 ? (
              <Doughnut data={donutChartData} options={donutChartOptions} />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center text-muted py-12">
                <PieIcon size={36} className="opacity-30 mb-2 text-teal" />
                <p className="text-sm font-bold text-primary">No Category Inventory</p>
                <p className="text-xs">Categories will appear here once inventory batches are added.</p>
              </div>
            )}
          </div>
        </div>

      </div>

      {/* CHART 3: DUAL-LINE DYNAMIC PRICING PROFILE */}
      <div className="card mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div>
            <h2>ML Dynamic Markdown & Demand Velocity Profile</h2>
            <p className="text-xs text-muted">
              Live XGBoost markdown discount percentages and sales demand velocities evaluated across expiry risk horizons
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="status-pill status-near-expiry font-mono text-xs">XGBoost ML</span>
          </div>
        </div>
        <div style={{ height: '240px', position: 'relative' }}>
          {trendsData.labels.length > 0 ? (
            <Line data={lineChartData} options={lineChartOptions} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center text-muted py-12">
              <TrendingUp size={36} className="opacity-30 mb-2 text-teal" />
              <p className="text-sm font-bold text-primary">No Active Pricing Horizons</p>
              <p className="text-xs">Dynamic pricing velocity curves will appear as inventory batches populate.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
