/**
 * lib/api.js
 * ----------
 * Reconciled API client for communicating with the FastAPI backend.
 * Points to http://127.0.0.1:8000 (or uses the Vite /api proxy).
 */

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';

const defaultHeaders = {
  'Content-Type': 'application/json',
  Authorization: 'Bearer demo',
};

/**
 * Generate initial sketch & traits from witness description and active disguises.
 */
export async function generateSketch(description, disguises = [], traits = null, caseId = null) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 60000);

  const payload = {
    description: (description || '').trim(),
    disguises: Array.isArray(disguises) ? disguises : Array.from(disguises || []),
    traits: traits || undefined,
  };

  try {
    const res = await fetch(`${API_BASE}/api/generate-sketch`, {
      method: 'POST',
      headers: defaultHeaders,
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Generation service returned error HTTP ${res.status}`);
    }

    const data = await res.json();
    const imageUrl = data.image_b64 || data.sketch_url || data.url || data.sketch_data || data.data || null;

    return {
      imageUrl,
      traits: data.traits || null,
      notes: data.traits?.notes || [],
      rawGeminiOutput: data.raw_gemini_output || '',
      caseId: data.case_id || null,
    };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Apply or remove a named disguise toggle chip (e.g., Mustache, Sunglasses).
 */
export async function applyDisguise(name, active, description = '', currentTraits = null, caseId = null) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 60000);

  const payload = {
    name,
    active: Boolean(active),
    description: (description || '').trim(),
    current_traits: currentTraits || undefined,
  };

  try {
    const res = await fetch(`${API_BASE}/api/apply-disguise`, {
      method: 'POST',
      headers: defaultHeaders,
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Disguise service returned error HTTP ${res.status}`);
    }

    const data = await res.json();
    const imageUrl = data.image_b64 || data.sketch_url || data.url || data.sketch_data || data.data || null;

    return {
      imageUrl,
      traits: data.traits || null,
      message: data.message || '',
      name: data.name,
      active: data.active,
      caseId: data.case_id || null,
    };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Refine sketch traits using feedback text and officer/witness role.
 */
export async function refineSketch(feedback, currentTraits = null, role = 'witness', description = '', caseId = null) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 60000);

  const normalizedRole = (role || '').toLowerCase() === 'officer' ? 'officer' : 'witness';
  const payload = {
    feedback: (feedback || '').trim(),
    current_traits: currentTraits || undefined,
    role: normalizedRole,
    description: (description || '').trim(),
  };

  try {
    const res = await fetch(`${API_BASE}/api/refine-sketch`, {
      method: 'POST',
      headers: defaultHeaders,
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Refinement service returned error HTTP ${res.status}`);
    }

    const data = await res.json();
    const imageUrl = data.image_b64 || data.sketch_url || data.url || data.sketch_data || data.data || null;

    return {
      imageUrl,
      traits: data.traits || null,
      summary: data.summary || '',
      caseId: data.case_id || null,
    };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Log export audit event.
 */
export async function exportAudit(caseId = null) {
  try {
    const res = await fetch(`${API_BASE}/api/export`, {
      method: 'POST',
      headers: defaultHeaders,
      body: JSON.stringify(caseId ? { case_id: caseId } : {}),
    });
    return res.ok;
  } catch {
    return false;
  }
}
