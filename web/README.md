# copy-spotter in the browser

A static page that runs copy-spotter with [Pyodide](https://pyodide.org) inside a Web Worker. Files are read with
the File API and compared in the tab; nothing is uploaded. The site is published at
https://wazzabeee.github.io/copy-spotter/.

| File | Role |
| --- | --- |
| `index.html`, `app.css`, `app.js` | The page: pick or drop files, options, progress, report iframe, downloads. |
| `worker.js` | Loads Pyodide, installs the wheels with micropip (no dependency resolution) and runs the comparison. |
| `copy_spotter_web.py` | Python glue over the public API, tested in CPython by `tests/test_web.py`. |
| `build.py` | Assembles the site into `web/_site`: Pyodide runtime and packages, project wheel, dependency wheels. |

Build and serve locally (needs network access the first time; downloads are cached in `web/.cache`):

```bash
uv run python web/build.py --serve
```

Then open http://localhost:8000. The dev server also serves `data/pdf/plagiarism` under `/_dev/samples/` for
testing; the built site does not contain it.

Everything the page loads is copied into the site, so it makes no request to another host:

- Pyodide is pinned in `build.py` (`PYODIDE_VERSION`), and its runtime files are checked against pinned sha256
  hashes. Its packages (cryptography, charset-normalizer, tqdm and their dependencies) are checked against the
  pinned `pyodide-lock.json`.
- pdfminer.six, odfpy and defusedxml are not in Pyodide: their versions and hashes come from `uv.lock`. odfpy only
  publishes an sdist, so the build makes a pure Python wheel from it, and .odt files work in the browser.

To upgrade Pyodide, change `PYODIDE_VERSION` and the hashes in `PYODIDE_CORE` (the build prints a mismatch error
with the new value of each file).
