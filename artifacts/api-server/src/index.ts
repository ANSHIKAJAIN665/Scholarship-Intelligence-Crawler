import app from "./app";
import { logger } from "./lib/logger";
import { spawn, type ChildProcess } from "node:child_process";
import { fileURLToPath } from "node:url";

const rawPort = process.env["PORT"];

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);
const scholarshipPort = Number(process.env.SCHOLARSHIP_API_PORT ?? "8765");

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

let scholarshipApi: ChildProcess | undefined;

async function startScholarshipApi(): Promise<void> {
  const workspaceRoot = fileURLToPath(new URL("../../../", import.meta.url));
  scholarshipApi = spawn(
    process.env.PYTHON_EXECUTABLE ?? "python3",
    [
      "-m",
      "uvicorn",
      "app:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(scholarshipPort),
      "--log-level",
      "info",
    ],
    {
      cwd: workspaceRoot,
      env: { ...process.env, PYTHONPATH: workspaceRoot },
      stdio: "inherit",
    },
  );
  scholarshipApi.on("error", (err) => {
    logger.error({ err }, "Unable to start FastAPI scholarship service");
  });
  scholarshipApi.on("exit", (code, signal) => {
    if (code !== null && code !== 0) {
      logger.error({ code, signal }, "FastAPI scholarship service exited unexpectedly");
      process.exit(1);
    }
  });

  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (scholarshipApi.exitCode !== null) {
      throw new Error("FastAPI scholarship service exited during startup");
    }
    try {
      const response = await fetch(`http://127.0.0.1:${scholarshipPort}/healthz`);
      if (response.ok) {
        logger.info({ scholarshipPort }, "FastAPI scholarship service is ready");
        return;
      }
    } catch {
      // Wait for Uvicorn to finish importing the app and binding its local port.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  scholarshipApi.kill("SIGTERM");
  throw new Error("FastAPI scholarship service did not become healthy within 30 seconds");
}

async function start(): Promise<void> {
  await startScholarshipApi();
  const server = app.listen(port, (err) => {
    if (err) {
      logger.error({ err }, "Error listening on port");
      process.exit(1);
    }

    logger.info({ port }, "Server listening");
  });

  const shutdown = (signal: NodeJS.Signals) => {
    scholarshipApi?.kill(signal);
    server.close(() => process.exit(0));
  };
  process.once("SIGTERM", shutdown);
  process.once("SIGINT", shutdown);
}

void start().catch((err: unknown) => {
  logger.error({ err }, "Unable to start API services");
  scholarshipApi?.kill("SIGTERM");
  process.exit(1);
});
