"""Generate a browser-friendly HTML timeline for research JSONL traces."""

from __future__ import annotations

import argparse
import functools
import html
import json
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent

HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Research Trace 可视化 - __TRACE_NAME__</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f4;
      --panel: #ffffff;
      --ink: #17201a;
      --muted: #667067;
      --line: #dfe4dc;
      --accent: #116a67;
      --shadow: 0 10px 30px rgba(23, 32, 26, .08);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; color: var(--ink); background: var(--bg); }
    .app { max-width: 1280px; margin: 0 auto; padding: 28px 20px 48px; }
    header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
    h1 { margin: 0; font-size: clamp(24px, 4vw, 38px); line-height: 1.08; letter-spacing: 0; }
    .sub { margin-top: 8px; color: var(--muted); font-size: 14px; line-height: 1.5; }
    .badge { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 8px 12px; color: var(--muted); white-space: nowrap; font-size: 13px; }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 18px 0; }
    .stat { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; box-shadow: var(--shadow); min-height: 78px; }
    .stat .n { font-size: 26px; font-weight: 720; }
    .stat .k { color: var(--muted); font-size: 13px; margin-top: 4px; }
    .controls { display: grid; grid-template-columns: minmax(220px, 1fr) 190px 170px; gap: 10px; margin: 18px 0 14px; }
    input, select, button { font: inherit; }
    input, select { width: 100%; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--ink); padding: 11px 12px; outline-color: var(--accent); }
    button { border: 1px solid var(--line); border-radius: 8px; background: #fff; padding: 11px 12px; color: var(--ink); cursor: pointer; }
    button:hover { border-color: var(--accent); color: var(--accent); }
    .layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 16px; align-items: start; }
    .side { position: sticky; top: 12px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; box-shadow: var(--shadow); }
    .side h2 { margin: 0 0 12px; font-size: 15px; }
    .type-list { display: grid; gap: 6px; }
    .type-row { display: flex; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 13px; border-bottom: 1px solid #eef1ec; padding: 6px 0; }
    .type-row strong { color: var(--ink); font-weight: 650; overflow-wrap: anywhere; }
    .timeline { display: grid; gap: 10px; }
    details.event { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); overflow: clip; }
    details.event[open] { border-color: rgba(17, 106, 103, .45); }
    summary { list-style: none; cursor: pointer; display: grid; grid-template-columns: 112px 190px minmax(0, 1fr) 92px; gap: 12px; align-items: center; padding: 14px 16px; }
    summary::-webkit-details-marker { display: none; }
    .time { color: var(--accent); font-variant-numeric: tabular-nums; font-size: 13px; }
    .type { display: inline-flex; align-items: center; justify-content: center; width: fit-content; max-width: 100%; min-height: 28px; border-radius: 999px; padding: 5px 9px; background: #e9f3f1; color: #0e5b58; font-weight: 680; font-size: 12px; overflow-wrap: anywhere; }
    .summary { min-width: 0; line-height: 1.42; font-size: 14px; overflow-wrap: anywhere; }
    .meta { color: var(--muted); font-size: 12px; text-align: right; }
    .detail { border-top: 1px solid var(--line); padding: 14px 16px 16px; background: #fbfcfa; }
    .kv { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
    .chip { border: 1px solid var(--line); border-radius: 999px; padding: 5px 9px; color: var(--muted); background: #fff; font-size: 12px; }
    pre { margin: 0; overflow: auto; max-height: 520px; border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #101714; color: #e7efe8; font-size: 12px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
    .empty { background: var(--panel); border: 1px dashed var(--line); border-radius: 8px; padding: 24px; color: var(--muted); text-align: center; }
    mark { background: #f4d35e; color: #17201a; padding: 0 2px; border-radius: 3px; }
    @media (max-width: 900px) {
      header { display: block; }
      .badge { display: inline-block; margin-top: 12px; }
      .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .controls { grid-template-columns: 1fr; }
      .layout { grid-template-columns: 1fr; }
      .side { position: static; }
      summary { grid-template-columns: 1fr; gap: 8px; }
      .meta { text-align: left; }
    }
  </style>
</head>
<body>
  <main class="app">
    <header>
      <div>
        <h1>Research Trace 可视化</h1>
        <div class="sub">__TRACE_NAME__ · time - 主要内容 - 展开可看所有内容</div>
      </div>
      <div class="badge" id="rangeBadge"></div>
    </header>

    <section class="stats" aria-label="摘要统计">
      <div class="stat"><div class="n" id="totalCount">0</div><div class="k">日志事件</div></div>
      <div class="stat"><div class="n" id="toolCount">0</div><div class="k">工具结果</div></div>
      <div class="stat"><div class="n" id="factCount">0</div><div class="k">事实记录</div></div>
      <div class="stat"><div class="n" id="claimCount">0</div><div class="k">声明记录</div></div>
    </section>

    <section class="controls" aria-label="筛选控件">
      <input id="search" type="search" placeholder="搜索 event_type、摘要、payload..." />
      <select id="typeFilter"><option value="all">全部事件类型</option></select>
      <button id="toggleAll" type="button">展开全部</button>
    </section>

    <section class="layout">
      <aside class="side">
        <h2>事件类型分布</h2>
        <div class="type-list" id="typeList"></div>
      </aside>
      <section class="timeline" id="timeline" aria-label="日志时间线"></section>
    </section>
  </main>

  <script>
    const rows = __ROWS_JSON__;
    const eventLabels = {
      run_started: '运行开始', query_understanding: '问题理解', tool_result: '工具结果',
      source_added: '来源记录', fact_added: '事实记录', verified_fact_table: '事实核验表',
      research_context_built: '研究上下文', synthesis_result: '综合结果', function_io: '函数输入输出',
      claim_verification: '声明核验', claim_added: '声明记录', memo_rendered: '报告渲染',
      final_output: '最终输出', guardrail_result: '护栏结果', run_completed: '运行完成',
      run_snapshot: '运行快照'
    };

    const typeFilter = document.querySelector('#typeFilter');
    const typeList = document.querySelector('#typeList');
    const timeline = document.querySelector('#timeline');
    const search = document.querySelector('#search');
    const toggleAll = document.querySelector('#toggleAll');

    function timeOnly(ts) {
      if (!ts) return '-';
      const date = new Date(ts);
      if (Number.isNaN(date.getTime())) return ts;
      return date.toISOString().slice(11, 23);
    }

    function shortDate(ts) {
      if (!ts) return '-';
      const date = new Date(ts);
      if (Number.isNaN(date.getTime())) return ts;
      return date.toISOString().replace('T', ' ').replace('Z', ' UTC');
    }

    function compact(value, max = 180) {
      const text = typeof value === 'string' ? value : JSON.stringify(value);
      if (!text) return '';
      return text.length > max ? text.slice(0, max - 1) + '...' : text;
    }

    function summarize(row) {
      const p = row.payload || {};
      switch (row.event_type) {
        case 'run_started': return `用户问题：${p.query || ''}`;
        case 'query_understanding': return `识别 ${p.entity?.symbol || p.entity?.company_name || '标的'}，路由为 ${p.route?.route || 'unknown'}，窗口：${p.time_window?.label || '-'}`;
        case 'tool_result': return `${p.tool || 'tool'} 返回：${compact(p.result, 150)}`;
        case 'source_added': return `${p.name || p.id || 'source'} · ${p.tool_name || p.kind || ''} · 可靠性 ${p.reliability || '-'}`;
        case 'fact_added': return `${p.metric || p.id || 'fact'}：${p.text || compact(p.value, 120)}`;
        case 'verified_fact_table': return `已核验事实 ${p.verified_facts?.length || 0} 条，缺失事实 ${p.missing_facts?.length || 0} 条`;
        case 'research_context_built': return `研究上下文建立：事实 ${p.facts?.length || 0} 条，缺口 ${p.missing_facts?.length || 0} 项`;
        case 'synthesis_result': return `生成候选声明 ${p.claims?.length || 0} 条`;
        case 'function_io': return `${p.function || p.tag || 'function'} · ${p.module || ''}`;
        case 'claim_verification': return `声明核验 ${p.passed ? '通过' : '未通过'}，问题 ${p.issues?.length || 0} 个`;
        case 'claim_added': return `${p.text || p.id || 'claim'}`;
        case 'memo_rendered': return p.final_output ? compact(p.final_output.replace(/\n+/g, ' / '), 180) : '报告渲染完成';
        case 'final_output': return compact((p.text || '').replace(/\n+/g, ' / '), 180) || '最终输出已生成';
        case 'guardrail_result': return `护栏 ${p.passed ? '通过' : '未通过'}，检查项 ${p.checks?.length || 0} 个`;
        case 'run_completed': return `运行完成：${p.status || 'completed'} · ${p.summary || p.user_query || ''}`;
        default: return compact(p, 180);
      }
    }

    function countByType() {
      return rows.reduce((acc, row) => {
        acc[row.event_type] = (acc[row.event_type] || 0) + 1;
        return acc;
      }, {});
    }

    function escapeHtml(text) {
      return String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    function highlight(text, query) {
      const safe = escapeHtml(text);
      if (!query) return safe;
      const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      return safe.replace(new RegExp(escaped, 'ig'), m => `<mark>${m}</mark>`);
    }

    function init() {
      const counts = countByType();
      const sortedTypes = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
      for (const [type, count] of sortedTypes) {
        const opt = document.createElement('option');
        opt.value = type;
        opt.textContent = `${eventLabels[type] || type} (${count})`;
        typeFilter.appendChild(opt);
      }
      typeList.innerHTML = sortedTypes.map(([type, count]) => `<div class="type-row"><strong>${escapeHtml(eventLabels[type] || type)}</strong><span>${count}</span></div>`).join('');
      document.querySelector('#totalCount').textContent = rows.length;
      document.querySelector('#toolCount').textContent = counts.tool_result || 0;
      document.querySelector('#factCount').textContent = counts.fact_added || 0;
      document.querySelector('#claimCount').textContent = counts.claim_added || 0;
      const first = rows[0]?.timestamp;
      const last = rows[rows.length - 1]?.timestamp;
      document.querySelector('#rangeBadge').textContent = `${shortDate(first)} - ${shortDate(last)}`;
      render();
    }

    function render() {
      const q = search.value.trim();
      const type = typeFilter.value;
      const filtered = rows.filter((row) => {
        const typeOk = type === 'all' || row.event_type === type;
        if (!typeOk) return false;
        if (!q) return true;
        const haystack = `${row.event_type}\n${summarize(row)}\n${JSON.stringify(row.payload || {})}`.toLowerCase();
        return haystack.includes(q.toLowerCase());
      });

      if (!filtered.length) {
        timeline.innerHTML = '<div class="empty">没有匹配的日志</div>';
        return;
      }

      timeline.innerHTML = filtered.map((row) => {
        const originalIndex = rows.indexOf(row) + 1;
        const summary = summarize(row);
        const payloadPretty = JSON.stringify(row, null, 2);
        const label = eventLabels[row.event_type] || row.event_type;
        const ids = [];
        if (row.payload?.id) ids.push(row.payload.id);
        if (row.payload?.tool) ids.push(row.payload.tool);
        if (row.payload?.run_id) ids.push(row.payload.run_id);
        return `<details class="event">
          <summary>
            <div class="time">${escapeHtml(timeOnly(row.timestamp))}</div>
            <div><span class="type">${escapeHtml(label)}</span></div>
            <div class="summary">${highlight(summary, q)}</div>
            <div class="meta">#${originalIndex}</div>
          </summary>
          <div class="detail">
            <div class="kv">
              <span class="chip">event_type: ${escapeHtml(row.event_type)}</span>
              <span class="chip">timestamp: ${escapeHtml(row.timestamp || '-')}</span>
              ${ids.map(id => `<span class="chip">${escapeHtml(id)}</span>`).join('')}
            </div>
            <pre>${highlight(payloadPretty, q)}</pre>
          </div>
        </details>`;
      }).join('');
    }

    toggleAll.addEventListener('click', () => {
      const details = [...document.querySelectorAll('details.event')];
      const shouldOpen = details.some(d => !d.open);
      details.forEach(d => d.open = shouldOpen);
      toggleAll.textContent = shouldOpen ? '收起全部' : '展开全部';
    });
    search.addEventListener('input', render);
    typeFilter.addEventListener('change', render);
    init();
  </script>
</body>
</html>
"""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise SystemExit(f"Expected object at {path}:{line_number}, got {type(row).__name__}")
            rows.append(row)
    return rows


def output_path_for(trace_path: Path, out: Path | None) -> Path:
    if out is not None:
        return out
    return trace_path.with_name(f"{trace_path.stem}_view.html")


def render_html(trace_path: Path, rows: list[dict[str, Any]]) -> str:
    rows_json = json.dumps(rows, ensure_ascii=False)
    return (
        HTML_TEMPLATE.replace("__TRACE_NAME__", html.escape(trace_path.name))
        .replace("__ROWS_JSON__", rows_json)
    )


def write_view(trace_path: Path, out: Path | None = None) -> Path:
    trace_path = trace_path.resolve()
    if not trace_path.exists():
        raise SystemExit(f"Trace file not found: {trace_path}")
    rows = load_jsonl(trace_path)
    view_path = output_path_for(trace_path, out).resolve()
    view_path.parent.mkdir(parents=True, exist_ok=True)
    view_path.write_text(render_html(trace_path, rows), encoding="utf-8")
    return view_path


def find_free_port(host: str, preferred_port: int) -> int:
    if preferred_port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])
    for port in range(preferred_port, preferred_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise SystemExit(f"No free port found from {preferred_port} to {preferred_port + 49}")


def effective_root_for(path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    try:
        path.resolve().relative_to(resolved_root)
    except ValueError:
        return path.resolve().parent
    return resolved_root


def relative_url_path(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve())
    return "/".join(rel.parts)


def serve(view_path: Path, host: str, port: int, root: Path) -> None:
    actual_port = find_free_port(host, port)
    root = effective_root_for(view_path, root)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root.resolve()))
    server = ThreadingHTTPServer((host, actual_port), handler)
    url_path = relative_url_path(view_path, root)
    print(f"HTML: {view_path}", flush=True)
    print(f"Preview: http://{host}:{actual_port}/{url_path}", flush=True)
    print("Press Ctrl+C to stop the preview server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped preview server.", flush=True)
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a clickable HTML view for a research JSONL trace.")
    parser.add_argument("trace", type=Path, help="Path to a .jsonl research trace file.")
    parser.add_argument("--out", type=Path, help="Output HTML path. Defaults to <trace>_view.html.")
    parser.add_argument("--serve", action="store_true", help="Start a local HTTP server and print a Codex-preview-friendly URL.")
    parser.add_argument("--host", default="127.0.0.1", help="Preview server host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8765, help="Preferred preview port. Use 0 for any free port.")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="Directory served by the preview server. Defaults to project root.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    view_path = write_view(args.trace, args.out)
    if args.serve:
        serve(view_path, args.host, args.port, args.root)
        return
    print(f"HTML: {view_path}")
    root = effective_root_for(view_path, args.root)
    url_path = relative_url_path(view_path, root)
    print(f"Preview after serving {root}: http://{args.host}:{args.port}/{url_path}")


if __name__ == "__main__":
    main()
