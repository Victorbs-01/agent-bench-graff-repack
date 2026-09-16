# agent-bench-graff-repack

Deterministic repack of Graff v0.0.298 for JCODE-GRAFF-BENCH-003.

Contains:
- `graff` binary: byte-for-byte identical to official v0.0.298 release
- `graff-launcher.sh`: wrapper that writes router config and starts transport shim
- `opencode_shim.py`: transport shim (adds x-opencode-session header)
- `.graff/.config.router`: created at runtime by launcher (not in repo, no secrets)
