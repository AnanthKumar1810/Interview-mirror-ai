"""Render an existing harness report for human inspection; no scoring calls."""
from __future__ import annotations
import argparse
from html import escape
import json
from pathlib import Path


def render(report):
    def text(value):
        return escape(str(value))
    summary = report['summary']
    rows = []
    for case in report['cases']:
        evidence = case.get('evidence_by_repeat', [])
        first = evidence[0] if evidence else []
        citations = ''.join('<li><b>'+text(item['dimension'])+'</b>: <q>'+text(item['quote'])+
                            '</q> — '+text(item['observation'])+'</li>' for item in first)
        dimensions = ', '.join(text(name)+': '+text(values['mean'])
                               for name, values in case['dimensions'].items())
        rows.append('<tr><td>'+text(case['id'])+'<br>'+text(case['language'])+'</td><td>'+
                    text(case['mean_score'])+'</td><td>'+text(case['score_std'])+'</td><td>'+
                    dimensions+'</td><td><ul>'+citations+'</ul></td><td>'+
                    text(case['human_reference'])+'</td></tr>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>InterviewMirror Evaluation Workbench</title>'
            '<style>body{font:16px system-ui;margin:32px;color:#18304a;background:#f5f8fc}'
            'table{border-collapse:collapse;background:white;width:100%}td,th{padding:12px;border:1px solid #ccd6e1;'
            'text-align:left;vertical-align:top}q{color:#155f62}pre{white-space:pre-wrap}'
            '.notice{padding:16px;background:#fff0c2;border-left:5px solid #a76700}</style>'
            '<h1>InterviewMirror Evaluation Workbench</h1><p class="notice">'
            'Repeated scores show stability, not correctness. Citation membership is checked; meaning is not verified. '
            'Null human metrics mean unmeasured. Evidence below is from the first repeat; JSON retains every repeat.</p>'
            '<p>Scorer: '+text(report['scorer_name'])+' | Dataset: '+text(report['dataset_id'])+'</p>'
            '<p>Cases: '+text(summary['n_cases'])+' | Scoring calls: '+text(summary['total_scoring_calls'])+
            ' | Human-reviewed cases: '+text(summary['human_reviewed_cases'])+'</p>'
            '<h2>Agreement and gates</h2><pre>'+text(json.dumps({
                'agreement':summary.get('human_score_agreement'), 'gate':report.get('gate'),
                'regression_gate':report.get('regression_gate')},indent=2))+'</pre>'
            '<table><thead><tr><th>Case</th><th>Mean score</th><th>Within-case SD</th><th>Dimensions</th>'
            '<th>Verbatim evidence</th><th>Human reference</th></tr></thead><tbody>'+''.join(rows)+
            '</tbody></table><h2>Limitations</h2><ul>'+''.join('<li>'+text(v)+'</li>'
            for v in report.get('limitations', []))+'</ul></html>')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(report),encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
