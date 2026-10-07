import { Router, type IRouter } from "express";
import healthRouter from "./health";

const router: IRouter = Router();

router.use(healthRouter);
router.use(async (req, res): Promise<void> => {
  const crawlerPort = Number(process.env.SCHOLARSHIP_API_PORT ?? "8765");
  const target = new URL(
    req.originalUrl.replace(/^\/api(?=\/|$)/, ""),
    `http://127.0.0.1:${crawlerPort}`,
  );
  const hasBody = !["GET", "HEAD"].includes(req.method);

  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers: {
        accept: req.header("accept") ?? "application/json",
        ...(hasBody ? { "content-type": "application/json" } : {}),
      },
      ...(hasBody ? { body: JSON.stringify(req.body ?? {}) } : {}),
    });
    const contentType = upstream.headers.get("content-type");
    if (contentType) {
      res.setHeader("content-type", contentType);
    }
    res.status(upstream.status).send(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    req.log.error({ err: error }, "Scholarship API upstream is unavailable");
    res.status(502).json({ error: "Scholarship API is temporarily unavailable" });
  }
});

export default router;
