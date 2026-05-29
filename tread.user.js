// ==UserScript==
// @name         TREAD — Leima deployment check
// @namespace    https://github.com/fxg55647/leima
// @version      2.0
// @description  Shows a modal warning when Leima deployment integrity is compromised
// @match        https://leima.io/*
// @match        https://leima.onrender.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// ==/UserScript==

const STATUS_URL = "https://fxg55647.github.io/leima/status.json?_=" + Date.now();

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

function checkMonitorFiles(current) {
    const stored = GM_getValue("monitor_files", null);
    GM_setValue("monitor_files", JSON.stringify(current));
    if (!stored) return null;
    let prev;
    try { prev = JSON.parse(stored); } catch { return null; }
    const changed = Object.keys(current).filter(k => current[k] !== prev[k]);
    return changed.length > 0 ? changed : null;
}

const COOLDOWN_MS = 5 * 60 * 1000;

function isCooledDown(key) {
    const last = GM_getValue("cooldown_" + key, 0);
    if (Date.now() - last < COOLDOWN_MS) return false;
    GM_setValue("cooldown_" + key, Date.now());
    return true;
}

GM_xmlhttpRequest({
    method: "GET",
    url: STATUS_URL,
    onload(r) {
        let d;
        try { d = JSON.parse(r.responseText); } catch { return; }

        const changedFiles = checkMonitorFiles(d.monitor_files || {});

        if (changedFiles && isCooledDown("monitor_changed")) {
            modal("TREAD — Surveillance files modified", [
                "The following files have changed since the last check:",
                changedFiles.join(", "),
                "These files control how Leima is monitored and deployed.",
                "Do not submit sensitive documents until you have verified the changes on GitHub.",
            ]);
            return;
        }

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
    },
    onerror() { /* silent on network error */ }
});
