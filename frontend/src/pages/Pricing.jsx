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
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', alignItems: 'stretch' }}>
        {/* INPUT FORM CARD */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="mb-0 flex items-center gap-2">
                <Tag className="text-teal" size={18} /> Input Parameters
              </h2>
              <span className="status-pill status-safe font-mono text-xs">XGBoost Regressor</span>
            </div>
            
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

              <button type="submit" className="btn btn-primary w-full mt-2" disabled={loading} style={{ width: '100%', height: '42px' }}>
                {loading ? <Loader2 className="animate-spin" size={18} /> : <Tag size={18} />}
                Get Recommendation
              </button>
            </form>
          </div>
        </div>

        {/* LIVE RESULT PANEL BESIDE INPUT FORM */}
        <div>
          {error && <div className="alert alert-error mb-4">{error}</div>}
          
          <div className="card h-full" style={{ minHeight: '380px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div className="flex items-center justify-between mb-1">
                <h2 className="mb-0 flex items-center gap-2">
                  <TrendingDown size={18} className="text-gold" /> ML Recommendation
                </h2>
                <span className="status-pill font-mono text-xs" style={{ background: 'var(--accent-gold-bg)', color: '#1C2B24' }}>
                  0% &ndash; 70% Range
                </span>
              </div>
              <p className="text-xs text-muted mb-4">Optimal discount rate balancing inventory clearance against margin preservation.</p>
            </div>

            {result ? (
              <div className="space-y-4">
                {/* Visual Discount Progress Bar Gauge */}
                <div>
                  <div className="flex justify-between items-center text-xs font-mono mb-1.5">
                    <span className="text-muted font-bold">Dynamic Clearance Gauge</span>
                    <span className="font-bold text-gold font-mono" style={{ fontSize: '13px' }}>
                      {discountPct.toFixed(0)}% OFF
                    </span>
                  </div>
                  <div style={{ height: '10px', width: '100%', background: 'var(--bg-page)', borderRadius: '999px', overflow: 'hidden', border: '1px solid var(--border-subtle)' }}>
                    <div 
                      style={{ 
                        width: `${Math.min(discountPct, 100)}%`, 
                        height: '100%', 
                        background: 'linear-gradient(90deg, var(--accent-teal) 0%, var(--accent-gold) 100%)', 
                        transition: 'width 0.6s ease' 
                      }} 
                    />
                  </div>
                </div>

                {/* PROMINENT DISCOUNT CALLOUT */}
                <div className="text-center py-4 bg-accent-gold-bg rounded-xl border border-subtle">
                  <div className="text-xs text-muted font-bold uppercase tracking-wider mb-1">Recommended Markdown</div>
                  <div className="font-display font-bold text-primary" style={{ fontSize: '3rem', lineHeight: 1 }}>
                    {discountPct.toFixed(0)}% OFF
                  </div>
                  <div className="text-xs text-muted font-mono mt-1.5">
                    Model Raw Score: {result.recommended_discount.toFixed(4)}
                  </div>
                </div>

                {/* RECOMMENDED PRICE BREAKDOWN */}
                {result.final_price != null && (
                  <div className="p-3.5 bg-accent-teal-bg rounded-xl border border-subtle flex justify-between items-center">
                    <div>
                      <span className="text-xs text-muted block uppercase tracking-wider font-bold">Recommended Final Price</span>
                      <span className="text-xs text-muted">Base Cost: ₹{parseFloat(formData.base_price || 0).toFixed(2)}</span>
                    </div>
                    <span className="text-2xl font-bold font-mono text-teal">
                      ₹{result.final_price.toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-muted my-auto">
                <Tag size={36} className="mx-auto mb-2 opacity-30 text-teal" strokeWidth={1.5} />
                <p className="text-sm font-bold text-primary mb-0.5">No recommendation calculated</p>
                <p className="text-xs">Fill out parameters on the left and click "Get Recommendation".</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
