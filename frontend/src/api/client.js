const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function fetchAPI(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  
  const defaultHeaders = {};
  const isFormData = options.body instanceof FormData;

  if (options.body && !isFormData) {
    defaultHeaders["Content-Type"] = "application/json";
    if (typeof options.body !== "string") {
      options.body = JSON.stringify(options.body);
    }
  }

  const timeoutMs = options.timeout || (endpoint.includes("/ocr") ? 60000 : 30000);
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const config = {
    ...options,
    signal: controller.signal,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      let errorMsg = `Error: ${response.status} ${response.statusText}`;
      let errorData = null;

      try {
        errorData = await response.json();
        if (errorData.detail) {
          errorMsg = Array.isArray(errorData.detail)
            ? errorData.detail.map(d => `${d.loc ? d.loc.join('.') + ': ' : ''}${d.msg}`).join(', ')
            : errorData.detail;
        }
      } catch {
        // Response body wasn't JSON
      }

      const customError = new Error(errorMsg);
      customError.status = response.status;
      customError.data = errorData;
      if (errorData && errorData.existing_batch) {
        customError.existing_batch = errorData.existing_batch;
      }
      throw customError;
    }
    
    return await response.json();
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error("OCR processing timed out. Please try again with a clearer or smaller image.");
    }
    if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
      throw new Error("Network error: Could not connect to the backend server. Please check if the server is running.");
    }
    throw error;
  }
}

export const getHealth = () => fetchAPI("/health");

export const getDashboardStats = () => fetchAPI("/api/dashboard/stats");

export const getInventory = (limit = 50, offset = 0, search = "", status = "") => {
  const params = new URLSearchParams({ limit, offset });
  if (search) params.append("search", search);
  if (status && status !== "ALL") params.append("status", status);
  return fetchAPI(`/inventory?${params.toString()}`);
};

export const getInventoryBySku = (sku) => fetchAPI(`/inventory/${encodeURIComponent(sku)}`);

export const scanOcr = (imageFile) => {
  const formData = new FormData();
  if (imageFile) formData.append("image", imageFile);
  return fetchAPI("/ocr/scan", {
    method: "POST",
    body: formData,
    timeout: 30000,
  });
};

export const createBatch = (data) => fetchAPI("/inventory/batches", {
  method: "POST",
  body: data,
});

export const recommendPricing = (data) => fetchAPI("/pricing/recommend", {
  method: "POST",
  body: data,
});

export const calculateTax = (data) => fetchAPI("/tax/calculate", {
  method: "POST",
  body: data,
});

export const getNgoCandidates = () => fetchAPI("/api/ngo/candidates");

export const dispatchDonation = (batchId, ngo_name) => fetchAPI(`/api/ngo/dispatch/${batchId}`, {
  method: "POST",
  body: { ngo_name },
});

export const createDonationRequest = (data) => fetchAPI("/api/ngo/request", {
  method: "POST",
  body: data,
});

export const getNgoDonations = () => fetchAPI("/api/ngo/donations");
