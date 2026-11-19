// Page logic: collect files, start the worker, show progress and the report. No file content leaves the tab.
const $ = (id) => document.getElementById(id);
const SUPPORTED = ["pdf", "docx", "odt", "txt"];
const extension = (name) => (name.match(/\.([^./]+)$/) || ["", ""])[1].toLowerCase();

let entries = []; // { path, file }: path is relative to what was picked or dropped, with "/" separators
let ignored = [];
let engineReady = false;
let running = false;
let result = null;
let runId = 0;

const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });

fetch("./manifest.json")
  .then((response) => response.json())
  .then((manifest) => {
    if (manifest.download_mb) $("load-size").textContent = `${Math.round(manifest.download_mb)} MB`;
  })
  .catch(() => {});

// Names as the command line gives them: paths relative to the chosen folder. When everything comes from one
// folder, that folder is the root; duplicates get a numbered suffix before their extension.
function documentNames() {
  const parts = entries.map((entry) => entry.path.split("/").filter(Boolean));
  const roots = new Set(parts.map((p) => (p.length > 1 ? p[0] : "")));
  const strip = roots.size === 1 && !roots.has("");
  const seen = new Map();
  return parts.map((p) => {
    let name = (strip ? p.slice(1) : p).join("/");
    const count = (seen.get(name) || 0) + 1;
    seen.set(name, count);
    if (count > 1) {
      const dot = name.lastIndexOf(".");
      name = `${name.slice(0, dot)} (${count})${name.slice(dot)}`;
    }
    return name;
  });
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function setStatus(text, isError = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", isError);
}

function refresh() {
  const names = documentNames();
  const list = $("files");
  list.replaceChildren(
    ...entries.map((entry, k) => {
      const item = document.createElement("li");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = names[k];
      const size = document.createElement("span");
      size.className = "size";
      size.textContent = formatSize(entry.file.size);
      item.append(name, size);
      return item;
    }),
  );
  $("file-panel").hidden = entries.length === 0 && ignored.length === 0;
  $("file-count").textContent = `${entries.length} document${entries.length === 1 ? "" : "s"}`;
  $("ignored").hidden = ignored.length === 0;
  $("ignored").textContent = ignored.length
    ? `Ignored ${ignored.length} file${ignored.length === 1 ? "" : "s"} in other formats: ${ignored.slice(0, 5).join(", ")}${ignored.length > 5 ? ", ..." : ""}`
    : "";
  $("run").disabled = running || entries.length < 2;
  if (!running) {
    setStatus(entries.length < 2 ? "Add at least two documents." : `Ready to compare ${entries.length} documents.`);
  }
}

function add(items) {
  for (const { path, file } of items) {
    const base = path.split("/").pop();
    if (base.startsWith(".")) continue; // hidden files, as the command line does
    if (SUPPORTED.includes(extension(base))) entries.push({ path, file });
    else ignored.push(base);
  }
  refresh();
}

const fromInput = (input) =>
  [...input.files].map((file) => ({ path: file.webkitRelativePath || file.name, file }));

$("pick-files").addEventListener("change", (event) => {
  add(fromInput(event.target));
  event.target.value = "";
});
$("pick-folder").addEventListener("change", (event) => {
  add(fromInput(event.target));
  event.target.value = "";
});
if (!("webkitdirectory" in document.createElement("input"))) $("folder-button").hidden = true;

$("clear").addEventListener("click", () => {
  entries = [];
  ignored = [];
  refresh();
});

// Drag and drop, including whole folders (read recursively through the entries API).
async function readEntry(entry) {
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
    return [{ path: entry.fullPath.replace(/^\//, ""), file }];
  }
  if (!entry.isDirectory) return [];
  const reader = entry.createReader();
  const children = [];
  for (;;) {
    const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
    if (!batch.length) break;
    children.push(...batch);
  }
  return (await Promise.all(children.map(readEntry))).flat();
}

const drop = $("drop");
["dragenter", "dragover"].forEach((type) =>
  drop.addEventListener(type, (event) => {
    event.preventDefault();
    drop.classList.add("over");
  }),
);
["dragleave", "drop"].forEach((type) => drop.addEventListener(type, () => drop.classList.remove("over")));
drop.addEventListener("drop", async (event) => {
  event.preventDefault();
  const items = [...(event.dataTransfer.items || [])];
  const fsEntries = items.map((item) => item.webkitGetAsEntry && item.webkitGetAsEntry()).filter(Boolean);
  if (fsEntries.length) add((await Promise.all(fsEntries.map(readEntry))).flat());
  else add([...event.dataTransfer.files].map((file) => ({ path: file.name, file })));
});
// A file dropped next to the zone would otherwise open in the tab and replace the page.
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());

function readOptions() {
  const blockSize = Number($("block-size").value);
  const thresholds = ["t-low", "t-medium", "t-high"].map((id) => Number($(id).value));
  if (!Number.isInteger(blockSize) || blockSize < 1) throw new Error("Minimum match length must be a whole number of at least 1.");
  const valid = thresholds.every((t, k) => $(["t-low", "t-medium", "t-high"][k]).value !== "" && t >= 0 && t <= 100);
  if (!valid || !(thresholds[0] < thresholds[1] && thresholds[1] < thresholds[2])) {
    throw new Error("Color thresholds must be increasing percentages between 0 and 100.");
  }
  return { blockSize, engine: $("engine").value, score: $("score").value, thresholds };
}

$("run").addEventListener("click", async () => {
  let options;
  try {
    options = readOptions();
  } catch (error) {
    $("step-options").closest("section").querySelector("details").open = true;
    setStatus(error.message, true);
    return;
  }
  running = true;
  runId += 1;
  $("run").disabled = true;
  $("progress").hidden = false;
  $("progress").removeAttribute("value");
  setStatus(engineReady ? "Reading files..." : "Waiting for the comparison program to finish loading...");
  const names = documentNames();
  const files = await Promise.all(
    entries.map(async (entry, k) => ({ name: names[k], buffer: await entry.file.arrayBuffer() })),
  );
  worker.postMessage({ id: runId, files, options }, files.map((file) => file.buffer));
});

const STAGES = { read: "Reading files", compare: "Comparing pairs" };

function finish() {
  running = false;
  $("progress").hidden = true;
  $("run").disabled = entries.length < 2;
}

function skippedText(skipped) {
  const why = { empty: "no text found (empty file or scanned PDF?)", unreadable: "could not be read" };
  return skipped.map((s) => `${s.name}: ${why[s.reason] || s.reason}${s.detail ? ` (${s.detail})` : ""}`).join("; ");
}

function showReport(message) {
  result = message;
  // In a srcdoc iframe, "#pair" links would resolve against this page's URL and navigate the frame away:
  // pin the base URL so in-report links stay in the report. Downloads keep the original HTML.
  const head = /<head[^>]*>/i;
  if (!head.test(message.html)) throw new Error("Unexpected report format (no <head>).");
  $("report").srcdoc = message.html.replace(head, (tag) => `${tag}<base href="about:srcdoc">`);
  $("results").hidden = false;
  $("skipped").hidden = message.skipped.length === 0;
  $("skipped").textContent = message.skipped.length ? `Skipped ${skippedText(message.skipped)}` : "";
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

worker.addEventListener("message", ({ data: message }) => {
  switch (message.type) {
    case "loading":
      $("engine-status").textContent = `${message.text}...`;
      break;
    case "ready":
      engineReady = true;
      $("engine-status").textContent = `Comparison program ready (copy-spotter ${message.version}).`;
      $("version").textContent = `Version ${message.version}.`;
      break;
    case "fatal":
      $("engine-status").textContent = `The comparison program could not load: ${message.text}. Reload the page to try again.`;
      $("engine-status").classList.add("warning");
      if (running) {
        finish();
        setStatus("Could not start the comparison.", true);
      }
      break;
    case "progress":
      if (message.id !== runId) break;
      $("progress").max = Math.max(message.total, 1);
      $("progress").value = message.done;
      setStatus(`${STAGES[message.stage] || message.stage}: ${message.done} of ${message.total}`);
      break;
    case "result":
      if (message.id !== runId) break;
      finish();
      if (message.error) {
        setStatus(message.error + (message.skipped.length ? ` Skipped ${skippedText(message.skipped)}` : ""), true);
        break;
      }
      try {
        showReport(message);
        setStatus(`Compared ${message.names.length} documents.`);
      } catch (error) {
        setStatus(error.message, true);
      }
      break;
    case "error":
      if (message.id !== runId) break;
      finish();
      setStatus(`Something went wrong: ${message.text}`, true);
      break;
  }
});

const DOWNLOADS = {
  html: ["copy-spotter-report.html", "text/html;charset=utf-8"],
  json: ["copy-spotter-results.json", "application/json;charset=utf-8"],
  csv: ["copy-spotter-results.csv", "text/csv;charset=utf-8"],
};

$("downloads").addEventListener("click", (event) => {
  const kind = event.target.closest("button")?.dataset.kind;
  if (!kind || !result) return;
  const [filename, type] = DOWNLOADS[kind];
  const url = URL.createObjectURL(new Blob([result[kind]], { type }));
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
});

refresh();
