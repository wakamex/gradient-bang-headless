# AGENTS

Repo-specific guidance for headless client work:

1. Read [HEADLESS_RULES.md](./HEADLESS_RULES.md) before adding or automating gameplay features.
2. Prefer implementation paths in this order:
   - direct edge-function call
   - direct Pipecat session client message
   - browser automation
3. Treat browser automation as a last resort for local-only UI state, discovery, or debugging.
4. When tracing a feature, start from `upstream/` source code and map:
   - frontend handler
   - Pipecat message
   - server handler
   - `AsyncGameClient` method
   - Supabase edge-function path
