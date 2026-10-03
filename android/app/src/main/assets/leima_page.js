/*
 * Leima page script: the only JavaScript the app runs inside web pages (Research Appliance phase B).
 * Evaluated as `(<this file>)(command, args)` through WebView.evaluateJavascript; returns a JSON
 * string. No native bridge is exposed to the page (no addJavascriptInterface).
 *
 * The page can observe that this script ran (it runs in the page's own JavaScript world). Element
 * references live in a non-enumerable property named by a per-app-run random key.
 *
 * Also loaded by tests/browser/test_leima_page_js.py, which runs it in Chromium.
 */
(function (command, args) {
  "use strict";
  var MAX_ELEMENTS = 300;
  var MAX_TEXT = 50000;
  var MAX_NAME = 120;
  var MAX_VALUE = 200;
  var SENSITIVE_AUTOCOMPLETE = /\b(current-password|new-password|one-time-code|cc-number|cc-csc|cc-exp|cc-exp-month|cc-exp-year)\b/i;
  var TEXT_INPUT_TYPES = ["", "text", "search", "email", "url", "tel", "number"];
  var INTERACTIVE = [
    "a[href]", "button", "input:not([type=hidden])", "textarea", "select", "summary",
    "[role=button]", "[role=link]", "[role=checkbox]", "[role=radio]", "[role=tab]", "[role=menuitem]",
    "[role=option]", "[role=switch]", "[role=textbox]", "[role=combobox]", "[role=searchbox]",
    "[contenteditable=''],[contenteditable=true]", "[onclick]", "[tabindex]:not([tabindex='-1'])"
  ].join(",");

  var store = window[args.key];
  if (!store) {
    store = { observationId: null, elements: null };
    Object.defineProperty(window, args.key, { value: store, enumerable: false, configurable: false, writable: false });
  }

  function clip(text, max) {
    text = (text || "").replace(/\s+/g, " ").trim();
    return text.length > max ? text.slice(0, max) + "…" : text;
  }

  function isSensitive(el) {
    if (el.tagName === "INPUT" && (el.getAttribute("type") || "").toLowerCase() === "password") return true;
    if (el.tagName === "INPUT" && el.type === "password") return true;
    var ac = el.getAttribute && el.getAttribute("autocomplete");
    return !!(ac && SENSITIVE_AUTOCOMPLETE.test(ac));
  }

  function isVisible(el) {
    if (!el.isConnected || el.getClientRects().length === 0) return false;
    var style = window.getComputedStyle(el);
    return style.visibility !== "hidden" && style.display !== "none";
  }

  function inViewport(el) {
    var r = el.getBoundingClientRect();
    return r.bottom > 0 && r.right > 0 && r.top < window.innerHeight && r.left < window.innerWidth;
  }

  function roleOf(el) {
    var explicit = el.getAttribute("role");
    if (explicit) return explicit.split(/\s+/)[0];
    var tag = el.tagName.toLowerCase();
    if (tag === "a") return "link";
    if (tag === "button" || tag === "summary") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {
      var type = (el.type || "text").toLowerCase();
      if (type === "checkbox" || type === "radio") return type;
      if (type === "submit" || type === "button" || type === "reset" || type === "image") return "button";
      if (type === "search") return "searchbox";
      return "textbox";
    }
    if (el.isContentEditable) return "textbox";
    return "generic";
  }

  function nameOf(el) {
    var label = el.getAttribute("aria-label");
    if (label) return clip(label, MAX_NAME);
    var labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      var text = labelledBy.split(/\s+/).map(function (id) {
        var ref = document.getElementById(id);
        return ref ? ref.innerText || ref.textContent : "";
      }).join(" ");
      if (text.trim()) return clip(text, MAX_NAME);
    }
    if (el.labels && el.labels.length) {
      return clip(Array.prototype.map.call(el.labels, function (l) { return l.innerText || l.textContent; }).join(" "), MAX_NAME);
    }
    if (el.tagName === "INPUT" && /^(submit|button|reset)$/i.test(el.type) && el.value) return clip(el.value, MAX_NAME);
    var inner = el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" ? "" : (el.innerText || el.textContent);
    if (inner && inner.trim()) return clip(inner, MAX_NAME);
    return clip(el.getAttribute("placeholder") || el.getAttribute("title") || el.getAttribute("alt") ||
      (el.querySelector && el.querySelector("img[alt]") ? el.querySelector("img[alt]").getAttribute("alt") : ""), MAX_NAME);
  }

  function isEnabled(el) {
    return !el.disabled && el.getAttribute("aria-disabled") !== "true";
  }

  function describe(el, id) {
    var item = { element_id: id, role: roleOf(el), name: nameOf(el), enabled: isEnabled(el), in_viewport: inViewport(el) };
    var tag = el.tagName;
    if (tag === "A") item.href = el.href;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      if (tag === "INPUT") item.input_type = (el.type || "text").toLowerCase();
      if (isSensitive(el)) {
        item.sensitive = true;
        item.has_value = !!el.value;
      } else if (tag === "INPUT" && (el.type === "checkbox" || el.type === "radio")) {
        item.checked = el.checked;
      } else {
        item.value = clip(el.value, MAX_VALUE);
      }
    }
    return item;
  }

  function frameLimitations(limitations) {
    var crossOrigin = 0, sameOrigin = 0;
    Array.prototype.forEach.call(document.querySelectorAll("iframe,frame"), function (f) {
      var doc = null;
      try { doc = f.contentDocument; } catch (e) { doc = null; }
      if (doc) sameOrigin++; else crossOrigin++;
    });
    if (crossOrigin) limitations.push({ code: "CROSS_ORIGIN_IFRAMES", count: crossOrigin, detail: "Content of cross-origin iframes was not read" });
    if (sameOrigin) limitations.push({ code: "IFRAMES_NOT_TRAVERSED", count: sameOrigin, detail: "Same-origin iframe content is not included" });
    var canvases = document.querySelectorAll("canvas").length;
    if (canvases) limitations.push({ code: "CANVAS", count: canvases, detail: "Canvas content is only visible in a screenshot" });
    var shadowHosts = 0, walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_ELEMENT), n = 0;
    while (walker.nextNode() && n++ < 20000) if (walker.currentNode.shadowRoot) shadowHosts++;
    if (shadowHosts) limitations.push({ code: "SHADOW_DOM", count: shadowHosts, detail: "Shadow DOM content was not traversed" });
  }

  function observe() {
    var limitations = [];
    var elements = [], refs = new Map();
    var nodes = document.querySelectorAll(INTERACTIVE);
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!isVisible(el)) continue;
      if (elements.length >= MAX_ELEMENTS) {
        limitations.push({ code: "ELEMENT_LIMIT", count: MAX_ELEMENTS, detail: "Only the first interactive elements were listed" });
        break;
      }
      var id = "el_" + (elements.length + 1);
      refs.set(id, el);
      elements.push(describe(el, id));
    }
    // Only the newest observation's references are kept: every older observation is stale.
    store.observationId = args.observation_id;
    store.elements = refs;
    var text = document.body ? document.body.innerText || "" : "";
    var truncated = text.length > MAX_TEXT;
    if (truncated) limitations.push({ code: "TEXT_TRUNCATED", count: MAX_TEXT, detail: "visible_text was cut" });
    frameLimitations(limitations);
    return {
      url: location.href,
      title: document.title,
      ready_state: document.readyState,
      visible_text: truncated ? text.slice(0, MAX_TEXT) : text,
      elements: elements,
      limitations: limitations
    };
  }

  function lookup() {
    if (store.observationId !== args.observation_id || !store.elements) return { error: "STALE_OBSERVATION" };
    var el = store.elements.get(args.element_id);
    if (!el) return { error: "UNKNOWN_ELEMENT" };
    if (!isVisible(el)) return { error: "STALE_OBSERVATION", detail: "Element is no longer in the page or visible" };
    return { el: el };
  }

  function click() {
    var found = lookup();
    if (found.error) return found;
    var el = found.el;
    if (!isEnabled(el)) return { error: "ELEMENT_DISABLED" };
    el.scrollIntoView({ block: "center", inline: "center" });
    if (el.focus) el.focus({ preventScroll: true });
    el.click();
    return { ok: true, method: "dom_click" };
  }

  function typeText() {
    var found = lookup();
    if (found.error) return found;
    var el = found.el;
    if (isSensitive(el)) return { error: "SENSITIVE_FIELD" };
    if (!isEnabled(el) || el.readOnly) return { error: "ELEMENT_DISABLED" };
    var isText = (el.tagName === "INPUT" && TEXT_INPUT_TYPES.indexOf((el.getAttribute("type") || "").toLowerCase()) >= 0) || el.tagName === "TEXTAREA";
    if (!isText && !el.isContentEditable) return { error: "NOT_TEXT_INPUT" };
    el.scrollIntoView({ block: "center", inline: "center" });
    el.focus({ preventScroll: true });
    if (el.isContentEditable && !isText) {
      el.textContent = args.replace ? args.text : el.textContent + args.text;
    } else {
      // The prototype's setter keeps framework-managed inputs (React etc.) in sync.
      var proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, args.replace ? args.text : el.value + args.text);
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return { ok: true, method: "dom_value_setter" };
  }

  function masks() {
    var vv = window.visualViewport || { width: window.innerWidth, height: window.innerHeight, offsetLeft: 0, offsetTop: 0 };
    var rects = [];
    Array.prototype.forEach.call(document.querySelectorAll("input,textarea,[autocomplete]"), function (el) {
      if (!isSensitive(el) || !isVisible(el)) return;
      var r = el.getBoundingClientRect();
      rects.push({ x: r.left - vv.offsetLeft, y: r.top - vv.offsetTop, width: r.width, height: r.height });
    });
    var visibleCrossOrigin = 0;
    Array.prototype.forEach.call(document.querySelectorAll("iframe,frame"), function (f) {
      var doc = null;
      try { doc = f.contentDocument; } catch (e) { doc = null; }
      if (!doc && isVisible(f) && inViewport(f)) visibleCrossOrigin++;
    });
    return { rects: rects, viewport: { width: vv.width, height: vv.height }, visible_cross_origin_iframes: visibleCrossOrigin };
  }

  function dom() {
    var clone = document.documentElement.cloneNode(true);
    var redactions = { sensitive_inputs: 0, hidden_inputs: 0, csrf_meta: 0 };
    Array.prototype.forEach.call(clone.querySelectorAll("input,textarea"), function (el) {
      if (isSensitive(el)) {
        if (el.hasAttribute("value")) redactions.sensitive_inputs++;
        el.removeAttribute("value");
        if (el.tagName === "TEXTAREA") el.textContent = "";
      } else if ((el.getAttribute("type") || "").toLowerCase() === "hidden" && el.hasAttribute("value")) {
        el.setAttribute("value", "");
        redactions.hidden_inputs++;
      }
    });
    Array.prototype.forEach.call(clone.querySelectorAll("meta[name]"), function (m) {
      if (/csrf|xsrf/i.test(m.getAttribute("name")) && m.hasAttribute("content")) {
        m.setAttribute("content", "");
        redactions.csrf_meta++;
      }
    });
    var doctype = document.doctype ? "<!DOCTYPE " + document.doctype.name + ">\n" : "";
    return { html: doctype + clone.outerHTML, redactions: redactions };
  }

  var commands = { observe: observe, click: click, type: typeText, masks: masks, dom: dom };
  var result;
  try {
    result = commands[command] ? commands[command]() : { error: "UNKNOWN_COMMAND" };
  } catch (e) {
    result = { error: "SCRIPT_ERROR", detail: String(e && e.message || e) };
  }
  return JSON.stringify(result);
})
