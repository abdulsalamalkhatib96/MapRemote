# Contributing

Keep changes focused on reliable URL remapping and safe system proxy lifecycle management. Discuss major changes before implementing them.

1. Fork and clone the repository if your use is authorized by the owner.
2. Create a feature branch.
3. Run `python3 -m unittest discover -s tests -v`.
4. With mitmdump installed, run `python3 smoke_test.py`.
5. For native changes, run `MAPREMOTE_BUILD_ONLY=1 bash Build.command` on macOS and verify the actual start/stop, permission prompts and restoration behavior manually.
6. Open a pull request describing changes, tests, and limitations.

Use fictional hosts and dummy data. Never commit local rules, captured traffic, secrets or CA keys. Preserve the small dependency footprint and document changes that affect privileges, certificates or network settings.
