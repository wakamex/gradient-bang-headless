# Gradient Bang Headless

This repo is the home for a headless client and automation tooling for Gradient Bang.

## Layout

- `upstream/`: game core submodule, pinned to `git@github.com:wakamex/gradient-bang.git`
- future headless client code: parent repo root

## Notes

- The live game client uses `https://api.gradient-bang.com/functions/v1/start`.
- Most gameplay edge functions are still protected by `X-API-Token`, so a public headless client will need a scoped gameplay-session/token flow before it can call gameplay endpoints directly.
