#!/usr/bin/env python3
"""
TimingStrategy 打分触发点可视化脚本（path A：诊断工具）

在 K 线上标注三类触发点 + 分数曲线副图，肉眼验证"每个底/顶分数对应的实际价格位置"，
是排查"打分是否偏早/偏晚"的直接手段。自包含单 HTML（原生 canvas，不引入新依赖）。

三层标注：
  1. 底部触发点（绿三角）+ 分数气泡（bottom_enter）
  2. 顶部触发点（红三角）+ 分数气泡（top_exit / top_no_pos 用不同标记）
  3. 分数曲线副图：bottom_score / top_score 双线 + min_score 阈值横线

用法:
    python3 scripts/plot_timing_signals.py [symbol] [min_score] [out_path]
示例:
    python3 scripts/plot_timing_signals.py                 # 合成行情
    python3 scripts/plot_timing_signals.py 600519 3        # 茅台真实行情, min_score=3
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_bars(symbol=None):
    """与 timing_strategy_backtest 一致：真实行情优先，否则合成"""
    if symbol:
        from datetime import date
        from data.akshare_source import AkshareDataSource
        src = AkshareDataSource()
        bars = src.fetch_daily_sorted(symbol, date(2023, 1, 1), date(2025, 1, 1))
        if bars and len(bars) > 120:
            return bars, f"真实行情 {symbol}"
    import numpy as np
    from datetime import datetime, timedelta
    from data.bar import Bar
    n = 400
    rng = np.random.default_rng(7)
    t = np.arange(n)
    trend = 0.0006 * t
    cycle = 0.09 * np.sin(2 * np.pi * 3 * t / n)
    cycle2 = 0.035 * np.sin(2 * np.pi * 13 * t / n)
    noise = rng.normal(0, 0.018, n).cumsum() * 0.15
    close = 50 * np.exp(trend + cycle + cycle2 + noise)
    prev = close[0]
    bars = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        hi = max(prev, close[i]) * (1 + rng.uniform(0, 0.005))
        lo = min(prev, close[i]) * (1 - rng.uniform(0, 0.005))
        bars.append(Bar(symbol or "SYN", base + timedelta(days=i), prev, hi, lo,
                        close[i], 1e6 * (1 + abs(rng.normal(0, 0.3)))))
        prev = close[i]
    return bars, f"合成行情 {symbol or 'SYN'}"


def build_engine(strategy, initial=500_000.0):
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer
    portfolio = Portfolio(initial_cash=initial)
    rc = RiskConfig()
    rc.max_single_trade_amount = 1_000_000.0
    rc.max_single_trade_ratio = 0.4
    rc.max_position_ratio = 0.8
    return BacktestEngine(
        strategy=strategy, portfolio=portfolio,
        risk_manager=RiskManager(rc),
        position_sizer=PercentSizer(percent=0.3, min_amount=1000.0),
        symbol=strategy.name, lookback=500,
    )


def render_html(bars, events, min_score, symbol, title):
    """生成自包含 HTML（原生 canvas）"""
    # bars 序列化
    bar_rows = [
        {"t": str(b.datetime), "o": float(b.open), "h": float(b.high),
         "l": float(b.low), "c": float(b.close), "v": float(b.volume or 0)}
        for b in bars
    ]
    # 事件按 index 对齐（标注第1层/第2层 + 用于索引分数曲线）
    ev_rows = [
        {"i": e["index"], "type": e["trigger_type"],
         "p": e["price_at_signal"], "bs": e["bottom_score"],
         "ts": e["top_score"], "f5": e.get("forward_return_5"),
         "f10": e.get("forward_return_10"), "f20": e.get("forward_return_20")}
        for e in events
    ]
    data = json.dumps({"bars": bar_rows, "ev": ev_rows, "min": int(min_score)},
                      ensure_ascii=False, default=str)

    # 事件明细行（HTML 表格）
    def _fmt(v):
        if v is None:
            return '<td style="color:#666">—</td>'
        cls = "fmt-good" if v > 0 else "fmt-bad"
        return f'<td class="{cls}">{v*100:+.1f}%</td>'
    tname = {"bottom_enter": "底部做多", "top_exit": "顶部了结",
             "top_no_pos": "顶部空仓"}
    row_html = "".join(
        f"<tr><td>{i+1}</td><td>{e['datetime']}</td><td>{tname.get(e['trigger_type'], e['trigger_type'])}</td>"
        f"<td>{e['price_at_signal']:.2f}</td><td>{e['bottom_score']:.1f}</td><td>{e['top_score']:.1f}</td>"
        f"{_fmt(e.get('forward_return_5'))}{_fmt(e.get('forward_return_10'))}{_fmt(e.get('forward_return_20'))}</tr>"
        for i, e in enumerate(events)
    ) or "<tr><td colspan='9' style='color:#888;text-align:center'>无触发事件</td></tr>"

    # 采用普通字符串模板 + 占位符注入（避免 f-string 双重转义 JS 花括号）
    tpl = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>__TITLE__</title>
<style>
body{font-family:-apple-system,'Segoe UI','PingFang SC',sans-serif;margin:0;background:#0f1117;color:#e6e6e6;}
header{padding:16px 24px;border-bottom:1px solid #222;}
h1{font-size:20px;margin:0;} .sub{color:#8a8f98;font-size:13px;margin-top:4px;}
.wrap{padding:20px 24px;display:grid;gap:16px;}
.panel{background:#171a22;border:1px solid #252a36;border-radius:8px;padding:14px;}
.panel h2{font-size:14px;color:#cfd3dc;margin:0 0 10px;}
#kline{height:440px;} #score{height:240px;}
canvas{width:100%;display:block;background:#0f1117;}
.legend{font-size:12px;color:#8a8f98;margin-top:8px;}
.dot{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 10px;vertical-align:middle;}
table{border-collapse:collapse;width:100%;font-size:12px;}
th,td{border:1px solid #252a36;padding:5px 8px;text-align:left;}
th{background:#1c2029;color:#cfd3dc;} td{color:#b8bcc6;}
.scroll{max-height:320px;overflow:auto;}
.fmt-good{color:#2ecc71;font-weight:600;}
.fmt-bad{color:#e74c3c;font-weight:600;}
</style></head><body>
<header><h1>__TITLE__</h1>
<div class="sub">__SYMBOL__ · __NBARS__ bars · __N_EV__ trigger events · min_score=__MIN__ · 触发点为事后标注(含 forward_return)</div>
</header>
<div class="wrap">
  <div class="panel"><h2>K线 + 打分触发点（绿=底部做多 / 红=顶部了结 / 橙=顶部空仓观望）</h2>
    <div id="kline"></div>
    <div class="legend">
      <span class="dot" style="background:#2ecc71"></span>底部触发(绿三角)
      <span class="dot" style="background:#e74c3c"></span>顶部了结(红三角)
      <span class="dot" style="background:#f39c12"></span>顶部空仓观望(橙三角)
      <span>气泡内数字 = 对应方向分数 / 等级</span>
    </div></div>
  <div class="panel"><h2>分数曲线（副图）</h2><div id="score"></div>
    <div class="legend"><span class="dot" style="background:#3ea6ff"></span>bottom_score
      <span class="dot" style="background:#f1c40f"></span>top_score
      <span class="dot" style="background:#e74c3c"></span>触发阈值 min_score
    </div></div>
  <div class="panel"><h2>触发事件明细（含事后 forward_return）</h2>
    <div class="scroll"><table>
      <tr><th>#</th><th>时间</th><th>类型</th><th>触发价</th><th>底分</th><th>顶分</th>
          <th>fwd5</th><th>fwd10</th><th>fwd20</th></tr>
      __ROW__
    </table></div></div>
</div>
<script>
const D = __DATA__;
const bars = D.bars, ev = D.ev, MIN = D.min;
// 事件按 index 索引
const K = {}; ev.forEach(e=>{K[e.i] = e;});
// ---- K线 + 触发点 ----
function drawKline(){
  const cv = document.getElementById('kline'), ctx = cv.getContext('2d');
  const W = cv.width = cv.offsetWidth, H = cv.height = cv.offsetHeight;
  const pad = {t:26, b:18, l:8, r:8};
  const all = [].concat(...bars.map(b=>[b.h,b.l,b.c,b.o]));
  const lo = Math.min(...all), hi = Math.max(...all);
  function sx(i){return pad.l + (bars.length>1 ? i*(W-pad.l-pad.r)/(bars.length-1) : pad.l)}
  function sy(v){return pad.t + (hi-v)*(H-pad.t-pad.b)/(hi-lo||1)}
  // 成交量底
  const vmax = Math.max(1, ...bars.map(b=>b.v));
  bars.forEach((b,i)=>{ const x=sx(i), vh=26*(b.v||0)/vmax;
    ctx.fillStyle = b.c>=b.o ? '#e74c3c22' : '#2ecc7122';
    ctx.fillRect(x-1.5, H-pad.b-vh, 3, vh);});
  // K线
  bars.forEach((b,i)=>{ const x=sx(i), up=b.c>=b.o;
    ctx.strokeStyle = ctx.fillStyle = up ? '#e74c3c' : '#2ecc71';
    ctx.beginPath(); ctx.moveTo(x,sy(b.h)); ctx.lineTo(x,sy(b.l)); ctx.stroke();
    const yo=sy(b.o), yc=sy(b.c);
    ctx.fillRect(x-3, Math.min(yo,yc), 6, Math.max(2, Math.abs(yc-yo)));});
  // 分数曲线(参考投影，非精确价格映射)
  ctx.strokeStyle = '#3ea6ff88'; ctx.lineWidth = 1;
  ctx.setLineDash([2,3]); ctx.beginPath();
  bars.forEach((b,i)=>{ const e=K[i]; if(!e)return; const x=sx(i); const v=e.bs;
    const y=sy(scoresToPrice(v,b));
    i?ctx.lineTo(x,y):ctx.moveTo(x,y);}); ctx.stroke();
  ctx.setLineDash([]);
  // 触发点标注
  ev.forEach(e=>{ const i=e.i, x=sx(i); if(i<0||i>=bars.length)return;
    const b=bars[i], y=sy(b.l);
    let color='#2ecc71', label=e.bs.toFixed(1);
    let dy = -6;
    if(e.type!=='bottom_enter'){ color = (e.type==='top_exit') ? '#e74c3c' : '#f39c12';
      dy = 6; label = e.ts.toFixed(1);
    }
    ctx.fillStyle = color;
    ctx.beginPath();
    if(e.type==='bottom_enter'){ ctx.moveTo(x, y-8); ctx.lineTo(x-6, y+2); ctx.lineTo(x+6, y+2); }
    else { ctx.moveTo(x, y+8); ctx.lineTo(x-6, y-2); ctx.lineTo(x+6, y-2); }
    ctx.fill();
    ctx.font = '9px sans-serif'; ctx.fillStyle = color;
    const bx = x + 4, by = y + dy + (e.type==='bottom_enter' ? -12 : 2);
    ctx.fillText(label, bx, by);
  });
  ctx.strokeStyle='#333'; ctx.strokeRect(0,0,W,H);
  ctx.fillStyle='#8a8f98'; ctx.font='10px sans-serif';
  const step = Math.max(1, Math.floor(bars.length/10));
  for(let i=0;i<bars.length;i+=step){ctx.fillText(String(bars[i].t).slice(5,10), sx(i)-12, H-2);}
}
// 辅助：把 score 映射到价格区间（可视化投影，非精确）
function scoresToPrice(v,b){ return b.l - (b.h-b.l)*0.05 * v; }
// ---- 分数副图 ----
function drawScore(){
  const cv = document.getElementById('score'), ctx = cv.getContext('2d');
  const W = cv.width = cv.offsetWidth, H = cv.height = cv.offsetHeight;
  const pad = {t:10,b:20,l:8,r:30};
  const x0=pad.l, x1=W-pad.r, y0=pad.t, y1=H-pad.b;
  ctx.clearRect(0,0,W,H); ctx.strokeStyle='#333'; ctx.strokeRect(0,0,W,H);
  // 构造连续序列：非触发 bar = 上一值或0
  const bsL=[], tsL=[];
  let curB=0, curT=0;
  for(let i=0;i<D.bars.length;i++){ const e=K[i];
    if(e){ curB=e.bs; curT=e.ts; }
    bsL.push(curB); tsL.push(curT);
  }
  function sy(v){return y0 + (10-v)*(y1-y0)/10}
  function sx(i){return x0 + (bars.length>1? i*(x1-x0)/(bars.length-1):x0)}
  // 阈值线
  ctx.strokeStyle='#e74c3c'; ctx.setLineDash([4,4]); ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(x0,sy(MIN)); ctx.lineTo(x1,sy(MIN)); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle='#e74c3c'; ctx.font='10px sans-serif'; ctx.fillText('min='+MIN, x1-40, sy(MIN)-3);
  // bottom(top) 曲线
  [['#3ea6ff',bsL],['#f1c40f',tsL]].forEach(([c,arr])=>{ ctx.strokeStyle=c; ctx.lineWidth=1.5; ctx.beginPath();
    arr.forEach((v,i)=>{ i?ctx.lineTo(sx(i),sy(v)):ctx.moveTo(sx(i),sy(v)); }); ctx.stroke();
  });
  // y 刻度 0-10
  ctx.fillStyle='#8a8f98'; ctx.font='10px sans-serif';
  for(let s=0;s<=10;s+=2){ctx.fillText(String(s), x1-22, sy(s)+3);}
  ctx.fillStyle='#8a8f98'; const st=Math.max(1,Math.floor(bars.length/10));
  for(let i=0;i<bars.length;i+=st){ctx.fillText(String(bars[i].t).slice(5,10), sx(i)-12, H-4);}
}
drawKline(); drawScore();
</script></body></html>"""

    subs = {
        "__TITLE__": title,
        "__SYMBOL__": symbol,
        "__NBARS__": str(len(bars)),
        "__N_EV__": str(len(ev_rows)),
        "__MIN__": str(int(min_score)),
        "__DATA__": data,
        "__ROW__": row_html,
    }
    for k, v in subs.items():
        tpl = tpl.replace(k, v)
    return tpl


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else None
    min_score = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    out_path = sys.argv[3] if len(sys.argv) > 3 else None

    from strategy.timing_strategy import TimingStrategy
    bars, source = load_bars(symbol)
    strategy = TimingStrategy(min_score=min_score, direction_mode="both", lookback=60)
    engine = build_engine(strategy)
    engine.run(bars)
    events = strategy.get_trigger_events(annotate=True)
    if not out_path:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                f"timing_signals_{symbol or 'syn'}_{min_score}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render_html(bars, events, min_score, symbol or "SYN",
                            f"TimingStrategy 打分触发点标注 · {source}"))
    print(f"已生成: {out_path}")
    print(f"触发事件数: {len(events)}")
    for e in events[:10]:
        f5 = e.get("forward_return_5")
        print(f"  [{e['datetime']}] {e['trigger_type']:>12} @{e['price_at_signal']:.2f} "
              f"bottom={e['bottom_score']} top={e['top_score']} "
              f"fwd5={round(f5*100,1) if f5 is not None else None}%")


if __name__ == "__main__":
    main()
