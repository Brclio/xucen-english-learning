var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// cloudflare/worker.js
var PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "same-origin",
  "X-Frame-Options": "DENY"
};
var encoder = new TextEncoder();
function headersFor(initial = {}) {
  const headers = new Headers(initial);
  for (const [name, value] of Object.entries(PRIVATE_HEADERS)) headers.set(name, value);
  const vary = (headers.get("Vary") || "").split(",").map((value) => value.trim()).filter(Boolean);
  if (!vary.some((value) => value.toLowerCase() === "authorization")) vary.push("Authorization");
  headers.set("Vary", vary.join(", "));
  return headers;
}
__name(headersFor, "headersFor");
function message(text, status, extra = {}, head = false) {
  return new Response(head ? null : text, { status, headers: headersFor({ "Content-Type": "text/plain; charset=utf-8", ...extra }) });
}
__name(message, "message");
function configured(password) {
  return typeof password === "string" && password.length >= 16 && !/^(?:REPLACE_|CHANGE_ME|INVALID_)/i.test(password);
}
__name(configured, "configured");
async function authorized(request, password) {
  const match = /^Basic\s+([A-Za-z0-9+/]+={0,2})$/i.exec(request.headers.get("Authorization") || "");
  if (!match) return false;
  let credentials;
  try {
    credentials = new TextDecoder("utf-8", { fatal: true }).decode(Uint8Array.from(atob(match[1]), (c) => c.charCodeAt(0)));
  } catch {
    return false;
  }
  const [actual, expected] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(credentials)),
    crypto.subtle.digest("SHA-256", encoder.encode(`learner:${password}`))
  ]);
  const a = new Uint8Array(actual), b = new Uint8Array(expected);
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i];
  return difference === 0;
}
__name(authorized, "authorized");
function decodedPath(url) {
  if (/%(?:2f|5c|00)/i.test(url.pathname)) return null;
  let path;
  try {
    path = decodeURIComponent(url.pathname);
  } catch {
    return null;
  }
  if (/[\\%\u0000-\u001f\u007f]/.test(path)) return null;
  const parts = path.split("/").filter(Boolean);
  if (parts.some((part) => part.startsWith("."))) return null;
  if (["scripts", "cloudflare", "test", "node_modules"].includes(parts[0])) return null;
  return path;
}
__name(decodedPath, "decodedPath");
function parseRange(value, size) {
  const match = /^bytes=(\d*)-(\d*)$/i.exec(value.trim());
  if (!match || !match[1] && !match[2] || size === 0) return null;
  const first = match[1] ? Number(match[1]) : null;
  const last = match[2] ? Number(match[2]) : null;
  if (first !== null && !Number.isSafeInteger(first) || last !== null && !Number.isSafeInteger(last)) return null;
  if (first === null) {
    if (last <= 0) return null;
    const length = Math.min(last, size);
    return { offset: size - length, length };
  }
  if (first >= size || last !== null && last < first) return null;
  const end = last === null ? size - 1 : Math.min(last, size - 1);
  return { offset: first, length: end - first + 1 };
}
__name(parseRange, "parseRange");
function ifRangeMatches(value, metadata) {
  if (!value) return true;
  if (value.startsWith('"') || value.startsWith("W/")) return !value.startsWith("W/") && value === metadata.httpEtag;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && metadata.uploaded instanceof Date && Math.floor(metadata.uploaded.getTime() / 1e3) <= Math.floor(timestamp / 1e3);
}
__name(ifRangeMatches, "ifRangeMatches");
function objectHeaders(metadata, key) {
  const headers = new Headers();
  metadata.writeHttpMetadata?.(headers);
  headers.set("Content-Type", key.endsWith(".mp4") ? "video/mp4" : "audio/mpeg");
  headers.delete("Content-Encoding");
  headers.set("Accept-Ranges", "bytes");
  if (metadata.httpEtag) headers.set("ETag", metadata.httpEtag);
  if (metadata.uploaded instanceof Date) headers.set("Last-Modified", metadata.uploaded.toUTCString());
  return headersFor(headers);
}
__name(objectHeaders, "objectHeaders");
async function serveMedia(request, env, key) {
  const isHead = request.method === "HEAD";
  if (!env.COURSE_MEDIA) return message("Media storage is not configured.", 503, {}, isHead);
  const metadata = await env.COURSE_MEDIA.head(key);
  if (!metadata) return message("Media not found.", 404, {}, isHead);
  const size = metadata.size;
  if (!Number.isSafeInteger(size) || size < 0) return message("Invalid media metadata.", 502, {}, isHead);
  const headers = objectHeaders(metadata, key);
  const etags = (request.headers.get("If-None-Match") || "").split(",").map((value) => value.trim());
  if (etags.includes("*") || metadata.httpEtag && etags.some((value) => value.replace(/^W\//, "") === metadata.httpEtag)) return new Response(null, { status: 304, headers });
  let range;
  const rangeValue = !isHead && request.headers.get("Range");
  if (rangeValue && ifRangeMatches(request.headers.get("If-Range"), metadata)) {
    range = parseRange(rangeValue, size);
    if (!range) {
      headers.set("Content-Range", `bytes */${size}`);
      headers.set("Content-Length", "0");
      return new Response(null, { status: 416, headers });
    }
  }
  headers.set("Content-Length", String(range ? range.length : size));
  if (range) headers.set("Content-Range", `bytes ${range.offset}-${range.offset + range.length - 1}/${size}`);
  if (isHead) return new Response(null, { status: 200, headers });
  const options = {};
  if (range) options.range = range;
  if (metadata.etag) options.onlyIf = { etagMatches: metadata.etag };
  const object = await env.COURSE_MEDIA.get(key, options);
  if (!object) return message("Media not found.", 404);
  if (!("body" in object)) return message("Media changed; please retry.", 409);
  return new Response(object.body, { status: range ? 206 : 200, headers });
}
__name(serveMedia, "serveMedia");
var worker_default = {
  async fetch(request, env) {
    const isHead = request.method === "HEAD";
    if (!configured(env.COURSE_PASSWORD)) return message("Private course is not configured. Set a strong COURSE_PASSWORD secret.", 503, {}, isHead);
    const url = new URL(request.url);
    if (url.protocol === "http:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
      url.protocol = "https:";
      return new Response(null, { status: 308, headers: headersFor({ Location: url.href }) });
    }
    if (!await authorized(request, env.COURSE_PASSWORD)) return message("Authentication required.", 401, { "WWW-Authenticate": 'Basic realm="Private course", charset="UTF-8"' }, isHead);
    if (!["GET", "HEAD"].includes(request.method)) return message("Method not allowed.", 405, { Allow: "GET, HEAD" });
    const path = decodedPath(url);
    if (path === null) return message("Not found.", 404, {}, isHead);
    try {
      if (path.startsWith("/media/videos/") || path.startsWith("/media/audio/")) {
        if (!/^\/media\/(?:videos\/[^/]+\.mp4|audio\/[^/]+\.mp3)$/.test(path)) return message("Not found.", 404, {}, isHead);
        return await serveMedia(request, env, path.slice(1));
      }
      if (!env.ASSETS) return message("Static assets are not configured.", 503, {}, isHead);
      const upstreamHeaders = new Headers(request.headers);
      upstreamHeaders.delete("Authorization");
      const assetUrl = new URL(request.url);
      if (path === "/") assetUrl.pathname = "/index.html";
      const response = await env.ASSETS.fetch(new Request(assetUrl, { method: request.method, headers: upstreamHeaders }));
      const headers = headersFor(response.headers);
      headers.set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'");
      return new Response(isHead ? null : response.body, { status: response.status, statusText: response.statusText, headers });
    } catch {
      return message("Course storage is temporarily unavailable.", 502, {}, isHead);
    }
  }
};
export {
  worker_default as default
};
//# sourceMappingURL=worker.js.map
