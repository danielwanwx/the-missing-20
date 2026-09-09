/* Optical decoding only. Product identity is not a physical quantity. */
(function (root) {
  const formats = ["ean_13", "upc_a", "code_128", "qr_code"];
  // Values from the pinned @zxing/library BarcodeFormat enum.
  const zxingFormats = { 14: "upc_a", 7: "ean_13", 4: "code_128", 11: "qr_code" };
  let library;
  function loadZXing() {
    if (root.ZXingBrowser) return Promise.resolve(root.ZXingBrowser);
    if (!library) library = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "/vendor/zxing-browser.min.js";
      script.onload = () => resolve(root.ZXingBrowser);
      script.onerror = () => { library = null; script.remove(); reject(new Error("Decoder unavailable; use a photo or enter the code.")); };
      document.head.append(script);
    });
    return library;
  }
  async function decoder() {
    try {
      const supported = await root.BarcodeDetector?.getSupportedFormats();
      if (formats.every((format) => supported?.includes(format))) {
        const native = new root.BarcodeDetector({ formats });
        let fallback;
        return async (canvas) => {
          let detected;
          try { detected = await native.detect(canvas); }
          catch { fallback ||= fallbackDecoder(); return (await fallback)(canvas); }
          if (!detected.some(result => result.format !== "qr_code")) return detected;
          fallback ||= fallbackDecoder();
          const checked = await (await fallback)(canvas);
          if (checked.length && !detected.some(result => result.rawValue === checked[0].rawValue && result.format === checked[0].format)) {
            throw new Error("Conflicting barcode readings; reduce glare and scan again.");
          }
          return checked;
        };
      }
    } catch { /* Known native capability failures use the pinned local fallback. */ }
    return fallbackDecoder();
  }
  async function fallbackDecoder() {
    const ZXing = await loadZXing();
    // Pinned DecodeHintType: 2 = supported formats, 3 = rotated/denser search.
    const reader = new ZXing.BrowserMultiFormatReader(new Map([
      [2, Object.keys(zxingFormats).map(Number)], [3, true],
    ]));
    function read(canvas) {
      try {
        const result = reader.decodeFromCanvas(canvas);
        const format = zxingFormats[result.getBarcodeFormat()];
        return format ? [{ rawValue: result.getText(), format }] : [];
      } catch (error) {
        // The production UMD minifies constructor names; getKind is its stable API.
        if (["NotFoundException", "ChecksumException", "FormatException"].includes(error.getKind?.() || error.name)) return [];
        throw error;
      }
    }
    let rotated;
    return async (canvas) => {
      const direct = read(canvas);
      if (direct[0]?.format === "qr_code") return direct;
      // The browser luminance source cannot rotate like ZXing's desktop source.
      rotated ||= document.createElement("canvas");
      rotated.width = canvas.height; rotated.height = canvas.width;
      const context = rotated.getContext("2d");
      context.translate(rotated.width, 0); context.rotate(Math.PI / 2);
      context.drawImage(canvas, 0, 0);
      const alternative = read(rotated);
      if (direct.length && alternative.length && (direct[0].rawValue !== alternative[0].rawValue || direct[0].format !== alternative[0].format)) {
        throw new Error("Conflicting barcode readings; reduce glare and scan again.");
      }
      return direct.length ? direct : alternative;
    };
  }
  class BarcodeCapture {
    constructor({ video, onCode, onState, makeDecoder = decoder }) {
      Object.assign(this, { video, onCode, onState, makeDecoder, generation: 0, timer: null, stream: null, url: null });
    }
    stop() {
      this.generation += 1;
      clearTimeout(this.timer);
      this.stream?.getTracks().forEach((track) => track.stop());
      this.stream = null;
      this.video.pause(); this.video.srcObject = null; this.video.removeAttribute("src");
      if (this.url) URL.revokeObjectURL(this.url);
      this.url = null;
    }
    async start(file) {
      this.stop();
      const generation = this.generation;
      this.onState("Opening decoder…");
      try {
        if (file && (!file.type.startsWith("video/") || file.size > 50 * 1024 * 1024)) throw new Error("Choose a video smaller than 50 MB.");
        const detect = await this.makeDecoder();
        if (generation !== this.generation) return;
        if (file) {
          this.url = URL.createObjectURL(file); this.video.src = this.url;
        } else {
          const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
          if (generation !== this.generation) { stream.getTracks().forEach((track) => track.stop()); return; }
          this.stream = stream; this.video.srcObject = stream;
        }
        await this.video.play();
        if (generation !== this.generation) return;
        this.onState("Scanning · stock changes only after verified receiving");
        const canvas = document.createElement("canvas");
        const seen = new Set();
        let previous = new Set();
        const tick = async () => {
          if (generation !== this.generation) return;
          if (this.video.ended) { this.stop(); this.onState("Video finished"); return; }
          try {
            if (this.video.readyState >= 2 && this.video.videoWidth) {
              const scale = Math.min(1, 1280 / this.video.videoWidth);
              canvas.width = Math.round(this.video.videoWidth * scale);
              canvas.height = Math.round(this.video.videoHeight * scale);
              canvas.getContext("2d").drawImage(this.video, 0, 0, canvas.width, canvas.height);
              const codes = await detect(canvas);
              if (generation !== this.generation) return;
              const current = new Set(codes.filter(result => formats.includes(result.format)).map(result => result.format + ":" + result.rawValue));
              for (const result of codes) {
                if (!formats.includes(result.format) || seen.has(result.rawValue)) continue;
                if (!previous.has(result.format + ":" + result.rawValue)) continue;
                if (seen.size >= 50) throw new Error("End this batch before scanning more codes.");
                seen.add(result.rawValue);
                await this.onCode(result.rawValue, result.format, file ? "video" : "camera");
                if (generation !== this.generation) return;
              }
              previous = current;
            }
            this.timer = setTimeout(tick, 250);
          } catch (error) { if (generation === this.generation) { this.stop(); this.onState(error.message || "Scanning unavailable; try a photo."); } }
        };
        await tick();
      } catch (error) {
        if (generation === this.generation) { this.stop(); this.onState(error.message || "Camera unavailable; use a photo or enter the code."); }
      }
    }
  }
  root.M20Barcode = { BarcodeCapture, decoder };
  if (typeof module !== "undefined") module.exports = root.M20Barcode;
})(globalThis);
