import { useState } from 'react';
import { calculateTax } from '../api/client';
import { Calculator, Loader2, Receipt } from 'lucide-react';

export default function Tax() {
  const [formData, setFormData] = useState({
    taxable_amount: '',
    tax_rate: ''
  });
  
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleCalculate = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const payload = {
        taxable_amount: parseFloat(formData.taxable_amount),
        tax_rate: parseFloat(formData.tax_rate)
      };
      
      const res = await calculateTax(payload);
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1>Tax Calculator</h1>
        <p className="text-sm text-muted">Compute statutory tax liability and net value using standardized rates.</p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
        {/* INPUT FORM CARD */}
        <div className="card">
          <h2 className="mb-4 flex items-center gap-2">
            <Calculator className="text-teal" size={20} /> Input Parameters
          </h2>

          <form onSubmit={handleCalculate}>
            <div className="form-group">
              <label className="form-label">Taxable Amount (₹) *</label>
              <div className="input-with-label">
                <span className="input-unit-prefix">₹</span>
                <input 
                  type="number" step="0.01" required 
                  name="taxable_amount" value={formData.taxable_amount} onChange={handleChange}
                  className="form-input has-prefix font-mono" placeholder="e.g. 1000.00"
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Tax Rate (Decimal) *</label>
              <div className="input-with-label">
                <input 
                  type="number" step="0.001" required 
                  name="tax_rate" value={formData.tax_rate} onChange={handleChange}
                  className="form-input font-mono" placeholder="e.g. 0.05 (for 5%) or 0.18 (for 18%)"
                />
              </div>
              <small className="text-xs text-muted mt-1 block">
                * Rate must be explicitly provided in decimal format (e.g., 0.05 = 5%).
              </small>
            </div>
            
            <button type="submit" className="btn btn-primary w-full mt-4" disabled={loading} style={{ width: '100%' }}>
              {loading ? <Loader2 className="animate-spin" size={18} /> : <Calculator size={18} />}
              Calculate Tax
            </button>
          </form>
        </div>

        {/* LIVE RESULT PANEL BESIDE INPUT FORM */}
        <div>
          {error && <div className="alert alert-error mb-4">{error}</div>}
          
          <div className="card h-full flex flex-col justify-between" style={{ minHeight: '340px', borderTop: '4px solid var(--accent-teal)' }}>
            <div>
              <h2 className="mb-2 flex items-center gap-2">
                <Receipt className="text-gold" size={22} /> Calculation Results
              </h2>
              <p className="text-xs text-muted mb-6">Detailed tax breakdown and grand total</p>
            </div>

            {result ? (
              <div className="space-y-4">
                <div className="flex justify-between items-center py-3 border-b border-subtle">
                  <span className="text-muted text-sm font-semibold">Taxable Amount</span>
                  <span className="font-bold font-mono text-primary">₹{parseFloat(formData.taxable_amount).toFixed(2)}</span>
                </div>
                
                <div className="flex justify-between items-center py-3 border-b border-subtle">
                  <span className="text-muted text-sm font-semibold">Applied Tax Rate</span>
                  <span className="font-bold font-mono text-teal">{(parseFloat(formData.tax_rate) * 100).toFixed(1)}% ({formData.tax_rate})</span>
                </div>

                <div className="flex justify-between items-center py-3 border-b border-subtle">
                  <span className="text-muted text-sm font-semibold">Tax Collected</span>
                  <span className="font-bold font-mono text-gold">
                    + ₹{result.tax_collected.toFixed(2)}
                  </span>
                </div>
                
                <div className="flex justify-between items-center pt-4 mt-2">
                  <span className="text-lg font-bold font-display text-primary">Final Total</span>
                  <span className="text-2xl font-bold font-mono text-teal">
                    ₹{result.final_amount.toFixed(2)}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-muted my-auto">
                <Receipt size={40} className="mx-auto mb-3 opacity-30 text-teal" strokeWidth={1.5} />
                <p className="text-sm font-bold text-primary mb-1">No tax calculation performed yet</p>
                <p className="text-xs">Fill out the taxable amount and rate on the left and click "Calculate Tax".</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
