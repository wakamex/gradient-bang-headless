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
    this.recentLogs = [];
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
  }

  async connect(command) {
    await this.close();

    const siteUrl = typeof command.siteUrl === "string" && command.siteUrl.trim()
      ? command.siteUrl.trim()
      : DEFAULT_SITE_URL;
    const connectTimeoutMs = numberOr(command.connectTimeoutMs, 120000);
    const postConnectWaitMs = numberOr(command.postConnectWaitMs, 0);

    this.logConsole = booleanOr(command.logConsole, false);
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
      ({ bodyTextLimit, logs }) => {
        const input = document.querySelector('input[placeholder="Enter Command"]');
        return {
          url: window.location.href,
          title: document.title,
          headings: Array.from(document.querySelectorAll("h1,h2,h3"))
            .map((node) => node.textContent?.trim())
            .filter(Boolean),
          buttons: Array.from(document.querySelectorAll("button"))
            .map((node) => node.textContent?.trim())
            .filter(Boolean),
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
        };
      },
      {
        bodyTextLimit,
        logs: this.recentLogs.slice(-20),
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
      await this.page.waitForFunction(
        () => {
          const fields = Array.from(document.querySelectorAll("input,textarea"));
          return fields.some((field) => {
            const placeholder = (field.placeholder || "").toLowerCase();
            return (
              (placeholder.includes("enter command") || fields.length === 1) &&
              field.disabled === false
            );
          });
        },
        { timeout: inputTimeoutMs },
      );
    }

    const input = this.page.locator("input, textarea").first();
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

    await locator.waitFor({
      state: "visible",
      timeout: numberOr(command.timeoutMs, 120000),
    });
    await locator.click({ force: booleanOr(command.force, false) });

    if (waitAfterMs > 0) {
      await this.page.waitForTimeout(waitAfterMs);
    }

    emitEvent("button_clicked", { label });
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
      level,
      message,
    };
    this.recentLogs.push(item);
    if (this.recentLogs.length > 100) {
      this.recentLogs.shift();
    }
    emitEvent("page_log", item);
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
    await Promise.race([
      this.page.waitForSelector('input[placeholder="Enter Command"]', {
        timeout: timeoutMs,
      }),
      this.page.waitForSelector('input[placeholder="ENTER COMMAND"]', {
        timeout: timeoutMs,
      }),
      this.page
        .getByRole("button", { name: /^ships$/i })
        .waitFor({ state: "visible", timeout: timeoutMs }),
      this.page
        .getByRole("button", { name: /^skip tutorial$/i })
        .waitFor({ state: "visible", timeout: timeoutMs }),
      this.page.waitForFunction(
        () => {
          const text = document.body.innerText;
          return text.includes("BANK") && text.includes("ON HAND");
        },
        { timeout: timeoutMs },
      ),
    ]);
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
