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
        <h1>Tax Ledger</h1>
        <p className="text-sm text-muted">Statutory tax liability calculator with precise Decimal precision arithmetic.</p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', alignItems: 'stretch' }}>
        {/* INPUT FORM CARD */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="mb-0 flex items-center gap-2">
                <Calculator className="text-teal" size={18} /> Tax Parameters
              </h2>
              <span className="status-pill status-safe font-mono text-xs">Exact Decimal</span>
            </div>

            <form onSubmit={handleCalculate}>
              <div className="form-group">
                <label className="form-label">Taxable Base Amount (₹) *</label>
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
                <small className="text-xs text-muted mt-1.5 block">
                  Provide statutory rate as decimal (e.g. 0.05 = 5% GST, 0.18 = 18% GST).
                </small>
              </div>
              
              <button type="submit" className="btn btn-primary w-full mt-3" disabled={loading} style={{ width: '100%', height: '42px' }}>
                {loading ? <Loader2 className="animate-spin" size={18} /> : <Calculator size={18} />}
                Calculate Statutory Tax
              </button>
            </form>
          </div>
        </div>

        {/* LIVE RESULT PANEL BESIDE INPUT FORM */}
        <div>
          {error && <div className="alert alert-error mb-4">{error}</div>}
          
          <div className="card h-full" style={{ minHeight: '340px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div className="flex items-center justify-between mb-1">
                <h2 className="mb-0 flex items-center gap-2">
                  <Receipt className="text-gold" size={18} /> Tax Breakdown
                </h2>
                <span className="status-pill font-mono text-xs" style={{ background: 'var(--accent-teal-bg)', color: 'var(--accent-teal)' }}>
                  Statutory Ledger
                </span>
              </div>
              <p className="text-xs text-muted mb-4">Itemized invoice calculation with statutory tax liability.</p>
            </div>

            {result ? (
              <div className="space-y-3">
                <div className="p-4 bg-page rounded-xl border border-subtle space-y-2.5">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-muted font-medium">Taxable Base</span>
                    <span className="font-bold font-mono text-primary">₹{parseFloat(formData.taxable_amount).toFixed(2)}</span>
                  </div>
                  
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-muted font-medium">Statutory Tax Rate</span>
                    <span className="font-bold font-mono text-teal">{(parseFloat(formData.tax_rate) * 100).toFixed(1)}%</span>
                  </div>

                  <div className="flex justify-between items-center text-sm pt-2 border-t border-subtle">
                    <span className="text-muted font-medium">Tax Collected</span>
                    <span className="font-bold font-mono text-gold">
                      + ₹{result.tax_collected.toFixed(2)}
                    </span>
                  </div>
                </div>
                
                {/* PROMINENT GRAND TOTAL */}
                <div className="p-4 bg-accent-teal-bg rounded-xl border border-subtle flex justify-between items-center">
                  <div>
                    <span className="text-xs text-muted block uppercase tracking-wider font-bold">Grand Total (Inc. Tax)</span>
                    <span className="text-xs text-muted font-mono">₹{parseFloat(formData.taxable_amount).toFixed(2)} + ₹{result.tax_collected.toFixed(2)}</span>
                  </div>
                  <span className="text-3xl font-bold font-mono text-teal">
                    ₹{result.final_amount.toFixed(2)}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-muted my-auto">
                <Receipt size={36} className="mx-auto mb-2 opacity-30 text-teal" strokeWidth={1.5} />
                <p className="text-sm font-bold text-primary mb-0.5">No tax calculation performed</p>
                <p className="text-xs">Fill out taxable base and rate on the left and click "Calculate Statutory Tax".</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
