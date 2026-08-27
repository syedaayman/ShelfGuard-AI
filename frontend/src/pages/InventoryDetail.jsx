import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getInventoryBySku } from '../api/client';
import { ArrowLeft, Loader2, Package } from 'lucide-react';

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

  if (loading) return <div className="flex justify-center mt-12"><Loader2 className="animate-spin text-accent" size={32} /></div>;

  return (
    <div>
      <div className="mb-6">
        <Link to="/inventory" className="text-accent hover:underline flex items-center gap-2 w-fit text-sm">
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
                <h1 className="mb-2 text-2xl flex items-center gap-3 font-bold text-white">
                  <Package size={26}/> {product.product_name}
                </h1>
                <div className="text-muted font-mono text-sm">{product.sku}</div>
              </div>
            </div>

            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-label">Category</span>
                <div className="stat-value" style={{fontSize: '1.15rem'}}>{product.category}</div>
              </div>
              <div className="stat-card">
                <span className="stat-label">Manufacturer</span>
                <div className="stat-value" style={{fontSize: '1.15rem'}}>{product.manufacturer || 'Unknown'}</div>
              </div>
              <div className="stat-card">
                <span className="stat-label">MRP (Package)</span>
                <div className="stat-value" style={{fontSize: '1.15rem'}}>
                  {product.mrp != null ? `₹${product.mrp.toFixed(2)}` : 'N/A'}
                </div>
              </div>
              <div className="stat-card">
                <span className="stat-label">Base Price</span>
                <div className="stat-value" style={{fontSize: '1.15rem'}}>
                  ${product.base_price.toFixed(2)}
                </div>
              </div>
            </div>
          </div>

          <h2 className="mb-4 text-xl font-bold border-b border-gray-700 pb-2">Tracked Batches</h2>

          {product.batches && product.batches.length > 0 ? (
            <div className="card">
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Batch / Lot</th>
                      <th>Internal ID</th>
                      <th>MFG Date</th>
                      <th>Expiry Date</th>
                      <th>Stock Quantity</th>
                      <th>Current Discount</th>
                      <th>Daily Demand</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {product.batches.map((batch) => (
                      <tr key={batch.id}>
                        <td>
                          {batch.batch_number ? (
                            <span className="bg-gray-800 px-2 py-0.5 rounded text-xs font-mono">{batch.batch_number}</span>
                          ) : (
                            <span className="text-muted italic text-xs">N/A</span>
                          )}
                        </td>
                        <td className="text-xs text-muted font-mono">{batch.internal_batch_id}</td>
                        <td>{batch.manufacturing_date || '-'}</td>
                        <td className={new Date(batch.expiry_date) < new Date() ? 'text-red-400 font-bold' : 'text-white'}>
                          {batch.expiry_date}
                        </td>
                        <td className="font-mono text-base font-bold text-white">{batch.stock_quantity} units</td>
                        <td>{(batch.current_discount * 100).toFixed(0)}%</td>
                        <td>{batch.daily_demand}</td>
                        <td>
                          <span className={`badge ${
                            batch.status === 'SAFE' ? 'badge-success' :
                            batch.status === 'WARNING' ? 'badge-warning text-amber-300' :
                            batch.status === 'CRITICAL' ? 'badge-warning text-orange-400' :
                            batch.status === 'DONATION' ? 'badge-neutral text-purple-300' :
                            batch.status === 'EXPIRED' ? 'badge-danger' :
                            'badge-neutral'
                          }`}>
                            {batch.status}
                          </span>
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
