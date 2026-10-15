import type { Worker as OcrWorker } from "tesseract.js";

function abortable<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const abort = () => reject(new DOMException("Reading cancelled", "AbortError"));
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    promise.then(resolve, reject).finally(() => signal.removeEventListener("abort", abort));
  });
}

/** All parsing/OCR stays in this browser. Dependencies are lazy and same-origin. */
export async function readSoilReport(file: File, progress: (text: string) => void, signal: AbortSignal): Promise<string> {
  if (!file.size || file.size > 10 * 1024 * 1024) throw new Error("Choose a report under 10 MB.");
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  if (!isPdf && !["image/png", "image/jpeg", "image/webp"].includes(file.type)) throw new Error("Choose a PDF, JPG, PNG or WebP report.");
  let worker: OcrWorker | undefined;
  const abort = () => { void worker?.terminate(); };
  signal.addEventListener("abort", abort, { once: true });
  const recognize = async (canvas: HTMLCanvasElement) => {
    signal.throwIfAborted();
    if (!worker) {
      progress("Loading the reader on this device…");
      const { createWorker } = await import("tesseract.js");
      worker = await abortable<OcrWorker>(createWorker("eng", 1, {
        workerPath: `${import.meta.env.BASE_URL}ocr/worker.min.js`,
        corePath: `${import.meta.env.BASE_URL}ocr`, langPath: `${import.meta.env.BASE_URL}ocr`,
        logger: message => { if (!signal.aborted && message.status === "recognizing text") progress(`Reading report… ${Math.round(message.progress * 100)}%`); },
      }).then(created => {
        if (signal.aborted) { void created.terminate(); throw new DOMException("Reading cancelled", "AbortError"); }
        return created;
      }), signal);
      signal.throwIfAborted();
      await abortable(worker.setParameters({ preserve_interword_spaces: "1" }), signal);
    }
    return (await abortable(worker.recognize(canvas), signal)).data.text;
  };
  try {
    if (isPdf) {
      progress("Reading PDF…");
      const pdf = await import("pdfjs-dist");
      const workerUrl = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
      pdf.GlobalWorkerOptions.workerSrc = workerUrl.default;
      const task = pdf.getDocument({ data: await file.arrayBuffer(), useSystemFonts: true });
      const cancelPdf = () => { void task.destroy(); };
      signal.addEventListener("abort", cancelPdf, { once: true });
      try {
        signal.throwIfAborted();
        const doc = await task.promise;
        if (doc.numPages > 3) throw new Error("Choose a PDF with at most 3 pages for one soil sample, or photograph its results table.");
        const pages: string[] = [];
        for (let number = 1; number <= doc.numPages; number++) {
          signal.throwIfAborted();
          const page = await doc.getPage(number);
          const content = await page.getTextContent();
          const lines = new Map<number, { x: number; text: string }[]>();
          for (const item of content.items) {
            if (!("str" in item)) continue;
            const y = Math.round(item.transform[5] / 3) * 3;
            lines.set(y, [...(lines.get(y) || []), { x: item.transform[4], text: item.str }]);
          }
          const text = [...lines].sort(([a], [b]) => b - a).map(([, row]) => row.sort((a,b) => a.x - b.x).map(i => i.text).join(" ")).join("\n");
          // Scans often contain a header text layer but the results are an image.
          const { extractSoilText } = await import("./soilReport");
          if (Object.keys(extractSoilText(text).draft.values).length) pages.push(text);
          else {
            const base = page.getViewport({ scale: 1 });
            const viewport = page.getViewport({ scale: Math.min(2.5, 2000 / Math.max(base.width, base.height)) });
            const canvas = document.createElement("canvas"); canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
            await page.render({ canvas, canvasContext: canvas.getContext("2d")!, viewport }).promise;
            pages.push(await recognize(canvas)); canvas.width = canvas.height = 0;
          }
          page.cleanup();
        }
        return pages.join("\n");
      } finally { signal.removeEventListener("abort", cancelPdf); await task.destroy(); }
    }
    const bitmap = await createImageBitmap(file);
    try {
      if (bitmap.width * bitmap.height > 25_000_000) throw new Error("Crop the photo to the soil results table and try again (maximum 25 megapixels).");
      const scale = Math.min(1, 2200 / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement("canvas"); canvas.width = Math.ceil(bitmap.width * scale); canvas.height = Math.ceil(bitmap.height * scale);
      const context = canvas.getContext("2d")!; context.fillStyle = "white"; context.fillRect(0, 0, canvas.width, canvas.height); context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      try { return await recognize(canvas); } finally { canvas.width = canvas.height = 0; }
    } finally { bitmap.close(); }
  } finally { signal.removeEventListener("abort", abort); await worker?.terminate(); }
}
