import { useState } from 'react';
import { scanOcr, createBatch } from '../api/client';
import { 
  Loader2, 
  Scan, 
  CheckCircle, 
  AlertTriangle, 
  AlertCircle, 
  Save, 
  PackagePlus, 
  ChevronDown, 
  ChevronUp, 
  ImageIcon, 
  Layers, 
  PlusCircle, 
  X,
  Sparkles
} from 'lucide-react';
import { Link } from 'react-router-dom';

export default function ExpiryScanner() {
  const [image, setImage] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);

  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState("");
  const [error, setError] = useState(null);
  const [ocrResult, setOcrResult] = useState(null);

  const [showRawOcr, setShowRawOcr] = useState(false);

  // Form states for verification
  const [formData, setFormData] = useState({
    product_name: '',
    manufacturer: '',
    category: '',
    sku: '',
    batch_number: '',
    manufacturing_date: '',
    expiry_date: '',
    mrp: '',
    base_price: '',
    stock_quantity: ''
  });

  const [successResult, setSuccessResult] = useState(null);
  const [existingBatchConflict, setExistingBatchConflict] = useState(null);

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setImage(file);
    setImagePreview(URL.createObjectURL(file));
    setError(null);
  };

  const handleRemoveImage = () => {
    setImage(null);
    setImagePreview(null);
    setError(null);
  };

  const handleScan = async () => {
    if (!image) {
      setError("Please upload a product packaging image before scanning.");
      return;
    }
    
    setLoading(true);
    setLoadingStep("Extracting packaging text with EasyOCR...");
    setError(null);
    setOcrResult(null);
    setSuccessResult(null);
    setExistingBatchConflict(null);

    try {
      setLoadingStep("Analyzing packaging with Gemini Vision AI...");
      const res = await scanOcr(image);
      
      setOcrResult(res);
      setFormData({
        product_name: res.product_name || '',
        manufacturer: res.manufacturer || '',
        category: res.category || '',
        sku: res.sku || '',
        batch_number: res.batch_number || '',
        manufacturing_date: res.manufacturing_date || '',
        expiry_date: res.expiry_date || '',
        mrp: res.mrp ? res.mrp.toString() : '',
        base_price: res.base_price ? res.base_price.toString() : (res.mrp ? res.mrp.toString() : ''),
        stock_quantity: ''
      });
    } catch (err) {
      setError(err.message || "Could not process image. Please try again with a clearer photo.");
    } finally {
      setLoading(false);
      setLoadingStep("");
    }
  };

  const handleFormChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const submitBatch = async (confirmExisting = false, forceNewBatch = false) => {
    setError(null);
    setExistingBatchConflict(null);
    
    if (!formData.product_name.trim()) {
      setError("Product name is required.");
      return;
    }

    if (!formData.expiry_date.trim()) {
      setError("Expiry date is required. Please verify or enter it.");
      return;
    }

    const qty = parseInt(formData.stock_quantity, 10);
    if (isNaN(qty) || qty <= 0) {
      setError("Stock quantity must be greater than zero.");
      return;
    }

    if (formData.manufacturing_date && formData.expiry_date) {
      if (formData.manufacturing_date > formData.expiry_date) {
        setError("Manufacturing date cannot be later than Expiry date.");
        return;
      }
    }

    setLoading(true);
    setLoadingStep(confirmExisting ? "Updating existing batch stock..." : (forceNewBatch ? "Creating separate new batch..." : "Saving batch to inventory..."));

    try {
      const payload = {
        product_name: formData.product_name.trim(),
        manufacturer: formData.manufacturer.trim() || null,
        category: formData.category.trim() || null,
        sku: formData.sku.trim() || null,
        batch_number: formData.batch_number.trim() || null,
        manufacturing_date: formData.manufacturing_date.trim() || null,
        expiry_date: formData.expiry_date.trim(),
        mrp: formData.mrp ? parseFloat(formData.mrp) : null,
        base_price: formData.base_price ? parseFloat(formData.base_price) : (formData.mrp ? parseFloat(formData.mrp) : null),
        stock_quantity: qty,
        confirm_existing: confirmExisting,
        force_new_batch: forceNewBatch
      };

      const res = await createBatch(payload);
      setSuccessResult({
        ...res,
        product_name: formData.product_name,
        added_stock: qty,
        is_updated: confirmExisting
      });
      setOcrResult(null);
    } catch (err) {
      if (err.status === 409 || err.existing_batch) {
        setExistingBatchConflict({
          message: err.message,
          batch: err.existing_batch
        });
      } else {
        setError(err.message || "Failed to save batch. Please try again.");
      }
    } finally {
      setLoading(false);
      setLoadingStep("");
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    submitBatch(false, false);
  };

  const handleConfirmAddStock = () => {
    submitBatch(true, false);
  };

  const handleForceNewBatch = () => {
    submitBatch(false, true);
  };

  const resetAll = () => {
    setImage(null);
    setImagePreview(null);
    setOcrResult(null);
    setSuccessResult(null);
    setError(null);
    setExistingBatchConflict(null);
    setFormData({
      product_name: '',
      manufacturer: '',
      category: '',
      sku: '',
      batch_number: '',
      manufacturing_date: '',
      expiry_date: '',
      mrp: '',
      base_price: '',
      stock_quantity: ''
    });
  };

  const renderConfidenceBadge = (fieldKey) => {
    const conf = ocrResult?.confidence?.[fieldKey];
    if (conf == null || conf === 0) {
      return (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 font-mono">
          Manual input
        </span>
      );
    }
    if (conf >= 0.8) {
      return (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-950 text-green-400 font-mono flex items-center gap-1">
          <Sparkles size={10} /> AI {(conf * 100).toFixed(0)}%
        </span>
      );
    }
    if (conf >= 0.5) {
      return (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-950 text-yellow-400 font-mono">
          Moderate ({(conf * 100).toFixed(0)}%)
        </span>
      );
    }
    return (
      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-950 text-red-400 font-mono">
        Low conf ({(conf * 100).toFixed(0)}%)
      </span>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-gray-700">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            Inventory Scanner
            <span className="text-xs font-normal px-2 py-0.5 rounded-full bg-accent/20 text-accent font-mono">
              Hybrid Vision AI
            </span>
          </h1>
          <p className="text-sm text-muted">
            Upload single product packaging photo to automatically extract product name, dates, MRP, and batch details.
          </p>
        </div>
      </div>
      
      {/* STEPS INDICATOR */}
      {!successResult && (
        <div className="flex mb-6 border-b border-gray-700 pb-3 text-xs tracking-wider uppercase font-semibold">
          <div className={`flex-1 text-center pb-1 ${!ocrResult ? 'text-accent border-b-2 border-accent' : 'text-muted'}`}>
            1. Upload Product Photo
          </div>
          <div className={`flex-1 text-center pb-1 ${ocrResult ? 'text-accent border-b-2 border-accent' : 'text-muted'}`}>
            2. Verify & Save Batch
          </div>
        </div>
      )}

      {error && (
        <div className="alert alert-error mb-6 flex items-start gap-2">
          <AlertCircle size={18} className="shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* STEP 3: SUCCESS VIEW */}
      {successResult && (
        <div className="card max-w-xl mx-auto text-center py-8 px-6 shadow-xl border border-green-500/30">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-500/10 text-green-400 mb-4">
            <CheckCircle size={36} />
          </div>
          <h2 className="text-2xl font-bold mb-1 text-white">Batch Saved Successfully</h2>
          <p className="text-sm text-muted mb-6">
            {successResult.is_updated ? "Stock successfully added to existing batch." : "New inventory batch successfully registered."}
          </p>
          
          <div className="bg-[#1e202d] border border-gray-700 rounded-lg p-5 text-left mb-6 mx-auto w-full shadow-inner">
            <div className="grid grid-cols-2 gap-y-3 gap-x-4 text-sm">
              <div className="text-muted">Product</div>
              <div className="font-bold text-white truncate">{successResult.product_name || formData.product_name}</div>
              
              <div className="text-muted">Internal Batch ID</div>
              <div className="font-mono text-accent text-xs font-semibold">{successResult.internal_batch_id}</div>

              {successResult.batch_number && (
                <>
                  <div className="text-muted">Batch / Lot #</div>
                  <div className="font-mono font-semibold">{successResult.batch_number}</div>
                </>
              )}

              <div className="text-muted">Expiry Date</div>
              <div className="font-bold text-white">{successResult.expiry_date}</div>

              <div className="text-muted border-t border-gray-700 pt-2">Units Added</div>
              <div className="font-bold text-green-400 border-t border-gray-700 pt-2 font-mono">+{successResult.added_stock} units</div>

              <div className="text-muted">Total Batch Stock</div>
              <div className="font-bold text-xl text-white font-mono">{successResult.stock_quantity} units</div>
            </div>
          </div>

          <div className="flex justify-center gap-3">
            <Link to="/inventory" className="btn btn-secondary px-6 py-2.5 text-sm">
              View Inventory
            </Link>
            <button onClick={resetAll} className="btn btn-primary flex items-center gap-2 px-6 py-2.5 text-sm">
              <PackagePlus size={16} /> Scan Another Product
            </button>
          </div>
        </div>
      )}

      {/* MAIN SCANNER WORKFLOW */}
      {!successResult && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* LEFT: SINGLE COMPACT UPLOAD CARD */}
          <div className={`col-span-1 ${ocrResult ? 'lg:col-span-4' : 'lg:col-span-12'} space-y-4`}>
            
            <div className="card p-4 bg-[#252836] border border-gray-700 flex flex-col justify-between max-w-md mx-auto">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Product Packaging Image</span>
                {imagePreview && (
                  <button 
                    onClick={handleRemoveImage} 
                    className="text-gray-400 hover:text-red-400 transition"
                    title="Remove image"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>

              {imagePreview ? (
                <div className="relative mb-3 bg-[#181a24] rounded border border-gray-700 flex items-center justify-center h-44 overflow-hidden">
                  <img src={imagePreview} alt="Product Packaging" className="object-contain h-full w-full" />
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-44 border border-dashed border-gray-700 rounded bg-[#1e202d] mb-3 text-muted">
                  <ImageIcon size={32} className="mb-2 opacity-40 text-accent" />
                  <span className="text-xs font-medium">Upload photo of packaging or label</span>
                  <span className="text-[11px] text-gray-500 mt-1">JPEG, PNG, WebP up to 15MB</span>
                </div>
              )}

              <label className="btn btn-secondary text-xs cursor-pointer w-full text-center py-2.5">
                {imagePreview ? 'Change Product Photo' : 'Choose Product Photo'}
                <input type="file" accept="image/*" className="hidden" onChange={handleImageChange} />
              </label>
            </div>

            {/* INITIAL SCAN BUTTON */}
            {!ocrResult && (
              <div className="card text-center py-6 bg-[#1e202d] border border-gray-700 max-w-md mx-auto">
                <p className="text-xs text-muted mb-4">
                  EasyOCR extracts text while Gemini Vision AI interprets packaging labels, manufacturing dates, expiry dates, and MRP.
                </p>
                <button 
                  className="btn btn-primary w-full flex justify-center items-center gap-2 py-3 text-sm font-semibold shadow-lg shadow-accent/20"
                  onClick={handleScan}
                  disabled={loading || !image}
                >
                  {loading ? <Loader2 className="animate-spin" size={18} /> : <Scan size={18} />}
                  {loading ? 'Analyzing Packaging...' : 'Scan Product Photo'}
                </button>
                {loading && (
                  <p className="text-accent text-xs mt-3 animate-pulse font-medium">
                    {loadingStep}
                  </p>
                )}
              </div>
            )}

            {/* OCR SUMMARY & RAW DATA TOGGLE (WHEN SCANNED) */}
            {ocrResult && (
              <div className="card p-4 bg-[#1e202d] border border-gray-700 space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-gray-800">
                  <span className="text-xs font-bold uppercase tracking-wider text-gray-400">AI Extraction Status</span>
                  <button 
                    onClick={handleScan}
                    disabled={loading}
                    className="text-xs text-accent hover:underline flex items-center gap-1"
                  >
                    <Scan size={12} /> Rescan
                  </button>
                </div>

                {/* WARNINGS */}
                {ocrResult.warnings && ocrResult.warnings.length > 0 && (
                  <div className="bg-yellow-950/40 border border-yellow-800 text-yellow-300 p-2.5 rounded text-xs">
                    <div className="font-semibold flex items-center mb-1"><AlertTriangle size={13} className="mr-1"/> Warnings</div>
                    <ul className="list-disc pl-4 space-y-0.5 text-[11px]">
                      {ocrResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  </div>
                )}

                {/* CONFLICTS */}
                {ocrResult.conflicts && ocrResult.conflicts.length > 0 && (
                  <div className="bg-red-950/40 border border-red-800 text-red-300 p-2.5 rounded text-xs">
                    <div className="font-semibold flex items-center mb-1"><AlertCircle size={13} className="mr-1"/> Discrepancies</div>
                    <ul className="list-disc pl-4 space-y-0.5 text-[11px]">
                      {ocrResult.conflicts.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                  </div>
                )}

                {/* ADVANCED RAW OCR OUTPUT COLLAPSIBLE */}
                <div>
                  <button 
                    onClick={() => setShowRawOcr(!showRawOcr)}
                    className="text-xs font-medium text-gray-400 hover:text-white flex items-center justify-between w-full py-1.5 px-2 bg-[#252836] rounded transition"
                  >
                    <span>Raw OCR Text</span>
                    {showRawOcr ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  
                  {showRawOcr && (
                    <pre className="mt-2 p-2.5 bg-black rounded text-[11px] text-gray-400 font-mono overflow-x-auto whitespace-pre-wrap max-h-48 border border-gray-800">
                      {ocrResult.raw_text || "No text detected."}
                    </pre>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* RIGHT: VERIFICATION & BATCH FORM */}
          {ocrResult && (
            <div className="col-span-1 lg:col-span-8">
              <div className="card p-6 border border-gray-700 shadow-xl">
                <div className="mb-5 pb-3 border-b border-gray-700 flex justify-between items-center">
                  <div>
                    <h2 className="text-lg font-bold text-white">Extracted Information</h2>
                    <p className="text-xs text-muted">Verify the AI-extracted fields below and provide the physical batch stock quantity.</p>
                  </div>
                  <button 
                    type="button" 
                    onClick={resetAll} 
                    className="text-xs text-gray-400 hover:text-white"
                  >
                    Discard & Start Over
                  </button>
                </div>

                {/* EXISTING BATCH CONFLICT CARD */}
                {existingBatchConflict && (
                  <div className="bg-[#2d2215] border border-amber-500 text-amber-100 p-4 rounded-lg mb-6 shadow-lg animate-fade-in">
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="text-amber-400 mt-0.5 shrink-0" size={20} />
                      <div className="space-y-2 w-full">
                        <h3 className="font-bold text-sm text-amber-300">Existing Batch Found in Inventory</h3>
                        <p className="text-xs text-amber-200">
                          {existingBatchConflict.message}
                        </p>
                        
                        {existingBatchConflict.batch && (
                          <div className="bg-[#1e170e] p-3 rounded border border-amber-700/50 text-xs grid grid-cols-2 gap-2 my-2 font-mono">
                            <div>Product: <span className="text-white font-sans font-semibold">{existingBatchConflict.batch.product_name}</span></div>
                            <div>SKU: <span className="text-white">{existingBatchConflict.batch.sku}</span></div>
                            <div>Batch #: <span className="text-white">{existingBatchConflict.batch.batch_number || 'N/A'}</span></div>
                            <div>Expiry: <span className="text-white font-bold">{existingBatchConflict.batch.expiry_date}</span></div>
                            <div>Current Stock: <span className="text-amber-400 font-bold">{existingBatchConflict.batch.stock_quantity} units</span></div>
                            <div>Incoming: <span className="text-green-400 font-bold">+{formData.stock_quantity} units</span></div>
                          </div>
                        )}

                        <div className="flex flex-wrap gap-2 pt-2">
                          <button 
                            type="button"
                            onClick={handleConfirmAddStock} 
                            disabled={loading}
                            className="btn btn-warning flex items-center gap-1.5 text-xs py-2 px-4 font-semibold"
                          >
                            {loading ? <Loader2 className="animate-spin" size={14} /> : <PlusCircle size={14} />}
                            Add to Existing Batch ({existingBatchConflict.batch ? existingBatchConflict.batch.stock_quantity + parseInt(formData.stock_quantity || 0) : ''} units total)
                          </button>
                          
                          <button 
                            type="button"
                            onClick={handleForceNewBatch} 
                            disabled={loading}
                            className="btn btn-secondary flex items-center gap-1.5 text-xs py-2 px-4"
                          >
                            <Layers size={14} /> Create Separate Batch
                          </button>

                          <button 
                            type="button"
                            onClick={() => setExistingBatchConflict(null)} 
                            className="text-xs text-gray-400 hover:text-white px-3 py-2"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-5">
                  
                  {/* SECTION 1: PRODUCT IDENTITY */}
                  <div>
                    <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3 pb-1 border-b border-gray-800">
                      Product Identity
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="col-span-1 md:col-span-2">
                        <label className="block text-xs font-semibold mb-1 flex justify-between">
                          <span>Product Name *</span>
                          {renderConfidenceBadge("product_name")}
                        </label>
                        <input 
                          type="text" 
                          name="product_name" 
                          value={formData.product_name} 
                          onChange={handleFormChange} 
                          className="form-input w-full font-medium" 
                          placeholder="e.g. Premium Mango Pickle" 
                          required 
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold mb-1 flex justify-between">
                          <span>Manufacturer / Brand</span>
                          {renderConfidenceBadge("manufacturer")}
                        </label>
                        <input 
                          type="text" 
                          name="manufacturer" 
                          value={formData.manufacturer} 
                          onChange={handleFormChange} 
                          className="form-input w-full" 
                          placeholder="e.g. Heritage Foods Ltd" 
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold mb-1 flex justify-between">
                          <span>Category</span>
                          {renderConfidenceBadge("category")}
                        </label>
                        <input 
                          type="text" 
                          name="category" 
                          value={formData.category} 
                          onChange={handleFormChange} 
                          className="form-input w-full" 
                          placeholder="e.g. Pickles, Dairy, Snacks" 
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold mb-1">
                          SKU (Optional)
                        </label>
                        <input 
                          type="text" 
                          name="sku" 
                          value={formData.sku} 
                          onChange={handleFormChange} 
                          className="form-input w-full font-mono text-xs" 
                          placeholder="Auto-generated if empty" 
                        />
                      </div>
                    </div>
                  </div>

                  {/* SECTION 2: BATCH & DATES */}
                  <div>
                    <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3 pb-1 border-b border-gray-800">
                      Batch & Expiry Dates
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold mb-1 flex justify-between">
                          <span>Batch / Lot Number</span>
                          {renderConfidenceBadge("batch_number")}
                        </label>
                        <input 
                          type="text" 
                          name="batch_number" 
                          value={formData.batch_number} 
                          onChange={handleFormChange} 
                          className="form-input w-full font-mono text-sm" 
                          placeholder="e.g. LOT-2026-A1" 
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold mb-1 flex justify-between text-yellow-400">
                          <span>Expiry Date (YYYY-MM-DD) *</span>
                          {renderConfidenceBadge("expiry_date")}
                        </label>
                        <input 
                          type="text" 
                          name="expiry_date" 
                          value={formData.expiry_date} 
                          onChange={handleFormChange} 
                          className={`form-input w-full font-medium ${!formData.expiry_date ? 'border-yellow-500/60 bg-yellow-950/10' : ''}`} 
                          placeholder="YYYY-MM-DD" 
                          required 
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold mb-1 flex justify-between">
                          <span>Manufacturing Date (YYYY-MM-DD)</span>
                          {renderConfidenceBadge("manufacturing_date")}
                        </label>
                        <input 
                          type="text" 
                          name="manufacturing_date" 
                          value={formData.manufacturing_date} 
                          onChange={handleFormChange} 
                          className="form-input w-full" 
                          placeholder="YYYY-MM-DD" 
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold mb-1 flex justify-between">
                          <span>MRP (Packaging Price)</span>
                          {renderConfidenceBadge("mrp")}
                        </label>
                        <input 
                          type="number" 
                          step="0.01" 
                          name="mrp" 
                          value={formData.mrp} 
                          onChange={handleFormChange} 
                          className="form-input w-full" 
                          placeholder="e.g. 150.00" 
                        />
                      </div>
                    </div>
                  </div>

                  {/* SECTION 3: INCOMING STOCK QUANTITY */}
                  <div>
                    <h3 className="text-xs font-bold text-accent uppercase tracking-wider mb-3 pb-1 border-b border-gray-800">
                      Physical Stock Quantity
                    </h3>
                    <div className="bg-[#252836] p-4 rounded-lg border border-accent/40 shadow-inner">
                      <label className="block text-sm font-bold text-white mb-1">
                        Incoming Batch Quantity (Units) *
                      </label>
                      <p className="text-xs text-muted mb-2">
                        Enter the physical unit count represented by this batch scan (e.g. 250 units).
                      </p>
                      <input 
                        type="number" 
                        min="1" 
                        name="stock_quantity" 
                        value={formData.stock_quantity} 
                        onChange={handleFormChange} 
                        className="form-input w-full text-2xl font-bold py-2.5 px-3 font-mono bg-[#181a24] border-accent focus:ring-accent" 
                        placeholder="e.g. 250" 
                        required 
                      />
                    </div>
                  </div>

                  {/* FORM ACTIONS */}
                  <div className="pt-3 border-t border-gray-700 flex gap-3">
                    <button 
                      type="button" 
                      onClick={resetAll} 
                      className="btn btn-secondary flex-1 py-2.5 text-sm" 
                      disabled={loading}
                    >
                      Cancel
                    </button>
                    <button 
                      type="submit" 
                      disabled={loading} 
                      className="btn btn-primary flex-2 flex justify-center items-center gap-2 py-2.5 px-6 text-sm font-semibold shadow-lg shadow-accent/20"
                    >
                      {loading ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                      {loading ? (loadingStep || 'Saving Batch...') : 'Save Batch to Inventory'}
                    </button>
                  </div>

                </form>
              </div>
            </div>
          )}

        </div>
      )}
    </div>
  );
}
