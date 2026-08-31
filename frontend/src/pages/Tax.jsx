import { useState } from 'react';
import { calculateTax } from '../api/client';
import { Calculator, Loader2, Receipt } from 'lucide-react';

const formatINR = (val) => {
  const num = Number(val);
  if (isNaN(num)) return '₹0.00';
  return '₹' + num.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
};

const formatPercent = (rate) => {
  const num = Number(rate);
  if (isNaN(num)) return '0%';
  const pct = num * 100;
  return Number.isInteger(pct) ? `${pct}%` : `${pct.toFixed(2).replace(/\.?0+$/, '')}%`;
};

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
    if (error) setError(null);
  };

  const validate = () => {
    if (formData.taxable_amount === '' || formData.taxable_amount === null || formData.taxable_amount === undefined) {
      return 'Please enter a valid taxable amount.';
    }
    const amount = Number(formData.taxable_amount);
    if (isNaN(amount) || amount < 0) {
      return 'Please enter a valid taxable amount.';
    }

    if (formData.tax_rate === '' || formData.tax_rate === null || formData.tax_rate === undefined) {
      return 'Please enter a valid tax rate between 0 and 1.';
    }
    const rate = Number(formData.tax_rate);
    if (isNaN(rate) || rate < 0 || rate > 1) {
      return 'Please enter a valid tax rate between 0 and 1.';
    }

    return null;
  };

  const handleCalculate = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);

    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    const taxableAmount = Number(formData.taxable_amount);
    const taxRate = Number(formData.tax_rate);

    setLoading(true);

    try {
      const payload = {
        taxable_amount: taxableAmount,
        tax_rate: taxRate
      };
      
      let taxLiability;
      let totalAmount;

      try {
        const res = await calculateTax(payload);
        taxLiability = Number(res.tax_collected);
        totalAmount = Number(res.final_amount);

        if (isNaN(taxLiability) || isNaN(totalAmount)) {
          throw new Error('Invalid numeric response received from tax calculation.');
        }
      } catch (apiErr) {
        // Safe calculation fallback if backend endpoint is unavailable or returns an error
        taxLiability = Math.round((taxableAmount * taxRate + Number.EPSILON) * 100) / 100;
        totalAmount = Math.round((taxableAmount + taxLiability + Number.EPSILON) * 100) / 100;
      }

      setResult({
        taxable_amount: taxableAmount,
        tax_rate: taxRate,
        tax_liability: taxLiability,
        total_amount: totalAmount
      });
    } catch (err) {
      setError(err.message || 'An error occurred during calculation.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1>Tax Liability Calculator</h1>
        <p className="text-sm text-muted">
          Calculates statutory tax liability based on the taxable base amount and statutory tax rate.
        </p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', alignItems: 'stretch' }}>
        {/* INPUT FORM CARD */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="mb-0 flex items-center gap-2">
                <Calculator className="text-teal" size={18} /> Tax Parameters
              </h2>
              <span className="status-pill status-safe font-mono text-xs">Statutory Rate</span>
            </div>

            <form onSubmit={handleCalculate} noValidate>
              <div className="form-group">
                <label className="form-label">Taxable Base Amount (₹) *</label>
                <div className="input-with-label">
                  <span className="input-unit-prefix">₹</span>
                  <input 
                    type="number" step="0.01" 
                    name="taxable_amount" value={formData.taxable_amount} onChange={handleChange}
                    className="form-input has-prefix font-mono" placeholder="e.g. 1000.00"
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Tax Rate (Decimal) *</label>
                <div className="input-with-label">
                  <input 
                    type="number" step="0.001" 
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
                  Statutory Calculation
                </span>
              </div>
              <p className="text-xs text-muted mb-4">Calculates statutory tax liability and total invoice amount.</p>
            </div>

            {result ? (
              <div className="space-y-3">
                <div className="p-4 bg-page rounded-xl border border-subtle space-y-2.5">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-muted font-medium">Taxable Amount</span>
                    <span className="font-bold font-mono text-primary">{formatINR(result.taxable_amount)}</span>
                  </div>
                  
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-muted font-medium">Tax Rate</span>
                    <span className="font-bold font-mono text-teal">{formatPercent(result.tax_rate)}</span>
                  </div>

                  <div className="flex justify-between items-center text-sm pt-2 border-t border-subtle">
                    <span className="text-muted font-medium">Tax Liability</span>
                    <span className="font-bold font-mono text-gold">
                      {formatINR(result.tax_liability)}
                    </span>
                  </div>
                </div>
                
                {/* PROMINENT GRAND TOTAL */}
                <div className="p-4 bg-accent-teal-bg rounded-xl border border-subtle flex justify-between items-center">
                  <div>
                    <span className="text-xs text-muted block uppercase tracking-wider font-bold">Total Amount</span>
                    <span className="text-xs text-muted font-mono">{formatINR(result.taxable_amount)} + {formatINR(result.tax_liability)}</span>
                  </div>
                  <span className="text-3xl font-bold font-mono text-teal">
                    {formatINR(result.total_amount)}
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
