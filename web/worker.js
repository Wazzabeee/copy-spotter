// Runs Python off the main thread so the page stays responsive while files are compared.
// Every file this worker loads comes from the same site: the Pyodide runtime, its packages and the wheels are
// copied next to it by web/build.py, so nothing is fetched from another host and no file is sent anywhere.
import { loadPyodide } from "./pyodide/pyodide.mjs";

const here = (path) => new URL(path, import.meta.url).href;
const post = (message) => postMessage(message);

const ready = (async () => {
  const started = performance.now();
  post({ type: "loading", text: "Downloading Python" });
  const manifest = await (await fetch(here("./manifest.json"))).json();
  const pyodide = await loadPyodide({ indexURL: here("./pyodide/") });
  post({ type: "loading", text: "Installing copy-spotter" });
  // Load the Pyodide packages by name from the local lock, then the wheels without dependency resolution:
  // micropip never has to look anything up on PyPI.
  await pyodide.loadPackage(manifest.packages, { messageCallback: () => {} });
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(manifest.wheels.map((name) => here(`./wheels/${encodeURIComponent(name)}`)), { deps: false });
  const glue = await (await fetch(here("./copy_spotter_web.py"))).text();
  pyodide.FS.writeFile("/home/pyodide/copy_spotter_web.py", glue);
  pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  const web = pyodide.pyimport("copy_spotter_web");
  const version = pyodide.pyimport("copy_spotter").__version__;
  const limits = { ...web.LIMITS.toJs({ dict_converter: Object.fromEntries }), min_block_size: web.MIN_BLOCK_SIZE };
  post({ type: "ready", version, limits, seconds: (performance.now() - started) / 1000 });
  return { pyodide, web };
})();
ready.catch((error) => post({ type: "fatal", text: String(error && error.message ? error.message : error) }));

onmessage = async ({ data }) => {
  const { id, files, options } = data;
  let pyodide, web;
  try {
    ({ pyodide, web } = await ready);
  } catch (error) {
    post({ type: "error", id, text: "the comparison program could not load. Reload the page to try again." });
    return;
  }
  const progress = (stage, done, total) => post({ type: "progress", id, stage, done, total });
  const notice = (text) => post({ type: "notice", id, text });
  const pyFiles = pyodide.toPy(files.map((file) => [file.name, new Uint8Array(file.buffer)]), { depth: 2 });
  let result;
  try {
    result = web.analyze.callKwargs(pyFiles, {
      block_size: options.blockSize,
      engine: options.engine,
      score: options.score,
      thresholds: options.thresholds,
      progress,
      notice,
    });
    post({ type: "result", id, ...result.toJs({ dict_converter: Object.fromEntries }) });
  } catch (error) {
    post({ type: "error", id, text: String(error && error.message ? error.message : error) });
  } finally {
    pyFiles.destroy();
    if (result) result.destroy();
  }
};
