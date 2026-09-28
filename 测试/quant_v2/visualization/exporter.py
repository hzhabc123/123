"""
Quant V2 可视化导出器

输出：
- to_json / to_csv：结构化记录导出（供 Replay/Dashboard/外部工具）
- render_html：自包含静态 HTML 报告（K线+成交量+均线+买卖点+净值+回撤+交易表）

设计原则：
- 图上指标 = 策略实际用的指标（由 recorder 在 bar 处附带上报，不事后重算）；
- 买卖点五类（Signal/Order/Trade/Stop/Reject）用不同形状/颜色严格区分；
- 图上成交点 = Trade 记录（T+1 撮合），与信号价拉开（信号日 vs 成交日），
  避免用户误以为"信号=成交"。
"""

import json
import csv
from datetime import datetime, date
from typing import Optional


def _fmt_dt(dt) -> str:
    """统一时间字符串，保证序列化稳定"""
    if dt is None:
        return ""
    if isinstance(dt, (datetime, date)):
        return dt.strftime("%Y-%m-%d" if isinstance(dt, date) and not isinstance(dt, datetime) else "%Y-%m-%d %H:%M")
    return str(dt)


class VisualExporter:
    """可视化导出器：解析 Recorder 记录并生成 JSON / CSV / HTML"""

    def __init__(self, recorder, analyzer=None):
        self.rec = recorder
        self.analyzer = analyzer

    # ---------------- 结构化导出 ----------------

    def to_dict(self) -> dict:
        return {
            "bars": self.rec.get("bar"),
            "indicators": self.rec.get("indicator"),
            "signals": self.rec.get("signal"),
            "orders": self.rec.get("order"),
            "trades": self.rec.get("trade"),
            "positions": self.rec.get("position"),
            "equity": self.rec.get("equity"),
            "risk_rejects": self.rec.get("risk_reject"),
            "stops": self.rec.get("stop"),
        }

    def to_json(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, default=str, indent=2)

    def export_equity_csv(self, filepath: str):
        # equity 表含两类记录（净值点含 equity；回撤点含 drawdown），按字段并集导出
        rows = [r for r in self.rec.get("equity") if r is not None]
        if not rows:
            return
        keys = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow({k: _fmt_dt(v) if isinstance(v, (datetime, date)) else v
                            for k, v in r.items()})

    # ---------------- HTML 报告 ----------------

    def _marker_layer(self, bars, rec_type, field_map, color, shape, label):
        """把某类记录对齐到时间轴，生成 scatter 数据"""
        points = []
        for r in self.rec.get(rec_type):
            t = _fmt_dt(r["timestamp"])
            # 找对应 bar 的 close 作为图形 Y（不代表成交价）
            close = None
            for b in bars:
                if _fmt_dt(b["timestamp"]) == t:
                    close = b["close"]
                    break
            if close is None:
                continue
            points.append({
                "t": t,
                "y": close,
                "price": r.get("price", 0.0),
                "color": color,
                "shape": shape,
                "label": label,
                "extra": {k: r.get(k, "") for k, v in field_map.items() if k in r},
            })
        return points

    def render_html(self, filepath: str, symbol: str = "", title: str = "Quant V2 回测可视化") -> str:
        bars = self.rec.get("bar") or []
        trades = self.rec.get("trade") or []
        indicators = self.rec.get("indicator") or []

        # 指标序列按 name 分组（图上与策略一致）
        ind_series = {}
        for r in indicators:
            ind_series.setdefault(r["name"], []).append({"t": _fmt_dt(r["timestamp"]), "v": r["value"]})

        # 标记层：五类买卖点
        signal_pts = self._marker_layer(bars, "signal", {}, "#ffa500", "arrow", "信号")
        order_pts = self._marker_layer(bars, "order", {}, "#888888", "circle", "订单")
        stop_pts = self._marker_layer(bars, "stop", {}, "#c0392b", "x", "止损")
        reject_pts = self._marker_layer(bars, "risk_reject", {}, "#95a5a6", "diamond", "拒绝")
        # 成交点按 side 分离：买入红三角 / 卖出绿三角（口径=portfolio.trades）
        all_trades = self._marker_layer(bars, "trade", {"side": 1, "trade_id": 1}, "#e74c3c", "triangle", "买入")
        trade_buy = [p for p in all_trades if str(p.get("extra", {}).get("side", "")).upper() in ("BUY", "OPEN", "COVER")]
        trade_sell = [p for p in all_trades if str(p.get("extra", {}).get("side", "")).upper() in ("SELL", "CLOSE", "SHORT")]

        equity = self.rec.get("equity") or []
        # 净值只取含 equity 字段的点
        equity_line = [{"t": _fmt_dt(r.get("datetime") or r.get("timestamp")), "v": r["equity"]}
                       for r in equity if "equity" in r]
        drawdown_line = [{"t": _fmt_dt(r.get("timestamp")), "v": r.get("drawdown", 0.0)}
                         for r in equity if "drawdown" in r]

        data_json = json.dumps({
            "bars": bars,
            "signal_pts": signal_pts,
            "order_pts": order_pts,
            "trade_buy": trade_buy,
            "trade_sell": trade_sell,
            "stop_pts": stop_pts,
            "reject_pts": reject_pts,
            "ind_series": ind_series,
            "equity_line": equity_line,
            "drawdown_line": drawdown_line,
        }, ensure_ascii=False, default=str)

        trades_table = "".join(
            f"<tr><td>{t.get('trade_id','')}</td><td>{t.get('symbol','')}</td>"
            f"<td>{_fmt_dt(t.get('timestamp',''))}</td><td>{t.get('side','')}</td>"
            f"<td>{t.get('price','')}</td><td>{t.get('qty','')}</td>"
            f"<td>{t.get('commission','')}</td><td>{t.get('slippage','')}</td></tr>"
            for t in trades
        ) or "<tr><td colspan='8' style='text-align:center;color:#888'>无成交</td></tr>"

        html = f"""<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">\n<title>{title}</title>\n<style>\n  body{{font-family:-apple-system,'Segoe UI','PingFang SC',sans-serif;margin:0;background:#0f1117;color:#e6e6e6;}}\n  header{{padding:16px 24px;border-bottom:1px solid #222;}}\n  h1{{font-size:20px;margin:0;}} .sub{{color:#8a8f98;font-size:13px;margin-top:4px;}}\n  .wrap{{padding:20px 24px;display:grid;gap:16px;}}\n  .panel{{background:#171a22;border:1px solid #252a36;border-radius:8px;padding:14px;}}\n  .panel h2{{font-size:14px;color:#cfd3dc;margin:0 0 10px;}}\n  #kline{{height:420px;}} #ind{{height:200px;}} #eq{{height:220px;}} #dd{{height:140px;}}\n  canvas{{width:100%;display:block;background:#0f1117;}}\n  .legend{{font-size:12px;color:#8a8f98;margin-top:8px;}}\n  table{{border-collapse:collapse;width:100%;font-size:12px;}}\n  th,td{{border:1px solid #252a36;padding:6px 8px;text-align:left;}}\n  th{{background:#1c2029;color:#cfd3dc;}} td{{color:#b8bcc6;}}\n  .scroll{{max-height:300px;overflow:auto;}}\n</style></head><body>\n<header><h1>{title}</h1>\n<div class=\"sub\">{symbol} · {len(bars)} bars · {len(trades)} trades · 由 BacktestRecorder 记录生成</div>\n</header>\n<div class=\"wrap\">\n  <div class=\"panel\"><h2>K线 · 成交量 · 买卖点</h2><div id=\"kline\"></div>\n    <div class=\"legend\">▲买入成交 ▼卖出成交 · 信号(橙箭头) 订单(灰点) · 止损(红✕) 拒绝(灰菱形) · 均线由策略指标绘制</div></div>\n  <div class=\"panel\"><h2>策略指标（与策略实际计算一致）</h2><div id=\"ind\"></div></div>\n  <div class=\"panel\"><h2>净值曲线</h2><div id=\"eq\"></div></div>\n  <div class=\"panel\"><h2>回撤曲线</h2><div id=\"dd\"></div></div>\n  <div class=\"panel\"><h2>交易明细</h2><div class=\"scroll\"><table>\n    <tr><th>ID</th><th>标的</th><th>时间</th><th>方向</th><th>成交价</th><th>数量</th><th>手续费</th><th>滑点</th></tr>\n    {trades_table}</table></div></div>\n</div>\n<script>\nconst D = {data_json};\nconst COLS = ['#3ea6ff','#f1c40f','#e74c3c'];\nconst X = D.bars.map(b=>b.timestamp);\n// ---- 简单 canvas 绘图（K线+成交量+标记层） ----\nfunction drawKline(){{const cv=document.getElementById('kline'),ctx=cv.getContext('2d');\nconst W=cv.width=cv.offsetWidth, H=cv.height=cv.offsetHeight;\nconst pad={{t:12,b:18,l:8,r:56}}, pw=W*0.55, cw=W-pw;\nconst all=[].concat(...D.bars.map(b=>[b.high,b.low,b.close,b.open]));\nconst lo=Math.min(...all), hi=Math.max(...all);\nconst x0=pad.l,x1=pad.l+cw-40;\nfunction sx(i){{return x0+(X.length>1?i*(x1-x0)/(X.length-1):x0)}}\nfunction sy(v){{return pad.t+(hi-v)*(H-pad.t-pad.b)/(hi-lo||1)}}\n// 成交量轴\nconst vmax=Math.max(1,...D.bars.map(b=>(b.volume||0)));\nD.bars.forEach((b,i)=>{{const x=sx(i);const vh=30*(b.volume||0)/vmax;\nctx.fillStyle=b.close>=b.open?'#e74c3c33':'#2ecc7133';ctx.fillRect(x-1.5,H-pad.b-vh,3,vh);}});\n// K线\nD.bars.forEach((b,i)=>{{const x=sx(i);const up=b.close>=b.open;\nctx.strokeStyle=up?'#e74c3c':'#2ecc71';ctx.fillStyle=up?'#e74c3c':'#2ecc71';\nctx.beginPath();ctx.moveTo(x,sy(b.high));ctx.lineTo(x,sy(b.low));ctx.stroke();\nconst yo=sy(b.open),yc=sy(b.close);\nctx.fillRect(x-3,Math.min(yo,yc),6,Math.max(2,Math.abs(yc-yo)));}});\n// 标记层（买卖点区分）\nfunction pts(arr,color,shape){{arr.forEach(p=>{{const i=X.indexOf(p.t);if(i<0)return;const x=sx(i),y=sy(p.y);\nctx.fillStyle=color;ctx.beginPath();\nif(shape==='triangle'){{ctx.moveTo(x,y-6);ctx.lineTo(x-5,y+4);ctx.lineTo(x+5,y+4);}}\nelse if(shape==='circle'){{ctx.arc(x,y,4,0,7);}}\nelse if(shape==='diamond'){{ctx.moveTo(x,y-5);ctx.lineTo(x+5,y);ctx.lineTo(x,y+5);ctx.lineTo(x-5,y);}}\nelse if(shape==='x'){{ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(x-4,y-4);ctx.lineTo(x+4,y+4);ctx.moveTo(x+4,y-4);ctx.lineTo(x-4,y+4);ctx.stroke();return;}}\nelse if(shape==='arrow'){{ctx.moveTo(x,y);ctx.lineTo(x-6,y-8);ctx.lineTo(x+6,y-8);}}\nctx.fill();}});}}\nctx.strokeStyle='#333';ctx.strokeRect(0,0,W,H);\n// 时间刻度\nctx.fillStyle='#8a8f98';ctx.font='10px sans-serif';\nconst step=Math.max(1,Math.floor(X.length/8));\nfor(let i=0;i<X.length;i+=step){{ctx.fillText(String(X[i]).slice(5,10),sx(i)-12,H-pad.b+4);}}\n}}\n// ---- 线性图（指标/净值/回撤） ----\nfunction drawLine(id,series,color,labels){{const cv=document.getElementById(id);if(!cv)return;\nconst ctx=cv.getContext('2d');const W=cv.width=cv.offsetWidth,H=cv.height=cv.offsetHeight;\nconst pad={{t:10,b:18,l:8,r:8}};ctx.clearRect(0,0,W,H);\nconst arr=Array.isArray(series)?series:(series[Object.keys(series)[0]]||[]);\nif(!arr.length){{ctx.fillStyle='#666';ctx.fillText('无数据',W/2-20,H/2);return;}}\nlet lo=Infinity,hi=-Infinity;arr.forEach(p=>{{if(p.v<lo)lo=p.v;if(p.v>hi)hi=p.v;}});\nif(lo===hi){{lo-=1;hi+=1;}}\nconst x0=pad.l,x1=W-pad.r,y0=pad.t,y1=H-pad.b;\nfunction sx(i){{return x0+(arr.length>1?i*(x1-x0)/(arr.length-1):x0)}}\nfunction sy(v){{return y0+(hi-v)*(y1-y0)/(hi-lo||1)}}\nctx.strokeStyle='#333';ctx.strokeRect(0,0,W,H);\nif(Array.isArray(series)){{const c=Array.isArray(color)?color[0]:color;\nctx.strokeStyle=c;ctx.beginPath();arr.forEach((p,i)=>{{i?ctx.lineTo(sx(i),sy(p.v)):ctx.moveTo(sx(i),sy(p.v));}});ctx.stroke();}}\nelse{{const cols=color;Object.keys(series).forEach((k,j)=>{{const s=series[k];ctx.strokeStyle=cols[j%cols.length];ctx.beginPath();\ns.forEach((p,i)=>{{i?ctx.lineTo(sx(i),sy(p.v)):ctx.moveTo(sx(i),sy(p.v));}});ctx.stroke();}});}}\nctx.fillStyle='#8a8f98';ctx.font='10px sans-serif';\nconst st=Math.max(1,Math.floor(arr.length/8));\nfor(let i=0;i<arr.length;i+=st){{ctx.fillText(String(arr[i].t).slice(5,10),sx(i)-12,y1+4);}}\n}}\ndrawKline();\ndrawLine('ind',D.ind_series,COLS);\ndrawLine('eq',D.equity_line,['#3ea6ff']);\ndrawLine('dd',D.drawdown_line,['#e74c3c']);\n</script></body></html>"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        return filepath
