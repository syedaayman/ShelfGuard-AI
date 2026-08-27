import { Routes, Route, NavLink } from 'react-router-dom';
import { LayoutDashboard, Package, ScanLine, Tag, Calculator, HeartHandshake, Activity } from 'lucide-react';

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
      <nav className="sidebar">
        <div className="sidebar-brand">
          <Package className="text-accent" />
          ShelfGuard
        </div>
        
        <div className="nav-links">
          <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} end>
            <LayoutDashboard size={20} /> Dashboard
          </NavLink>
          <NavLink to="/inventory" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Package size={20} /> Inventory
          </NavLink>
          <NavLink to="/scanner" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <ScanLine size={20} /> Inventory Scanner
          </NavLink>
          <NavLink to="/pricing" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Tag size={20} /> Pricing
          </NavLink>
          <NavLink to="/tax" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Calculator size={20} /> Tax Ledger
          </NavLink>
          <NavLink to="/ngo" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <HeartHandshake size={20} /> NGO Donations
          </NavLink>
        </div>
        
        <div style={{ marginTop: 'auto' }}>
          <div className="nav-item">
            <Activity size={20} /> API Ready
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
