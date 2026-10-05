# Refactoring paid acquisition dashboard

Client-facing reporting page for Refactoring, built by Growletter.

- `build/build.py` rebuilds the page from `build/raw/` (Windsor Meta pulls, creative images, logo).
  Run `python3 build/build.py --end YYYY-MM-DD`, then copy `build/out/index.html` to `site/index.html`.
- `site/` is the Netlify publish directory (no build command).
- Signups: ad sets with "| Reg" in the name count Complete Registration; all others count Lead.
