// Renders PNG icons + social preview from the SVG mark (run once; outputs are committed).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
(async () => {
  const svg = fs.readFileSync(path.join(__dirname, "../public/icons/icon.svg"), "utf8");
  const b = await chromium.launch();
  const p = await b.newPage();
  const shot = async (html, w, h, out) => { await p.setViewportSize({ width: w, height: h }); await p.setContent(html); await p.screenshot({ path: out, omitBackground: true }); };
  const icon = (pad, bg) => `<html><body style="margin:0;background:${bg}"><div style="width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;box-sizing:border-box;padding:${pad}">${svg.replace("<svg", '<svg style="width:100%;height:100%"')}</div></body></html>`;
  const out = path.join(__dirname, "../public/icons");
  for (const [s, f] of [[192, "icon-192.png"], [512, "icon-512.png"], [180, "apple-touch-icon.png"], [32, "favicon-32.png"]]) await shot(icon("0", "transparent"), s, s, path.join(out, f));
  await shot(icon("12%", "#2563eb"), 512, 512, path.join(out, "icon-maskable-512.png"));
  const og = `<html><body style="margin:0;width:1200px;height:630px;font-family:system-ui,Segoe UI,Roboto,sans-serif;background:linear-gradient(135deg,#eff6ff,#ecfdf5);display:flex;align-items:center;padding:80px;box-sizing:border-box">
    <div><div style="display:flex;align-items:center;gap:24px">${svg.replace("<svg", '<svg style="width:120px;height:120px"')}<span style="font-size:72px;font-weight:800;color:#0f172a">Tracelow</span></div>
    <p style="font-size:52px;font-weight:700;color:#1e3a8a;margin:48px 0 16px;max-width:980px;line-height:1.15">Mach deinen digitalen Fußabdruck kleiner.</p>
    <p style="font-size:30px;color:#334155;margin:0">Datenlecks · Auffindbarkeit · Lösch-Anfragen nach DSGVO · EU-Hosting</p></div></body></html>`;
  await shot(og, 1200, 630, path.join(__dirname, "../public/og.png"));
  fs.copyFileSync(path.join(__dirname, "../public/og.png"), path.join(__dirname, "../../marketing/brand/social-preview.png"));
  await b.close();
  console.log("assets rendered");
})();
