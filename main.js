const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("node:child_process");
const http = require("node:http");
const net = require("node:net");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const APP_DATA_DIR = path.join(app.getPath("appData"), "SekyBarcode");
let backend = null;
let backendPort = null;
let shutdownToken = null;
let mainWindow = null;
let quitting = false;

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  app.whenReady().then(startApplication).catch(showStartupError);
}

function backendExecutable() {
  const resources = app.isPackaged ? process.resourcesPath : app.getAppPath();
  return path.join(resources, "backend", "SekyBarcodeBackend.exe");
}

async function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(error => error ? reject(error) : resolve(port));
    });
  });
}

async function startBackend() {
  const executable = backendExecutable();
  const legacyDatabase = path.join(app.getPath("desktop"), "Seky Barcode APP", "SekyBarcode.sqlite3");
  const userDatabase = path.join(APP_DATA_DIR, "SekyBarcode.sqlite3");
  if (!fs.existsSync(userDatabase) && fs.existsSync(legacyDatabase) && await isPortOpen(8765)) {
    throw new Error("Close the older Seky Barcode window and server, then open this app again so it can safely move your existing database.");
  }
  backendPort = await findFreePort();
  shutdownToken = crypto.randomBytes(32).toString("hex");
  backend = spawn(executable, [], {
    windowsHide: true,
    stdio: "ignore",
    env: {
      ...process.env,
      SEKY_APP_DATA_DIR: APP_DATA_DIR,
      SEKY_APP_LEGACY_DB: path.join(app.getPath("desktop"), "Seky Barcode APP", "SekyBarcode.sqlite3"),
      SEKY_APP_HOST: "127.0.0.1",
      SEKY_APP_PORT: String(backendPort),
      SEKY_APP_NO_BROWSER: "1",
      SEKY_APP_SHUTDOWN_TOKEN: shutdownToken
    }
  });
  backend.once("error", error => {
    console.error("Could not start Seky Barcode backend:", error);
  });
  backend.once("exit", (code, signal) => {
    if (!quitting) {
      console.error(`Seky Barcode backend stopped (code=${code}, signal=${signal}).`);
      if (mainWindow && !mainWindow.isDestroyed()) {
        dialog.showErrorBox("Seky Barcode", "The local database service stopped. Close and reopen Seky Barcode.");
        app.quit();
      }
    }
  });
  await waitForBackend();
}

function isPortOpen(port) {
  return new Promise(resolve => {
    const socket = net.connect({ host: "127.0.0.1", port });
    socket.setTimeout(250);
    socket.once("connect", () => { socket.destroy(); resolve(true); });
    socket.once("timeout", () => { socket.destroy(); resolve(false); });
    socket.once("error", () => resolve(false));
  });
}

function waitForBackend() {
  const address = `http://127.0.0.1:${backendPort}/api/items`;
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const poll = () => {
      if (!backend || backend.exitCode !== null) {
        reject(new Error("The local database service closed before it became ready."));
        return;
      }
      const request = http.get(address, response => {
        response.resume();
        if (response.statusCode === 200) resolve();
        else retry();
      });
      request.setTimeout(800, () => request.destroy());
      request.on("error", retry);
      function retry() {
        if (Date.now() - startedAt > 20000) {
          reject(new Error("The local database service did not become ready within 20 seconds."));
          return;
        }
        setTimeout(poll, 250);
      }
    };
    poll();
  });
}

async function startApplication() {
  app.setAppUserModelId("com.seky.barcode");
  try {
    await startBackend();
  } catch (error) {
    await stopBackend();
    throw error;
  }

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 980,
    minHeight: 700,
    title: "Seky Barcode",
    icon: app.isPackaged
      ? path.join(process.resourcesPath, "assets", "seky-barcode.ico")
      : path.join(app.getAppPath(), "assets", "seky-barcode.ico"),
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  mainWindow.on("closed", () => { mainWindow = null; });
  await mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`);
}

function sendShutdownRequest() {
  if (!backendPort || !shutdownToken) return Promise.resolve();
  return new Promise(resolve => {
    const payload = JSON.stringify({ token: shutdownToken });
    const request = http.request({
      hostname: "127.0.0.1",
      port: backendPort,
      path: "/api/shutdown",
      method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) },
      timeout: 1200
    }, response => {
      response.resume();
      response.once("end", resolve);
    });
    request.once("error", resolve);
    request.once("timeout", () => { request.destroy(); resolve(); });
    request.end(payload);
  });
}

async function stopBackend() {
  if (!backend) return;
  quitting = true;
  const child = backend;
  await sendShutdownRequest();
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 2500))
  ]);
  if (child.exitCode === null) child.kill();
  backend = null;
}

let stopping = false;
app.on("before-quit", event => {
  if (stopping || !backend) return;
  event.preventDefault();
  stopping = true;
  stopBackend().finally(() => app.quit());
});

async function showStartupError(error) {
  console.error(error);
  await dialog.showMessageBox({
    type: "error",
    title: "Seky Barcode could not start",
    message: "Seky Barcode could not start its local database service.",
    detail: `${error.message}\n\nYour existing database files have not been deleted. If the problem continues, contact the person who installed the app.`
  });
  app.quit();
}
