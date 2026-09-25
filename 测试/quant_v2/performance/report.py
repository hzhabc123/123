"""
Quant V2 报告生成器

- HTML 报告：净值曲线、绩效指标、成交明细
- CSV 导出：净值曲线、成交记录
"""

import json
from datetime import datetime


class ReportGenerator:
    def __init__(self, analyzer, trades: list, equity_curve: list, portfolio=None):
        self.analyzer = analyzer
        self.trades = trades
        self.equity_curve = equity_curve
        self.portfolio = portfolio

    def export_equity_csv(self, filepath: str):
        df = self.analyzer.to_dataframe()
        df.to_csv(filepath, index=False)

    def export_trades_csv(self, filepath: str):
        import csv
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["trade_id", "order_id", "symbol", "side", "price", "qty", "commission", "trade_time"])
            for t in self.trades:
                writer.writerow([t.trade_id, t.order_id, t.symbol, t.side.value, t.price, t.qty, t.commission, t.trade_time])

    def generate_html(self, filepath: str):
        m = self.analyzer.compute()
        equity_js = [[str(e["datetime"]), round(e["equity"], 2)] for e in self.equity_curve]
        close_js = [[str(e["datetime"]), round(e["close"], 4)] for e in self.equity_curve]
        trade_rows = ""
        for t in self.trades:
            trade_rows += (f"<tr><td>{t.trade_id}</td><td>{t.symbol}</td>"
                           f"<td class='{'up' if t.side.name=='BUY' else 'down'}'>{t.side.value}</td>"
                           f"<td>{t.price:.4f}</td><td>{t.qty}</td>"
                           f"<td>{t.commission:.2f}</td><td>{t.trade_time}</td></tr>")
        if not self.trades:
            trade_rows = "<tr><td colspan='7'>无成交</td></tr>"
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Quant V2 回测报告</title>
<style>
  body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; margin:0; background:#0f172a; color:#e2e8f0; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
  h1 {{ font-size:24px; border-bottom:1px solid #334155; padding-bottom:12px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:20px 0; }}
  .card {{ background:#1e293b; border-radius:10px; padding:16px; }}
  .card .v {{ font-size:22px; font-weight:700; margin-top:4px; }}
  .card .l {{ color:#94a3b8; font-size:12px; }}
  .pos {{ color:#22c55e; }} .neg {{ color:#ef4444; }}
  .chart {{ background:#1e293b; border-radius:10px; padding:16px; margin:20px 0; }}
  table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
  th, td {{ padding:8px; text-align:right; border-bottom:1px solid #334155; font-size:13px; }}
  th {{ color:#94a3b8; font-weight:500; }}
  td:first-child {{ text-align:left; }}
  .up {{ color:#22c55e; }} .down {{ color:#ef4444; }}
  .section {{ margin-top:28px; }}
  .section h2 {{ font-size:18px; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
</head>
<body>
<div class="wrap">
  <h1>📊 Quant V2 回测报告</h1>
  <div class="cards">
    <div class="card"><div class="l">总收益率</div><div class="v {'pos' if m.total_return>=0 else 'neg'}">{m.total_return:.2%}</div></div>
    <div class="card"><div class="l">年化收益</div><div class="v {'pos' if m.annual_return>=0 else 'neg'}">{m.annual_return:.2%}</div></div>
    <div class="card"><div class="l">夏普比率</div><div class="v">{m.sharpe_ratio:.2f}</div></div>
    <div class="card"><div class="l">最大回撤</div><div class="v neg">{m.max_drawdown:.2%}</div></div>
    <div class="card"><div class="l">胜率</div><div class="v">{m.win_rate:.2%}</div></div>
    <div class="card"><div class="l">交易数</div><div class="v">{m.total_trades}</div></div>
    <div class="card"><div class="l">卡玛比率</div><div class="v">{m.calmar_ratio:.2f}</div></div>
  </div>
  <div class="chart"><h2>净值曲线</h2><div id="main" style="height:340px;"></div></div>
  <div class="section"><h2>绩效指标</h2>
    <table><tr><th>指标</th><th>值</th><th>指标</th><th>值</th></tr>
      <tr><td>索提诺比率</td><td>{m.sortino_ratio:.4f}</td><td>年化波动</td><td>{m.annual_volatility:.2%}</td></tr>
      <tr><td>盈亏比</td><td>{m.profit_loss_ratio:.4f}</td><td>换手率</td><td>{m.turnover:.4f}</td></tr>
      <tr><td>Alpha</td><td>{m.alpha:.4f}</td><td>Beta</td><td>{m.beta:.4f}</td></tr>
      <tr><td>信息比率</td><td>{m.information_ratio:.4f}</td><td>基准收益</td><td>{m.benchmark_return:.2%}</td></tr>
    </table>
  </div>
  <div class="section"><h2>成交明细（{len(self.trades)} 笔）</h2>
    <table><tr><th>成交ID</th><th>标的</th><th>方向</th><th>价格</th><th>数量</th><th>费用</th><th>时间</th></tr>{trade_rows}</table>
  </div>
  <p style="color:#64748b;font-size:12px;margin-top:30px;">Quant V2 回测系统 · 生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>
<script>
  var eco = echarts.init(document.getElementById('main'));
  eco.setOption({{ tooltip: {{ trigger: 'axis' }}, legend: {{ data: ['净值', '收盘价'], textStyle: {{color:'#94a3b8'}} }},
    grid: {{ left:60, right:60, top:30, bottom:40 }},
    xAxis: {{ type:'category', data: __JSON_EQUITY__, axisLabel:{{color:'#94a3b8'}} }},
    yAxis: [{{ type:'value', name:'净值', axisLabel:{{color:'#94a3b8'}} }}, {{ type:'value', name:'价格', axisLabel:{{color:'#94a3b8'}} }}],
    series: [{{ name:'净值', type:'line', showSymbol:false, data: __JSON_EQUITY__, lineStyle:{{color:'#38bdf8'}}, areaStyle:{{color:'rgba(56,189,248,0.15)'}} }},
      {{ name:'收盘价', type:'line', showSymbol:false, yAxisIndex:1, data: __JSON_CLOSE__, lineStyle:{{color:'#f59e0b'}} }}]
  }});
  window.addEventListener('resize', ()=>eco.resize());
</script>
</body>
</html>"""
        html = html.replace("__JSON_EQUITY__", json.dumps(equity_js))
        html = html.replace("__JSON_CLOSE__", json.dumps(close_js))
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        return filepath
