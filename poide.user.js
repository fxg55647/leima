// ==UserScript==
// @name         POIDE — Leima deployment check
// @namespace    https://github.com/fxg55647/leima
// @version      1.0
// @description  Verifies Leima deployment integrity before each session
// @match        https://leima.onrender.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// ==/UserScript==

const STATUS_URL = "https://fxg55647.github.io/leima/status.json";

function banner(color, message, detail) {
    const el = document.createElement("div");
    el.id = "poide-banner";
    el.style.cssText = `
        position:fixed; top:0; left:0; right:0; z-index:999999;
        background:${color}; color:#fff; padding:10px 16px;
        font:14px/1.4 system-ui,sans-serif; display:flex;
        justify-content:space-between; align-items:center;
        box-shadow:0 2px 6px rgba(0,0,0,.3);
    `;
    const text = document.createElement("span");
    text.textContent = message + (detail ? " — " + detail : "");
    const close = document.createElement("button");
    close.textContent = "×";
    close.style.cssText = "background:none;border:none;color:#fff;font-size:18px;cursor:pointer;padding:0 4px;";
    close.onclick = () => el.remove();
    el.appendChild(text);
    el.appendChild(close);
    document.body.prepend(el);
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
    if (d.deploying && !d.deploying_commit_ok) return "VAROITUS: tuotantoon ajetaan commit joka ei täsmää GitHubiin";
    if (d.deploying)            return "deploy käynnissä — odota hetki";
    if (!d.deployment_ok)       return "deployed commit ei täsmää GitHubiin";
    if (d.cron_fresh === false)  return "monitorointi myöhässä — GitHub Actions ruuhka?";
    return "tila tuntematon";
}

const ALERT_COOLDOWN_MS = 5 * 60 * 1000;

function alertIfDangerousDeploy(d) {
    if (!d.deploying || d.deploying_commit_ok !== false || !d.deploying_commit) return;
    const last = GM_getValue("last_deploy_alert", 0);
    if (Date.now() - last < ALERT_COOLDOWN_MS) return;
    GM_setValue("last_deploy_alert", Date.now());
    alert(
        "⚠ POIDE VAROITUS ⚠\n\n" +
        "Renderiin ajetaan commit joka EI täsmää GitHub-repoon:\n" +
        (d.deploying_commit || "?").slice(0, 7) + " ≠ " + (d.expected_commit || "?").slice(0, 7) + "\n\n" +
        "Älä lähetä arkaluonteisia dokumentteja ennen kuin tilanne selviää.\n" +
        "Tarkista GitHub Actions ja Render dashboard."
    );
}

function historyLabel(h) {
    if (!h || h.scanned_deploys === 0) return null;
    if (h.last_mismatch_at) {
        const days = Math.floor((Date.now() - new Date(h.last_mismatch_at)) / 86400000);
        return { level: days < 7 ? "red" : "orange",
                 text: `mismatch historiassa ${days} pv sitten (${h.last_mismatch_commit})` };
    }
    if (h.clean_since) {
        const days = Math.floor((Date.now() - new Date(h.clean_since)) / 86400000);
        return { level: "green", text: `puhdas historia ${days} pv` };
    }
    return null;
}

GM_xmlhttpRequest({
    method: "GET",
    url: STATUS_URL,
    onload(r) {
        let d;
        try { d = JSON.parse(r.responseText); }
        catch { banner("#e67e22", "POIDE ✗", "status.json ei ole kelvollinen JSON"); return; }

        const changed = checkMonitorFiles(d.monitor_files || {});
        const hist = historyLabel(d.history);

        alertIfDangerousDeploy(d);

        if (!d.ok) {
            banner("#c0392b", "POIDE ✗ — tarkista GitHub Actions ennen käyttöä", failReason(d));
        } else if (changed) {
            banner("#e67e22", "POIDE ⚠ — valvontatiedostot muuttuneet edellisestä sessiosta",
                changed.join(", "));
        } else if (hist && hist.level !== "green") {
            banner(hist.level === "red" ? "#c0392b" : "#e67e22",
                "POIDE ⚠ — " + hist.text, null);
        } else {
            const detail = hist ? hist.text : null;
            banner("#27ae60", "POIDE ✓ — koodi tarkistettu, deployment kunnossa", detail);
            setTimeout(() => document.getElementById("poide-banner")?.remove(), 5000);
        }
    },
    onerror() {
        banner("#e67e22", "POIDE ✗", "ei yhteyttä status.json:iin");
    }
});
