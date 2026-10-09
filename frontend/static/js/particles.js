/* ============================================================
 * 数智实训平台 · 背景粒子场
 * 单文件、零依赖，直接由 Flask 静态目录提供。
 *
 * 用法：
 *   <canvas id="dt-particles" aria-hidden="true"
 *           style="position:fixed;inset:0;width:100%;height:100%;z-index:0;pointer-events:none"></canvas>
 *   <script src="static/js/particles.js"></script>
 *   <script>DTParticles.init({ accent: '#BEF264', density: 1.0 });</script>
 *
 * 设计约束：
 *   - 纯装饰层：pointer-events:none，不抢任何点击，不参与布局
 *   - respects prefers-reduced-motion：该媒体查询命中时整体关闭，连 rAF 都不启动
 *   - 页面不可见 / 过场动画（#splash.active）期间暂停渲染，不空转 CPU
 *   - 高 DPI 下 devicePixelRatio 上限 2，避免 4K 屏粒子过细且掉帧
 * ============================================================ */
(function (global) {
    'use strict';

    var DEFAULTS = {
        canvasId: 'dt-particles',
        accent: '#BEF264',        // 品牌主色 lime-400，与按钮/进度条一致
        density: 1.35,            // 粒子密度系数
        maxCount: 150,
        linkDistance: 138,        // 粒子连线阈值（CSS 像素）
        cursorRadius: 185,        // 光标影响半径
        baseSpeed: 0.21,          // 基础漂移速度
        clickBurst: 18,           // 点击迸发粒子数，0 = 关闭
        lineAlpha: 0.22,          // 普通连线最大不透明度
        cursorLineAlpha: 0.38,    // 光标连线最大不透明度
        pointerEase: 0.12,        // 光标跟随缓动，越小越"重"
        burstLife: 1.5            // 迸发粒子寿命（秒）
    };

    var C = {};                   // 配置快照
    var cv = null, ctx = null;
    var dpr = 1, W = 0, H = 0;
    var parts = [], bursts = [];
    var running = false, rafId = 0;
    var lastT = 0, fpsEma = 60, frameGate = 0;
    var suspended = false, hidden = false;
    var reduced = false, reducedMq = null;
    var pointer = { x: 0, y: 0, sx: 0, sy: 0, active: false, raw: false };
    var burstScan = 0;
    var splashTimer = 0;
    var resizeTimer = 0;

    // ---------- 工具 ----------
    function rand(a, b) { return a + Math.random() * (b - a); }

    function rgbOf(hex) {
        var h = String(hex || '').replace('#', '');
        if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
        var n = parseInt(h, 16);
        if (isNaN(n)) n = 0xBEF264;
        return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
    }

    function rgba(c, a) {
        return 'rgba(' + c.r + ',' + c.g + ',' + c.b + ',' + a + ')';
    }

    function targetCount() {
        var n = Math.round(W * H / 13000 * C.density);
        n = Math.max(26, Math.min(C.maxCount, n));
        // 小屏再压一档，避免手机上发热
        if (W < 560) n = Math.min(n, 42);
        return n;
    }

    // ---------- 粒子 ----------
    function makeParticle() {
        return {
            x: Math.random() * W,
            y: Math.random() * H,
            vx: rand(-1, 1) * C.baseSpeed,
            vy: rand(-1, 1) * C.baseSpeed,
            r: rand(1.1, 2.7),
            a: rand(0.32, 0.82),
            ph: Math.random() * Math.PI * 2,
            pf: rand(0.5, 1.7)     // 呼吸频率
        };
    }

    function sync() {
        var want = targetCount();
        while (parts.length < want) parts.push(makeParticle());
        if (parts.length > want) parts.length = want;
    }

    function resize() {
        cv = cv || document.getElementById(C.canvasId);
        if (!cv) return;
        dpr = Math.min(2, Math.max(1, global.devicePixelRatio || 1));
        W = cv.clientWidth || global.innerWidth || 1;
        H = cv.clientHeight || global.innerHeight || 1;
        cv.width = Math.round(W * dpr);
        cv.height = Math.round(H * dpr);
        if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        sync();
    }

    // ---------- 渲染 ----------
    function clear() {
        ctx.clearRect(0, 0, W, H);
    }

    function step(dt) {
        var i, p, k;
        var sp = dt * 60;                     // 以 60fps 为基准的时间缩放
        var ease = 1 - Math.pow(1 - C.pointerEase, Math.min(4, sp));

        // 光标平滑跟随
        if (pointer.raw) { pointer.sx = pointer.x; pointer.sy = pointer.y; pointer.raw = false; }
        pointer.x += (pointer.sx - pointer.x) * ease;
        pointer.y += (pointer.sy - pointer.y) * ease;

        // 漂移 + 边界环绕
        for (i = 0; i < parts.length; i++) {
            p = parts[i];
            p.x += p.vx * sp;
            p.y += p.vy * sp;
            p.ph += p.pf * dt * 1.6;
            if (p.x < -12) p.x = W + 12; else if (p.x > W + 12) p.x = -12;
            if (p.y < -12) p.y = H + 12; else if (p.y > H + 12) p.y = -12;
        }

        // 光标附近的粒子轻微吸附，形成"被数据流牵引"的手感
        if (pointer.active) {
            var rr = C.cursorRadius * 1.35;
            for (i = 0; i < parts.length; i++) {
                p = parts[i];
                var dx = pointer.x - p.x, dy = pointer.y - p.y;
                var d2 = dx * dx + dy * dy;
                if (d2 < rr * rr && d2 > 1) {
                    var f = (1 - Math.sqrt(d2) / rr) * 0.16 * sp;
                    p.x += dx * f;
                    p.y += dy * f;
                }
            }
        }

        // 迸发粒子
        for (i = bursts.length - 1; i >= 0; i--) {
            k = bursts[i];
            k.x += k.vx * sp;
            k.y += k.vy * sp;
            k.vx *= (1 - 1.6 * dt);
            k.vy *= (1 - 1.6 * dt);
            k.t -= dt;
            if (k.t <= 0) bursts.splice(i, 1);
        }
    }

    function draw() {
        var i, j, p, q, k, alpha, t;
        var accent = C._rgb;
        clear();

        // 1) 粒子本体（带呼吸）
        for (i = 0; i < parts.length; i++) {
            p = parts[i];
            t = 0.72 + 0.28 * Math.sin(p.ph);
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r * (0.85 + 0.3 * t), 0, 6.2832);
            ctx.fillStyle = rgba(accent, p.a * t);
            ctx.fill();
        }

        // 2) 粒子间连线：按 x 排序做扫描，只比邻居，避免 O(n^2)
        parts.sort(function (a, b) { return a.x - b.x; });
        var L = C.linkDistance, L2 = L * L, inv = 1 / L;
        for (i = 0; i < parts.length; i++) {
            p = parts[i];
            for (j = i + 1; j < parts.length; j++) {
                q = parts[j];
                var dx = q.x - p.x;
                if (dx > L) break;                       // x 已超出阈值，后面的更远
                var dy = q.y - p.y;
                if (dy > L || dy < -L) continue;
                var d2 = dx * dx + dy * dy;
                if (d2 > L2) continue;
                alpha = (1 - Math.sqrt(d2) * inv) * C.lineAlpha;
                ctx.beginPath();
                ctx.moveTo(p.x, p.y);
                ctx.lineTo(q.x, q.y);
                ctx.strokeStyle = rgba(accent, alpha);
                ctx.lineWidth = 0.7;
                ctx.stroke();
            }
        }

        // 3) 光标连线：强化"人机同行"的示意
        if (pointer.active) {
            var R = C.cursorRadius, R2 = R * R, rinv = 1 / R;
            for (i = 0; i < parts.length; i++) {
                p = parts[i];
                var cdx = pointer.x - p.x, cdy = pointer.y - p.y;
                var cd2 = cdx * cdx + cdy * cdy;
                if (cd2 > R2) continue;
                alpha = (1 - Math.sqrt(cd2) * rinv) * C.cursorLineAlpha;
                ctx.beginPath();
                ctx.moveTo(pointer.x, pointer.y);
                ctx.lineTo(p.x, p.y);
                ctx.strokeStyle = rgba(accent, alpha);
                ctx.lineWidth = 0.85;
                ctx.stroke();
            }
        }

        // 4) 迸发粒子
        for (i = 0; i < bursts.length; i++) {
            k = bursts[i];
            var life = Math.max(0, Math.min(1, k.t / C.burstLife));
            ctx.beginPath();
            ctx.arc(k.x, k.y, k.r * (0.4 + life), 0, 6.2832);
            ctx.fillStyle = rgba(accent, 0.55 * life);
            ctx.fill();
        }
    }

    function frame(now) {
        rafId = requestAnimationFrame(frame);
        if (!lastT) { lastT = now; return; }
        var dt = (now - lastT) / 1000;
        lastT = now;
        if (dt > 0.05) dt = 0.05;                 // 切回前台时防止大跳跃

        fpsEma = fpsEma * 0.9 + (1 / Math.max(dt, 0.0001)) * 0.1;

        // 低端设备自动降档：低于 42fps 时隔帧渲染
        if (fpsEma < 42) { frameGate++; if (frameGate % 2 === 1) return; }

        step(dt);
        draw();
    }

    // ---------- 暂停 / 恢复 ----------
    function splashActive() {
        var s = document.getElementById('splash');
        return !!(s && s.classList.contains('active'));
    }

    function shouldRun() {
        return !hidden && !suspended && !reduced && !splashActive();
    }

    function start() {
        if (running || reduced) return;
        if (!shouldRun()) return;
        running = true;
        lastT = 0;
        rafId = requestAnimationFrame(frame);
        // 过场动画结束后自动续跑（无需页面侧配合）
        global.clearInterval(splashTimer);
        splashTimer = global.setInterval(function () {
            if (running) return;
            if (shouldRun()) start();
        }, 600);
    }

    function stop() {
        if (rafId) cancelAnimationFrame(rafId);
        rafId = 0;
        running = false;
        lastT = 0;
        global.clearInterval(splashTimer);
    }

    function evaluate() {
        if (shouldRun()) start(); else stop();
    }

    // ---------- 交互 ----------
    function onMove(x, y) {
        pointer.sx = x;
        pointer.sy = y;
        pointer.raw = true;
        pointer.active = true;
    }

    function bindEvents() {
        global.addEventListener('resize', function () {
            global.clearTimeout(resizeTimer);
            resizeTimer = global.setTimeout(function () { resize(); evaluate(); }, 150);
        }, { passive: true });

        global.addEventListener('mousemove', function (e) {
            onMove(e.clientX, e.clientY);
        }, { passive: true });

        global.addEventListener('mouseleave', function () { pointer.active = false; });
        global.addEventListener('blur', function () { pointer.active = false; });

        global.addEventListener('touchmove', function (e) {
            if (e.touches && e.touches.length) onMove(e.touches[0].clientX, e.touches[0].clientY);
        }, { passive: true });
        global.addEventListener('touchend', function () { pointer.active = false; }, { passive: true });

        document.addEventListener('visibilitychange', function () {
            hidden = document.hidden;
            evaluate();
        });
    }

    function bindBurst() {
        document.addEventListener('pointerdown', function (e) {
            if (reduced || C.clickBurst <= 0) return;
            // 表单控件、按钮、链接上不打扰，避免干扰真实交互
            var t = e.target;
            if (t && t.closest && t.closest('input, textarea, select, button, a, label, [role="button"]')) return;
            spawnBurst(e.clientX, e.clientY);
        }, { passive: true });
    }

    // 在指定位置迸发一簇粒子（点击时调用，也可外部主动调用）
    function spawnBurst(x, y) {
        var n = C.clickBurst;
        for (var i = 0; i < n; i++) {
            var ang = (i / n) * 6.2832 + rand(-0.3, 0.3);
            var spd = rand(0.25, 1.15);
            bursts.push({
                x: x, y: y,
                vx: Math.cos(ang) * spd,
                vy: Math.sin(ang) * spd,
                r: rand(1.1, 2.4),
                t: C.burstLife
            });
        }
        if (bursts.length > 240) bursts.splice(0, bursts.length - 240);
    }

    // ---------- 对外接口 ----------
    var API = {
        init: function (opts) {
            C = {};
            for (var k in DEFAULTS) if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) C[k] = DEFAULTS[k];
            if (opts) for (var j in opts) if (Object.prototype.hasOwnProperty.call(opts, j)) C[j] = opts[j];
            C._rgb = rgbOf(C.accent);

            // 尊重系统「减少动态效果」设置：整层不渲染
            reducedMq = global.matchMedia ? global.matchMedia('(prefers-reduced-motion: reduce)') : null;
            reduced = !!(reducedMq && reducedMq.matches);
            if (reduced) return API;
            if (!ctx) {
                cv = document.getElementById(C.canvasId);
                if (!cv || !cv.getContext) return API;
                ctx = cv.getContext('2d');
                if (!ctx) return API;
                bindEvents();
                bindBurst();
                if (reducedMq.addEventListener) {
                    reducedMq.addEventListener('change', function (e) { reduced = e.matches; evaluate(); });
                }
            }
            resize();
            evaluate();
            return API;
        },
        pause: function () { suspended = true; stop(); },
        resume: function () { suspended = false; evaluate(); },
        burst: function (x, y) { spawnBurst(x, y); },
        stats: function () { return { particles: parts.length, bursts: bursts.length, running: running, reduced: reduced, fps: Math.round(fpsEma) }; }
    };

    global.DTParticles = API;
})(window);
