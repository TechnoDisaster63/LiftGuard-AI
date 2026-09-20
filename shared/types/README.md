Types currently live directly in `frontend/lib/api.ts`, hand-mirrored against
`backend/app/schemas/*.py`, rather than duplicated here — with one frontend
consumer there's no generation step to justify yet. If a second consumer
(mobile app, admin CLI) shows up, that's the point to either move the
interfaces here or generate them from the FastAPI OpenAPI schema
(`/openapi.json`) instead of hand-mirroring.
