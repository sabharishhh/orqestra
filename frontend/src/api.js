const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TOKEN = import.meta.env.VITE_ORQESTRA_TOKEN || "";

const HEADERS = TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};

const get = async (path, errMsg) => {
    const res = await fetch(`${API_BASE}${path}`, { headers: HEADERS });
    if (!res.ok) throw new Error(`${errMsg} (${res.status})`);
    return res.json();
};

// ---- v3 (existing) ----
export const fetchROI = () => get("/roi/summary", "Failed to fetch ROI");
export const fetchContradictions = (status = "open") =>
    get(`/contradictions/?status=${status}`, "Failed to fetch Contradictions");
export const fetchResolution = (id) => get(`/resolutions/${id}`, "Failed to fetch Resolution");
export const fetchPendingResolutions = () =>
    get("/resolutions/pending", "Failed to fetch pending resolutions");
export const fetchLineage = (id) => get(`/contradictions/${id}/lineage`, "Lineage data not found");
export const fetchLineageGraph = (id) =>
    get(`/contradictions/${id}/lineage-graph`, "Lineage graph not found");
export const fetchBlastRadius = (id) =>
    get(`/contradictions/${id}/blast-radius`, "Blast radius not found");

// ---- v4 estate (Sprint 11) ----
export const fetchSystems = () => get("/systems/", "Failed to fetch systems");
export const fetchEstateScore = () => get("/systems/estate/score", "Failed to fetch estate score");
export const fetchSystemScore = (id) =>
    get(`/systems/${id}/score`, "Failed to fetch system score");
export const fetchSystemSubscriptions = (id) =>
    get(`/systems/${id}/subscriptions`, "Failed to fetch subscriptions");
export const fetchSystemRecentClaims = (id, limit = 20) =>
    get(`/systems/${id}/claims/recent?limit=${limit}`, "Failed to fetch recent claims");
export const fetchSystemKB = (id) => get(`/systems/${id}/kb`, "Failed to fetch KB");
export const fetchSystemCanonLookups = (id, limit = 50) =>
    get(`/systems/${id}/canon_lookups/recent?limit=${limit}`, "Failed to fetch canon lookups");

// ---- v4 canon (Sprint 11) ----
export const fetchCanonList = (includeEmpty = false) =>
    get(`/canon/list?include_empty=${includeEmpty}`, "Failed to fetch canon list");

export const fetchCanonLookupSummary = () =>
    get("/canon/lookups/summary", "Failed to fetch canon lookup summary");

export const fetchCanonGraph = () => get("/canon/graph", "Failed to fetch canon graph");

export const fetchCanonStores = async () => {
    const graph = await fetchCanonGraph();
    return graph.stores.map((s) => ({
        store_id: s.store_id,
        store_name: s.store_name,
        store_description: s.store_description,
        entity_count: s.entities.length,
    }));
};

export const declareCanonValue = async ({ store_id, canonical_name, canonical_value, canonical_claim_text, declared_by }) => {
    const res = await fetch(`${API_BASE}/canon/declare`, {
        method: "POST",
        headers: { ...HEADERS, "Content-Type": "application/json" },
        body: JSON.stringify({ store_id, canonical_name, canonical_value, canonical_claim_text, declared_by }),
    });
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`Declare failed (${res.status}): ${body}`);
    }
    return res.json();
};

export const promoteCanonCandidate = async (candidate_id, { canonical_value, canonical_claim_text, declared_by }) => {
    const res = await fetch(`${API_BASE}/canon/promote/${candidate_id}`, {
        method: "POST",
        headers: { ...HEADERS, "Content-Type": "application/json" },
        body: JSON.stringify({ canonical_value, canonical_claim_text, declared_by }),
    });
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`Promote failed (${res.status}): ${body}`);
    }
    return res.json();
};

export const createAgent = async ({ name, provider, description, kb_yaml, subscriptions }) => {
    const res = await fetch(`${API_BASE}/systems/`, {
        method: "POST",
        headers: { ...HEADERS, "Content-Type": "application/json" },
        body: JSON.stringify({ name, provider, description, kb_yaml, subscriptions }),
    });
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`Create agent failed (${res.status}): ${body}`);
    }
    return res.json();
};