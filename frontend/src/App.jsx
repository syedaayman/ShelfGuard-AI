import { Routes, Route, NavLink } from 'react-router-dom';
import { LayoutDashboard, Package, ScanLine, Tag, Calculator, HeartHandshake, ShieldCheck } from 'lucide-react';

import Dashboard from './pages/Dashboard';
import Inventory from './pages/Inventory';
import InventoryDetail from './pages/InventoryDetail';
import ExpiryScanner from './pages/ExpiryScanner';
import Pricing from './pages/Pricing';
import Tax from './pages/Tax';
import NgoDonations from './pages/NgoDonations';

function App() {
  return (
    <div className="app-container">
      {/* Floating Deep Forest Green Sidebar */}
      <nav className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <ShieldCheck size={20} strokeWidth={2.5} />
          </div>
          <span>ShelfGuard</span>
        </div>
        
        <div className="nav-links">
          <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} end>
            <LayoutDashboard size={19} strokeWidth={2} /> Dashboard
          </NavLink>
          <NavLink to="/inventory" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Package size={19} strokeWidth={2} /> Inventory Batches
          </NavLink>
          <NavLink to="/scanner" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <ScanLine size={19} strokeWidth={2} /> Inventory Scanner
          </NavLink>
          <NavLink to="/pricing" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Tag size={19} strokeWidth={2} /> Dynamic Pricing
          </NavLink>
          <NavLink to="/tax" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Calculator size={19} strokeWidth={2} /> Tax Ledger
          </NavLink>
          <NavLink to="/ngo" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <HeartHandshake size={19} strokeWidth={2} /> NGO Relief Router
          </NavLink>
        </div>
        
        {/* NGO Partners Active Cluster (Mirrors "Active Users +70" in Reference Design) */}
        <div className="sidebar-partners">
          <div className="sidebar-partners-title">NGO Relief Partners</div>
          <div className="avatar-group">
            <div className="avatar avatar-gold" title="Feeding India (Zomato)">FI</div>
            <div className="avatar" title="Robin Hood Army">RH</div>
            <div className="avatar" title="Akshaya Patra">AP</div>
            <div className="avatar" title="Roti Bank Foundation">RB</div>
            <div className="avatar avatar-count" title="No Food Waste & 5 More Partner Organizations">+5</div>
          </div>
        </div>
      </nav>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/inventory/:sku" element={<InventoryDetail />} />
          <Route path="/scanner" element={<ExpiryScanner />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/tax" element={<Tax />} />
          <Route path="/ngo" element={<NgoDonations />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
