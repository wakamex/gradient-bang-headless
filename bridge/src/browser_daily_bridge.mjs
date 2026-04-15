import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as esbuild from "esbuild";
import { chromium } from "playwright-core";

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const BRIDGE_ROOT = path.resolve(MODULE_DIR, "..");
const RUNTIME_ENTRY = path.join(MODULE_DIR, "browser_page_runtime.mjs");
const RUNTIME_HTML = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Gradient Bang Headless Daily Runtime</title>
  </head>
  <body>
    <script type="module" src="/runtime.mjs"></script>
  </body>
</html>`;

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
    return serialize(error);
  }
  return { message: String(error) };
}

async function waitForRuntime(page, timeoutMs = 15000) {
  await page.waitForFunction(() => typeof globalThis.__gradientHeadlessBridge === "object", null, {
    timeout: timeoutMs,
  });
}

export class BrowserDailyBridge {
  constructor({ emitDiagnostic }) {
    this.emitDiagnostic = emitDiagnostic;
    this.bundleText = null;
    this.server = null;
    this.serverUrl = null;
    this.browser = null;
    this.context = null;
    this.page = null;
    this.pendingLogLevel = "info";
  }

  async connect(command) {
    await this._ensurePage();
    return this._callRuntime("connect", command);
  }

  async sendClientMessage(command) {
    return this._callRuntime("sendClientMessage", command);
  }

  async sendClientRequest(command) {
    return this._callRuntime("sendClientRequest", command);
  }

  async sendText(command) {
    return this._callRuntime("sendText", command);
  }

  async disconnectBot() {
    return this._callRuntime("disconnectBot", {});
  }

  async disconnect() {
    if (!this.page) {
      return { disconnected: false };
    }
    return this._callRuntime("disconnect", {});
  }

  async status() {
    if (!this.page) {
      return {
        hasClient: false,
        connected: false,
        state: "disconnected",
        transport: "daily",
      };
    }
    return this._callRuntime("status", {});
  }

  async setLogLevel(command) {
    this.pendingLogLevel = String(command.level ?? "info");
    if (!this.page) {
      return { level: this.pendingLogLevel };
    }
    return this._callRuntime("setLogLevel", { level: this.pendingLogLevel });
  }

  async close() {
    if (this.page) {
      try {
        await this._callRuntime("close", {});
      } catch (error) {
        this.emitDiagnostic("bridge_warning", {
          message: "browser runtime close failed",
          error: serializeError(error),
        });
      }
    }

    for (const target of [this.context, this.browser]) {
      if (!target) {
        continue;
      }
      try {
        await target.close();
      } catch (error) {
        this.emitDiagnostic("bridge_warning", {
          message: "browser transport shutdown failed",
          error: serializeError(error),
        });
      }
    }

    if (this.server) {
      await new Promise((resolve) => this.server.close(resolve));
    }

    this.page = null;
    this.context = null;
    this.browser = null;
    this.server = null;
    this.serverUrl = null;
    return { closed: true };
  }

  async _callRuntime(method, payload) {
    await this._ensurePage();
    try {
      return await this.page.evaluate(
        async ({ runtimeMethod, runtimePayload }) => {
          const runtime = globalThis.__gradientHeadlessBridge;
          if (!runtime || typeof runtime[runtimeMethod] !== "function") {
            throw new Error(`runtime method ${runtimeMethod} is unavailable`);
          }
          return runtime[runtimeMethod](runtimePayload);
        },
        { runtimeMethod: method, runtimePayload: payload },
      );
    } catch (error) {
      if (String(error).includes("Target page, context or browser has been closed")) {
        await this.close();
      }
      throw error;
    }
  }

  async _ensurePage() {
    if (this.page && !this.page.isClosed()) {
      return;
    }

    await this._ensureServer();
    this.browser = await chromium.launch({
      headless: true,
      args: [
        "--autoplay-policy=no-user-gesture-required",
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
      ],
    });
    this.context = await this.browser.newContext();
    await this.context.grantPermissions(["camera", "microphone"], {
      origin: this.serverUrl,
    });
    this.page = await this.context.newPage();

    await this.page.exposeBinding("__gradientBridgeEmit", async (_source, message) => {
      if (message && typeof message.event === "string") {
        this.emitDiagnostic(message.event, message);
      } else {
        this.emitDiagnostic("browser_runtime_message", {
          message: serialize(message),
        });
      }
    });

    this.page.on("console", (message) => {
      this.emitDiagnostic("browser_console", {
        level: message.type(),
        text: message.text(),
      });
    });
    this.page.on("pageerror", (error) => {
      this.emitDiagnostic("browser_page_error", serializeError(error));
    });

    await this.page.goto(`${this.serverUrl}/runtime.html`);
    await waitForRuntime(this.page);
    await this._callRuntime("setLogLevel", { level: this.pendingLogLevel });
  }

  async _ensureServer() {
    if (this.server) {
      return;
    }

    if (!this.bundleText) {
      const result = await esbuild.build({
        entryPoints: [RUNTIME_ENTRY],
        bundle: true,
        format: "esm",
        platform: "browser",
        write: false,
      });
      this.bundleText = result.outputFiles[0].text;
    }

    this.server = http.createServer((req, res) => {
      const requestPath = req.url || "/";
      if (requestPath === "/" || requestPath === "/runtime.html") {
        res.setHeader("content-type", "text/html; charset=utf-8");
        res.end(RUNTIME_HTML);
        return;
      }
      if (requestPath === "/runtime.mjs") {
        res.setHeader("content-type", "text/javascript; charset=utf-8");
        res.end(this.bundleText);
        return;
      }
      res.statusCode = 404;
      res.end("not found");
    });

    await new Promise((resolve) => this.server.listen(0, "127.0.0.1", resolve));
    const address = this.server.address();
    this.serverUrl = `http://127.0.0.1:${address.port}`;
  }
}
