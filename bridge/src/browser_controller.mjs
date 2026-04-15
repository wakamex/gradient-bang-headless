#!/usr/bin/env node

import { createRequire } from "node:module";
import process from "node:process";
import readline from "node:readline";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const HELP_TEXT = `Usage: node src/browser_controller.mjs

Reads newline-delimited JSON commands from stdin and writes newline-delimited
JSON responses/events to stdout.

Supported commands:
  {"id":"1","op":"connect","email":"you@example.com","password":"...","characterName":"Pilot"}
  {"id":"2","op":"status"}
  {"id":"3","op":"sendCommand","text":"skip tutorial"}
  {"id":"4","op":"clickButton","label":"Skip Tutorial"}
  {"id":"5","op":"screenshot","path":"/tmp/gradient.png"}
  {"id":"6","op":"close"}`;

const DEFAULT_SITE_URL = "https://game.gradient-bang.com/";
const DEFAULT_VIEWPORT = { width: 1440, height: 1200 };
const DEFAULT_TRAFFIC_LIMIT = 200;
const DEFAULT_TRAFFIC_BODY_LIMIT = 2000;
const DEFAULT_NETWORK_FILTERS = [
  "api.gradient-bang.com",
  "/functions/v1/",
  "/start/",
  "/auth/v1/",
];

