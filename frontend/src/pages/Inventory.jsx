import { useState, useEffect } from 'react';
import { getInventory } from '../api/client';
import { Link } from 'react-router-dom';
import { Search, Loader2, Filter, X, ShieldCheck, AlertTriangle, AlertCircle, HeartHandshake, XCircle } from 'lucide-react';

const STATUS_CHIPS = [
  { label: 'All Statuses', value: 'ALL' },
  { label: 'SAFE (> 7d)', value: 'SAFE' },
  { label: 'NEAR EXPIRY (2-7d)', value: 'NEAR_EXPIRY' },
  { label: 'CRITICAL (6h-2d)', value: 'CRITICAL' },
  { label: 'DONATION (≤ 6h)', value: 'DONATION' },
  { label: 'EXPIRED', value: 'EXPIRED' },
];

export default function Inventory() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
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

  const getStatusPill = (status) => {
    switch (status) {
      case 'SAFE':
        return (
          <span className="status-pill status-safe">
            <ShieldCheck size={13} /> SAFE
          </span>
        );
      case 'NEAR_EXPIRY':
        return (
          <span className="status-pill status-near-expiry">
            <AlertTriangle size={13} /> NEAR EXPIRY
          </span>
        );
      case 'CRITICAL':
        return (
          <span className="status-pill status-critical">
            <AlertCircle size={13} /> CRITICAL
          </span>
        );
      case 'DONATION':
        return (
          <span className="status-pill status-donation">
            <HeartHandshake size={13} /> DONATION
          </span>
        );
      case 'EXPIRED':
        return (
          <span className="status-pill status-expired">
            <XCircle size={13} /> EXPIRED
          </span>
        );
      default:
        return <span className="status-pill">{status}</span>;
    }
  };

  const isFiltered = search.trim().length > 0 || statusFilter !== 'ALL';

  return (
    <div>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1>Inventory Batches</h1>
          <p className="text-sm text-muted">Real-time inventory tracking with dynamic expiry status recalculation.</p>
        </div>
      </div>

      {/* Search & Filter Card */}
      <div className="card mb-6 p-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <form onSubmit={handleSearchSubmit} className="flex gap-2 flex-1">
            <div className="relative flex-1">
              <input
                type="text"
                className="form-input text-sm pl-9 pr-3"
                placeholder="Search Product, SKU, Batch Number, Manufacturer..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <Search className="absolute left-3 top-3 text-muted" size={16} />
            </div>
            <button type="submit" className="btn btn-secondary text-sm py-2">
              Search
            </button>
          </form>

          {isFiltered && (
            <button
              type="button"
              className="btn btn-ghost text-xs flex items-center gap-1"
              onClick={handleClearFilters}
            >
              <X size={14} /> Clear Filters
            </button>
          )}
        </div>

        {/* Filter Chips Horizontal Row */}
        <div className="flex items-center gap-2 flex-wrap mt-4 pt-3 border-t border-subtle">
          <div className="text-xs font-bold text-muted mr-1 flex items-center gap-1">
            <Filter size={13} /> Filter:
          </div>
          {STATUS_CHIPS.map((chip) => (
            <button
              key={chip.value}
              type="button"
              className={`filter-chip ${statusFilter === chip.value ? 'active' : ''}`}
              onClick={() => {
                setStatusFilter(chip.value);
                setPage(0);
              }}
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="alert alert-error mb-4">{error}</div>}

      {/* Results Header Count */}
      <div className="flex justify-between items-center mb-3 px-1 text-xs text-muted">
        <div>
          Showing <span className="font-bold text-primary font-mono">{total > 0 ? page * limit + 1 : 0}</span> to{' '}
          <span className="font-bold text-primary font-mono">{Math.min((page + 1) * limit, total)}</span> of{' '}
          <span className="font-bold text-primary font-mono">{total}</span> batches
          {isFiltered && <span className="text-teal font-medium ml-1">(Filtered)</span>}
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div className="flex justify-center items-center py-16">
            <Loader2 className="animate-spin text-teal" size={32} />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-16 text-muted">
            <p className="text-base font-bold mb-1 text-primary">No matching inventory batches found.</p>
            <p className="text-xs">Try clearing filters or adjusting your search query.</p>
            {isFiltered && (
              <button className="btn btn-secondary text-xs mt-3" onClick={handleClearFilters}>
                Clear Filters
              </button>
            )}
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>SKU</th>
                  <th>Batch / Lot</th>
                  <th>Stock</th>
                  <th>MFG Date</th>
                  <th>Expiry Date</th>
                  <th>Remaining Shelf Life</th>
                  <th>MRP / Base</th>
                  <th>AI Dynamic Discount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.internal_batch_id} data-status={item.status}>
                    <td className="font-bold">
                      <Link to={`/inventory/${encodeURIComponent(item.sku)}`} className="text-primary hover:text-teal transition">
                        {item.product_name}
                      </Link>
                      {item.manufacturer && (
                        <div className="text-xs text-muted font-normal">{item.manufacturer}</div>
                      )}
                    </td>
                    <td>
                      <Link to={`/inventory/${encodeURIComponent(item.sku)}`} className="text-teal hover:underline font-mono text-xs font-semibold">
                        {item.sku}
                      </Link>
                    </td>
                    <td>
                      {item.batch_number ? (
                        <span className="bg-page border border-subtle px-2 py-0.5 rounded-md text-xs font-mono text-primary font-semibold">
                          {item.batch_number}
                        </span>
                      ) : (
                        <span className="text-muted text-xs italic">N/A</span>
                      )}
                    </td>
                    <td>
                      <span className="font-mono font-bold text-primary">{item.stock_quantity}</span>
                    </td>
                    <td className="text-muted text-xs font-mono">
                      {item.manufacturing_date || '-'}
                    </td>
                    <td className="text-xs font-mono font-semibold">
                      {item.expiry_date}
                    </td>
                    <td className="text-xs font-semibold">
                      <span style={{
                        color: item.status === 'EXPIRED' ? 'var(--status-expired)' :
                               item.status === 'DONATION' ? '#B57F1E' :
                               item.status === 'CRITICAL' ? 'var(--status-critical)' :
                               item.status === 'NEAR_EXPIRY' ? 'var(--status-near-expiry)' :
                               'var(--status-safe)'
                      }}>
                        {item.remaining_text || '-'}
                      </span>
                    </td>
                    <td className="text-xs font-mono">
                      {item.mrp != null ? `₹${item.mrp.toFixed(2)}` : (item.base_price != null ? `₹${item.base_price.toFixed(2)}` : '-')}
                    </td>
                    <td>
                      {/* AI Dynamic Discount Pill Treatment */}
                      {item.is_override ? (
                        item.override_reason === 'EXPIRED' ? (
                          <span className="status-pill status-expired">
                            EXPIRED (0%)
                          </span>
                        ) : (
                          <span className="status-pill status-donation">
                            NGO RELIEF (100%)
                          </span>
                        )
                      ) : (
                        <div className="flex flex-col items-start gap-0.5">
                          <span className="status-pill status-safe font-mono" style={{ fontSize: '11px' }}>
                            ▼ {item.dynamic_discount_percent != null ? item.dynamic_discount_percent.toFixed(0) : 0}% OFF
                          </span>
                          <span className="text-xs font-mono font-bold text-primary ml-1">
                            ₹{item.final_price != null ? item.final_price.toFixed(2) : (item.mrp || item.base_price || 0).toFixed(2)}
                          </span>
                        </div>
                      )}
                    </td>
                    <td>
                      {getStatusPill(item.status)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {total > 0 && (
          <div className="flex justify-between items-center p-4 border-t border-subtle">
            <div className="text-xs text-muted">
              Page <span className="font-mono font-bold text-primary">{page + 1}</span> of{' '}
              <span className="font-mono font-bold text-primary">{Math.ceil(total / limit) || 1}</span>
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
