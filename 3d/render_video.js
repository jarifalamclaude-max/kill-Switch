// Renders kill_switch_tutorial.mp4 from index.html: every frame is drawn by window.renderAt(t), so it is reproducible.
//
//   KS_CDN=<folder with three.min.js (r128) and OrbitControls.js (0.128.0)> node render_video.js [options]
//     --times 1.5,20,33        only save those frames as PNG (into --out, default ./frames) to look at them
//     --range 0:1920           frame range for this worker (default: all 64 s x 30 fps)
//     --out <folder>           where frames go (JPEG for the video)
//     --encode <file.mp4>      after rendering, encode all frames in --out with ffmpeg (h264, yuv420p, faststart)
//
// The CDN scripts are served from local copies through Playwright's request routing (no network needed);
// Google Fonts are skipped (Inter and JetBrains Mono are installed locally).
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? a.concat([[v.slice(2), all[i + 1]]]) : a), []));
const FPS = 30, T_END = 64, N = T_END * FPS;
const CDN = process.env.KS_CDN || path.join(__dirname, 'cdn');
const out = args.out || path.join(__dirname, 'frames');
fs.mkdirSync(out, { recursive: true });

const page_html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
// same skeleton the artifact host wraps around the page
const wrapped = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' +
  '<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>' +
  '</head><body>' + page_html + '</body></html>';

(async () => {
  const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.log('[page]', m.type(), m.text().slice(0, 300)); });
  page.on('pageerror', e => console.log('[pageerror]', e.message));
  await page.route('**/*', route => {
    const u = route.request().url();
    if (u.startsWith('http://ks.local/index.html')) return route.fulfill({ body: wrapped, contentType: 'text/html; charset=utf-8' });
    if (u.endsWith('/three.js/r128/three.min.js')) return route.fulfill({ path: path.join(CDN, 'three.min.js'), contentType: 'application/javascript' });
    if (u.endsWith('/three@0.128.0/examples/js/controls/OrbitControls.js')) return route.fulfill({ path: path.join(CDN, 'OrbitControls.js'), contentType: 'application/javascript' });
    return route.abort();
  });
  await page.goto('http://ks.local/index.html?video=1');
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
  await page.evaluate(() => document.fonts.ready);
  if (args.times) {
    for (const t of args.times.split(',').map(Number)) {
      await page.evaluate(t => window.renderAt(t), t);
      await page.screenshot({ path: path.join(out, `t${t.toFixed(2).padStart(6, '0')}.png`) });
      console.log('saved', t);
    }
  } else {
    const [a, b] = (args.range || `0:${N}`).split(':').map(Number);
    const t0 = Date.now();
    for (let i = a; i < b; i++) {
      await page.evaluate(t => window.renderAt(t), i / FPS);
      fs.writeFileSync(path.join(out, `f${String(i).padStart(5, '0')}.jpg`), await page.screenshot({ type: 'jpeg', quality: 94 }));
      if ((i - a) % 120 === 0) console.log(`frame ${i} (${((Date.now() - t0) / Math.max(1, i - a + 1)).toFixed(0)} ms/frame)`);
    }
  }
  await browser.close();
  if (args.encode) {
    execFileSync('/usr/bin/ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', path.join(out, 'f%05d.jpg'), '-c:v', 'libx264', '-preset', 'slow',
      '-crf', args.crf || '21', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-r', String(FPS), args.encode], { stdio: 'inherit' });
    console.log('encoded', args.encode, fs.statSync(args.encode).size, 'bytes');
  }
})();
