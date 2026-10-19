"""Render a portable, self-contained HTML acceptance report with original screenshots."""
import argparse
import base64
import html
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text())
    root = Path(__file__).resolve().parents[1]
    esc = lambda value: html.escape(str(value))
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>CARLA 测试与开发进度报告</title>',
             '<style>body{margin:0;background:#edf2f7;color:#172536;font:16px/1.75 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:32px}section{background:white;padding:28px;margin:24px 0;border-radius:12px}h1,h2,h3{line-height:1.4}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd6e2;text-align:left;vertical-align:top}th{background:#e7eef6}figure{margin:24px 0}img{display:block;width:100%;height:auto;border:1px solid #bdcbd9}figcaption{font-size:14px;overflow-wrap:anywhere;padding:8px;background:#edf2f7}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f8;padding:16px;font-size:13px}a{color:#075aad}.passed{color:#08744d}.failed{color:#b02d2d}.note{border-left:4px solid #e3a126;padding:12px;background:#fff6df}@media print{body{background:white}section{break-before:page;padding:0}figure{break-inside:avoid}details{display:block}main{padding:0}}</style><main>']
    parts += [f'<h1>{esc(data["title"])}</h1><p>{esc(data["date"])}</p>',
              f'<p class="note">{esc(data["scope"])}</p><section><h2>结论与当前运行状态</h2>']
    parts += [f'<p>{esc(line)}</p>' for line in data['summary']]
    parts += ['</section><section><h2>功能完成情况</h2><table><tr><th>功能</th><th>当前结论</th><th>未完成与限制</th></tr>']
    for row in data['features']:
        parts.append('<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in row) + '</tr>')
    parts += ['</table></section><section><h2>后续开发顺序</h2><ol>']
    parts += [f'<li>{esc(line)}</li>' for line in data['next_steps']]
    parts += ['</ol></section><section><h2>测试索引</h2><ol>']
    for index, case in enumerate(data['cases'], 1):
        parts.append(f'<li><a href="#case-{index}">{esc(case["title"])}</a></li>')
    parts += ['</ol></section>']
    image_count = 0
    rendered_images = {}
    for index, case in enumerate(data['cases'], 1):
        report = json.loads((root / case['report']).read_text()) if case.get('report') else {}
        state = case.get('state', report.get('state', '未执行'))
        parts.append(f'<section id="case-{index}"><h2>{index}. {esc(case["title"])}</h2><p class="{esc(state)}">结果：{esc(state)}</p>')
        for label, field in [('测试步骤与检查点', 'steps'), ('实际观察', 'observed'), ('范围与后续', 'limits')]:
            if case.get(field):
                parts.append(f'<h3>{label}</h3><p>{esc(case[field])}</p>')
        paths = list(case.get('images', []))
        paths += report.get('screenshots', [])
        if case.get('include_discovered_images', True):
            paths += [p for p in report.get('evidence', []) if Path(p).suffix.lower() in ('.png', '.jpg', '.jpeg')]
        seen = set()
        for path in paths:
            source = (root / path).resolve()
            if source in seen:
                continue
            seen.add(source)
            if source in rendered_images:
                number = rendered_images[source]
                parts.append(f'<p>此步骤共用的原始截图：<a href="#figure-{number}">图 {number} · {esc(source.name)}</a>。</p>')
                continue
            if not source.is_relative_to(root) or not source.is_file():
                raise ValueError('Missing or out-of-project screenshot: ' + str(source))
            mime = 'image/png' if source.suffix == '.png' else 'image/jpeg'
            raw = source.read_bytes()
            if not (raw.startswith(b'\x89PNG') or raw.startswith(b'\xff\xd8')):
                raise ValueError('Invalid image: ' + str(source))
            image_count += 1
            rendered_images[source] = image_count
            caption = case.get('captions', {}).get(source.name, source.name)
            parts.append(f'<figure id="figure-{image_count}"><img loading="lazy" alt="{esc(caption)}" src="data:{mime};base64,{base64.b64encode(raw).decode()}"><figcaption>图 {image_count} · {esc(caption)}<br>原始证据：{esc(source.relative_to(root))}</figcaption></figure>')
        if report:
            parts.append('<details><summary>机器验证记录、命令与证据路径</summary><pre>' + esc(json.dumps(report, ensure_ascii=False, indent=2)) + '</pre></details>')
        parts.append('</section>')
    parts += [f'<footer>共嵌入 {image_count} 张原始截图／测试图像。图片已内嵌，单个 HTML 文件可独立迁移；机器报告和采集数据按各节路径保留在项目中。</footer></main></html>']
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(parts))
    print(json.dumps({'output': str(args.output.resolve()), 'images': image_count,
                      'cases': len(data['cases']), 'bytes': args.output.stat().st_size}))


if __name__ == '__main__':
    main()
