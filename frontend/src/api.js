const API_BASE = "http://localhost:8000";

export const fetchROI = async () => {
    const res = await fetch(`${API_BASE}/roi/summary`);
    if (!res.ok) throw new Error("Failed to fetch ROI");
    return res.json();
};

export const fetchContradictions = async (status = "open") => {
    const res = await fetch(`${API_BASE}/contradictions/?status=${status}`);
    if (!res.ok) throw new Error("Failed to fetch Contradictions");
    return res.json();
};

export const fetchResolution = async (id) => {
    const res = await fetch(`${API_BASE}/resolutions/${id}`);
    if (!res.ok) throw new Error("Failed to fetch Resolution");
    return res.json();
};

// FIX: Added explicit fetch for pending resolutions hitting the correct mounted path
export const fetchPendingResolutions = async () => {
    const res = await fetch(`${API_BASE}/resolutions/pending`);
    if (!res.ok) throw new Error("Failed to fetch pending resolutions");
    return res.json();
};