/* ergOS Harmony UI: glass shaping, charts, icons and Indian number formatting. Exposes window.ErgOS. */
(function () {
  'use strict';
  var SVGNS = 'http://www.w3.org/2000/svg';
  var uid = 0;
  var SAMPLE = {"demand":[732,726,784,740,794,775,744,783,737,771,734,734,762,798,729,736,771,814,792,991,1396,1699,2165,2372,2618,2876,3154,3149,3038,3179,3289,3342,3436,3521,3650,3765,3789,3765,3685,3742,3765,3765,3309,2315,2223,2818,3433,3765,3765,3765,3765,3765,3666,3684,3705,3586,3555,3451,3447,3415,3355,3243,3050,2826,2900,2784,2658,2637,2589,2337,2194,1904,1730,1688,1684,1663,1607,1565,1539,1417,1395,1342,1311,1269,1299,1187,1146,1092,750,741,754,743,753,750,757,705],"iex":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,2716,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],"now":88,"days":["Oct 1","Oct 2","Oct 3","Oct 4","Oct 5","Oct 6","Oct 7","Oct 8","Oct 9","Oct 10","Oct 11","Oct 12"],"savings":[34013.55,19686.03,36008.67,14708.26,38696.97,39652.33,37181.03,34686.63,22240.71,40460.03,36844.49,37013.36],"volume":[19800,14200,20600,12100,21400,22300,21900,20800,16900,22500,21200,21673],"heat":[{"label":"Wed 7","values":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1806,2057,2401,2655,2558,2561,2568,2568,2598,2611,2572,2540,2590,2584,2608,2654,2623,2602,2614,2621,2546,2648,2634,2645,2636,2587,2324,2017,1841,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},{"label":"Thu 8","values":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1785,2051,2338,2609,2631,2596,2590,2608,2602,2634,2593,2695,2664,2608,2620,2632,2634,2605,2692,2709,2646,2648,2600,2321,2095,1817,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},{"label":"Fri 9","values":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1523,1626,1814,2154,2103,2058,2105,2043,2103,2157,2144,2124,2071,2084,2060,2133,1895,1725,1443,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},{"label":"Sat 10","values":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1846,2210,2508,2742,2737,2738,2729,2667,2702,2683,2643,2643,2674,2671,2723,2755,2694,2752,2759,2755,2684,2666,2667,2664,2383,2180,1954,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},{"label":"Sun 11","values":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1734,1917,2184,2436,2350,2419,2449,2434,2430,2397,2361,2435,2380,2436,2457,2388,2388,2454,2427,2360,2100,1864,1745,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},{"label":"Mon 12","values":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1974,2143,2527,2808,2769,2732,2756,2706,2692,2807,2768,2753,2802,2742,2795,2789,2715,2720,2725,2719,2760,2721,2740,2706,2799,2732,2468,2213,1990,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},{"label":"Tue 13","values":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1889,2240,2445,2720,2719,2658,2709,2678,2656,2752,2677,2713,2743,2723,2695,2718,2723,2750,2669,2723,2686,2689,2749,2446,2183,1943,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]}],"solar":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,7,21,41,64,90,119,150,182,216,249,282,315,346,376,404,430,453,473,489,503,512,518,520,518,512,503,489,473,326,310,291,271,249,315,282,249,216,182,150,119,90,64,41,21,7,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],"wind":[210,221,242,245,250,256,250,254,260,269,257,253,242,254,259,244,258,267,266,262,246,227,225,209,199,191,177,177,175,184,181,182,177,177,170,159,170,178,180,177,164,150,141,127,135,132,142,137,150,158,142,135,149,150,165,162,152,160,172,169,162,164,185,197,190,189,185,182,200,199,210,216,215,229,225,236,231,236,234,234,253,265,260,272,263,260,269,271,256,268,256,246,251,242,233,218],"hydro":[150,151,153,154,155,156,157,158,159,160,161,161,162,162,162,162,162,161,161,160,160,159,158,157,155,154,153,152,150,149,148,146,145,144,143,142,141,140,139,139,138,138,138,138,138,138,139,140,140,141,142,143,144,145,147,148,149,151,152,153,154,156,157,158,159,160,160,161,161,162,162,162,162,162,161,161,160,159,158,157,156,155,154,152,151,150,148,147,146,145,143,142,141,141,140,139],"forecast":[747,746,755,764,767,767,767,762,754,752,748,760,751,752,759,770,768,821,953,1138,1409,1725,2050,2346,2637,2834,2967,3079,3352,3391,3452,3555,3654,3755,3850,3920,3955,3974,3974,3744,3653,3379,2860,3069,3069,2707,3201,3509,3699,3765,3745,3729,3717,3681,3639,3596,3549,3491,3445,3382,3302,3178,3075,2961,2844,2761,2714,2601,2483,2332,2151,1971,1895,1786,1725,1691,1660,1605,1550,1495,1443,1387,1363,1320,1280,1235,1128,1013,923,840,771,771,774,764,763,759]};

  /* ---------- formatting ---------- */
  function inr(n, dp) {
    dp = dp == null ? 0 : dp;
    var neg = n < 0, s = Math.abs(n).toFixed(dp), p = s.split('.'), x = p[0];
    var last = x.slice(-3), rest = x.slice(0, -3);
    if (rest) last = ',' + last;
    rest = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',');
    return (neg ? '−' : '') + rest + last + (p[1] ? '.' + p[1] : '');
  }
  function compact(n) {
    var a = Math.abs(n);
    if (a >= 1e7) return (n / 1e7).toFixed(2).replace(/\.?0+$/, '') + ' Cr';
    if (a >= 1e5) return (n / 1e5).toFixed(2).replace(/\.?0+$/, '') + ' L';
    if (a >= 1e3) return (n / 1e3).toFixed(a >= 1e4 ? 0 : 1).replace(/\.0$/, '') + 'k';
    return String(Math.round(n));
  }
  function niceStep(raw) {
    var p = Math.pow(10, Math.floor(Math.log10(raw || 1))), m = raw / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function slotTime(i) { var m = i * 15; return pad(Math.floor(m / 60) % 24) + ':' + pad(m % 60); }

  /* ---------- icons (24px grid, 1.75 stroke) ---------- */
  var ICONS = {
    bolt: '<path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12L13 2z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    grid: '<path d="M12 2.5 7 21.5M12 2.5l5 19"/><path d="M4.5 7h15M6.5 11.5h11"/><path d="M4.5 7v2M19.5 7v2M8.6 15.6l6.8 3.9M15.4 15.6l-6.8 3.9"/>',
    tower: '<path d="M12 2.5 7 21.5M12 2.5l5 19"/><path d="M4.5 7h15M6.5 11.5h11"/><path d="M4.5 7v2M19.5 7v2M8.6 15.6l6.8 3.9M15.4 15.6l-6.8 3.9"/>',
    solar: '<circle cx="17.5" cy="5.5" r="2.2"/><path d="M17.5 1.6v.7M21.4 5.5h-.7M20.3 2.7l-.5.5M13.6 5.5h.7M14.7 2.7l.5.5"/><path d="M2.8 12.2h12.6l2.1 6.6H4.9z"/><path d="M7.9 12.2l.7 6.6M11.9 12.2l1.4 6.6M3.9 15.5h12.6"/><path d="M11 18.8v2.7M8 21.5h6"/>',
    wind: '<path d="M12 10.4v11.1M9 21.5h6"/><circle cx="12" cy="9" r="1.4"/><path d="M12 7.6c-.5-2.3-.1-4.3 1.1-5.6.9 1.6.5 3.7-1.1 5.6z"/><path d="M12 7.6c-.5-2.3-.1-4.3 1.1-5.6.9 1.6.5 3.7-1.1 5.6z" transform="rotate(120 12 9)"/><path d="M12 7.6c-.5-2.3-.1-4.3 1.1-5.6.9 1.6.5 3.7-1.1 5.6z" transform="rotate(240 12 9)"/>',
    hydro: '<path d="M12 2.8s-5.3 5.8-5.3 9.9a5.3 5.3 0 0 0 10.6 0c0-4.1-5.3-9.9-5.3-9.9z"/><path d="M9.4 13.2c.9.7 1.8.7 2.6 0s1.8-.7 2.6 0"/><path d="M2.5 21.2c1.6-1 3.2-1 4.8 0s3.2 1 4.7 0 3.2-1 4.8 0 3.1 1 4.7 0"/>',
    exchange: '<path d="M4 8.5h13.5M14 4.5l4 4-4 4"/><path d="M20 15.5H6.5M10 11.5l-4 4 4 4"/>',
    mic: '<rect x="9" y="2.5" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5v4M8.5 21.5h7"/>',
    sparkle: '<path d="M11 3.5c.6 4 2.6 6 6.6 6.6-4 .6-6 2.6-6.6 6.6-.6-4-2.6-6-6.6-6.6 4-.6 6-2.6 6.6-6.6z"/><path d="M18.5 15.5c.2 1.3.9 2 2.2 2.2-1.3.2-2 .9-2.2 2.2-.2-1.3-.9-2-2.2-2.2 1.3-.2 2-.9 2.2-2.2z"/>',
    keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6.5 10h.01M10 10h.01M14 10h.01M17.5 10h.01M7.5 14h9"/>',
    stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="2.5"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    volume: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"/>',
    trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    rupee: '<path d="M6 4h12M6 9h12M14.5 20 7 12.5h2.5a4.25 4.25 0 0 0 0-8.5"/>',
    battery: '<rect x="2.5" y="7" width="16" height="10" rx="2.5"/><path d="M21.5 11v2M6.5 10.5v3M10 10.5v3"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    'chevron-left': '<path d="m15 18-6-6 6-6"/>',
    'chevron-right': '<path d="m9 18 6-6-6-6"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'arrow-left': '<path d="M19 12H5M12 19l-7-7 7-7"/>',
    'arrow-right': '<path d="M5 12h14M12 5l7 7-7 7"/>',
    'arrow-up': '<path d="M12 19V5M5 12l7-7 7 7"/>',
    download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    message: '<path d="M21 12a8.5 8.5 0 0 1-12.4 7.6L3.5 21l1.4-5A8.5 8.5 0 1 1 21 12z"/>',
    factory: '<path d="M3 21V10l5.5 3.5V10l5.5 3.5V6l7-3v18z"/><path d="M7 17h2M11.5 17h2M16 17h2"/>',
    home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v11h13V10"/>',
    gauge: '<path d="M12 14.5 16 10"/><path d="M3.5 18a9 9 0 1 1 17 0"/>',
    sliders: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.3-4.3"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    clip: '<path d="m21 11.5-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.9-8.9a3.7 3.7 0 0 1 5.2 5.2l-8.9 8.9a1.8 1.8 0 0 1-2.6-2.6l8.2-8.2"/>',
    bell: '<path d="M6 8.5a6 6 0 1 1 12 0c0 6.5 3 8.5 3 8.5H3s3-2 3-8.5"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
    moon: '<path d="M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7z"/>',
    pin: '<path d="M12 21.5s7-6 7-11.5a7 7 0 0 0-14 0c0 5.5 7 11.5 7 11.5z"/><circle cx="12" cy="10" r="2.5"/>',
    check: '<path d="M5 12.5 9.5 17 19 7"/>',
    layers: '<path d="M12 3 2.5 8 12 13l9.5-5L12 3z"/><path d="m2.5 13 9.5 5 9.5-5"/>',
    bars: '<path d="M5 20v-8M12 20V5M19 20v-5M3 20.5h18"/>',
    calc: '<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M8.5 7.5h7M8.5 12h.01M12 12h.01M15.5 12h.01M8.5 16h.01M12 16h.01M15.5 16h.01"/>',
    antenna: '<circle cx="12" cy="11" r="1.6"/><path d="M12 12.6V22M8.5 22h7M5.6 4.6a9 9 0 0 0 0 12.8M18.4 4.6a9 9 0 0 1 0 12.8M8.4 7.4a5 5 0 0 0 0 7.2M15.6 7.4a5 5 0 0 1 0 7.2"/>',
    receipt: '<path d="M5.5 3v18l2.2-1.4L10 21l2-1.4 2 1.4 2.3-1.4 2.2 1.4V3l-2.2 1.4L14 3l-2 1.4L10 3 7.7 4.4z"/><path d="M9 9h6M9 13h6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    apps: '<rect x="4" y="4" width="6.5" height="6.5" rx="1.8"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.8"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.8"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.8"/>',
    eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
    save: '<path d="M5 3h11l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a1 1 0 0 1 1-1z"/><path d="M8 3v5h7V3M8 21v-6h8v6"/>',
    shield: '<path d="M12 21.5s7.5-3.5 7.5-9.5V5.5L12 3 4.5 5.5V12c0 6 7.5 9.5 7.5 9.5z"/><path d="m9 12 2 2 4-4"/>',
    leaf: '<path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15"/><path d="M5 19 13 11"/>',
    more: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    play: '<path d="M7 4.5v15l12-7.5z"/>'
  };
  function ICON_SM(n) { return icon(n, 14); }
  function icon(name, size) {
    size = size || 18;
    var inner = ICONS[name] || ICONS.bolt;
    return '<svg class="eg-ico" viewBox="0 0 24 24" width="' + size + '" height="' + size +
      '" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + inner + '</svg>';
  }

  /* ---------- svg helpers ---------- */
  function s(tag, attrs, parent) {
    var e = document.createElementNS(SVGNS, tag);
    for (var k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, str, cls, anchor) {
    var t = s('text', { x: x, y: y, 'class': cls || 'eg-axis', 'text-anchor': anchor || 'start' }, parent);
    t.textContent = str;
    return t;
  }
  function gradient(defs, key, top, bottom) {
    var id = 'egg' + (++uid);
    var g = s('linearGradient', { id: id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    s('stop', { offset: '0', 'class': 'eg-stop-' + key, 'stop-opacity': top }, g);
    s('stop', { offset: '1', 'class': 'eg-stop-' + key, 'stop-opacity': bottom }, g);
    return 'url(#' + id + ')';
  }
  function responsive(host, draw) {
    var last = -1;
    function run() {
      var w = Math.round(host.clientWidth || 600);
      if (w === last) return;
      last = w;
      host.innerHTML = '';
      draw(w);
    }
    run();
    if (window.ResizeObserver) new ResizeObserver(function () { requestAnimationFrame(run); }).observe(host);
    return { redraw: function () { last = -1; run(); } };
  }
  function linePath(pts) {
    return pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join('');
  }
  function smoothPath(pts) {
    if (pts.length < 3) return linePath(pts);
    var d = 'M' + pts[0][0].toFixed(1) + ',' + pts[0][1].toFixed(1);
    for (var i = 0; i < pts.length - 1; i++) {
      var p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
      var c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
      var c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += 'C' + c1x.toFixed(1) + ',' + c1y.toFixed(1) + ' ' + c2x.toFixed(1) + ',' + c2y.toFixed(1) + ' ' + p2[0].toFixed(1) + ',' + p2[1].toFixed(1);
    }
    return d;
  }

  /* ---------- folder glass ---------- */
  function folderPath(w, h, tw, dip, r, run) {
    var y = dip;
    return 'M0,' + r + 'Q0,0 ' + r + ',0' +
      'L' + (tw - run * 0.15) + ',0' +
      'C' + (tw + run * 0.35) + ',0 ' + (tw + run * 0.35) + ',' + y + ' ' + (tw + run) + ',' + y +
      'L' + (w - r) + ',' + y + 'Q' + w + ',' + y + ' ' + w + ',' + (y + r) +
      'L' + w + ',' + (h - r) + 'Q' + w + ',' + h + ' ' + (w - r) + ',' + h +
      'L' + r + ',' + h + 'Q0,' + h + ' 0,' + (h - r) + 'Z';
  }
  function folder(front) {
    if (!front || front.__egShaped) return;
    front.__egShaped = true;
    var edge = document.createElementNS(SVGNS, 'svg');
    edge.setAttribute('class', 'eg-folder__edge');
    edge.setAttribute('aria-hidden', 'true');
    var ep = s('path', { 'class': 'eg-folder__edge-line' }, edge);
    front.insertBefore(edge, front.firstChild);
    function shape() {
      var w = front.offsetWidth, h = front.offsetHeight;
      if (!w || !h) return;
      var cs = getComputedStyle(front);
      var dip = parseFloat(cs.getPropertyValue('--folder-dip')) || 56;
      var ratio = parseFloat(cs.getPropertyValue('--folder-tab')) || 0.42;
      var r = Math.min(36, h / 4);
      var run = Math.min(130, Math.max(70, w * 0.11));
      var tw = Math.max(170, Math.min(w - run - r - 20, w * ratio));
      var d = folderPath(w, h, tw, dip, r, run);
      front.style.clipPath = "path('" + d + "')";
      front.style.webkitClipPath = "path('" + d + "')";
      front.classList.add('is-shaped');
      edge.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
      edge.setAttribute('width', w);
      edge.setAttribute('height', h);
      ep.setAttribute('d', d);
    }
    shape();
    if (window.ResizeObserver) new ResizeObserver(function () { requestAnimationFrame(shape); }).observe(front);
  }

  /* ---------- sparkline ---------- */
  function sparkline(host, values, opts) {
    opts = opts || {};
    var key = opts.series || host.getAttribute('data-series') || 'iex';
    return responsive(host, function (W) {
      var H = opts.height || 40, pad = 3;
      var svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, 'class': 'eg-svg', role: 'img', 'aria-label': opts.label || 'trend' }, host);
      var defs = s('defs', {}, svg);
      var max = Math.max.apply(null, values), min = Math.min.apply(null, values);
      if (opts.zero) min = 0;
      var rng = max - min || 1;
      var pts = values.map(function (v, i) {
        return [pad + i * (W - pad * 2) / (values.length - 1), H - pad - (v - min) / rng * (H - pad * 2)];
      });
      var d = monoPath(pts);
      s('path', { d: d + 'L' + pts[pts.length - 1][0] + ',' + H + 'L' + pts[0][0] + ',' + H + 'Z', fill: gradient(defs, key, 0.32, 0) }, svg);
      s('path', { d: d, 'class': 'eg-line s-' + key, 'stroke-width': 1.75, fill: 'none' }, svg);
      var e = pts[pts.length - 1];
      s('circle', { cx: e[0], cy: e[1], r: 3, 'class': 'eg-dot-end f-' + key }, svg);
    });
  }

  /* ---------- monotone curves (no overshoot, never dips below a stack) ---------- */
  function fp(p) { return p[0].toFixed(1) + ',' + p[1].toFixed(1); }
  function monoSegs(pts) {
    var n = pts.length, segs = [], d = [], m = [], i;
    if (n < 2) return segs;
    for (i = 0; i < n - 1; i++) d.push((pts[i + 1][1] - pts[i][1]) / ((pts[i + 1][0] - pts[i][0]) || 1));
    m[0] = d[0]; m[n - 1] = d[n - 2];
    for (i = 1; i < n - 1; i++) m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
    for (i = 0; i < n - 1; i++) {
      if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
      var a = m[i] / d[i], b = m[i + 1] / d[i], s2 = a * a + b * b;
      if (s2 > 9) { var t = 3 / Math.sqrt(s2); m[i] = t * a * d[i]; m[i + 1] = t * b * d[i]; }
    }
    for (i = 0; i < n - 1; i++) {
      var p0 = pts[i], p1 = pts[i + 1], dx = (p1[0] - p0[0]) / 3;
      segs.push([p0, [p0[0] + dx, p0[1] + m[i] * dx], [p1[0] - dx, p1[1] - m[i + 1] * dx], p1]);
    }
    return segs;
  }
  function monoPath(pts) {
    if (pts.length < 2) return pts.length ? 'M' + fp(pts[0]) : '';
    return 'M' + fp(pts[0]) + monoSegs(pts).map(function (s) { return 'C' + fp(s[1]) + ' ' + fp(s[2]) + ' ' + fp(s[3]); }).join('');
  }
  function monoBack(pts) {
    var segs = monoSegs(pts);
    if (!segs.length) return pts.length ? 'L' + fp(pts[0]) : '';
    return 'L' + fp(pts[pts.length - 1]) + segs.reverse().map(function (s) { return 'C' + fp(s[2]) + ' ' + fp(s[1]) + ' ' + fp(s[0]); }).join('');
  }

  /* ---------- energy sources ---------- */
  var SOURCES = {
    hydro: { label: 'Hydro', icon: 'hydro' },
    wind: { label: 'Wind', icon: 'wind' },
    solar: { label: 'Solar', icon: 'solar' },
    iex: { label: 'Power exchange', icon: 'exchange' },
    grid: { label: 'Grid', icon: 'grid' },
    battery: { label: 'Battery', icon: 'battery' },
    gov: { label: 'Shared battery', icon: 'battery' },
    demand: { label: 'Demand', icon: 'bolt' }
  };
  var PALETTES = ['harmony', 'volt', 'verdant', 'aurora'];
  function palette(el, name) {
    PALETTES.forEach(function (p) { el.classList.remove('eg-pal-' + p); });
    if (name && name !== 'harmony') el.classList.add('eg-pal-' + name);
  }

  /* ---------- area chart engine: stacked or overlaid, with cursor pills ---------- */
  function areaChart(host, o) {
    o = o || {};
    var series = o.series || [];
    var n = o.length || (series[0] ? series[0].values.length : 0);
    var stacked = !!o.stacked;
    var unit = o.unit || 'kW';
    var fmt = o.format || function (v) { return inr(Math.round(v)) + ' ' + unit; };
    var isSlots = o.slots != null ? o.slots : n === 96;
    var xLabel = o.xLabel || function (i) { return isSlots ? slotTime(i + 1) : String(i + 1); };
    var now = o.now != null ? o.now : null;
    var maxI = o.cursorMax != null ? o.cursorMax : n - 1;
    var rest = o.cursor != null ? o.cursor : (now != null ? now : maxI);
    var H = o.height || 340;
    var api = { cursor: rest };
    host.classList.add('eg-ac');
    if (!host.hasAttribute('tabindex')) host.setAttribute('tabindex', '0');
    if (!host.hasAttribute('role')) host.setAttribute('role', 'group');
    host.setAttribute('aria-label', o.label || 'Chart');

    // stack upper / lower bounds (null = no data)
    var bands = series.map(function () { return null; });
    var base = []; for (var b = 0; b < n; b++) base.push(0);
    series.forEach(function (s, si) {
      var lo = [], up = [];
      for (var i = 0; i < n; i++) {
        var v = s.values[i];
        if (v == null) { lo.push(null); up.push(null); continue; }
        var l = stacked ? base[i] : 0;
        lo.push(l); up.push(l + v);
        if (stacked) base[i] = l + v;
      }
      var end = -1, start = -1;
      for (i = 0; i < n; i++) if (up[i] != null) { if (start < 0) start = i; end = i; }
      bands[si] = { s: s, lo: lo, up: up, start: start, end: end };
    });
    var lineVals = o.line ? o.line.values : null;
    var peak = 0;
    bands.forEach(function (bd) { bd.up.forEach(function (v) { if (v != null && v > peak) peak = v; }); });
    if (lineVals) lineVals.forEach(function (v) { if (v != null && v > peak) peak = v; });
    var step = niceStep(peak / 4 || 1);
    var yMax = o.yMax || step * Math.ceil(peak * 1.06 / step);

    var r = responsive(host, function (W) {
      var yAxis = o.yAxis !== false;
      var L = yAxis ? 52 : 14, R = 16, T = 58, B = 48;
      var pw = W - L - R, ph = H - T - B, dx = pw / (n - 1);
      var X = function (i) { return L + i * dx; };
      var Y = function (v) { return T + ph - v / yMax * ph; };
      var svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, 'class': 'eg-svg eg-ac__svg', 'aria-hidden': 'true' }, host);
      var defs = s('defs', {}, svg);
      var glowId = 'egf' + (++uid);
      var fl = s('filter', { id: glowId, x: '-10%', y: '-40%', width: '120%', height: '180%' }, defs);
      s('feGaussianBlur', { stdDeviation: 4.5 }, fl);
      var hid = 'egh' + (++uid);
      var pat = s('pattern', { id: hid, width: 7, height: 7, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
      s('line', { x1: 0, y1: 0, x2: 0, y2: 7, 'class': 'eg-hatch' }, pat);

      // grid
      if (yAxis) text(svg, L - 12, T - 12, unit, 'eg-axis eg-axis--unit', 'end');
      for (var v = 0; v <= yMax + 0.001; v += step) {
        s('line', { x1: L, x2: W - R, y1: Y(v), y2: Y(v), 'class': v ? 'eg-gridline' : 'eg-baseline' }, svg);
        if (yAxis) text(svg, L - 12, Y(v) + 4, v >= 1e5 ? compact(v) : inr(v), 'eg-axis', 'end');
      }
      // forecast zone
      if (now != null && now < n - 1) {
        s('rect', { x: X(now), y: T, width: W - R - X(now), height: ph, fill: 'url(#' + hid + ')', 'class': 'eg-future' }, svg);
        text(svg, W - R - 8, T + 16, 'Forecast', 'eg-axis eg-axis--tag', 'end');
      }

      // bands
      var gBands = s('g', {}, svg);
      var bandEls = [];
      bands.forEach(function (bd, si) {
        if (bd.start < 0) { bandEls.push(null); return; }
        var key = bd.s.key, dashed = !!bd.s.dashed;
        var g = s('g', { 'class': 'eg-band', 'data-key': key }, gBands);
        var top = [], bot = [], minY = T + ph;
        for (var i = bd.start; i <= bd.end; i++) {
          var p = [X(i), Y(bd.up[i])]; top.push(p); bot.push([X(i), Y(bd.lo[i])]);
          if (p[1] < minY) minY = p[1];
        }
        var gid = 'ega' + (++uid);
        var grad = s('linearGradient', { id: gid, x1: 0, y1: minY, x2: 0, y2: T + ph, gradientUnits: 'userSpaceOnUse' }, defs);
        var a0 = dashed ? 0.26 : (stacked ? 0.78 : 0.62), a1 = dashed ? 0.02 : (stacked ? 0.14 : 0.03);
        s('stop', { offset: 0, 'class': 'eg-stop-' + key, 'stop-opacity': a0 }, grad);
        s('stop', { offset: 0.6, 'class': 'eg-stop-' + key, 'stop-opacity': (a0 + a1) / 2.4 }, grad);
        s('stop', { offset: 1, 'class': 'eg-stop-' + key, 'stop-opacity': a1 }, grad);
        if (bd.s.fill !== false) s('path', { d: monoPath(top) + monoBack(bot) + 'Z', fill: 'url(#' + gid + ')', 'class': 'eg-area' }, g);
        // top edge: only where the band has thickness
        var runs = [], cur = null;
        for (i = bd.start; i <= bd.end; i++) {
          var thick = bd.up[i] - bd.lo[i] > 0.5;
          if (thick) { if (!cur) { cur = []; if (i > bd.start) cur.push([X(i - 1), Y(bd.up[i - 1])]); } cur.push([X(i), Y(bd.up[i])]); }
          else if (cur) { cur.push([X(i), Y(bd.up[i])]); runs.push(cur); cur = null; }
        }
        if (cur) runs.push(cur);
        runs.forEach(function (run) {
          var d = monoPath(run);
          if (dashed) { s('path', { d: d, 'class': 'eg-ac-dash s-' + key }, g); return; }
          s('path', { d: d, 'class': 'eg-ac-glow s-' + key, filter: 'url(#' + glowId + ')' }, g);
          s('path', { d: d, 'class': 'eg-ac-line s-' + key }, g);
        });
        bandEls.push(g);
      });

      // demand line + forecast
      if (lineVals) {
        var lp = [], fpz = [];
        for (var i = 0; i < n; i++) {
          if (lineVals[i] == null) continue;
          if (now == null || i <= now) lp.push([X(i), Y(lineVals[i])]);
          if (now != null && i >= now) fpz.push([X(i), Y(lineVals[i])]);
        }
        s('path', { d: monoPath(lp), 'class': 'eg-demand' }, svg);
        if (fpz.length > 1 && (!o.line || o.line.forecast !== false)) s('path', { d: monoPath(fpz), 'class': 'eg-forecast' }, svg);
      }
      // now marker
      if (now != null) {
        var nv = lineVals ? lineVals[now] : (bands.length ? bands[bands.length - 1].up[now] : null);
        if (nv != null) {
          var hl = s('circle', { cx: X(now), cy: Y(nv), r: 13, 'class': 'eg-halo' }, svg);
          if (!lineVals && bands.length) { hl.style.fill = 'var(--c-' + bands[bands.length - 1].s.key + ')'; hl.style.fillOpacity = '.25'; }
          var nd = s('circle', { cx: X(now), cy: Y(nv), r: 5, 'class': 'eg-nowdot' }, svg);
          if (!lineVals && bands.length) nd.style.fill = 'var(--c-' + bands[bands.length - 1].s.key + ')';
        }
      }

      // cursor
      var cg = s('g', { 'class': 'eg-ac-cursorg' }, svg);
      var cl = s('line', { y1: T - 10, y2: T + ph, 'class': 'eg-ac-cursor' }, cg);
      var dots = bands.map(function (bd) { return bd.start < 0 ? null : s('circle', { r: 4.5, 'class': 'eg-ac-dot s-' + bd.s.key }, cg); });
      var ldot = lineVals ? s('circle', { r: 4, 'class': 'eg-ac-dot eg-ac-dot--line' }, cg) : null;

      // html overlay: value pills, tick pills, time pill
      var over = document.createElement('div'); over.className = 'eg-ac__over'; host.appendChild(over);
      var pills = document.createElement('div'); pills.className = 'eg-ac__pills'; over.appendChild(pills);
      var ticks = [];
      var tickIdx = [];
      if (isSlots) {
        var steps = [1, 2, 3, 4, 6, 12], hs = 12;
        for (var k = 0; k < steps.length; k++) if (pw / 24 * steps[k] >= 74) { hs = steps[k]; break; }
        for (var h = 0; h <= 24; h += hs) tickIdx.push({ i: Math.min(n - 1, h * 4), t: pad(h) + ':00' });
      } else {
        var every = Math.max(1, Math.ceil(70 / dx));
        for (var j = 0; j < n; j += every) tickIdx.push({ i: j, t: xLabel(j) });
      }
      tickIdx.forEach(function (tk, ti) {
        var e = document.createElement('span');
        e.className = 'eg-ac__tick' + (ti === 0 ? ' is-first' : '') + (ti === tickIdx.length - 1 && tk.i === n - 1 ? ' is-last' : '');
        e.textContent = tk.t; e.style.left = X(tk.i) + 'px'; over.appendChild(e);
        ticks.push({ el: e, x: X(tk.i) });
      });
      var tp = document.createElement('span'); tp.className = 'eg-ac__time';
      tp.innerHTML = '<i>‹</i><b></b><i>›</i>'; over.appendChild(tp);

      function focusAt(i, my) {
        var keys = [];
        bands.forEach(function (bd, si) { if (bd.start >= 0 && bd.up[i] != null && bd.up[i] - bd.lo[i] > 0.5) keys.push(si); });
        if (!keys.length) return -1;
        if (my != null) {
          if (stacked) {
            for (var q = 0; q < keys.length; q++) { var bd = bands[keys[q]]; if (my >= Y(bd.up[i]) - 2 && my <= Y(bd.lo[i]) + 2) return keys[q]; }
          } else {
            var best = -1, dist = 1e9;
            keys.forEach(function (si) { var dd = Math.abs(Y(bands[si].up[i]) - my); if (dd < dist) { dist = dd; best = si; } });
            if (best >= 0) return best;
          }
        }
        if (o.focus) for (var z = 0; z < keys.length; z++) if (bands[keys[z]].s.key === o.focus) return keys[z];
        if (stacked) return keys[keys.length - 1];
        for (z = keys.length - 1; z >= 0; z--) if (!bands[keys[z]].s.dashed) return keys[z];
        return keys[0];
      }
      function pill(cls, key, label, value, icon) {
        return '<span class="eg-ac__pill ' + cls + '"' + (key ? ' style="--pill: var(--c-' + key + ')"' : '') + '>' +
          (icon ? ICON_SM(icon) : '') + '<small>' + label + '</small>' + value + '</span>';
      }
      function setCursor(i, my, hovering) {
        i = Math.max(0, Math.min(maxI, i));
        api.cursor = i;
        var cx = X(i), fi = focusAt(i, my);
        cl.setAttribute('x1', cx); cl.setAttribute('x2', cx);
        bands.forEach(function (bd, si) {
          var dot = dots[si]; if (!dot) return;
          var ok = bd.up[i] != null && bd.up[i] - bd.lo[i] > 0.5;
          dot.setAttribute('visibility', ok ? 'visible' : 'hidden');
          if (ok) { dot.setAttribute('cx', cx); dot.setAttribute('cy', Y(bd.up[i])); dot.setAttribute('r', si === fi ? 5.5 : 3.5); }
          if (bandEls[si]) bandEls[si].classList.toggle('is-dim', !!hovering && fi >= 0 && si !== fi);
        });
        if (ldot) {
          var lv = lineVals[i];
          ldot.setAttribute('visibility', lv == null ? 'hidden' : 'visible');
          if (lv != null) { ldot.setAttribute('cx', cx); ldot.setAttribute('cy', Y(lv)); }
        }
        // pills
        var html = '';
        if (stacked) {
          if (lineVals && lineVals[i] != null) html += pill('', null, (o.line.label || 'Total'), fmt(lineVals[i]));
          if (fi >= 0) { var fb = bands[fi], src = SOURCES[fb.s.key] || {}; html += pill('eg-ac__pill--solid', fb.s.key, fb.s.label || src.label || fb.s.key, fmt(fb.up[i] - fb.lo[i]), src.icon); }
        } else {
          bands.forEach(function (bd, si) {
            if (bd.start < 0 || bd.up[i] == null) return;
            var cls = bd.s.dashed ? '' : (si === fi ? 'eg-ac__pill--solid' : 'eg-ac__pill--outline');
            html += pill(cls, bd.s.key, bd.s.label || bd.s.key, fmt(bd.up[i] - bd.lo[i]));
          });
        }
        pills.innerHTML = html;
        var pwid = pills.offsetWidth || 200;
        pills.style.left = Math.max(pwid / 2 + 4, Math.min(W - pwid / 2 - 4, cx)) + 'px';
        // time pill + ticks
        tp.querySelector('b').textContent = xLabel(i);
        var twid = tp.offsetWidth || 90;
        tp.style.left = Math.max(twid / 2, Math.min(W - twid / 2, cx)) + 'px';
        ticks.forEach(function (t) { t.el.classList.toggle('is-hidden', Math.abs(t.x - cx) < twid / 2 + 34); });
        if (o.onHover) {
          var row = { index: i, label: xLabel(i), focus: fi >= 0 ? bands[fi].s.key : null, line: lineVals ? lineVals[i] : null };
          bands.forEach(function (bd) { row[bd.s.key] = bd.up[i] == null ? null : bd.up[i] - bd.lo[i]; });
          o.onHover(row);
        }
      }
      function fromEvent(ev) {
        var rect = svg.getBoundingClientRect(), sc = W / rect.width;
        return { i: Math.round(((ev.clientX - rect.left) * sc - L) / dx), y: (ev.clientY - rect.top) * sc };
      }
      svg.addEventListener('pointermove', function (ev) { var p = fromEvent(ev); setCursor(p.i, p.y, true); });
      svg.addEventListener('pointerleave', function () { setCursor(rest, null, false); });
      api._set = setCursor;
      setCursor(api.cursor, null, false);
    });
    host.addEventListener('keydown', function (ev) {
      var k = ev.key, st = ev.shiftKey ? 4 : 1, i = api.cursor;
      if (k === 'ArrowLeft') i -= st; else if (k === 'ArrowRight') i += st; else if (k === 'Home') i = 0; else if (k === 'End') i = maxI; else return;
      ev.preventDefault(); api._set(i, null, true);
    });
    host.addEventListener('blur', function () { api._set(rest, null, false); });
    api.redraw = r.redraw;
    api.setCursor = function (i) { api._set(i, null, true); };
    api.palette = function (name) { palette(host, name); };
    return api;
  }

  /* ---------- energy supply: stacked sources under the demand line ---------- */
  function supplyChart(host, opts) {
    opts = opts || {};
    var demand = opts.demand || SAMPLE.demand;
    var now = opts.now != null ? opts.now : SAMPLE.now;
    var layers = opts.layers || [
      { key: 'hydro', values: SAMPLE.hydro }, { key: 'wind', values: SAMPLE.wind }, { key: 'solar', values: SAMPLE.solar },
      { key: 'iex', values: SAMPLE.iex }, { key: 'grid' }
    ];
    var base = demand.map(function () { return 0; });
    var series = layers.map(function (ly) {
      var vals = demand.map(function (d, i) {
        if (i > now) return null;
        var room = Math.max(0, d - base[i]);
        var v = ly.values ? Math.max(0, Math.min(ly.values[i] || 0, room)) : room;
        base[i] += v;
        return v;
      });
      return { key: ly.key, label: ly.label || (SOURCES[ly.key] || {}).label || ly.key, values: vals };
    });
    if (opts.palette) palette(host, opts.palette);
    return areaChart(host, {
      stacked: true, series: series, line: { label: 'Demand', values: demand }, now: now, cursorMax: now,
      height: opts.height || 360, yMax: opts.yMax, unit: 'kW', slots: true,
      label: opts.label || 'Energy supply by source, 15-minute blocks. Use arrow keys to move between blocks.',
      onHover: opts.onHover && function (row) {
        var out = { slot: row.index, block: row.index + 1, time: slotTime(row.index + 1), demand: demand[row.index], focus: row.focus };
        series.forEach(function (sr) { out[sr.key] = row[sr.key] || 0; });
        opts.onHover(out);
      }
    });
  }

  /* ---------- trend chart: overlaid series, e.g. actual vs forecast ---------- */
  function trendChart(host, opts) {
    opts = opts || {};
    var series = opts.series || [
      { key: 'demand', label: 'Forecast', values: SAMPLE.forecast, dashed: true },
      { key: 'iex', label: 'Actual', values: SAMPLE.demand.map(function (v, i) { return i <= SAMPLE.now ? v : null; }) }
    ];
    if (opts.palette) palette(host, opts.palette);
    return areaChart(host, {
      stacked: false, series: series, now: opts.now != null ? opts.now : (opts.series ? null : SAMPLE.now),
      cursor: opts.cursor != null ? opts.cursor : (opts.series ? null : 44), height: opts.height || 340, yMax: opts.yMax,
      unit: opts.unit || 'kW', format: opts.format, xLabel: opts.xLabel, slots: opts.slots, yAxis: opts.yAxis,
      label: opts.label || 'Actual demand against forecast', onHover: opts.onHover
    });
  }

  /* ---------- savings trajectory (bars + line) ---------- */
  function savingsChart(host, opts) {
    opts = opts || {};
    var labels = opts.labels || SAMPLE.days, bars = opts.savings || SAMPLE.savings, line = opts.volume || SAMPLE.volume;
    var H = opts.height || 300;
    return responsive(host, function (W) {
      var L = 56, R = 52, T = 28, B = 30, n = bars.length;
      var pw = W - L - R, ph = H - T - B, slot = pw / n, bw = Math.min(34, slot * 0.56);
      var bStep = niceStep(Math.max.apply(null, bars) / 4), lStep = niceStep(Math.max.apply(null, line) / 4);
      var ticks = Math.max(Math.ceil(Math.max.apply(null, bars) / bStep), Math.ceil(Math.max.apply(null, line) / lStep));
      var bMax = bStep * ticks, lMax = lStep * ticks;
      var Yb = function (v) { return T + ph - v / bMax * ph; };
      var Yl = function (v) { return T + ph - v / lMax * ph; };
      var svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, 'class': 'eg-svg', role: 'img', 'aria-label': 'Daily net savings and cleared volume' }, host);
      var defs = s('defs', {}, svg);
      var g = gradient(defs, 'iex', 0.95, 0.22);
      var gf = 'egf' + (++uid), gfl = s('filter', { id: gf, x: '-10%', y: '-40%', width: '120%', height: '180%' }, defs);
      s('feGaussianBlur', { stdDeviation: 4 }, gfl);
      text(svg, L - 10, 12, '₹', 'eg-axis eg-axis--unit', 'end');
      text(svg, W - R + 10, 12, 'kWh', 'eg-axis eg-axis--unit', 'start');
      for (var k = 0; k <= ticks; k++) {
        var v = bStep * k, y = Yb(v);
        s('line', { x1: L, x2: W - R, y1: y, y2: y, 'class': k ? 'eg-gridline' : 'eg-baseline' }, svg);
        text(svg, L - 10, y + 4, compact(v), 'eg-axis', 'end');
        text(svg, W - R + 10, y + 4, compact(lStep * k), 'eg-axis', 'start');
      }
      var avg = bars.reduce(function (a, b) { return a + b; }, 0) / n;
      var maxI = bars.indexOf(Math.max.apply(null, bars));
      bars.forEach(function (v, i) {
        var cx = L + slot * (i + 0.5), x = cx - bw / 2, y = Yb(v), h = T + ph - y, rr = Math.min(8, bw / 2, h);
        var d = 'M' + x + ',' + (T + ph) + 'V' + (y + rr) + 'Q' + x + ',' + y + ' ' + (x + rr) + ',' + y + 'H' + (x + bw - rr) + 'Q' + (x + bw) + ',' + y + ' ' + (x + bw) + ',' + (y + rr) + 'V' + (T + ph) + 'Z';
        var b = s('path', { d: d, fill: g, 'class': 'eg-bar' + (i === maxI ? ' is-max' : '') }, svg);
        var tt = s('title', {}, b); tt.textContent = labels[i] + ': ₹' + inr(v, 2) + ' saved, ' + inr(line[i]) + ' kWh';
        text(svg, cx, H - 8, labels[i].replace('Oct ', ''), 'eg-axis', 'middle');
        if (i === maxI) text(svg, cx, y - 8, '₹' + compact(v), 'eg-axis eg-axis--strong', 'middle');
      });
      var ay = Yb(avg);
      s('line', { x1: L, x2: W - R, y1: ay, y2: ay, 'class': 'eg-avgline' }, svg);
      text(svg, L + 6, ay - 6, 'Avg ₹' + inr(avg) + ' / day', 'eg-axis eg-axis--tag', 'start');
      var pts = line.map(function (v, i) { return [L + slot * (i + 0.5), Yl(v)]; });
      s('path', { d: monoPath(pts), 'class': 'eg-ac-glow s-grid', filter: 'url(#' + gf + ')' }, svg);
      s('path', { d: monoPath(pts), 'class': 'eg-line s-grid', 'stroke-width': 2, fill: 'none' }, svg);
      pts.forEach(function (p) { s('circle', { cx: p[0], cy: p[1], r: 3.2, 'class': 'eg-linedot s-grid' }, svg); });
      var tg = s('g', { 'class': 'eg-tag' }, svg);
      var tr = s('rect', { rx: 9, 'class': 'eg-tag__bg' }, tg);
      var tt2 = text(tg, W - R - 12, ay + 4, 'Avg \u20b9' + inr(avg) + ' / day', 'eg-axis eg-axis--strong', 'end');
      var bb = tt2.getBBox ? tt2.getBBox() : { x: W - R - 140, y: ay - 8, width: 128, height: 14 };
      tr.setAttribute('x', bb.x - 9); tr.setAttribute('y', bb.y - 4); tr.setAttribute('width', bb.width + 18); tr.setAttribute('height', bb.height + 8);
    });
  }

  /* ---------- 96-slot heatmap ---------- */
  function heatmap(host, opts) {
    opts = opts || {};
    var rows = opts.rows || SAMPLE.heat;
    var key = opts.series || 'iex';
    return responsive(host, function (W) {
      var L = 56, R = 4, T = 6, B = 26, rh = opts.rowHeight || 24, gap = 4, n = rows[0].values.length;
      var H = T + rows.length * (rh + gap) - gap + B;
      var cw = (W - L - R) / n;
      var max = opts.max || Math.max.apply(null, rows.map(function (r) { return Math.max.apply(null, r.values); }));
      var svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, 'class': 'eg-svg', role: 'img', 'aria-label': 'Cleared kW per 15-minute block' }, host);
      rows.forEach(function (row, ri) {
        var y = T + ri * (rh + gap);
        text(svg, 0, y + rh / 2 + 4, row.label, 'eg-axis', 'start');
        row.values.forEach(function (v, i) {
          var c = s('rect', { x: L + i * cw + 0.6, y: y, width: Math.max(1, cw - 1.2), height: rh, rx: Math.min(3, cw / 3), 'class': v > 0 ? 'eg-cell f-' + key : 'eg-cell is-empty' }, svg);
          if (v > 0) c.setAttribute('fill-opacity', (0.18 + 0.82 * v / max).toFixed(2));
          var t = s('title', {}, c); t.textContent = row.label + ' · Block ' + (i + 1) + ' (' + slotTime(i) + ') · ' + inr(v) + ' kW';
        });
      });
      for (var h = 0; h <= 24; h += 3) {
        text(svg, L + h * 4 * cw, H - 6, pad(h % 24 === 0 && h ? 24 : h) + ':00', 'eg-axis', h === 0 ? 'start' : h === 24 ? 'end' : 'middle');
      }
    });
  }

  /* ---------- source mix ring ---------- */
  function ring(host, opts) {
    opts = opts || {};
    var parts = opts.parts || [{ key: 'grid', value: 33.18 }, { key: 'iex', value: 17.66 }, { key: 'solar', value: 0 }];
    var size = opts.size || 168, sw = opts.stroke || 14;
    host.innerHTML = '';
    var r = (size - sw) / 2, c = size / 2, C = 2 * Math.PI * r;
    var total = parts.reduce(function (a, p) { return a + p.value; }, 0) || 1;
    var svg = s('svg', { viewBox: '0 0 ' + size + ' ' + size, width: size, height: size, 'class': 'eg-svg eg-ring', role: 'img', 'aria-label': opts.label || 'Source mix' }, host);
    s('circle', { cx: c, cy: c, r: r, 'class': 'eg-ring__track', 'stroke-width': sw, fill: 'none' }, svg);
    var gapLen = sw * 0.9, off = 0;
    parts.forEach(function (p) {
      if (!p.value) return;
      var len = Math.max(0, p.value / total * C - gapLen);
      s('circle', { cx: c, cy: c, r: r, fill: 'none', 'stroke-width': sw, 'stroke-linecap': 'round', 'class': 'eg-ring__arc s-' + p.key,
        'stroke-dasharray': len + ' ' + (C - len), 'stroke-dashoffset': -off - gapLen / 2, transform: 'rotate(-90 ' + c + ' ' + c + ')' }, svg);
      off += p.value / total * C;
    });
  }

  /* ---------- mini bars (thumbnails) ---------- */
  function miniBars(host, values, key) {
    key = key || host.getAttribute('data-series') || 'iex';
    var W = host.clientWidth || 60, H = host.clientHeight || 36, n = values.length, bw = W / n;
    var max = Math.max.apply(null, values) || 1;
    host.innerHTML = '';
    var svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, 'class': 'eg-svg', 'aria-hidden': 'true' }, host);
    values.forEach(function (v, i) {
      var h = Math.max(1.5, v / max * H);
      s('rect', { x: i * bw + bw * 0.15, y: H - h, width: bw * 0.7, height: h, rx: Math.min(1.5, bw / 3), 'class': 'f-' + key }, svg);
    });
  }

  /* ---------- AI real talk: voice bar ---------- */
  function voiceBar(el, opts) {
    opts = opts || {};
    var waveBox = el.querySelector('.eg-voice__wave');
    var cv = waveBox && waveBox.querySelector('canvas');
    if (waveBox && !cv) { cv = document.createElement('canvas'); waveBox.appendChild(cv); }
    var textEl = el.querySelector('.eg-voice__text');
    var timerEl = el.querySelector('.eg-voice__timer');
    var mic = el.querySelector('[data-voice="mic"]');
    var ctx = cv ? cv.getContext('2d') : null;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var state = el.getAttribute('data-state') || 'idle';
    var since = performance.now(), analyser = null, freq = null, raf = 0, amp = 0, timers = [];
    var placeholder = opts.placeholder || (textEl ? textEl.textContent : 'Ask anything');
    var api = {};

    function level(t, i, nb) {
      var x = i / Math.max(1, nb - 1);
      var env = Math.pow(Math.sin(Math.PI * (0.06 + x * 0.88)), 0.7);
      var syll = 0.55 + 0.45 * Math.sin(t * 0.0047) * Math.sin(t * 0.0021 + 1.3);
      var v = Math.abs(0.5 * Math.sin(t * 0.0062 + i * 0.52) + 0.32 * Math.sin(t * 0.0137 - i * 0.91) + 0.22 * Math.sin(t * 0.0029 + i * 1.73));
      var a = state === 'listening' ? 1 : state === 'speaking' ? 0.8 : 0;
      return Math.min(1, v * env * syll * a * 1.25);
    }
    function draw(t) {
      if (!ctx) return;
      var dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
      if (!w || !h) return;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = getComputedStyle(cv).color;
      var bw = 3, gap = 3.2, nb = Math.floor((w + gap) / (bw + gap)), off = (w - (nb * (bw + gap) - gap)) / 2, sum = 0;
      if (analyser) analyser.getByteFrequencyData(freq);
      for (var i = 0; i < nb; i++) {
        var lv;
        if (analyser && state === 'listening') { var k = Math.floor(i / nb * freq.length * 0.6); lv = freq[k] / 255; }
        else lv = level(t, i, nb);
        sum += lv;
        var bh = Math.max(bw, lv * h * 0.92), x = off + i * (bw + gap), y = (h - bh) / 2;
        ctx.globalAlpha = state === 'thinking' ? 0.25 + 0.75 * Math.max(0, Math.sin(t * 0.008 - i * 0.35)) : (state === 'idle' ? 0.45 : 1);
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x, y, bw, bh, bw / 2); else ctx.rect(x, y, bw, bh);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      var target = nb ? sum / nb * 2.2 : 0;
      amp += (Math.min(1, target) - amp) * 0.25;
      el.style.setProperty('--amp', amp.toFixed(3));
    }
    function tick(t) {
      draw(t);
      if (timerEl && state === 'listening') {
        var sec = Math.floor((t - since) / 1000);
        timerEl.textContent = Math.floor(sec / 60) + ':' + pad(sec % 60);
      }
      if (!reduce) raf = requestAnimationFrame(tick);
    }
    function setState(s, txt) {
      state = s; since = performance.now();
      el.setAttribute('data-state', s);
      if (mic) mic.setAttribute('aria-label', s === 'idle' ? 'Start talking' : s === 'listening' ? 'Stop and send' : 'Stop');
      if (mic) mic.setAttribute('aria-pressed', s === 'listening' ? 'true' : 'false');
      if (timerEl && s === 'listening') timerEl.textContent = '0:00';
      if (txt != null) setText(txt); else if (s === 'idle') setText(placeholder);
      if (reduce) draw(performance.now());
    }
    function setText(txt) {
      if (!textEl) return;
      textEl.textContent = txt.length > 120 ? '…' + txt.slice(-118) : txt;
    }
    function clearTimers() { timers.forEach(clearTimeout); timers = []; }
    function type(str, ms, done) {
      var words = str.split(' '), i = 0, step = ms / words.length;
      (function next() {
        i++; setText(words.slice(0, i).join(' '));
        if (i < words.length) timers.push(setTimeout(next, step)); else if (done) timers.push(setTimeout(done, 450));
      })();
    }
    function demo() {
      clearTimers();
      var q = opts.question || 'Why did demand dip at eleven today?';
      var a = opts.answer || 'Demand fell to 2,120 kW in blocks 44 and 45 during the lunch shutdown. You had 2,716 kW cleared on IEX, so about 596 kW was surplus for 30 minutes. Trim those two blocks in tomorrow’s bid.';
      setState('listening', '');
      type(q, 2200, function () {
        setState('thinking', 'Reading blocks 44–45…');
        timers.push(setTimeout(function () {
          setState('speaking', '');
          type(a, 5200, function () { timers.push(setTimeout(function () { setState('idle'); }, 1600)); });
        }, 1300));
      });
    }
    function startLive() {
      if (!opts.live || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
        var AC = window.AudioContext || window.webkitAudioContext, ac = new AC();
        analyser = ac.createAnalyser(); analyser.fftSize = 256; freq = new Uint8Array(analyser.frequencyBinCount);
        ac.createMediaStreamSource(stream).connect(analyser);
        api.stream = stream;
      }).catch(function () { analyser = null; });
    }
    if (mic) mic.addEventListener('click', function () {
      if (opts.onMic) { opts.onMic(state, api); return; }
      if (state === 'idle') { if (opts.demo !== false) demo(); else { startLive(); setState('listening', ''); } }
      else { clearTimers(); setState('idle'); }
    });
    var kb = el.querySelector('[data-voice="keyboard"]');
    if (kb && opts.onKeyboard) kb.addEventListener('click', function () { opts.onKeyboard(api); });
    if (ctx) { if (reduce) draw(performance.now()); else raf = requestAnimationFrame(tick); }
    if (window.ResizeObserver && cv) new ResizeObserver(function () { if (reduce) draw(performance.now()); }).observe(cv);
    api.setState = setState; api.setText = setText; api.demo = demo;
    api.state = function () { return state; };
    api.stop = function () { clearTimers(); cancelAnimationFrame(raf); };
    setState(state, state === 'idle' ? null : (textEl ? textEl.textContent : ''));
    return api;
  }

  /* ---------- mount ---------- */
  function mount(root) {
    root = root || document;
    Array.prototype.forEach.call(root.querySelectorAll('[data-icon]'), function (el) {
      if (el.__egIcon) return; el.__egIcon = true;
      el.insertAdjacentHTML('afterbegin', icon(el.getAttribute('data-icon'), +el.getAttribute('data-size') || 18));
    });
    Array.prototype.forEach.call(root.querySelectorAll('.eg-folder__front'), folder);
    Array.prototype.forEach.call(root.querySelectorAll('.eg-voice[data-auto]'), function (v) { if (!v.__egVoice) v.__egVoice = voiceBar(v, { demo: v.getAttribute('data-auto') !== 'static' }); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { mount(); });
  else mount();

  window.ErgOS = Object.assign(window.ErgOS || {}, {
    icon: icon, icons: Object.keys(ICONS), mount: mount, folder: folder,
    sparkline: sparkline, supplyChart: supplyChart, savingsChart: savingsChart,
    heatmap: heatmap, ring: ring, miniBars: miniBars,
    areaChart: areaChart, trendChart: trendChart, voiceBar: voiceBar, palette: palette, palettes: PALETTES, sources: SOURCES,
    inr: inr, compact: compact, slotTime: slotTime, sample: SAMPLE
  });
})();
