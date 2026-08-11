import { spawn } from "node:child_process";
import { once } from "node:events";
import { createConnection } from "node:net";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const serveEntry = resolve(root, "node_modules", "serve", "build", "main.js");
const server = spawn(process.execPath, [serveEntry, "dist", "--listen", "4173", "--no-clipboard"], {
  cwd: root,
  stdio: "inherit"
});

async function waitForServer() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const connected = await new Promise((resolveConnection) => {
      const socket = createConnection({ host: "127.0.0.1", port: 4173 });
      socket.once("connect", () => {
        socket.destroy();
        resolveConnection(true);
      });
      socket.once("error", () => resolveConnection(false));
    });
    if (connected) return;
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  throw new Error("The preview server did not start on port 4173.");
}

async function run(script) {
  const child = spawn(process.execPath, [resolve(root, script)], {
    cwd: root,
    stdio: "inherit"
  });
  const [code] = await once(child, "exit");
  if (code !== 0) throw new Error(`${script} failed with exit code ${code}.`);
}

try {
  await waitForServer();
  await run("tests/accessibility.mjs");
  await run("tests/visual.mjs");
} finally {
  server.kill();
}
