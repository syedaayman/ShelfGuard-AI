import { useState } from 'react';
import { recommendPricing } from '../api/client';
import { Tag, Loader2, TrendingDown } from 'lucide-react';

export default function Pricing() {
  const [formData, setFormData] = useState({
    remaining_hours: '',
    base_price: '',
    initial_quantity: '',
    daily_demand: ''
  });
  
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleRecommend = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const payload = {
        remaining_hours: parseFloat(formData.remaining_hours),
        base_price: parseFloat(formData.base_price),
        initial_quantity: parseInt(formData.initial_quantity, 10),
        daily_demand: parseInt(formData.daily_demand, 10)
      };
      
      const res = await recommendPricing(payload);
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const discountPct = result ? (result.recommended_discount * 100) : 0;

  return (
    <div>
      <div className="mb-6">
        <h1>Dynamic Pricing Engine</h1>
        <p className="text-sm text-muted">XGBoost ML dynamic markdown recommendations based on remaining shelf life and sales velocity.</p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
        {/* INPUT FORM CARD */}
        <div className="card">
          <h2 className="mb-4 flex items-center gap-2">
            <Tag className="text-teal" size={20} /> Input Parameters
          </h2>
          
          <form onSubmit={handleRecommend}>
            <div className="form-group">
              <label className="form-label">Remaining Hours to Expiry *</label>
              <div className="input-with-label">
                <input 
                  type="number" step="any" required 
                  name="remaining_hours" value={formData.remaining_hours} onChange={handleChange}
                  className="form-input has-suffix font-mono" placeholder="e.g. 48.5"
                />
                <span className="input-unit-suffix">hrs</span>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Base Cost / Selling Price *</label>
              <div className="input-with-label">
                <span className="input-unit-prefix">₹</span>
                <input 
                  type="number" step="any" required 
                  name="base_price" value={formData.base_price} onChange={handleChange}
                  className="form-input has-prefix font-mono" placeholder="e.g. 150.00"
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Initial Quantity (Batch Stock) *</label>
              <div className="input-with-label">
                <input 
                  type="number" required 
                  name="initial_quantity" value={formData.initial_quantity} onChange={handleChange}
                  className="form-input has-suffix font-mono" placeholder="e.g. 10"
                />
                <span className="input-unit-suffix">units</span>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Daily Demand Velocity *</label>
              <div className="input-with-label">
                <input 
                  type="number" required 
                  name="daily_demand" value={formData.daily_demand} onChange={handleChange}
                  className="form-input has-suffix font-mono" placeholder="e.g. 2"
                />
                <span className="input-unit-suffix">units/day</span>
              </div>
            </div>

            <button type="submit" className="btn btn-primary w-full mt-4" disabled={loading} style={{ width: '100%' }}>
              {loading ? <Loader2 className="animate-spin" size={18} /> : <Tag size={18} />}
              Get Recommendation
            </button>
          </form>
        </div>

        {/* LIVE RESULT PANEL BESIDE INPUT FORM */}
        <div>
          {error && <div className="alert alert-error mb-4">{error}</div>}
          
          <div className="card h-full flex flex-col justify-between" style={{ minHeight: '380px' }}>
            <div>
              <div className="flex items-center gap-2 mb-2 text-gold">
                <TrendingDown size={22} />
                <h2 className="mb-0 text-primary" style={{ margin: 0 }}>ML Discount Recommendation</h2>
              </div>
              <p className="text-xs text-muted mb-6">Trained XGBoost regression model prediction (0% &ndash; 70% range)</p>
            </div>

            {result ? (
              <div>
                {/* Visual Discount Progress Bar Gauge */}
                <div className="mb-6">
                  <div className="flex justify-between items-center text-xs font-mono mb-2">
                    <span className="text-muted font-bold">Discount Gauge</span>
                    <span className="font-bold text-gold" style={{ fontSize: '13px' }}>
                      {discountPct.toFixed(0)}% OFF
                    </span>
                  </div>
                  <div style={{ height: '14px', width: '100%', background: 'var(--bg-page)', borderRadius: '999px', overflow: 'hidden', border: '1px solid var(--border-subtle)' }}>
                    <div 
                      style={{ 
                        width: `${Math.min(discountPct, 100)}%`, 
                        height: '100%', 
                        background: 'linear-gradient(90deg, var(--accent-teal) 0%, var(--accent-gold) 100%)', 
                        transition: 'width 0.8s cubic-bezier(0.16, 1, 0.3, 1)' 
                      }} 
                    />
                  </div>
                </div>

                <div className="text-center py-4 bg-accent-gold-bg rounded-2xl border border-subtle mb-4">
                  <div className="font-display font-bold text-primary" style={{ fontSize: '3.5rem', lineHeight: 1 }}>
                    {discountPct.toFixed(0)}<span style={{ fontSize: '1.75rem' }}>%</span>
                  </div>
                  <div className="text-xs text-muted font-mono mt-2">
                    Raw Prediction: {result.recommended_discount.toFixed(4)}
                  </div>
                </div>

                {result.final_price != null && (
                  <div className="p-4 bg-accent-teal-bg rounded-2xl border border-subtle flex justify-between items-center">
                    <div>
                      <span className="text-xs text-muted block uppercase tracking-wider font-bold">Recommended Price</span>
                      <span className="text-xs text-muted">Base: ₹{parseFloat(formData.base_price || 0).toFixed(2)}</span>
                    </div>
                    <span className="text-2xl font-bold font-mono text-teal">
                      ₹{result.final_price.toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-muted my-auto">
                <Tag size={40} className="mx-auto mb-3 opacity-30 text-teal" strokeWidth={1.5} />
                <p className="text-sm font-bold text-primary mb-1">No recommendation calculated yet</p>
                <p className="text-xs">Fill out the parameters on the left and click "Get Recommendation".</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
