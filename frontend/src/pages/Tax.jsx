import { useState } from 'react';
import { calculateTax } from '../api/client';
import { Calculator, Loader2 } from 'lucide-react';

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
      <h1 className="mb-6">Tax Calculator</h1>
      
      <div className="grid" style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem'}}>
        <div className="card">
          <h2 className="mb-4">Input Parameters</h2>
          <form onSubmit={handleCalculate}>
            <div className="form-group">
              <label className="form-label">Taxable Amount ($)</label>
              <input 
                type="number" step="0.01" required 
                name="taxable_amount" value={formData.taxable_amount} onChange={handleChange}
                className="form-input" placeholder="e.g. 100.00"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Tax Rate (Decimal)</label>
              <input 
                type="number" step="0.001" required 
                name="tax_rate" value={formData.tax_rate} onChange={handleChange}
                className="form-input" placeholder="e.g. 0.05 for 5%"
              />
              <small className="text-muted mt-1 block" style={{display: 'block'}}>
                * Rate must be explicitly provided. No default rate exists.
              </small>
            </div>
            
            <button type="submit" className="btn btn-primary w-full mt-4" disabled={loading} style={{width: '100%'}}>
              {loading ? <Loader2 className="animate-spin" size={18} /> : <Calculator size={18} />}
              Calculate Tax
            </button>
          </form>
        </div>

        <div>
          {error && <div className="alert alert-error mb-4">{error}</div>}
          
          {result && (
            <div className="card border-accent" style={{borderColor: 'var(--accent)', borderWidth: '2px'}}>
              <h2 className="mb-6">Calculation Results</h2>
              
              <div className="flex justify-between items-center mb-4 pb-4 border-b" style={{borderBottom: '1px solid var(--border)'}}>
                <span className="text-muted">Taxable Amount</span>
                <span className="font-semibold">${parseFloat(formData.taxable_amount).toFixed(2)}</span>
              </div>
              
              <div className="flex justify-between items-center mb-4 pb-4 border-b" style={{borderBottom: '1px solid var(--border)'}}>
                <span className="text-muted">Applied Tax Rate</span>
                <span className="font-semibold">{parseFloat(formData.tax_rate)}</span>
              </div>

              <div className="flex justify-between items-center mb-4 pb-4 border-b" style={{borderBottom: '1px solid var(--border)'}}>
                <span className="text-muted">Tax Collected</span>
                <span className="text-warning font-semibold">+ ${result.tax_collected.toFixed(2)}</span>
              </div>
              
              <div className="flex justify-between items-center mt-6">
                <span className="text-lg font-bold">Final Amount</span>
                <span className="text-2xl text-accent font-bold">${result.final_amount.toFixed(2)}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
