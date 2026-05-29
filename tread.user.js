// ==UserScript==
// @name         TREAD — Leima deployment check
// @namespace    https://github.com/fxg55647/leima
// @version      3.0
// @description  Shows a modal warning when Leima deployment integrity is compromised
// @match        https://leima.io/*
// @match        https://leima.onrender.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// ==/UserScript==

const REPO   = "fxg55647/leima";
const BRANCH = "main";

const MONITOR_PATHS = [
    ".github/workflows/tread-a.yml",
    ".github/workflows/tread-b.yml",
    ".github/workflows/tread-c.yml",
    ".github/workflows/tread-d.yml",
    ".github/workflows/tread-e.yml",
    ".github/workflows/tread-run.yml",
    ".github/workflows/monthly-audit.yml",
    ".github/workflows/code_review.yml",
    "tread_check.py",
    "tread_arweave.py",
    "monthly_audit.py",
    "code_review.py",
    "POLICY.example.md",
];

const TS          = Date.now();
const TREE_URL    = `https://api.github.com/repos/${REPO}/git/trees/${BRANCH}?recursive=1&_=${TS}`;
const STATUS_URL  = `https://api.github.com/repos/${REPO}/contents/status.json?ref=gh-pages&_=${TS}`;
const COOLDOWN_MS = 5 * 60 * 1000;


function modal(title, lines) {
    document.getElementById("tread-modal")?.remove();

    const overlay = document.createElement("div");
    overlay.id = "tread-modal";
    overlay.style.cssText = [
        "all:initial", "display:flex", "position:fixed", "inset:0",
        "z-index:2147483647", "background:rgba(0,0,0,0.75)",
        "align-items:center", "justify-content:center",
        "font-family:system-ui,sans-serif",
    ].join(";");

    const box = document.createElement("div");
    box.style.cssText = [
        "all:initial", "display:block",
        "background:#1a1a1a", "color:#fff",
        "border:2px solid #c0392b", "border-radius:10px",
        "padding:2rem 2rem 1.5rem", "max-width:420px", "width:90%",
        "box-shadow:0 8px 40px rgba(0,0,0,0.7)",
        "font-family:system-ui,sans-serif",
    ].join(";");

    const h = document.createElement("div");
    h.style.cssText = "all:initial;display:block;font:bold 16px system-ui;color:#e74c3c;margin-bottom:1rem;letter-spacing:0.03em;";
    h.textContent = "⚠ " + title;

    const body = document.createElement("div");
    body.style.cssText = "all:initial;display:block;font:14px/1.6 system-ui;color:#ddd;margin-bottom:1.5rem;";
    lines.forEach(line => {
        const p = document.createElement("p");
        p.style.cssText = "all:initial;display:block;font:14px/1.6 system-ui;color:#ddd;margin:0 0 0.4rem;";
        p.textContent = line;
        body.appendChild(p);
    });

    const btn = document.createElement("button");
    btn.textContent = "Dismiss";
    btn.style.cssText = [
        "all:initial", "display:inline-block", "cursor:pointer",
        "background:#c0392b", "color:#fff",
        "border:none", "border-radius:5px",
        "padding:0.5rem 1.25rem",
        "font:bold 13px system-ui",
    ].join(";");
    btn.onclick = () => overlay.remove();
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

    box.appendChild(h);
    box.appendChild(body);
    box.appendChild(btn);
    overlay.appendChild(box);
    document.documentElement.appendChild(overlay);
}


function isCooledDown(key) {
    const last = GM_getValue("cooldown_" + key, 0);
    if (Date.now() - last < COOLDOWN_MS) return false;
    GM_setValue("cooldown_" + key, Date.now());
    return true;
}


function checkFileHashes(current) {
    const stored = GM_getValue("tread_file_hashes_v3", null);
    GM_setValue("tread_file_hashes_v3", JSON.stringify(current));
    if (!stored) return null;
    let prev;
    try { prev = JSON.parse(stored); } catch { return null; }
    const changed = Object.keys(current).filter(k => current[k] !== prev[k]);
    return changed.length ? changed : null;
}


function gmFetch(url, headers) {
    return new Promise((resolve, reject) => {
        GM_xmlhttpRequest({
            method: "GET",
            url,
            headers: headers || {},
            onload: r => resolve(r),
            onerror: reject,
        });
    });
}


async function main() {
    // 1. Hae git tree ja laske hashit itse — ei luoteta status.json:iin
    try {
        const r = await gmFetch(TREE_URL, {"Accept": "application/vnd.github+json"});
        const tree = JSON.parse(r.responseText).tree || [];
        const hashes = {};
        for (const item of tree) {
            if (MONITOR_PATHS.includes(item.path)) hashes[item.path] = item.sha;
        }
        const changed = checkFileHashes(hashes);
        if (changed && isCooledDown("files_changed")) {
            modal("TREAD — Surveillance files modified", [
                "The following files have changed:",
                changed.join(", "),
                "These files control how Leima is monitored and deployed.",
                "Do not submit sensitive documents until you have verified the changes on GitHub.",
            ]);
            return;
        }
    } catch { /* silent on network error */ }

    // 2. Hae status.json GitHub API:lla (1 min cache) — tarkista deploy-status
    try {
        const r = await gmFetch(STATUS_URL, {"Accept": "application/vnd.github.raw"});
        const d = JSON.parse(r.responseText);

        const dangerousDeploy = d.deploying && d.deploying_commit_ok === false && d.deploying_commit;
        if (dangerousDeploy && isCooledDown("danger_" + (d.deploying_commit || "").slice(0, 7))) {
            modal("TREAD — Unauthorized deploy detected", [
                "A commit is being deployed that does NOT match the GitHub repository.",
                (d.deploying_commit || "?").slice(0, 7) + " ≠ " + (d.expected_commit || "?").slice(0, 7),
                "Do not submit sensitive documents until this is resolved.",
                "Check GitHub Actions and the Render dashboard.",
            ]);
        } else if (!d.ok && !d.deploying && isCooledDown("mismatch")) {
            modal("TREAD — Deployment mismatch", [
                "The running code does not match the verified GitHub commit.",
                "This may indicate a deployment issue or unauthorized change.",
                "Do not submit sensitive documents until this is resolved.",
            ]);
        }
    } catch { /* silent on network error */ }

    // 3. Tarkista security_model — hälytä jos muuttunut
    try {
        const r = await gmFetch("https://leima.io/version");
        const d = JSON.parse(r.responseText);
        const current = d.security_model;
        if (current) {
            const stored = GM_getValue("security_model", null);
            if (stored === null) {
                GM_setValue("security_model", current);
            } else if (stored !== current && isCooledDown("security_model_" + current)) {
                GM_setValue("security_model", current);
                modal("TREAD — Security model updated", [
                    "Leima's security model has changed: " + stored + " → " + current,
                    "Review what changed before submitting sensitive documents.",
                    "Check the release notes on GitHub.",
                ]);
            }
        }
    } catch { /* silent on network error */ }
}

main();
setInterval(main, 60 * 1000);
