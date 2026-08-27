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
        initial_quantity: parseInt(formData.initial_quantity),
        daily_demand: parseInt(formData.daily_demand)
      };
      
      const res = await recommendPricing(payload);
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="mb-6">Dynamic Pricing Engine</h1>
      
      <div className="grid" style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem'}}>
        <div className="card">
          <h2 className="mb-4">Input Parameters</h2>
          <form onSubmit={handleRecommend}>
            <div className="form-group">
              <label className="form-label">Remaining Hours</label>
              <input 
                type="number" step="any" required 
                name="remaining_hours" value={formData.remaining_hours} onChange={handleChange}
                className="form-input" placeholder="e.g. 48.5"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Base Price (₹)</label>
              <input 
                type="number" step="any" required 
                name="base_price" value={formData.base_price} onChange={handleChange}
                className="form-input" placeholder="e.g. 150.00"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Initial Quantity (Stock)</label>
              <input 
                type="number" required 
                name="initial_quantity" value={formData.initial_quantity} onChange={handleChange}
                className="form-input" placeholder="e.g. 10"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Daily Demand</label>
              <input 
                type="number" required 
                name="daily_demand" value={formData.daily_demand} onChange={handleChange}
                className="form-input" placeholder="e.g. 2"
              />
            </div>
            <button type="submit" className="btn btn-primary w-full mt-4" disabled={loading} style={{width: '100%'}}>
              {loading ? <Loader2 className="animate-spin" size={18} /> : <Tag size={18} />}
              Get Recommendation
            </button>
          </form>
        </div>

        <div>
          {error && <div className="alert alert-error mb-4">{error}</div>}
          
          {result && (
            <div className="card border-accent" style={{borderColor: 'var(--accent)', borderWidth: '2px'}}>
              <div className="flex items-center gap-2 mb-2 text-accent">
                <TrendingDown size={24} />
                <h2 className="mb-0" style={{margin: 0}}>Recommended Discount</h2>
              </div>
              <p className="text-muted mb-4">Based on XGBoost model predictions (capped at 70%)</p>
              
              <div className="text-center py-6">
                <div style={{fontSize: '4rem', fontWeight: 700, lineHeight: 1}}>
                  {(result.recommended_discount * 100).toFixed(0)}<span style={{fontSize: '2rem'}}>%</span>
                </div>
                <div className="text-muted mt-2">
                  Fractional Value: {result.recommended_discount.toFixed(4)}
                </div>
                {result.final_price != null && (
                  <div className="mt-4 p-3 bg-gray-800/80 rounded-lg border border-gray-700">
                    <span className="text-xs text-muted block uppercase tracking-wider">Final Selling Price</span>
                    <span className="text-xl font-bold font-mono text-emerald-400">
                      ₹{result.final_price.toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
