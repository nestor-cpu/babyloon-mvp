# babyloon.ai API Reference

**Base URL:** `https://api.babyloon.ai` (production) | `http://localhost:8000` (local)
**Patent:** PCT/IB2026/053131
**Auth:** Bearer JWT in `Authorization` header. Missing/invalid token → fallback L2 (E6).

---

## System

### `GET /health`
```json
{ "status": "ok", "model_loaded": true, "patent": "PCT/IB2026/053131" }
```

---

## E5 — Hash-Chain Registry

### `POST /registry/append`
Requires L0.
```json
// Request
{ "record_type": "corpus_segment", "payload": { "segment_id": "...", ... } }

// Response — full record with hashes
{ "id": "uuid", "type": "corpus_segment", "payload": {...}, "prev_hash": "sha256...", "record_hash": "sha256...", "timestamp": "2026-..." }
```

### `GET /registry/verify`
```json
{ "valid": true, "message": "chain intact" }
```

### `GET /registry/{record_id}`
Returns single record by UUID.

### `GET /registry/session/{session_id}`
Returns all inference records for a session.

### `GET /registry`
Requires L1+. Returns all records.

---

## E2 + E6 — Agent Identity

### `POST /agent/register`
```json
// Request
{ "name": "MyAgent", "level": "L1", "ttl_days": 90 }

// Response
{ "agent": { "agent_id": "uuid", "authorization_level": "L1", ... }, "token": "eyJ..." }
```

**Levels:**
| Level | Corpus | Attention layers | Operations |
|-------|--------|-----------------|------------|
| L0 | Full | All | generate, manifest, registry, admin |
| L1 | Verified (CC0, CC-BY, Apache-2.0) | Upper half | generate, manifest, registry |
| L2 | Public (CC0, Public Domain) | Last only | generate, manifest |
| *fallback* | Public | Last only | generate, manifest |

### `POST /agent/verify`
Send JWT in Authorization header. Returns current agent's verification result.

### `GET /agent/{agent_id}`
Returns agent record.

### `GET /agents`
Requires L0. Returns all registered agents.

---

## E3 — Trust Scores

### `GET /trust/scores`
L0: returns all scores. L1/L2: returns only active segments (trust ≥ 0.3).

### `GET /trust/top?k=5`
Returns top-K segments by trust score.

### `POST /trust/update`
Requires L0. Hot-reload trust score without model restart.
```json
{ "segment_id": "seg-wikipedia-001", "trust_score": 0.97 }
```

### `POST /trust/reload`
Requires L0. Reloads trust_scores.json from disk.

---

## E4 — Manifest

### `GET /manifest/{session_id}`
Returns full JSONL manifest (all token records) for a session.

### `GET /manifest/{session_id}/summary`
```json
{
  "session_id": "uuid",
  "agent_id": "uuid",
  "total_tokens": 128,
  "license_purity": 0.94,
  "high_trust_ratio": 0.87,
  "dominant_sources": [
    { "segment_id": "seg-wiki-001", "source_name": "Wikipedia EN", "total_weight": 0.65, "trust_score": 0.95 }
  ],
  "started_at": "2026-...",
  "finalized_at": "2026-...",
  "manifest_hash": "sha256..."
}
```

### `GET /manifest`
Lists all session IDs.

---

## Pipeline — /generate

### `POST /generate`
Full E1+E2+E3+E4+E5 pipeline.

```json
// Request
{
  "prompt": "What is the capital of France?",
  "max_new_tokens": 256,
  "temperature": 0.7,
  "stream": false,
  "session_id": null
}

// Response
{
  "session_id": "uuid",
  "agent_level": "L1",
  "generated_text": "The capital of France is Paris.",
  "token_provenances": [
    {
      "token_id": 1234,
      "token_text": " The",
      "position": 0,
      "attribution": [
        { "segment_id": "seg-wiki-001", "source_name": "Wikipedia EN", "weight": 0.71, "license_class": "CC-BY-SA", "trust_score": 0.95 }
      ],
      "dominant_source": { ... },
      "average_trust": 0.92,
      "license_purity": 1.0
    }
  ],
  "trust_distribution": [...],
  "average_trust": 0.91,
  "summary": { ... }
}
```

**Streaming:** Set `"stream": true` → returns `application/x-ndjson` stream, one JSON line per token + final `{"__summary__": {...}}` line.

---

## Error Responses

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid level, malformed payload) |
| 403 | Insufficient agent level |
| 404 | Record/session not found |
| 503 | Model not loaded (`LOAD_MODEL=0`) |
