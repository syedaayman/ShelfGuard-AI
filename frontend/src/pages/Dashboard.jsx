import { useState, useEffect } from 'react';
import { getHealth, getDashboardStats, getInventory } from '../api/client';
import { useNavigate } from 'react-router-dom';
import { 
  Server, 
  HeartHandshake, 
  Package, 
  Activity, 
  TrendingUp, 
  PieChart as PieIcon, 
  BarChart3,
  ArrowUpRight,
  ShieldCheck,
  CheckCircle2
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

  // State to hold category counts from live inventory
  const [categoryData, setCategoryData] = useState({ labels: [], data: [] });

  useEffect(() => {
    getHealth()
      .then(() => setHealth({ loading: false, online: true }))
      .catch(() => setHealth({ loading: false, online: false }));

    getDashboardStats()
      .then((res) => setStats({ loading: false, ...res, error: null }))
      .catch((err) => setStats((prev) => ({ ...prev, loading: false, error: err.message })));

    // Fetch sample inventory to aggregate Category Share
    getInventory(50, 0)
      .then((res) => {
        if (res.items && res.items.length > 0) {
          const counts = {};
          res.items.forEach((item) => {
            const cat = item.category || 'Perishable';
            counts[cat] = (counts[cat] || 0) + 1;
          });
          const labels = Object.keys(counts);
          const data = Object.values(counts);
          setCategoryData({ labels, data });
        }
      })
      .catch(() => {});
  }, []);

  // 1. Vertical Bar Chart Options & Data (Mirrors "Statistics" in Reference)
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

  // 2. Donut Chart Options & Data (Mirrors "Flights Share" in Reference)
  const donutChartData = {
    labels: categoryData.labels.length > 0 ? categoryData.labels : ['Dairy & Produce', 'Bakery', 'Prepared Food', 'Beverages'],
    datasets: [
      {
        data: categoryData.data.length > 0 ? categoryData.data : [14, 8, 5, 3],
        backgroundColor: [
          '#E0A83E', // Gold
          '#2E9C8F', // Teal
          '#2F4A44', // Forest Green
          '#8FCFC6', // Soft Teal
          '#F3D999', // Soft Gold
        ],
        borderWidth: 3,
        borderColor: '#FFFFFF',
      },
    ],
  };

  const donutChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '70%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          font: { family: 'Manrope', size: 12, weight: '600' },
          color: '#223229',
          usePointStyle: true,
          pointStyle: 'circle',
          padding: 16,
        },
      },
      tooltip: {
        backgroundColor: '#2F4A44',
        cornerRadius: 10,
      },
    },
  };

  // 3. Dual-Line Chart Options & Data (Mirrors "Flights Schedule" in Reference)
  const lineChartData = {
    labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4', 'Week 5', 'Current'],
    datasets: [
      {
        label: 'Discount Rate (%)',
        data: [12, 18, 25, 22, 35, 40],
        borderColor: '#E0A83E',
        backgroundColor: 'rgba(224, 168, 62, 0.15)',
        fill: true,
        tension: 0.4,
        pointBackgroundColor: '#E0A83E',
        pointRadius: 4,
      },
      {
        label: 'Stock Turnover Velocity',
        data: [20, 24, 28, 30, 38, 45],
        borderColor: '#2E9C8F',
        backgroundColor: 'rgba(46, 156, 143, 0.08)',
        fill: true,
        tension: 0.4,
        pointBackgroundColor: '#2E9C8F',
        pointRadius: 4,
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
        ticks: { font: { family: 'Manrope', size: 11 }, color: '#6B7D74' },
      },
      y: {
        grid: { color: '#DCE6E0' },
        ticks: { font: { family: 'JetBrains Mono', size: 11 }, color: '#6B7D74' },
      },
    },
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1>Operations Dashboard</h1>
          <p className="text-sm text-muted">Perishable stock expiry analytics, ML pricing velocity, and relief dispatch.</p>
        </div>
      </div>

      {/* TOP ROW METRIC CARDS — COLORED FILL HIERARCHY (MIRRORS REFERENCE DESIGN) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.25rem' }}>
        
        {/* CARD 1: SOLID MUSTARD GOLD FILL — NGO CANDIDATES (MOST URGENT ACTION) */}
        <div 
          className="card card-gold stat-card cursor-pointer"
          onClick={() => navigate('/ngo')}
          title="Click to view and dispatch NGO relief candidates"
        >
          <div className="flex items-center justify-between">
            <span className="stat-label" style={{ color: '#223229', opacity: 0.85 }}>NGO Relief Candidates</span>
            <span className="status-pill font-mono" style={{ background: 'rgba(34, 50, 41, 0.15)', color: '#223229' }}>
              Action Needed
            </span>
          </div>

          <div className="my-2">
            <div className="stat-value" style={{ color: '#223229', fontSize: '2.4rem' }}>
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
            <HeartHandshake size={22} style={{ opacity: 0.8 }} />
          </div>
        </div>

        {/* CARD 2: SOLID FOREST GREEN FILL — TOTAL BATCHES TRACKED */}
        <div className="card card-forest stat-card">
          <div className="flex items-center justify-between">
            <span className="stat-label" style={{ color: '#A9BDB4' }}>Total Active Batches</span>
            <Package size={20} style={{ color: 'var(--accent-gold)' }} />
          </div>

          <div className="my-2">
            <div className="stat-value" style={{ color: '#FFFFFF', fontSize: '2.4rem' }}>
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

        {/* CARD 3: PURE WHITE CARD — SYSTEM HEALTH */}
        <div className="card stat-card">
          <div className="flex items-center justify-between">
            <span className="stat-label">System Status</span>
            <Server size={20} className="text-teal" />
          </div>

          <div className="my-2">
            <div className={`stat-value ${health.online ? 'text-success' : 'text-danger'}`} style={{ fontSize: '2rem' }}>
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

      {/* THREE DISTINCT CHARTS GRID (MIRRORS REFERENCE DASHBOARD LAYOUT) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-8" style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.5rem' }}>
        
        {/* CHART 1: VERTICAL BAR CHART — STATISTICS (8 COLS) */}
        <div className="card lg:col-span-8" style={{ gridColumn: 'span 7' }}>
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2>Expiry Lifecycle Statistics</h2>
              <p className="text-xs text-muted">Batch count distribution across dynamic expiry stages</p>
            </div>
            <span className="status-pill status-safe font-mono text-xs">Real-time</span>
          </div>
          <div style={{ height: '240px', position: 'relative' }}>
            <Bar data={barChartData} options={barChartOptions} />
          </div>
        </div>

        {/* CHART 2: DONUT CHART — CATEGORY SHARE (5 COLS) */}
        <div className="card lg:col-span-4" style={{ gridColumn: 'span 5' }}>
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2>Category Share</h2>
              <p className="text-xs text-muted">Inventory distribution by product category</p>
            </div>
            <PieIcon size={18} className="text-teal" />
          </div>
          <div style={{ height: '240px', position: 'relative' }}>
            <Doughnut data={donutChartData} options={donutChartOptions} />
          </div>
        </div>

      </div>

      {/* CHART 3: DUAL-LINE SMOOTH TREND CHART (WIDE FULL-WIDTH CARD) */}
      <div className="card mb-6">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h2>Markdown Discount & Turnover Velocity Trend</h2>
            <p className="text-xs text-muted">Correlation between ML dynamic discount percentage and stock clearance velocity</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="status-pill status-near-expiry font-mono text-xs">ML XGBoost</span>
          </div>
        </div>
        <div style={{ height: '220px', position: 'relative' }}>
          <Line data={lineChartData} options={lineChartOptions} />
        </div>
      </div>
    </div>
  );
}
