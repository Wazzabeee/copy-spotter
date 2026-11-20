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
| `smoke.mjs` | Runs a built site in Node with Pyodide and prints the CSV export; CI diffs it with the CLI's. |

## Limits

A tab runs Python on one thread, and its memory is capped: a wasm32 heap cannot grow past 4 GB, and browsers often
stop well before. So the web app is stricter than the command line. The limits are in `copy_spotter_web.py`
(`MIN_BLOCK_SIZE`, `LIMITS`), and the page receives them from the worker:

| Limit | Value | Why |
| --- | --- | --- |
| Minimum match length | 4 words or more | Blocks of 2 or 3 words are mostly common phrases. With a block size of 2, 500 documents needed a 3.5 GB heap. |
| Warning | more than 200 documents or 400,000 words | Shows the expected time and memory, then compares anyway. |
| Refusal | more than 1000 documents or 2,000,000 words | Points to the command line. Too many documents are refused before any file is read. |

The estimate is fitted on Pyodide runs of generated English-like documents of 1000 to 3000 words, with a block size
of 4:

| Run | Compare time | Memory (wasm heap) |
| --- | --- | --- |
| 200 documents, 412k words | 5 s | 270 MB |
| 500 documents, 1M words | 48 s | 670 MB |
| 1000 documents, 2M words | 131 s | 1.2 GB |

The model is 30 MB plus 0.6 MB per 1000 words, and 0.3 s per 1000 pairs.

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

The `Web app` workflow (`.github/workflows/pages.yml`) builds and smoke tests the site on every pull request and
deploys it to GitHub Pages on every push to main.

To upgrade Pyodide, change `PYODIDE_VERSION` and the hashes in `PYODIDE_CORE` (the build prints a mismatch error
with the new value of each file).
