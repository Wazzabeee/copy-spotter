// Smoke test of a built site in Node: load Pyodide, its packages and the wheels from the site as worker.js does,
// compare the documents of a directory with copy_spotter_web.analyze and print the CSV export on stdout.
// Usage: node web/smoke.mjs web/_site data/pdf/plagiarism > web.csv
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [site, samples] = process.argv.slice(2).map((arg) => path.resolve(arg));
const manifest = JSON.parse(fs.readFileSync(path.join(site, "manifest.json"), "utf8"));
const { loadPyodide } = await import(pathToFileURL(path.join(site, "pyodide", "pyodide.mjs")).href);
const pyodide = await loadPyodide({ indexURL: path.join(site, "pyodide") + path.sep });
await pyodide.loadPackage(manifest.packages, { messageCallback: () => {} });

pyodide.FS.mkdirTree("/wheels");
for (const name of manifest.wheels) {
  pyodide.FS.writeFile(`/wheels/${name}`, fs.readFileSync(path.join(site, "wheels", name)));
}
const micropip = pyodide.pyimport("micropip");
await micropip.install(manifest.wheels.map((name) => `emfs:/wheels/${name}`), { deps: false });
pyodide.FS.writeFile("/home/pyodide/copy_spotter_web.py", fs.readFileSync(path.join(site, "copy_spotter_web.py")));
pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");

const files = fs
  .readdirSync(samples)
  .filter((name) => !name.startsWith("."))
  .map((name) => [name, new Uint8Array(fs.readFileSync(path.join(samples, name)))]);
const result = pyodide.pyimport("copy_spotter_web").analyze(pyodide.toPy(files, { depth: 2 }));
const out = result.toJs({ dict_converter: Object.fromEntries });
if (out.error || out.skipped.length) {
  console.error("Smoke test failed:", out.error, JSON.stringify(out.skipped));
  process.exit(1);
}
console.error(`Compared ${out.names.length} documents with copy-spotter ${out.version} in Pyodide`);
process.stdout.write(out.csv);
process.exit(0);
