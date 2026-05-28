// ==UserScript==
// @name         POIDE — Leima deployment check
// @namespace    https://github.com/fxg55647/leima
// @version      1.0
// @description  Verifies Leima deployment integrity before each session
// @match        https://leima.io/*
// @match        https://leima.onrender.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// ==/UserScript==

const STATUS_URL = "https://fxg55647.github.io/leima/status.json";

function banner(color, message, detail) {
    document.getElementById("poide-banner")?.remove();
    const el = document.createElement("div");
    el.id = "poide-banner";
    el.style.cssText = [
        "all:initial",
        "display:flex",
        "position:fixed",
        "top:0","left:0","right:0",
        "z-index:2147483647",
        "min-height:40px",
        "background:" + color,
        "color:#fff",
        "padding:10px 16px",
        "font:bold 13px/1.4 system-ui,sans-serif",
        "justify-content:space-between",
        "align-items:center",
        "box-shadow:0 2px 8px rgba(0,0,0,.4)",
        "box-sizing:border-box",
    ].join(";");
    const text = document.createElement("span");
    text.style.cssText = "all:initial;color:#fff;font:bold 13px/1.4 system-ui,sans-serif;";
    text.textContent = message + (detail ? " — " + detail : "");
    const close = document.createElement("button");
    close.textContent = "×";
    close.style.cssText = "all:initial;color:#fff;font-size:20px;cursor:pointer;padding:0 4px;line-height:1;";
    close.onclick = () => el.remove();
    el.appendChild(text);
    el.appendChild(close);
    document.documentElement.appendChild(el);
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

function failReason(d) {
    if (d.deploying && !d.deploying_commit_ok) return "WARNING: commit being deployed does not match GitHub";
    if (d.deploying)            return "deploy in progress — wait before submitting documents";
    if (!d.deployment_ok)       return "deployed commit does not match GitHub";
    if (d.cron_fresh === false)  return "monitoring delayed — GitHub Actions backlog?";
    return "status unknown";
}

const ALERT_COOLDOWN_MS = 5 * 60 * 1000;

function alertIfDangerousDeploy(d) {
    if (!d.deploying || d.deploying_commit_ok !== false || !d.deploying_commit) return;
    const last = GM_getValue("last_deploy_alert", 0);
    if (Date.now() - last < ALERT_COOLDOWN_MS) return;
    GM_setValue("last_deploy_alert", Date.now());
    alert(
        "⚠ TREAD WARNING ⚠\n\n" +
        "A commit is being deployed that does NOT match the GitHub repository:\n" +
        (d.deploying_commit || "?").slice(0, 7) + " ≠ " + (d.expected_commit || "?").slice(0, 7) + "\n\n" +
        "Do not submit sensitive documents until this is resolved.\n" +
        "Check GitHub Actions and the Render dashboard."
    );
}

function historyLabel(h) {
    if (!h || h.scanned_deploys === 0) return null;
    if (h.last_mismatch_at) {
        const days = Math.floor((Date.now() - new Date(h.last_mismatch_at)) / 86400000);
        return { level: days < 7 ? "red" : "orange",
                 text: `mismatch in history ${days}d ago (${h.last_mismatch_commit})` };
    }
    if (h.clean_since) {
        const days = Math.floor((Date.now() - new Date(h.clean_since)) / 86400000);
        return { level: "green", text: `clean history for ${days}d` };
    }
    return null;
}

GM_xmlhttpRequest({
    method: "GET",
    url: STATUS_URL,
    onload(r) {
        let d;
        try { d = JSON.parse(r.responseText); }
        catch { banner("#e67e22", "TREAD ✗", "status.json is not valid JSON"); return; }

        const changed = checkMonitorFiles(d.monitor_files || {});
        const hist = historyLabel(d.history);

        alertIfDangerousDeploy(d);

        if (!d.ok) {
            banner("#c0392b", "TREAD ✗ — check GitHub Actions before use", failReason(d));
        } else if (d.deploying) {
            banner("#e67e22", "TREAD ⚠ — deploy detected", "code is changing — wait before submitting sensitive documents");
        } else if (changed) {
            banner("#e67e22", "TREAD ⚠ — monitor files changed since last session", changed.join(", "));
        } else if (hist && hist.level !== "green") {
            banner(hist.level === "red" ? "#c0392b" : "#e67e22",
                "TREAD ⚠ — " + hist.text, null);
        } else {
            const detail = hist ? hist.text : null;
            banner("#27ae60", "TREAD ✓ — code verified, deployment matches git", detail);
            setTimeout(() => document.getElementById("poide-banner")?.remove(), 5000);
        }
    },
    onerror() {
        banner("#e67e22", "TREAD ✗", "could not reach status.json");
    }
});
