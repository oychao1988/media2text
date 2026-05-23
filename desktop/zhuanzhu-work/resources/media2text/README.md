# media2text sidecar bundle (P7)

Built by `npm run prepare-bundle` from repo root:

```
resources/media2text/
  bin/media2text          # wrapper → system python3 + site-packages
  site-packages/          # pip install --target (media2text + deps)
```

**Note:** The wrapper uses **system Python 3.12+** (`python3` on PATH). A fully embedded Python runtime / PyInstaller onefile is deferred (see P7 PR).

Development without bundle: `<repo>/.venv/bin/media2text`.
