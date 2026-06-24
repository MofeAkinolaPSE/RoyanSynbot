import "dotenv/config";
import express, { NextFunction, Request, Response } from "express";
import cors from "cors";
import { handleDemo } from "./routes/demo";

export function createServer() {
  const app = express();

  // Middleware — scoped to /api/* only so the Express body parser does NOT
  // consume request streams for routes that Vite will forward to FastAPI.
  // Applying express.json() globally was causing "request aborted" errors
  // because raw-body consumed the stream before Vite's proxy could pipe it.
  app.use(cors());
  app.use("/api", express.json());
  app.use("/api", express.urlencoded({ extended: true }));

  // Example API routes
  app.get("/api/ping", (_req, res) => {
    const ping = process.env.PING_MESSAGE ?? "ping";
    res.json({ message: ping });
  });

  app.get("/api/demo", handleDemo);

  // Suppress "request aborted" noise — these are normal browser cancellations
  // (navigation, StrictMode double-invoke, component unmount) not real errors.
  app.use((err: Error, _req: Request, res: Response, next: NextFunction) => {
    if (err.message === "request aborted") {
      // Connection was closed by the client; nothing to respond to.
      return;
    }
    next(err);
  });

  return app;
}
