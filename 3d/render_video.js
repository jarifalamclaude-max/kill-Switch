// Renders kill_switch_tutorial.mp4 (with the English voice-over) from index.html. Every frame is drawn by
// window.renderAt(sceneTime), so the video is reproducible.
//
// Voice-over: narration/lines.json says when each line starts (a scene time, or an expression of the page's
// TIMES such as "T_KILL-0.2"); narration/<id>.wav is the spoken line (make_voice.py). Where a line is longer than
// the scene time until the next line, that stretch of the scene is played slower, so the picture always waits
// for the voice. The warp is piecewise linear between the line starts.
//
//   KS_CDN=<folder with three.min.js (r128) and OrbitControls.js (0.128.0)> node render_video.js [options]
//     --times 1.5,20,33        only save those frames (video seconds) as PNG into --out, to look at them
//     --range 0:1920           frame range for this worker (default: all frames)
//     --out <folder>           where frames go (JPEG for the video)
//     --encode <file.mp4>      after rendering, encode all frames in --out and mix in the voice-over (ffmpeg)
//     --plan                   only print the warp and the length of the video
//
// The CDN scripts are served from local copies through Playwright's request routing (no network needed);
// Google Fonts are skipped (Inter and JetBrains Mono are installed locally).
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) =>
  (v.startsWith('--') ? a.concat([[v.slice(2), all[i + 1] !== undefined && !all[i + 1].startsWith('--') ? all[i + 1] : true]]) : a), []));
const FPS = 30, GAP = 0.35, TAIL = 0.9;
const CDN = process.env.KS_CDN || path.join(__dirname, 'cdn');
const out = args.out || path.join(__dirname, 'frames');
fs.mkdirSync(out, { recursive: true });
const NARR = path.join(__dirname, 'narration');

const page_html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
// same skeleton the artifact host wraps around the page
const wrapped = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' +
  '<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>' +
  '</head><body>' + page_html + '</body></html>';

const duration = f => parseFloat(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString());

// knots [scene time, video time]: each line gets at least its spoken length (+GAP) before the next one starts
function buildWarp(TIMES) {
  const lines = JSON.parse(fs.readFileSync(path.join(NARR, 'lines.json'), 'utf8')).map(l => {
    const at = Function(...Object.keys(TIMES), `return (${l.at});`)(...Object.values(TIMES));
    return { id: l.id, at, dur: duration(path.join(NARR, l.id + '.wav')) };
  }).sort((a, b) => a.at - b.at);
  const knots = [[0, 0]];
  let v = lines[0].at; knots.push([lines[0].at, v]);
  lines.forEach((l, i) => {
    const next = i + 1 < lines.length ? lines[i + 1].at : TIMES.T_END;
    const need = l.dur + (i + 1 < lines.length ? GAP : TAIL);
    l.v = v; v += Math.max(next - l.at, need); knots.push([next, v]);
  });
  return { lines, knots, T_VIDEO: v };
}
const sceneOf = (knots, tv) => {
  for (let i = 1; i < knots.length; i++) {
    const [s0, v0] = knots[i - 1], [s1, v1] = knots[i];
    if (tv <= v1) return v1 > v0 ? s0 + (s1 - s0) * (tv - v0) / (v1 - v0) : s1;
  }
  return knots[knots.length - 1][0];
};

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
  const TIMES = await page.evaluate(() => window.TIMES);
  const W = buildWarp(TIMES), N = Math.ceil(W.T_VIDEO * FPS);
  fs.writeFileSync(path.join(NARR, 'timeline.json'), JSON.stringify({ T_VIDEO: W.T_VIDEO, knots: W.knots, lines: W.lines.map(l => ({ id: l.id, scene: l.at, video: l.v, dur: l.dur })) }, null, 1));
  if (args.plan !== undefined) {
    W.lines.forEach(l => console.log(`${l.id}  scene ${l.at.toFixed(2)}  video ${l.v.toFixed(2)}  ${l.dur.toFixed(2)} s`));
    console.log(`video ${W.T_VIDEO.toFixed(2)} s, ${N} frames`);
  } else if (args.times) {
    for (const t of args.times.split(',').map(Number)) {
      await page.evaluate(t => window.renderAt(t), sceneOf(W.knots, t));
      await page.screenshot({ path: path.join(out, `t${t.toFixed(2).padStart(6, '0')}.png`) });
      console.log('saved', t);
    }
  } else {
    const [a, b] = (args.range || `0:${N}`).split(':').map(Number);
    const t0 = Date.now();
    for (let i = a; i < Math.min(b, N); i++) {
      await page.evaluate(t => window.renderAt(t), sceneOf(W.knots, i / FPS));
      fs.writeFileSync(path.join(out, `f${String(i).padStart(5, '0')}.jpg`), await page.screenshot({ type: 'jpeg', quality: 94 }));
      if ((i - a) % 120 === 0) console.log(`frame ${i} / ${N} (${((Date.now() - t0) / Math.max(1, i - a + 1)).toFixed(0)} ms/frame)`);
    }
  }
  await browser.close();
  if (args.encode) {
    // voice: every line delayed to its start, mixed into one track as long as the video
    const inputs = [], filters = [];
    W.lines.forEach((l, k) => { inputs.push('-i', path.join(NARR, l.id + '.wav'));
      filters.push(`[${k + 1}:a]aresample=48000,adelay=${Math.round(l.v * 1000)}:all=1[a${k}]`); });
    const mix = W.lines.map((l, k) => `[a${k}]`).join('') + `amix=inputs=${W.lines.length}:normalize=0,apad,atrim=0:${W.T_VIDEO.toFixed(3)},loudnorm=I=-16:TP=-1.5:LRA=11[voice]`;
    execFileSync('/usr/bin/ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', path.join(out, 'f%05d.jpg'), ...inputs,
      '-filter_complex', filters.join(';') + ';' + mix, '-map', '0:v', '-map', '[voice]',
      '-c:v', 'libx264', '-preset', 'slow', '-crf', args.crf || '23', '-pix_fmt', 'yuv420p', '-r', String(FPS),
      '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-movflags', '+faststart', '-shortest', args.encode], { stdio: 'inherit' });
    console.log('encoded', args.encode, fs.statSync(args.encode).size, 'bytes');
  }
})();
