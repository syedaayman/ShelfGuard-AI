import { useState, useEffect, useRef } from 'react';
import { getNgoCandidates, createDonationRequest, getNgoDonations } from '../api/client';
import { HeartHandshake, Loader2, Send, CheckCircle2, Clock, XCircle } from 'lucide-react';
import Toast from '../components/Toast';

const NGO_PARTNERS = [
  'Feeding India (Zomato)',
  'Food Bank Alliance',
  'Robin Hood Army',
  'Roti Bank Foundation',
  'No Food Waste',
];

export default function NgoDonations() {
  const [candidates, setCandidates] = useState([]);
  const [donations, setDonations] = useState([]);

  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [loadingDonations, setLoadingDonations] = useState(true);

  const [errorCandidates, setErrorCandidates] = useState(null);
  const [errorDonations, setErrorDonations] = useState(null);

  const [selectedNgo, setSelectedNgo] = useState(NGO_PARTNERS[0]);
  const [selectedBatches, setSelectedBatches] = useState({});

  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [submittingDonation, setSubmittingDonation] = useState(false);
  
  // Toast notifications state
  const [toast, setToast] = useState({ message: '', type: 'success' });

  const pollIntervalRef = useRef(null);

  const fetchCandidates = async () => {
    setLoadingCandidates(true);
    try {
      const data = await getNgoCandidates();
      setCandidates(data);

      // Initialize selection map
      const initialSelection = {};
      data.forEach((c) => {
        initialSelection[c.batch_id] = {
          selected: false,
          quantity: c.stock_quantity,
        };
      });
      setSelectedBatches(initialSelection);
      setErrorCandidates(null);
    } catch (err) {
      setErrorCandidates(err.message);
    } finally {
      setLoadingCandidates(false);
    }
  };

  const fetchDonations = async () => {
    setLoadingDonations(true);
    try {
      const data = await getNgoDonations();
      setDonations(data);
      setErrorDonations(null);
    } catch (err) {
      setErrorDonations(err.message);
    } finally {
      setLoadingDonations(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
    fetchDonations();
  }, []);

  // Poll donations history every 4 seconds to update approval status automatically
  useEffect(() => {
    pollIntervalRef.current = setInterval(() => {
      getNgoDonations()
        .then((data) => {
          setDonations(data);
          const hasPending = data.some((d) => d.status === 'PENDING');
          if (!hasPending) {
            getNgoCandidates().then(setCandidates).catch(() => {});
          }
        })
        .catch(() => {});
    }, 4000);

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  const handleCheckboxToggle = (batchId) => {
    setSelectedBatches((prev) => ({
      ...prev,
      [batchId]: {
        ...prev[batchId],
        selected: !prev[batchId]?.selected,
      },
    }));
  };

  const handleSelectAll = (e) => {
    const isChecked = e.target.checked;
    setSelectedBatches((prev) => {
      const updated = { ...prev };
      candidates.forEach((c) => {
        updated[c.batch_id] = {
          ...updated[c.batch_id],
          selected: isChecked,
        };
      });
      return updated;
    });
  };

  const handleQuantityChange = (batchId, val, maxStock) => {
    const parsed = parseInt(val, 10);
    const validQty = isNaN(parsed) ? 1 : Math.max(1, Math.min(parsed, maxStock));
    setSelectedBatches((prev) => ({
      ...prev,
      [batchId]: {
        ...prev[batchId],
        quantity: validQty,
      },
    }));
  };

  const getSelectedItems = () => {
    return candidates
      .filter((c) => selectedBatches[c.batch_id]?.selected)
      .map((c) => ({
        candidate: c,
        quantity: selectedBatches[c.batch_id]?.quantity || c.stock_quantity,
      }));
  };

  const selectedItems = getSelectedItems();
  const totalItemsToDonate = selectedItems.reduce((acc, item) => acc + item.quantity, 0);

  const handleSubmitDonation = async () => {
    if (selectedItems.length === 0) return;

    setSubmittingDonation(true);

    try {
      const payload = {
        ngo_name: selectedNgo,
        items: selectedItems.map((item) => ({
          batch_id: item.candidate.batch_id,
          quantity: item.quantity,
        })),
      };

      await createDonationRequest(payload);
      setToast({
        message: `Submitted donation request for ${selectedItems.length} batch(es) (${totalItemsToDonate} units) to ${selectedNgo}.`,
        type: 'success'
      });
      setShowConfirmModal(false);

      // Reset selection and refresh
      fetchCandidates();
      fetchDonations();
    } catch (err) {
      setToast({
        message: err.message || 'Failed to create donation request.',
        type: 'error'
      });
    } finally {
      setSubmittingDonation(false);
    }
  };

  const formatCountdown = (seconds) => {
    if (seconds <= 0) return 'Approving...';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `Approval in ${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const renderExpiryCountdownPill = (remainingHours, text) => {
    const hours = remainingHours != null ? remainingHours : 6.0;
    if (hours <= 2.0) {
      return (
        <span className="status-pill status-critical font-mono" style={{ fontSize: '11px' }}>
          <Clock size={12} /> {text || `${hours.toFixed(1)}h remaining`}
        </span>
      );
    }
    return (
      <span className="status-pill status-near-expiry font-mono" style={{ fontSize: '11px' }}>
        <Clock size={12} /> {text || `${hours.toFixed(1)}h remaining`}
      </span>
    );
  };

  return (
    <div>
      <Toast 
        message={toast.message} 
        type={toast.type} 
        onClose={() => setToast({ message: '', type: 'success' })} 
      />

      <div className="flex items-center gap-3 mb-6">
        <HeartHandshake size={32} className="text-gold" strokeWidth={2.2} />
        <div>
          <h1>NGO Relief Router</h1>
          <p className="text-sm text-muted">
            Route fresh perishable inventory within the 6-hour expiry window to verified relief partners.
          </p>
        </div>
      </div>

      {/* Donation Candidates Section */}
      <div className="card mb-8">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6 pb-4 border-b border-subtle">
          <div>
            <h2 className="mb-0 flex items-center gap-2">
              Donation Candidates
              <span className="status-pill status-near-expiry font-mono" style={{ fontSize: '11px' }}>
                0 &lt; Remaining &le; 6 Hours
              </span>
            </h2>
            <p className="text-xs text-muted mt-1">
              Active batches inside the 6-hour donation window are eligible. Expired batches are excluded.
            </p>
          </div>

          <div className="flex items-center gap-3 w-full md:w-auto">
            <label className="text-xs font-bold text-secondary whitespace-nowrap">
              NGO Partner:
            </label>
            <select
              className="form-input text-sm py-1.5 px-3 rounded-xl"
              value={selectedNgo}
              onChange={(e) => setSelectedNgo(e.target.value)}
              style={{ minWidth: '180px' }}
            >
              {NGO_PARTNERS.map((ngo) => (
                <option key={ngo} value={ngo}>
                  {ngo}
                </option>
              ))}
            </select>

            <button
              className="btn btn-primary text-sm flex items-center gap-1.5 py-2 px-4 whitespace-nowrap"
              disabled={selectedItems.length === 0}
              onClick={() => setShowConfirmModal(true)}
            >
              <Send size={15} /> Confirm Donation ({selectedItems.length})
            </button>
          </div>
        </div>

        {errorCandidates ? (
          <div className="alert alert-error">{errorCandidates}</div>
        ) : loadingCandidates ? (
          <div className="flex justify-center p-12">
            <Loader2 className="animate-spin text-teal" size={28} />
          </div>
        ) : candidates.length === 0 ? (
          <div className="text-center p-12 text-muted">
            <CheckCircle2 className="mx-auto mb-2 text-teal" size={36} />
            <p className="text-base font-bold text-primary mb-1">No Donation Candidates Currently Eligible</p>
            <p className="text-xs">
              All inventory batches are either SAFE (&gt;6h remaining) or already EXPIRED.
            </p>
          </div>
        ) : (
          <div className="table-wrapper overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th className="w-10 text-center">
                    <input
                      type="checkbox"
                      className="rounded border-subtle bg-white cursor-pointer"
                      onChange={handleSelectAll}
                      checked={
                        candidates.length > 0 &&
                        candidates.every((c) => selectedBatches[c.batch_id]?.selected)
                      }
                    />
                  </th>
                  <th>Product Name</th>
                  <th>SKU</th>
                  <th>Batch / Lot</th>
                  <th>Available Stock</th>
                  <th>Remaining Shelf Life</th>
                  <th>MRP / Base Price</th>
                  <th>Donation Quantity</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => {
                  const isSelected = !!selectedBatches[c.batch_id]?.selected;
                  const qty = selectedBatches[c.batch_id]?.quantity || c.stock_quantity;
                  const remainingHrs = c.remaining_hours != null ? c.remaining_hours : 6.0;
                  const progressPct = Math.max(0, Math.min(100, (remainingHrs / 6.0) * 100));

                  return (
                    <tr
                      key={c.batch_id}
                      data-status={remainingHrs <= 2.0 ? "CRITICAL" : "NEAR_EXPIRY"}
                      style={{ background: isSelected ? 'var(--accent-gold-bg)' : undefined }}
                    >
                      <td className="text-center">
                        <input
                          type="checkbox"
                          className="rounded border-subtle bg-white cursor-pointer"
                          checked={isSelected}
                          onChange={() => handleCheckboxToggle(c.batch_id)}
                        />
                      </td>
                      <td className="font-bold text-primary">
                        {c.product_name}
                        {c.manufacturer && (
                          <span className="block text-xs text-muted font-normal">{c.manufacturer}</span>
                        )}
                      </td>
                      <td className="font-mono text-xs text-teal font-bold">{c.sku}</td>
                      <td>
                        {c.batch_number ? (
                          <span className="bg-page border border-subtle px-2 py-0.5 rounded text-xs font-mono text-primary font-bold">
                            {c.batch_number}
                          </span>
                        ) : (
                          <span className="text-muted text-xs italic">N/A</span>
                        )}
                      </td>
                      <td>
                        <span className="font-mono font-bold text-primary">{c.stock_quantity}</span>
                      </td>
                      <td>
                        <div className="flex flex-col items-start gap-1">
                          {renderExpiryCountdownPill(remainingHrs, c.remaining_text)}
                          {/* Thin Progress Bar under each row showing remaining window */}
                          <div style={{ width: '120px', height: '4px', background: 'var(--bg-page)', borderRadius: '999px', overflow: 'hidden', border: '1px solid var(--border-subtle)' }}>
                            <div 
                              style={{ 
                                width: `${progressPct}%`, 
                                height: '100%', 
                                background: remainingHrs <= 2.0 ? 'var(--status-critical)' : 'var(--accent-gold)',
                                transition: 'width 0.3s ease'
                              }} 
                            />
                          </div>
                        </div>
                      </td>
                      <td className="text-xs font-mono font-bold">
                        {c.mrp != null ? `₹${c.mrp.toFixed(2)}` : (c.base_price != null ? `₹${c.base_price.toFixed(2)}` : '-')}
                      </td>
                      <td>
                        <input
                          type="number"
                          min="1"
                          max={c.stock_quantity}
                          className="form-input text-xs py-1 px-2.5 w-24 font-mono font-bold text-primary"
                          value={qty}
                          onChange={(e) => handleQuantityChange(c.batch_id, e.target.value, c.stock_quantity)}
                          disabled={!isSelected}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" style={{ position: 'fixed', inset: 0, background: 'rgba(34, 50, 41, 0.6)', display: 'flex', alignItems: 'center', justifyCenter: 'center', zIndex: 9999 }}>
          <div className="card max-w-lg w-full p-6 shadow-2xl" style={{ width: '100%', maxWidth: '520px', background: '#FFFFFF' }}>
            <h3 className="text-xl font-bold text-primary mb-2 flex items-center gap-2">
              <HeartHandshake className="text-gold" size={22} /> Confirm NGO Relief Dispatch
            </h3>
            <p className="text-xs text-muted mb-4">
              Upon confirmation, a <strong className="text-gold">PENDING</strong> donation request will be registered. Inventory stock will be transactionally deducted after the 120-second simulated approval window.
            </p>

            <div className="bg-page rounded-xl border border-subtle p-3.5 mb-4 text-xs space-y-2">
              <div className="flex justify-between">
                <span className="text-muted">Selected NGO Partner:</span>
                <span className="font-bold text-primary">{selectedNgo}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Total Selected Batches:</span>
                <span className="font-bold text-primary font-mono">{selectedItems.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Total Donated Units:</span>
                <span className="font-bold text-teal font-mono">+{totalItemsToDonate} units</span>
              </div>
            </div>

            <div className="max-h-48 overflow-y-auto border border-subtle rounded-xl p-3 mb-5 space-y-1.5 bg-white">
              {selectedItems.map((item) => (
                <div
                  key={item.candidate.batch_id}
                  className="flex justify-between text-xs py-1 border-b border-subtle last:border-none"
                >
                  <span className="text-primary truncate" style={{ maxWidth: '280px' }}>
                    {item.candidate.product_name} (<span className="font-mono">{item.candidate.batch_number || item.candidate.sku}</span>)
                  </span>
                  <span className="font-mono font-bold text-gold">
                    Qty: {item.quantity} / {item.candidate.stock_quantity}
                  </span>
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                className="btn btn-secondary text-xs px-4 py-2"
                onClick={() => setShowConfirmModal(false)}
                disabled={submittingDonation}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary text-xs px-5 py-2 flex items-center gap-1.5"
                onClick={handleSubmitDonation}
                disabled={submittingDonation}
              >
                {submittingDonation ? (
                  <Loader2 className="animate-spin" size={14} />
                ) : (
                  <Send size={14} />
                )}
                Confirm & Submit Dispatch
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Donation History Section */}
      <div className="card">
        <div className="flex justify-between items-center mb-6 pb-3 border-b border-subtle">
          <div>
            <h2>Donation Dispatch History</h2>
            <p className="text-xs text-muted mt-1">
              Tracks pending and completed relief dispatches with 120-second simulated approval state.
            </p>
          </div>

          <button
            className="btn btn-secondary text-xs py-1.5 px-3"
            onClick={fetchDonations}
          >
            Refresh History
          </button>
        </div>

        {errorDonations ? (
          <div className="alert alert-error">{errorDonations}</div>
        ) : loadingDonations ? (
          <div className="flex justify-center p-12">
            <Loader2 className="animate-spin text-teal" size={28} />
          </div>
        ) : donations.length === 0 ? (
          <div className="text-center p-12 text-muted">No donation dispatches recorded yet.</div>
        ) : (
          <div className="table-wrapper overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>Receipt Ref</th>
                  <th>Product Name</th>
                  <th>Batch / SKU</th>
                  <th>NGO Partner</th>
                  <th>Qty Donated</th>
                  <th>Requested Time</th>
                  <th>Status / Approval</th>
                </tr>
              </thead>
              <tbody>
                {donations.map((d) => (
                  <tr key={d.donation_id || d.tax_receipt_reference}>
                    <td className="text-muted font-mono text-xs">
                      {d.tax_receipt_reference}
                    </td>
                    <td className="font-bold text-primary">{d.product_name}</td>
                    <td>
                      <span className="bg-page border border-subtle px-2 py-0.5 rounded text-xs font-mono text-primary font-bold">
                        {d.batch_number || d.sku}
                      </span>
                    </td>
                    <td className="text-secondary font-semibold">{d.ngo_name}</td>
                    <td className="font-mono font-bold text-teal">+{d.quantity}</td>
                    <td className="text-xs text-muted font-mono">
                      {new Date(d.requested_at || d.dispatch_timestamp).toLocaleTimeString()}
                    </td>
                    <td>
                      {d.status === 'PENDING' ? (
                        <span className="status-pill status-near-expiry font-mono text-xs">
                          <Clock size={12} /> {formatCountdown(d.remaining_seconds_to_approve)}
                        </span>
                      ) : d.status === 'APPROVED' ? (
                        <span className="status-pill status-safe font-mono text-xs">
                          <CheckCircle2 size={12} /> APPROVED
                        </span>
                      ) : (
                        <span className="status-pill status-expired font-mono text-xs">
                          <XCircle size={12} /> {d.status}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
