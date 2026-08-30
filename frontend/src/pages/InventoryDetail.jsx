import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getInventoryBySku } from '../api/client';
import { ArrowLeft, Loader2, Package, ShieldCheck, AlertTriangle, AlertCircle, HeartHandshake, XCircle } from 'lucide-react';

export default function InventoryDetail() {
  const { sku } = useParams();
  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getInventoryBySku(sku)
      .then((data) => {
        setProduct(data);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sku]);

  const getStatusPill = (status) => {
    switch (status) {
      case 'SAFE':
        return (
          <span className="status-pill status-safe">
            <ShieldCheck size={13} /> SAFE
          </span>
        );
      case 'WARNING':
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

  if (loading) return <div className="flex justify-center mt-12"><Loader2 className="animate-spin text-teal" size={32} /></div>;

  return (
    <div>
      <div className="mb-6">
        <Link to="/inventory" className="btn btn-secondary text-xs inline-flex items-center gap-2">
          <ArrowLeft size={16} /> Back to Inventory Batches
        </Link>
      </div>

      {error ? (
        <div className="alert alert-error">{error}</div>
      ) : product ? (
        <>
          <div className="card mb-8">
            <div className="flex justify-between items-start mb-6">
              <div>
                <h1 className="mb-1 text-2xl flex items-center gap-3 font-bold text-primary">
                  <Package size={26} className="text-teal" /> {product.product_name}
                </h1>
                <div className="text-muted font-mono text-sm">{product.sku}</div>
              </div>
            </div>

            <div className="stats-grid">
              <div className="stat-card p-4 rounded-xl bg-page">
                <span className="stat-label">Category</span>
                <div className="stat-value text-primary" style={{ fontSize: '1.15rem' }}>{product.category || 'Perishable'}</div>
              </div>
              <div className="stat-card p-4 rounded-xl bg-page">
                <span className="stat-label">Manufacturer</span>
                <div className="stat-value text-primary" style={{ fontSize: '1.15rem' }}>{product.manufacturer || 'Unknown'}</div>
              </div>
              <div className="stat-card p-4 rounded-xl bg-page">
                <span className="stat-label">MRP (Package)</span>
                <div className="stat-value font-mono text-primary" style={{ fontSize: '1.15rem' }}>
                  {product.mrp != null ? `₹${product.mrp.toFixed(2)}` : 'N/A'}
                </div>
              </div>
              <div className="stat-card p-4 rounded-xl bg-page">
                <span className="stat-label">Base Price</span>
                <div className="stat-value font-mono text-teal" style={{ fontSize: '1.15rem' }}>
                  ₹{product.base_price.toFixed(2)}
                </div>
              </div>
            </div>
          </div>

          <h2 className="mb-4 text-xl font-bold border-b border-subtle pb-2">Tracked Batches</h2>

          {product.batches && product.batches.length > 0 ? (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left' }}>Batch / Lot</th>
                      <th style={{ textAlign: 'left' }}>Internal ID</th>
                      <th style={{ textAlign: 'center' }}>MFG Date</th>
                      <th style={{ textAlign: 'center' }}>Expiry Date</th>
                      <th style={{ textAlign: 'center' }}>Stock Quantity</th>
                      <th style={{ textAlign: 'center' }}>Current Discount</th>
                      <th style={{ textAlign: 'center' }}>Daily Demand</th>
                      <th style={{ textAlign: 'center' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {product.batches.map((batch) => (
                      <tr key={batch.id} data-status={batch.status}>
                        <td style={{ textAlign: 'left' }}>
                          {batch.batch_number ? (
                            <span className="bg-page border border-subtle px-2 py-0.5 rounded text-xs font-mono text-primary font-bold">
                              {batch.batch_number}
                            </span>
                          ) : (
                            <span className="text-muted italic text-xs">N/A</span>
                          )}
                        </td>
                        <td style={{ textAlign: 'left' }} className="text-xs text-muted font-mono">{batch.internal_batch_id}</td>
                        <td style={{ textAlign: 'center' }} className="text-xs font-mono text-muted">{batch.manufacturing_date || '-'}</td>
                        <td style={{ textAlign: 'center' }} className="text-xs font-mono font-semibold">
                          {batch.expiry_date}
                        </td>
                        <td style={{ textAlign: 'center' }} className="font-mono text-sm font-bold text-primary">{batch.stock_quantity} units</td>
                        <td style={{ textAlign: 'center' }} className="font-mono font-bold text-gold">{(batch.current_discount * 100).toFixed(0)}% OFF</td>
                        <td style={{ textAlign: 'center' }} className="font-mono font-bold">{batch.daily_demand}</td>
                        <td style={{ textAlign: 'center' }}>
                          {getStatusPill(batch.status)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="card text-center py-8 text-muted">
              No batches found for this product.
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
