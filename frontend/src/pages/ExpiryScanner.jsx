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
  Upload, 
  X,
  Sparkles,
  CheckCircle2
} from 'lucide-react';
import { Link } from 'react-router-dom';

export default function ExpiryScanner() {
  const [image, setImage] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [dragActive, setDragActive] = useState(false);

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

  const processFile = (file) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setError("Please upload an image file (JPEG, PNG, WebP).");
      return;
    }
    setImage(file);
    setImagePreview(URL.createObjectURL(file));
    setError(null);
  };

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    processFile(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
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
    if (loading) {
      return;
    }
    
    setLoading(true);
    setLoadingStep("Preprocessing image & analyzing packaging...");
    setError(null);
    setOcrResult(null);
    setSuccessResult(null);
    setExistingBatchConflict(null);

    try {
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
        mrp: res.mrp != null ? res.mrp.toString() : '',
        base_price: res.base_price != null ? res.base_price.toString() : '',
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
    const val = formData[fieldKey];
    if (!val || conf == null || conf === 0) {
      return (
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-page text-muted font-mono whitespace-nowrap shrink-0 border border-subtle" title="Could not confidently extract this field — please verify manually.">
          Manual input
        </span>
      );
    }
    if (conf >= 0.8) {
      return (
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-teal-bg text-teal font-mono inline-flex items-center gap-1 font-bold whitespace-nowrap shrink-0">
          <Sparkles size={10} /> Mistral {(conf * 100).toFixed(0)}%
        </span>
      );
    }
    if (conf >= 0.5) {
      return (
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-gold-bg text-gold font-mono font-bold whitespace-nowrap shrink-0">
          Moderate ({(conf * 100).toFixed(0)}%)
        </span>
      );
    }
    return (
      <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-gold-bg text-gold font-mono font-bold whitespace-nowrap shrink-0" title="Could not confidently extract this field — please verify manually.">
        Low conf ({(conf * 100).toFixed(0)}%)
      </span>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-subtle">
        <div>
          <h1 className="flex items-center gap-3">
            Inventory Scanner
            <span className="status-pill status-safe font-mono text-xs">
              Mistral Vision AI
            </span>
          </h1>
          <p className="text-sm text-muted">
            Upload product packaging photo to automatically extract product details, batch numbers, MRP, and shelf life dates.
          </p>
        </div>
      </div>
      
      {/* VISUAL STEPPER COMPONENT */}
      {!successResult && (
        <div className="stepper-container">
          <div className={`stepper-step ${!ocrResult ? 'active' : 'completed'}`}>
            <div className="stepper-circle">
              {ocrResult ? <CheckCircle2 size={18} /> : 1}
            </div>
            <div className="stepper-label">1. Upload Packaging Photo</div>
          </div>

          <div className={`stepper-line ${ocrResult ? 'completed' : ''}`} />

          <div className={`stepper-step ${ocrResult ? 'active' : ''}`}>
            <div className="stepper-circle">2</div>
            <div className="stepper-label">2. Verify & Save Batch</div>
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
        <div className="card max-w-xl mx-auto text-center py-8 px-6">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-accent-teal-bg text-teal mb-4">
            <CheckCircle size={36} />
          </div>
          <h2 className="text-2xl font-bold mb-1">Batch Saved Successfully</h2>
          <p className="text-sm text-muted mb-6">
            {successResult.is_updated ? "Stock successfully added to existing batch." : "New inventory batch successfully registered."}
          </p>
          
          <div className="card p-5 text-left mb-6 mx-auto w-full border border-subtle bg-page">
            <div className="grid grid-cols-2 gap-y-3 gap-x-4 text-sm" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div className="text-muted">Product</div>
              <div className="font-bold text-primary truncate">{successResult.product_name || formData.product_name}</div>
              
              <div className="text-muted">Internal Batch ID</div>
              <div className="font-mono text-teal text-xs font-bold">{successResult.internal_batch_id}</div>

              {successResult.batch_number && (
                <>
                  <div className="text-muted">Batch / Lot #</div>
                  <div className="font-mono font-bold text-primary">{successResult.batch_number}</div>
                </>
              )}

              <div className="text-muted">Expiry Date</div>
              <div className="font-bold text-primary font-mono">{successResult.expiry_date}</div>

              <div className="text-muted border-t border-subtle pt-2">Units Added</div>
              <div className="font-bold text-teal border-t border-subtle pt-2 font-mono">+{successResult.added_stock} units</div>

              <div className="text-muted">Total Batch Stock</div>
              <div className="font-bold text-xl text-primary font-mono">{successResult.stock_quantity} units</div>
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
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6" style={{ display: 'grid', gridTemplateColumns: ocrResult ? '1fr 2fr' : '1fr', gap: '1.5rem' }}>
          
          {/* LEFT: DROPZONE CARD */}
          <div className="space-y-4">
            
            <div className="card p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-muted">Product Packaging Photo</span>
                {imagePreview && (
                  <button 
                    onClick={handleRemoveImage} 
                    className="btn-ghost text-muted hover:text-danger p-1"
                    title="Remove image"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>

              {/* DROPZONE AREA */}
              {!imagePreview ? (
                <div 
                  className={`dropzone ${dragActive ? 'drag-active' : ''}`}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  <label className="cursor-pointer flex flex-col items-center justify-center">
                    <Upload size={36} className="mb-3 text-teal" strokeWidth={1.5} />
                    <span className="text-sm font-bold text-primary mb-1">Drag & drop packaging photo here</span>
                    <span className="text-xs text-muted mb-3">or click to browse your file system</span>
                    <span className="btn btn-secondary text-xs py-1.5 px-4">Choose Photo</span>
                    <input type="file" accept="image/*" className="hidden" onChange={handleImageChange} />
                  </label>
                </div>
              ) : (
                <div className="product-image-container relative mb-3">
                  <img 
                    src={imagePreview} 
                    alt="Product Packaging" 
                    className="product-image-preview" 
                  />
                </div>
              )}

              {imagePreview && (
                <label className="btn btn-secondary text-xs cursor-pointer w-full text-center py-2 mt-3" style={{ width: '100%' }}>
                  Change Product Photo
                  <input type="file" accept="image/*" className="hidden" onChange={handleImageChange} />
                </label>
              )}
            </div>

            {/* INITIAL SCAN BUTTON */}
            {!ocrResult && (
              <div className="card text-center py-6">
                <p className="text-xs text-muted mb-4">
                  Mistral Vision model (Ministral 3 14B) accurately extracts packaging text, product details, batch numbers, MRP, and shelf-life dates directly from packaging photos.
                </p>
                <button 
                  className="btn btn-primary w-full flex justify-center items-center gap-2 py-3 text-sm font-bold"
                  onClick={handleScan}
                  disabled={loading || !image}
                  style={{ width: '100%' }}
                >
                  {loading ? <Loader2 className="animate-spin" size={18} /> : <Scan size={18} />}
                  {loading ? 'Analyzing Packaging...' : 'Scan Product Photo'}
                </button>
                {loading && (
                  <p className="text-teal text-xs mt-3 animate-pulse font-medium">
                    {loadingStep}
                  </p>
                )}
              </div>
            )}

            {/* OCR SUMMARY & RAW DATA TOGGLE (WHEN SCANNED) */}
            {ocrResult && (
              <div className="card p-4 space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-subtle">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted">AI Extraction Status</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent-teal-bg text-teal font-mono font-bold flex items-center gap-1">
                      <Sparkles size={10} />
                      Extracted using Mistral Vision
                    </span>
                  </div>
                  <button 
                    onClick={handleScan}
                    disabled={loading}
                    className="text-xs text-teal hover:underline flex items-center gap-1 font-bold"
                  >
                    <Scan size={12} /> Rescan
                  </button>
                </div>

                {/* AI INTERPRETATION / PRODUCT INFORMATION SUMMARY */}
                {ocrResult.warnings && ocrResult.warnings.length > 0 && (
                  <div className="p-3.5 bg-page rounded-xl border border-subtle text-xs">
                    <div className="font-bold text-primary flex items-center gap-1.5 mb-2">
                      <Sparkles size={14} className="text-teal shrink-0" />
                      <span>AI Interpretation</span>
                    </div>
                    <ul className="space-y-1.5 text-[11px] text-muted list-disc pl-4 leading-relaxed">
                      {ocrResult.warnings.map((w, i) => (
                        <li key={i} className="text-secondary">{w}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* CONFLICTS / DISCREPANCIES */}
                {ocrResult.conflicts && ocrResult.conflicts.length > 0 && (
                  <div className="alert alert-error text-xs p-3">
                    <div className="font-bold flex items-center mb-1"><AlertCircle size={14} className="mr-1"/> Discrepancies</div>
                    <ul className="list-disc pl-4 space-y-0.5 text-[11px]">
                      {ocrResult.conflicts.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                  </div>
                )}

                {/* ADVANCED RAW OCR OUTPUT COLLAPSIBLE */}
                <div>
                  <button 
                    onClick={() => setShowRawOcr(!showRawOcr)}
                    className="btn-ghost text-xs font-bold text-muted hover:text-primary flex items-center justify-between w-full py-1.5 px-2 bg-page rounded-lg transition"
                  >
                    <span>Raw OCR Text</span>
                    {showRawOcr ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  
                  {showRawOcr && (
                    <pre className="mt-2 p-2.5 bg-page rounded-lg text-[11px] text-muted font-mono overflow-x-auto whitespace-pre-wrap max-h-48 border border-subtle">
                      {ocrResult.raw_text || "No text detected."}
                    </pre>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* RIGHT: VERIFICATION & BATCH FORM */}
          {ocrResult && (
            <div>
              <div className="card p-6">
                <div className="mb-5 pb-3 border-b border-subtle flex justify-between items-center">
                  <div>
                    <h2>Extracted Information</h2>
                    <p className="text-xs text-muted">Verify the AI-extracted fields below and provide the physical batch stock quantity.</p>
                  </div>
                  <button 
                    type="button" 
                    onClick={resetAll} 
                    className="btn-ghost text-xs text-muted hover:text-primary"
                  >
                    Cancel / Reset
                  </button>
                </div>

                {/* CONFLICT WARNING BANNER (409 EXISTING BATCH) */}
                {existingBatchConflict && (
                  <div className="alert alert-error mb-6 flex flex-col items-start gap-3">
                    <div className="flex items-center gap-2 font-bold text-sm">
                      <AlertTriangle size={18} />
                      {existingBatchConflict.message}
                    </div>
                    <p className="text-xs">
                      A batch with number <strong className="font-mono">{formData.batch_number}</strong> already exists for this product. 
                      Saving as an existing batch will add your entered quantity to the current stock.
                    </p>
                    <div className="flex gap-2 mt-1">
                      <button 
                        type="button" 
                        onClick={handleConfirmAddStock} 
                        className="btn btn-primary text-xs py-1.5 px-3"
                      >
                        Add to Existing Stock
                      </button>
                      <button 
                        type="button" 
                        onClick={handleForceNewBatch} 
                        className="btn btn-secondary text-xs py-1.5 px-3"
                      >
                        Force New Unique Batch
                      </button>
                    </div>
                  </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                  
                  {/* PRODUCT NAME & SKU */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">Product Name *</label>
                        {renderConfidenceBadge('product_name')}
                      </div>
                      <input 
                        type="text" 
                        required 
                        name="product_name" 
                        value={formData.product_name} 
                        onChange={handleFormChange} 
                        className="form-input" 
                        placeholder="e.g. Organic Whole Milk 1L"
                      />
                    </div>

                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">SKU / Code</label>
                        {renderConfidenceBadge('sku')}
                      </div>
                      <input 
                        type="text" 
                        name="sku" 
                        value={formData.sku} 
                        onChange={handleFormChange} 
                        className="form-input font-mono text-sm" 
                        placeholder="Auto-generated if blank"
                      />
                    </div>
                  </div>

                  {/* MANUFACTURER & CATEGORY */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">Manufacturer</label>
                        {renderConfidenceBadge('manufacturer')}
                      </div>
                      <input 
                        type="text" 
                        name="manufacturer" 
                        value={formData.manufacturer} 
                        onChange={handleFormChange} 
                        className="form-input" 
                        placeholder="e.g. Amul Dairy"
                      />
                    </div>

                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">Category</label>
                        {renderConfidenceBadge('category')}
                      </div>
                      <input 
                        type="text" 
                        name="category" 
                        value={formData.category} 
                        onChange={handleFormChange} 
                        className="form-input" 
                        placeholder="e.g. Dairy & Fresh Produce"
                      />
                    </div>
                  </div>

                  {/* BATCH NUMBER & QUANTITY */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">Batch / Lot Number</label>
                        {renderConfidenceBadge('batch_number')}
                      </div>
                      <input 
                        type="text" 
                        name="batch_number" 
                        value={formData.batch_number} 
                        onChange={handleFormChange} 
                        className="form-input font-mono text-sm" 
                        placeholder="e.g. BATCH-2026-X9"
                      />
                    </div>

                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">Stock Quantity (Units) *</label>
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-page text-muted font-mono whitespace-nowrap shrink-0 border border-subtle" title="Physical stock quantity requires manual verification.">
                          Manual input
                        </span>
                      </div>
                      <input 
                        type="number" 
                        required 
                        min="1"
                        name="stock_quantity" 
                        value={formData.stock_quantity} 
                        onChange={handleFormChange} 
                        className="form-input font-mono text-sm font-bold" 
                        placeholder="e.g. 50"
                      />
                    </div>
                  </div>

                  {/* DATES: MFG & EXPIRY */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">Manufacturing Date</label>
                        {renderConfidenceBadge('manufacturing_date')}
                      </div>
                      <input 
                        type="text" 
                        name="manufacturing_date" 
                        value={formData.manufacturing_date} 
                        onChange={handleFormChange} 
                        className="form-input font-mono text-sm" 
                        placeholder="YYYY-MM-DD"
                      />
                    </div>

                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">Expiry Date *</label>
                        {renderConfidenceBadge('expiry_date')}
                      </div>
                      <input 
                        type="text" 
                        required 
                        name="expiry_date" 
                        value={formData.expiry_date} 
                        onChange={handleFormChange} 
                        className="form-input font-mono text-sm font-bold text-teal" 
                        placeholder="YYYY-MM-DD"
                      />
                    </div>
                  </div>

                  {/* PRICES: MRP & BASE PRICE */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">Maximum Retail Price (MRP)</label>
                        {renderConfidenceBadge('mrp')}
                      </div>
                      <div className="input-with-label w-full">
                        <span className="input-unit-prefix">₹</span>
                        <input 
                          type="number" 
                          step="0.01"
                          name="mrp" 
                          value={formData.mrp} 
                          onChange={handleFormChange} 
                          className="form-input has-prefix font-mono text-sm w-full" 
                          placeholder="0.00"
                        />
                      </div>
                    </div>

                    <div className="form-group mb-0">
                      <div className="flex justify-between items-center gap-2 mb-1.5 h-6">
                        <label className="form-label mb-0 truncate">Base Cost Price</label>
                        {renderConfidenceBadge('base_price')}
                      </div>
                      <div className="input-with-label w-full">
                        <span className="input-unit-prefix">₹</span>
                        <input 
                          type="number" 
                          step="0.01"
                          name="base_price" 
                          value={formData.base_price} 
                          onChange={handleFormChange} 
                          className="form-input has-prefix font-mono text-sm w-full" 
                          placeholder="0.00"
                        />
                      </div>
                    </div>
                  </div>

                  {/* SUBMIT BUTTON */}
                  <div className="pt-3 border-t border-subtle">
                    <button 
                      type="submit" 
                      disabled={loading}
                      className="btn btn-primary w-full flex items-center justify-center gap-2 py-3 text-base"
                      style={{ width: '100%' }}
                    >
                      {loading ? <Loader2 className="animate-spin" size={20} /> : <Save size={20} />}
                      Save Batch to Inventory
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