function requireString(value, name) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${name} is required`);
  }
  return value;
}

function numberOr(value, fallback) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function booleanOr(value, fallback) {
  return typeof value === "boolean" ? value : fallback;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeText(value) {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function serialize(value) {
  if (value === undefined) {
    return null;
  }
  return JSON.parse(
    JSON.stringify(value, (_key, current) => {
      if (current instanceof Error) {
        return {
          name: current.name,
          message: current.message,
          stack: current.stack,
        };
      }
      return current;
    }),
  );
}

function truncateText(value, limit) {
  if (typeof value !== "string") {
    return null;
  }
  if (value.length <= limit) {
    return value;
  }
  return `${value.slice(0, limit)}...`;
}

function stringArrayOr(value, fallback) {
  if (!Array.isArray(value)) {
    return fallback;
  }
  const items = value
    .filter((item) => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length > 0 ? items : fallback;
}

function serializeError(error) {
  if (error instanceof Error) {
    return serialize({
      name: error.name,
      message: error.message,
      stack: error.stack,
    });
  }
  return { message: String(error) };
}

function writeMessage(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function emitEvent(event, payload = {}) {
  writeMessage({
    type: "event",
    event,
    ...serialize(payload),
  });
}

class HostedGameBrowser {
  constructor() {
    this.browser = null;
    this.context = null;
    this.page = null;
    this.logConsole = false;
    this.logNetwork = false;
    this.logTransport = false;
    this.recentLogs = [];
    this.recentTraffic = [];
    this.trafficLimit = DEFAULT_TRAFFIC_LIMIT;
    this.trafficBodyLimit = DEFAULT_TRAFFIC_BODY_LIMIT;
    this.networkFilters = DEFAULT_NETWORK_FILTERS;
  }

  async close() {
    try {
      if (this.page) {
        await this.page.close({ runBeforeUnload: false });
      }
    } catch {}
    try {
      if (this.context) {
        await this.context.close();
      }
    } catch {}
    try {
      if (this.browser) {
        await this.browser.close();
      }
    } catch {}

    this.page = null;
    this.context = null;
    this.browser = null;
    this.recentLogs = [];
    this.recentTraffic = [];
  }

  async connect(command) {
    await this.close();

    const siteUrl = typeof command.siteUrl === "string" && command.siteUrl.trim()
      ? command.siteUrl.trim()
      : DEFAULT_SITE_URL;
    const connectTimeoutMs = numberOr(command.connectTimeoutMs, 120000);
    const postConnectWaitMs = numberOr(command.postConnectWaitMs, 0);

    this.logConsole = booleanOr(command.logConsole, false);
    this.logNetwork = booleanOr(command.logNetwork, false);
    this.logTransport = booleanOr(command.logTransport, false);
    this.trafficLimit = numberOr(command.trafficLimit, DEFAULT_TRAFFIC_LIMIT);
    this.trafficBodyLimit = numberOr(command.trafficBodyLimit, DEFAULT_TRAFFIC_BODY_LIMIT);
    this.networkFilters = stringArrayOr(command.networkFilters, DEFAULT_NETWORK_FILTERS);
    this.browser = await chromium.launch({
      headless: booleanOr(command.headless, true),
      args: ["--use-gl=swiftshader"],
    });
    this.context = await this.browser.newContext({
      viewport: {
        width: numberOr(command.viewportWidth, DEFAULT_VIEWPORT.width),
        height: numberOr(command.viewportHeight, DEFAULT_VIEWPORT.height),
      },
      permissions: ["camera", "microphone"],
    });
    if (this.logTransport) {
      await this.context.exposeBinding("__gbHeadlessEmitTraffic", async (_source, payload) => {
        this._recordTraffic(payload);
      });
      await this.context.addInitScript(
        ({ trafficBodyLimit }) => {
          const MARK = "__gbHeadlessWrapped";
          const preview = (value) => {
            if (typeof value === "string") {
              return value.length <= trafficBodyLimit ?
                  value
                : `${value.slice(0, trafficBodyLimit)}...`;
            }
            if (value instanceof ArrayBuffer) {
              return `[ArrayBuffer ${value.byteLength}]`;
            }
            if (ArrayBuffer.isView(value)) {
              return `[${value.constructor.name} ${value.byteLength}]`;
            }
            try {
              const rendered = String(value);
              return rendered.length <= trafficBodyLimit ?
                  rendered
                : `${rendered.slice(0, trafficBodyLimit)}...`;
            } catch {
              return "[unserializable]";
            }
          };
          const emit = (event) => {
            try {
              window.__gbHeadlessEmitTraffic(event);
            } catch {}
          };
          if (
            typeof window.RTCDataChannel === "function" &&
            !window.RTCDataChannel.prototype.send?.[MARK]
          ) {
            const originalSend = window.RTCDataChannel.prototype.send;
            const wrappedSend = function wrappedSend(data) {
              emit({
                kind: "rtc_datachannel_send",
                label: this.label || null,
                readyState: this.readyState || null,
                dataPreview: preview(data),
              });
              return originalSend.apply(this, arguments);
            };
            wrappedSend[MARK] = true;
            window.RTCDataChannel.prototype.send = wrappedSend;
          }
          if (typeof window.WebSocket === "function" && !window.WebSocket.prototype.send?.[MARK]) {
            const originalSend = window.WebSocket.prototype.send;
            const wrappedSend = function wrappedSend(data) {
              emit({
                kind: "websocket_send",
                url: this.url || null,
                dataPreview: preview(data),
              });
              return originalSend.apply(this, arguments);
            };
            wrappedSend[MARK] = true;
            window.WebSocket.prototype.send = wrappedSend;
          }
        },
        { trafficBodyLimit: this.trafficBodyLimit },
      );
    }
    this.page = await this.context.newPage();
    this._installPageListeners(this.page);

    await this.page.goto(siteUrl, {
      waitUntil: "networkidle",
      timeout: connectTimeoutMs,
    });
    await this._signIn(command, connectTimeoutMs);
    await this._selectCharacter(command, connectTimeoutMs);
    await this._waitForGameShell(connectTimeoutMs);

    if (postConnectWaitMs > 0) {
      await this.page.waitForTimeout(postConnectWaitMs);
    }

    emitEvent("connected", { siteUrl });
    return await this.status({ bodyTextLimit: command.bodyTextLimit });
  }

  async status(command = {}) {
    this._ensurePage();
    const bodyTextLimit = numberOr(command.bodyTextLimit, 4000);
    const snapshot = await this.page.evaluate(
      ({ bodyTextLimit, logs, traffic }) => {
        const input = Array.from(document.querySelectorAll("input,textarea")).find((field) => {
          const placeholder = (field.placeholder || "").toLowerCase();
          return placeholder.includes("enter command");
        });
        return {
          url: window.location.href,
          title: document.title,
          headings: Array.from(document.querySelectorAll("h1,h2,h3"))
            .map((node) => (node.innerText || node.textContent || "").trim())
            .filter(Boolean),
          buttons: Array.from(document.querySelectorAll("button"))
            .map((node) => (node.innerText || node.textContent || "").trim())
            .filter(Boolean),
          clickTargets: Array.from(document.querySelectorAll("button, [role], [tabindex]"))
            .filter((node) => {
              const role = node.getAttribute("role");
              return (
                node.tagName === "BUTTON" ||
                ["button", "link", "menuitem", "option", "tab"].includes(
                  (role || "").toLowerCase(),
                ) ||
                (node.hasAttribute("tabindex") && typeof node.onclick === "function")
              );
            })
            .map((node) => ({
              tag: node.tagName,
              role: node.getAttribute("role"),
              text: (node.innerText || node.textContent || "").trim().replace(/\s+/g, " "),
              ariaLabel: node.getAttribute("aria-label") || "",
              title: node.getAttribute("title") || "",
            }))
            .filter((node) => node.text || node.ariaLabel || node.title),
          inputs: Array.from(document.querySelectorAll("input,textarea")).map((node) => ({
            tag: node.tagName,
            type: "type" in node ? node.type : null,
            placeholder: node.placeholder || "",
            value: node.value || "",
            disabled: Boolean(node.disabled),
          })),
          commandInput:
            input ?
              {
                placeholder: input.placeholder,
                value: input.value,
                disabled: input.disabled,
              }
            : null,
          bodyText: document.body.innerText.slice(0, bodyTextLimit),
          recentLogs: logs,
          recentTraffic: traffic,
        };
      },
      {
        bodyTextLimit,
        logs: this.recentLogs.slice(-20),
        traffic: this.recentTraffic.slice(-50),
      },
    );
    return snapshot;
  }

  async sendCommand(command) {
    this._ensurePage();
    const text = requireString(command.text, "text");
    const inputTimeoutMs = numberOr(command.inputTimeoutMs, 180000);
    const waitAfterMs = numberOr(command.waitAfterMs, 15000);
    const waitForEnabled = booleanOr(command.waitForInputEnabled, true);

    if (waitForEnabled) {
      await this._waitForEnabledCommandInput(inputTimeoutMs);
    }

    const input = this.page
      .locator(
        'input[placeholder*="enter command" i]:not([disabled]), textarea[placeholder*="enter command" i]:not([disabled])',
      )
      .first();
    await input.fill(text);
    await input.press("Enter");

    if (waitAfterMs > 0) {
      await this.page.waitForTimeout(waitAfterMs);
    }

    emitEvent("command_sent", { text });
    return await this.status({ bodyTextLimit: command.bodyTextLimit });
  }

  async clickButton(command) {
    this._ensurePage();
    const label = requireString(command.label, "label");
    const waitAfterMs = numberOr(command.waitAfterMs, 5000);
    const matcher = new RegExp(`^${escapeRegExp(label)}$`, "i");
    const locator = this.page.getByRole("button", { name: matcher }).first();
    const normalizedLabel = normalizeText(label);

    try {
      await locator.waitFor({
        state: "visible",
        timeout: numberOr(command.timeoutMs, 120000),
      });
      await locator.click({ force: booleanOr(command.force, false) });
    } catch {
      await this.page.waitForFunction(
        (expected) =>
          Array.from(document.querySelectorAll("button, [role], [tabindex]"))
            .filter((node) => {
              const role = node.getAttribute("role");
              return (
                node.tagName === "BUTTON" ||
                ["button", "link", "menuitem", "option", "tab"].includes(
                  (role || "").toLowerCase(),
                ) ||
                (node.hasAttribute("tabindex") && typeof node.onclick === "function")
              );
            })
            .some((node) => {
              const text =
                (node.innerText || node.textContent || "").trim().replace(/\s+/g, " ").toLowerCase();
              const aria = node.getAttribute("aria-label")?.trim().replace(/\s+/g, " ").toLowerCase() || "";
              const title = node.getAttribute("title")?.trim().replace(/\s+/g, " ").toLowerCase() || "";
              return text === expected || aria === expected || title === expected;
            }),
        normalizedLabel,
        { timeout: numberOr(command.timeoutMs, 120000) },
      );
      await this.page.evaluate((expected) => {
        const button = Array.from(document.querySelectorAll("button, [role], [tabindex]")).find(
          (node) => {
            const role = node.getAttribute("role");
            if (
              node.tagName !== "BUTTON" &&
              !["button", "link", "menuitem", "option", "tab"].includes(
                (role || "").toLowerCase(),
              ) &&
              !(node.hasAttribute("tabindex") && typeof node.onclick === "function")
            ) {
              return false;
            }
            const text =
              (node.innerText || node.textContent || "").trim().replace(/\s+/g, " ").toLowerCase();
            const aria = node.getAttribute("aria-label")?.trim().replace(/\s+/g, " ").toLowerCase() || "";
            const title = node.getAttribute("title")?.trim().replace(/\s+/g, " ").toLowerCase() || "";
            return text === expected || aria === expected || title === expected;
          },
        );
        if (!button) {
          throw new Error(`button not found by text: ${expected}`);
        }
        if (typeof button.click === "function") {
          button.click();
          return;
        }
        button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
      }, normalizedLabel);
    }

    if (waitAfterMs > 0) {
      await this.page.waitForTimeout(waitAfterMs);
    }

    emitEvent("button_clicked", {
      label,
      timestamp: new Date().toISOString(),
    });
    return await this.status({ bodyTextLimit: command.bodyTextLimit });
  }

  async screenshot(command) {
    this._ensurePage();
    const path = requireString(command.path, "path");
    await this.page.screenshot({
      path,
      fullPage: booleanOr(command.fullPage, true),
    });
    return { path };
  }

  _ensurePage() {
    if (!this.page) {
      throw new Error("browser session is not connected");
    }
  }

  _installPageListeners(page) {
    page.on("pageerror", (error) => {
      this._recordLog("pageerror", error.stack || error.message || String(error));
    });
    page.on("console", (message) => {
      if (!this.logConsole) {
        return;
      }
      const text = message.text();
      if (this._shouldLogConsole(text)) {
        this._recordLog(`console:${message.type()}`, text);
      }
    });
    page.on("request", (request) => {
      if (!this.logNetwork || !this._shouldCaptureUrl(request.url())) {
        return;
      }
      this._recordTraffic({
        kind: "http_request",
        method: request.method(),
        resourceType: request.resourceType(),
        url: request.url(),
        postData: truncateText(request.postData(), this.trafficBodyLimit),
      });
    });
    page.on("requestfailed", (request) => {
      if (!this.logNetwork || !this._shouldCaptureUrl(request.url())) {
        return;
      }
      this._recordTraffic({
        kind: "http_request_failed",
        method: request.method(),
        resourceType: request.resourceType(),
        url: request.url(),
        failure: request.failure()?.errorText || null,
      });
    });
    page.on("response", async (response) => {
      if (!this.logNetwork || !this._shouldCaptureUrl(response.url())) {
        return;
      }
      const headers = response.headers();
      const contentType = headers["content-type"] || headers["Content-Type"] || null;
      let bodyPreview = null;
      if (this._isTextLikeResponse(contentType, response.request().resourceType())) {
        try {
          bodyPreview = truncateText(await response.text(), this.trafficBodyLimit);
        } catch {
          bodyPreview = null;
        }
      }
      this._recordTraffic({
        kind: "http_response",
        method: response.request().method(),
        resourceType: response.request().resourceType(),
        status: response.status(),
        url: response.url(),
        contentType,
        bodyPreview,
      });
    });
    page.on("websocket", (websocket) => {
      if (!this.logNetwork || !this._shouldCaptureUrl(websocket.url())) {
        return;
      }
      this._recordTraffic({
        kind: "websocket_open",
        url: websocket.url(),
      });
      websocket.on("framesent", ({ payload }) => {
        this._recordTraffic({
          kind: "websocket_frame_sent",
          url: websocket.url(),
          payloadPreview: truncateText(payload, this.trafficBodyLimit),
        });
      });
      websocket.on("framereceived", ({ payload }) => {
        this._recordTraffic({
          kind: "websocket_frame_received",
          url: websocket.url(),
          payloadPreview: truncateText(payload, this.trafficBodyLimit),
        });
      });
      websocket.on("close", () => {
        this._recordTraffic({
          kind: "websocket_close",
          url: websocket.url(),
        });
      });
    });
  }

  _shouldLogConsole(text) {
    return (
      text.includes("[GAME CONTEXT]") ||
      text.includes("[GAME EVENT]") ||
      text.includes("[RTVI Message]") ||
      text.includes("Requested device not found") ||
      text.includes("Character selected") ||
      text.includes("Character card selected") ||
      text.includes("Bot is ready")
    );
  }

  _recordLog(level, message) {
    const item = {
      timestamp: new Date().toISOString(),
      level,
      message,
    };
    this.recentLogs.push(item);
    if (this.recentLogs.length > 100) {
      this.recentLogs.shift();
    }
    emitEvent("page_log", item);
  }

  _recordTraffic(payload) {
    const item = {
      timestamp: new Date().toISOString(),
      ...serialize(payload),
    };
    this.recentTraffic.push(item);
    if (this.recentTraffic.length > this.trafficLimit) {
      this.recentTraffic.shift();
    }
    emitEvent("traffic", item);
  }

  _isTextLikeResponse(contentType, resourceType) {
    if (resourceType === "fetch" || resourceType === "xhr") {
      return true;
    }
    if (!contentType) {
      return false;
    }
    return (
      contentType.includes("application/json") ||
      contentType.startsWith("text/") ||
      contentType.includes("application/problem+json")
    );
  }

  _shouldCaptureUrl(url) {
    return this.networkFilters.some((pattern) => url.includes(pattern));
  }

  async _signIn(command, timeoutMs) {
    const email = requireString(command.email, "email");
    const password = requireString(command.password, "password");

    const signInButton = this.page.getByRole("button", {
      name: /^sign in$/i,
    });
    const emailInput = this.page.getByPlaceholder("Email");

    await Promise.race([
      signInButton.waitFor({ state: "visible", timeout: timeoutMs }).then(() => "button"),
      emailInput.waitFor({ state: "visible", timeout: timeoutMs }).then(() => "form"),
    ]);

    if (await signInButton.isVisible().catch(() => false)) {
      await signInButton.click();
    }

    await emailInput.waitFor({ state: "visible", timeout: timeoutMs });
    await emailInput.fill(email);
    await this.page.getByPlaceholder("Password").fill(password);
    await this.page.getByRole("button", { name: /^join$/i }).click();
  }

  async _selectCharacter(command, timeoutMs) {
    const characterName = requireString(command.characterName, "characterName");
    const locator = this.page
      .locator('[role="button"]')
      .filter({ hasText: new RegExp(escapeRegExp(characterName), "i") })
      .first();

    await locator.waitFor({ state: "visible", timeout: timeoutMs });
    await locator.evaluate((node) => node.click());
  }

  async _waitForGameShell(timeoutMs) {
    await this.page.waitForFunction(
      () => {
        const text = document.body.innerText;
        if (
          text.includes("INITIALIZING GAME INSTANCES") ||
          text.includes("AWAITING MAP DATA") ||
          text.includes("AWAITING SHIP DATA")
        ) {
          return false;
        }
        return Array.from(document.querySelectorAll("input,textarea")).some((field) => {
          const placeholder = (field.placeholder || "").toLowerCase();
          return placeholder.includes("enter command") && field.disabled === false;
        });
      },
      { timeout: timeoutMs },
    );
  }

  async _waitForEnabledCommandInput(timeoutMs) {
    await this.page.waitForFunction(
      () =>
        Array.from(document.querySelectorAll("input,textarea")).some((field) => {
          const placeholder = (field.placeholder || "").toLowerCase();
          return placeholder.includes("enter command") && field.disabled === false;
        }),
      { timeout: timeoutMs },
    );
  }
}

const controller = new HostedGameBrowser();

async function handleCommand(command) {
  switch (command.op) {
    case "connect":
      return await controller.connect(command);
    case "status":
      return await controller.status(command);
    case "sendCommand":
      return await controller.sendCommand(command);
    case "clickButton":
      return await controller.clickButton(command);
    case "screenshot":
      return await controller.screenshot(command);
    case "close":
      await controller.close();
      return { closed: true };
    default:
      throw new Error(`unsupported op: ${command.op}`);
  }
}

async function main() {
  if (process.argv.includes("--help") || process.argv.includes("-h")) {
    process.stdout.write(`${HELP_TEXT}\n`);
    process.exit(0);
  }

  emitEvent("browser_ready");

  const rl = readline.createInterface({
    input: process.stdin,
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    const raw = line.trim();
    if (!raw) {
      continue;
    }

    let command;
    try {
      command = JSON.parse(raw);
    } catch (error) {
      writeMessage({
        type: "fatal",
        error: serializeError(error),
      });
      continue;
    }

    try {
      const result = await handleCommand(command);
      writeMessage({
        type: "response",
        id: command.id ?? null,
        ok: true,
        result: serialize(result),
      });
    } catch (error) {
      writeMessage({
        type: "response",
        id: command.id ?? null,
        ok: false,
        error: serializeError(error),
      });
    }
  }

  await controller.close();
}

main().catch(async (error) => {
  writeMessage({
    type: "fatal",
    error: serializeError(error),
  });
  await controller.close();
  process.exit(1);
});
