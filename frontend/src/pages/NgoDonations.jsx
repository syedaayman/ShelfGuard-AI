import { useState, useEffect, useRef } from 'react';
import { getNgoCandidates, createDonationRequest, getNgoDonations } from '../api/client';
import { HeartHandshake, Loader2, Send, CheckCircle2, Clock, XCircle } from 'lucide-react';

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
  const [selectedBatches, setSelectedBatches] = useState({}); // { [batchId]: { selected: boolean, quantity: number } }

  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [submittingDonation, setSubmittingDonation] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submitSuccess, setSubmitSuccess] = useState(null);

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
          // If any pending donations were approved, refresh candidates list as well
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
    setSubmitError(null);
    setSubmitSuccess(null);

    try {
      const payload = {
        ngo_name: selectedNgo,
        items: selectedItems.map((item) => ({
          batch_id: item.candidate.batch_id,
          quantity: item.quantity,
        })),
      };

      await createDonationRequest(payload);
      setSubmitSuccess(
        `Successfully submitted donation request for ${selectedItems.length} batch(es) (${totalItemsToDonate} items) to ${selectedNgo}. Approval simulation active (120 seconds).`
      );
      setShowConfirmModal(false);

      // Reset selection and refresh
      fetchCandidates();
      fetchDonations();
    } catch (err) {
      setSubmitError(err.message);
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

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <HeartHandshake size={32} className="text-amber-400" />
        <div>
          <h1 className="text-2xl font-bold m-0">NGO Food Relief Routing</h1>
          <p className="text-sm text-muted m-0">
            Route fresh perishable batches nearing 6-hour expiry window to verified food-relief partners.
          </p>
        </div>
      </div>

      {submitError && <div className="alert alert-error mb-4">{submitError}</div>}
      {submitSuccess && <div className="alert alert-info mb-4 text-emerald-300 border-emerald-500/30 bg-emerald-500/10">{submitSuccess}</div>}

      {/* Donation Candidates Section */}
      <div className="card mb-8">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6 pb-4 border-b border-gray-700">
          <div>
            <h2 className="text-lg font-bold m-0 flex items-center gap-2">
              Donation Candidates
              <span className="text-xs bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded font-mono font-normal">
                0 &lt; Remaining &le; 6 Hours
              </span>
            </h2>
            <p className="text-xs text-muted mt-1 m-0">
              Only active batches within the 6-hour donation window are eligible. Expired batches are strictly excluded.
            </p>
          </div>

          <div className="flex items-center gap-3 w-full md:w-auto">
            <label className="text-xs font-semibold text-gray-300 whitespace-nowrap">
              NGO Partner (Demo):
            </label>
            <select
              className="form-input text-sm py-1.5 px-3 bg-gray-800 border-gray-700 text-white rounded-md"
              value={selectedNgo}
              onChange={(e) => setSelectedNgo(e.target.value)}
            >
              {NGO_PARTNERS.map((ngo) => (
                <option key={ngo} value={ngo}>
                  {ngo}
                </option>
              ))}
            </select>

            <button
              className="btn btn-primary text-sm flex items-center gap-1.5 py-1.5 px-4 whitespace-nowrap"
              disabled={selectedItems.length === 0}
              onClick={() => setShowConfirmModal(true)}
            >
              <Send size={15} /> Confirm Donation ({selectedItems.length})
            </button>
          </div>
        </div>

        {errorCandidates ? (
          <div className="text-rose-400 p-4 text-sm">{errorCandidates}</div>
        ) : loadingCandidates ? (
          <div className="flex justify-center p-12">
            <Loader2 className="animate-spin text-accent" size={28} />
          </div>
        ) : candidates.length === 0 ? (
          <div className="text-center p-12 text-muted">
            <CheckCircle2 className="mx-auto mb-2 text-emerald-400" size={32} />
            <p className="text-base font-semibold text-white mb-1">No Donation Candidates Currently Eligible</p>
            <p className="text-xs">
              All inventory batches are either SAFE/CRITICAL (&gt; 6h remaining) or already EXPIRED.
            </p>
          </div>
        ) : (
          <div className="table-wrapper overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-gray-700 text-xs font-semibold text-gray-400">
                  <th className="py-3 px-3 w-10 text-center">
                    <input
                      type="checkbox"
                      className="rounded border-gray-700 bg-gray-800"
                      onChange={handleSelectAll}
                      checked={
                        candidates.length > 0 &&
                        candidates.every((c) => selectedBatches[c.batch_id]?.selected)
                      }
                    />
                  </th>
                  <th className="py-3 px-3">Product Name</th>
                  <th className="py-3 px-3">SKU</th>
                  <th className="py-3 px-3">Batch / Lot</th>
                  <th className="py-3 px-3">Available Stock</th>
                  <th className="py-3 px-3">Remaining Shelf Life</th>
                  <th className="py-3 px-3">MRP / Price</th>
                  <th className="py-3 px-3">Donation Quantity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 text-sm">
                {candidates.map((c) => {
                  const isSelected = !!selectedBatches[c.batch_id]?.selected;
                  const qty = selectedBatches[c.batch_id]?.quantity || c.stock_quantity;

                  return (
                    <tr
                      key={c.batch_id}
                      className={`hover:bg-gray-800/40 transition ${
                        isSelected ? 'bg-purple-950/20' : ''
                      }`}
                    >
                      <td className="py-3 px-3 text-center">
                        <input
                          type="checkbox"
                          className="rounded border-gray-700 bg-gray-800 cursor-pointer"
                          checked={isSelected}
                          onChange={() => handleCheckboxToggle(c.batch_id)}
                        />
                      </td>
                      <td className="py-3 px-3 font-semibold text-white">
                        {c.product_name}
                        {c.manufacturer && (
                          <span className="block text-xs text-muted font-normal">{c.manufacturer}</span>
                        )}
                      </td>
                      <td className="py-3 px-3 font-mono text-xs text-accent">{c.sku}</td>
                      <td className="py-3 px-3">
                        {c.batch_number ? (
                          <span className="bg-gray-800 border border-gray-700 px-2 py-0.5 rounded text-xs font-mono">
                            {c.batch_number}
                          </span>
                        ) : (
                          <span className="text-muted text-xs italic">N/A</span>
                        )}
                      </td>
                      <td className="py-3 px-3 font-mono font-bold text-white">
                        {c.stock_quantity}
                      </td>
                      <td className="py-3 px-3 text-xs font-medium text-purple-300">
                        {c.remaining_text || `${c.remaining_hours.toFixed(1)} hours remaining`}
                      </td>
                      <td className="py-3 px-3 text-xs font-mono">
                        {c.mrp != null ? `₹${c.mrp.toFixed(2)}` : `$${c.base_price.toFixed(2)}`}
                      </td>
                      <td className="py-3 px-3">
                        <input
                          type="number"
                          min="1"
                          max={c.stock_quantity}
                          className="form-input text-xs py-1 px-2 w-24 bg-gray-900 border-gray-700 text-white font-mono"
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
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-lg max-w-lg w-full p-6 shadow-2xl">
            <h3 className="text-xl font-bold text-white mb-2 flex items-center gap-2">
              <HeartHandshake className="text-amber-400" /> Confirm NGO Donation
            </h3>
            <p className="text-xs text-muted mb-4">
              Please review the donation details. Upon confirmation, a <strong className="text-yellow-400">PENDING</strong> donation request will be registered. Inventory stock will be transactionally deducted after the 120-second simulated approval window.
            </p>

            <div className="bg-gray-800/60 rounded border border-gray-700 p-3 mb-4 text-xs space-y-2">
              <div className="flex justify-between">
                <span className="text-muted">Selected NGO Partner:</span>
                <span className="font-bold text-amber-300">{selectedNgo}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Total Selected Batches:</span>
                <span className="font-bold text-white">{selectedItems.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Total Donated Units:</span>
                <span className="font-bold text-emerald-400">{totalItemsToDonate}</span>
              </div>
            </div>

            <div className="max-h-48 overflow-y-auto border border-gray-800 rounded p-2 mb-4 space-y-1">
              {selectedItems.map((item) => (
                <div
                  key={item.candidate.batch_id}
                  className="flex justify-between text-xs py-1 border-b border-gray-800 last:border-none"
                >
                  <span className="text-gray-300">
                    {item.candidate.product_name} ({item.candidate.batch_number || item.candidate.sku})
                  </span>
                  <span className="font-mono text-amber-300 font-bold">
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
                className="btn btn-primary text-xs px-4 py-2 flex items-center gap-1.5"
                onClick={handleSubmitDonation}
                disabled={submittingDonation}
              >
                {submittingDonation ? (
                  <Loader2 className="animate-spin" size={14} />
                ) : (
                  <Send size={14} />
                )}
                Confirm & Submit Donation
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Donation History Section */}
      <div className="card">
        <div className="flex justify-between items-center mb-6 pb-3 border-b border-gray-700">
          <div>
            <h2 className="text-lg font-bold m-0">Donation History</h2>
            <p className="text-xs text-muted m-0 mt-1">
              Tracks pending and completed NGO donation dispatches with 120-second simulated approval state.
            </p>
          </div>

          <button
            className="btn btn-secondary text-xs py-1 px-3"
            onClick={fetchDonations}
          >
            Refresh History
          </button>
        </div>

        {errorDonations ? (
          <div className="text-rose-400 p-4 text-sm">{errorDonations}</div>
        ) : loadingDonations ? (
          <div className="flex justify-center p-12">
            <Loader2 className="animate-spin text-accent" size={28} />
          </div>
        ) : donations.length === 0 ? (
          <div className="text-center p-12 text-muted">No donation history recorded yet.</div>
        ) : (
          <div className="table-wrapper overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-gray-700 text-xs font-semibold text-gray-400">
                  <th className="py-3 px-3">Receipt Ref</th>
                  <th className="py-3 px-3">Product Name</th>
                  <th className="py-3 px-3">Batch / SKU</th>
                  <th className="py-3 px-3">NGO Partner</th>
                  <th className="py-3 px-3">Qty Donated</th>
                  <th className="py-3 px-3">Requested Time</th>
                  <th className="py-3 px-3">Status / Approval</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 text-sm">
                {donations.map((d) => (
                  <tr key={d.donation_id || d.tax_receipt_reference} className="hover:bg-gray-800/40 transition">
                    <td className="py-3 px-3 text-muted font-mono text-xs">
                      {d.tax_receipt_reference}
                    </td>
                    <td className="py-3 px-3 font-semibold text-white">{d.product_name}</td>
                    <td className="py-3 px-3">
                      <span className="bg-gray-800 border border-gray-700 px-2 py-0.5 rounded text-xs font-mono">
                        {d.batch_number || d.sku}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-gray-300">{d.ngo_name}</td>
                    <td className="py-3 px-3 font-mono font-bold text-emerald-400">{d.quantity}</td>
                    <td className="py-3 px-3 text-xs text-muted">
                      {new Date(d.requested_at || d.dispatch_timestamp).toLocaleTimeString()}
                    </td>
                    <td className="py-3 px-3">
                      {d.status === 'PENDING' ? (
                        <span className="inline-flex items-center gap-1.5 bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 px-2.5 py-1 rounded text-xs font-mono font-semibold animate-pulse">
                          <Clock size={13} /> {formatCountdown(d.remaining_seconds_to_approve)}
                        </span>
                      ) : d.status === 'APPROVED' ? (
                        <span className="inline-flex items-center gap-1 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-2.5 py-1 rounded text-xs font-semibold">
                          <CheckCircle2 size={13} /> APPROVED
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 bg-rose-500/20 text-rose-400 border border-rose-500/30 px-2.5 py-1 rounded text-xs font-semibold">
                          <XCircle size={13} /> {d.status}
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
