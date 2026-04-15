# AGENTS

Repo-specific guidance for headless client work:

1. Read [HEADLESS_RULES.md](./HEADLESS_RULES.md) before adding or automating gameplay features.
2. Prefer implementation paths in this order:
   - direct edge-function call
   - direct Pipecat session client message
   - temporary off-path diagnostics only
3. Do not ship browser automation as a supported gameplay path in this repo.
4. When tracing a feature, start from `upstream/` source code and map:
   - frontend handler
   - Pipecat message
   - server handler
   - `AsyncGameClient` method
   - Supabase edge-function path
