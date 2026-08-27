import { useState, useEffect } from 'react';
import { getInventory } from '../api/client';
import { Link } from 'react-router-dom';
import { Search, Loader2, Filter, X } from 'lucide-react';

const STATUS_OPTIONS = [
  { label: 'All Statuses', value: 'ALL' },
  { label: 'SAFE (> 7 days)', value: 'SAFE' },
  { label: 'NEAR EXPIRY (2 to 7 days)', value: 'NEAR_EXPIRY' },
  { label: 'CRITICAL (6h to 2 days)', value: 'CRITICAL' },
  { label: 'DONATION (within 6h)', value: 'DONATION' },
  { label: 'EXPIRED', value: 'EXPIRED' },
];

export default function Inventory() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [showFilterDropdown, setShowFilterDropdown] = useState(false);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const limit = 20;

  const fetchInventoryData = async (searchQuery, statusVal, pageIndex) => {
    setLoading(true);
    setError(null);
    try {
      const offset = pageIndex * limit;
      const res = await getInventory(limit, offset, searchQuery, statusVal);
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInventoryData(search, statusFilter, page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, statusFilter]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(0);
    fetchInventoryData(search, statusFilter, 0);
  };

  const handleClearFilters = () => {
    setSearch('');
    setStatusFilter('ALL');
    setPage(0);
    fetchInventoryData('', 'ALL', 0);
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'SAFE':
        return <span className="badge badge-success px-2 py-0.5 text-xs font-semibold">SAFE</span>;
      case 'NEAR_EXPIRY':
        return <span className="badge bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 px-2 py-0.5 text-xs font-semibold">NEAR EXPIRY</span>;
      case 'CRITICAL':
        return <span className="badge bg-orange-500/20 text-orange-400 border border-orange-500/30 px-2 py-0.5 text-xs font-semibold">CRITICAL</span>;
      case 'DONATION':
        return <span className="badge bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-0.5 text-xs font-semibold animate-pulse">DONATION</span>;
      case 'EXPIRED':
        return <span className="badge badge-danger px-2 py-0.5 text-xs font-semibold">EXPIRED</span>;
      default:
        return <span className="badge badge-neutral">{status}</span>;
    }
  };

  const isFiltered = search.trim().length > 0 || statusFilter !== 'ALL';

  return (
    <div>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold">Inventory Batches</h1>
          <p className="text-sm text-muted">Real-time inventory tracking with dynamic expiry status recalculation.</p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Search Bar */}
          <form onSubmit={handleSearchSubmit} className="flex gap-2">
            <div className="relative">
              <input
                type="text"
                className="form-input text-sm pl-9 pr-3 py-1.5"
                placeholder="Search Product, SKU, Batch, Manufacturer..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ minWidth: '260px' }}
              />
              <Search className="absolute left-3 top-2.5 text-gray-400" size={14} />
            </div>
            <button type="submit" className="btn btn-primary text-sm flex items-center gap-1 py-1.5">
              Search
            </button>
          </form>

          {/* Filter Dropdown Toggle Button */}
          <div className="relative">
            <button
              type="button"
              className={`btn ${statusFilter !== 'ALL' ? 'btn-primary' : 'btn-secondary'} text-sm flex items-center gap-1.5 py-1.5`}
              onClick={() => setShowFilterDropdown(!showFilterDropdown)}
            >
              <Filter size={15} />
              Filter: {STATUS_OPTIONS.find((o) => o.value === statusFilter)?.label.split(' ')[0]}
            </button>

            {showFilterDropdown && (
              <div className="absolute right-0 mt-2 w-64 bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50 p-2">
                <div className="text-xs font-semibold text-gray-400 px-3 py-1.5 uppercase tracking-wider">
                  Filter by Expiry Status
                </div>
                {STATUS_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    className={`w-full text-left px-3 py-2 text-xs rounded-md transition flex items-center justify-between ${
                      statusFilter === opt.value
                        ? 'bg-accent/20 text-accent font-bold'
                        : 'text-gray-300 hover:bg-gray-800'
                    }`}
                    onClick={() => {
                      setStatusFilter(opt.value);
                      setPage(0);
                      setShowFilterDropdown(false);
                    }}
                  >
                    <span>{opt.label}</span>
                    {statusFilter === opt.value && <span className="text-accent">•</span>}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Clear Filters Button */}
          {isFiltered && (
            <button
              type="button"
              className="btn btn-secondary text-sm flex items-center gap-1 text-gray-300 hover:text-white py-1.5"
              onClick={handleClearFilters}
              title="Clear Search and Status Filters"
            >
              <X size={15} /> Clear Filters
            </button>
          )}
        </div>
      </div>

      {error && <div className="alert alert-error mb-4">{error}</div>}

      {/* Results Header Count */}
      <div className="flex justify-between items-center mb-3 px-1 text-xs text-muted">
        <div>
          Showing <span className="font-semibold text-white">{total > 0 ? page * limit + 1 : 0}</span> to{' '}
          <span className="font-semibold text-white">{Math.min((page + 1) * limit, total)}</span> of{' '}
          <span className="font-semibold text-white">{total}</span> batches
          {isFiltered && <span className="text-accent font-medium ml-1">(Filtered)</span>}
        </div>
      </div>

      <div className="card">
        {loading ? (
          <div className="flex justify-center items-center py-16">
            <Loader2 className="animate-spin text-accent" size={32} />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-16 text-muted">
            <p className="text-base font-semibold mb-1">No matching inventory batches found.</p>
            <p className="text-xs">Try clearing filters or adjusting your search query.</p>
            {isFiltered && (
              <button
                className="btn btn-secondary text-xs mt-3"
                onClick={handleClearFilters}
              >
                Clear Filters
              </button>
            )}
          </div>
        ) : (
          <div className="table-wrapper overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-gray-700 text-xs font-semibold text-gray-400">
                  <th className="py-3 px-3">Product</th>
                  <th className="py-3 px-3">SKU</th>
                  <th className="py-3 px-3">Batch / Lot</th>
                  <th className="py-3 px-3">Stock</th>
                  <th className="py-3 px-3">MFG Date</th>
                  <th className="py-3 px-3">Expiry Date</th>
                  <th className="py-3 px-3">Remaining Shelf Life</th>
                  <th className="py-3 px-3">MRP / Base Price</th>
                  <th className="py-3 px-3">AI Dynamic Discount</th>
                  <th className="py-3 px-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 text-sm">
                {items.map((item) => (
                  <tr key={item.internal_batch_id} className="hover:bg-gray-800/50 transition">
                    <td className="py-3 px-3 font-semibold text-white">
                      <Link to={`/inventory/${encodeURIComponent(item.sku)}`} className="hover:text-accent transition">
                        {item.product_name}
                      </Link>
                      {item.manufacturer && (
                        <div className="text-xs text-muted font-normal">{item.manufacturer}</div>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      <Link to={`/inventory/${encodeURIComponent(item.sku)}`} className="text-accent hover:underline font-mono text-xs">
                        {item.sku}
                      </Link>
                    </td>
                    <td className="py-3 px-3">
                      {item.batch_number ? (
                        <span className="bg-gray-800 border border-gray-700 px-2 py-0.5 rounded text-xs font-mono text-gray-200">
                          {item.batch_number}
                        </span>
                      ) : (
                        <span className="text-muted text-xs italic">N/A</span>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      <span className="font-mono font-bold text-white">{item.stock_quantity}</span>
                    </td>
                    <td className="py-3 px-3 text-muted text-xs">
                      {item.manufacturing_date || '-'}
                    </td>
                    <td className="py-3 px-3 text-xs font-mono">
                      {item.expiry_date}
                    </td>
                    <td className="py-3 px-3 text-xs font-medium">
                      <span className={
                        item.status === 'EXPIRED' ? 'text-rose-400 font-semibold' :
                        item.status === 'DONATION' ? 'text-purple-300 font-semibold' :
                        item.status === 'CRITICAL' ? 'text-orange-400 font-semibold' :
                        item.status === 'NEAR_EXPIRY' ? 'text-yellow-400' :
                        'text-emerald-400'
                      }>
                        {item.remaining_text || '-'}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-xs font-mono">
                      {item.mrp != null ? `₹${item.mrp.toFixed(2)}` : (item.base_price != null ? `₹${item.base_price.toFixed(2)}` : '-')}
                    </td>
                    <td className="py-3 px-3">
                      {item.is_override ? (
                        item.override_reason === 'EXPIRED' ? (
                          <span className="badge bg-rose-500/20 text-rose-400 border border-rose-500/30 px-2 py-0.5 text-xs font-semibold">
                            N/A (EXPIRED)
                          </span>
                        ) : (
                          <span className="badge bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-0.5 text-xs font-semibold animate-pulse">
                            NGO RELIEF (100%)
                          </span>
                        )
                      ) : (
                        <div>
                          <span className="badge bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 text-xs font-bold font-mono">
                            ▼ {item.dynamic_discount_percent != null ? item.dynamic_discount_percent.toFixed(0) : 0}% OFF
                          </span>
                          <div className="text-xs text-white font-mono font-semibold mt-0.5">
                            ₹{item.final_price != null ? item.final_price.toFixed(2) : (item.mrp || item.base_price || 0).toFixed(2)}
                          </div>
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      {getStatusBadge(item.status, item.remaining_text)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {total > 0 && (
          <div className="flex justify-between items-center mt-4 pt-3 border-t border-gray-700">
            <div className="text-xs text-muted">
              Page {page + 1} of {Math.ceil(total / limit) || 1}
            </div>
            <div className="flex gap-2">
              <button 
                className="btn btn-secondary text-xs" 
                disabled={page === 0} 
                onClick={() => setPage(p => p - 1)}
              >
                Previous
              </button>
              <button 
                className="btn btn-secondary text-xs" 
                disabled={(page + 1) * limit >= total} 
                onClick={() => setPage(p => p + 1)}
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
