"""Catch broken navigation and missing accessibility hooks in the static UI."""
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'static'


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


def test_progress_navigation_and_review_controls_are_accessible():
    parser = Elements()
    parser.feed((ROOT / 'index.html').read_text(encoding='utf-8'))
    ids = [attrs['id'] for _, attrs in parser.items if 'id' in attrs]
    assert len(ids) == len(set(ids))
    by_id = {attrs.get('id'): (tag, attrs) for tag, attrs in parser.items}
    assert by_id['progress-nav'][0] == 'button'
    assert by_id['studio-nav'][0] == 'button'
    assert 'hidden' in by_id['progress-view'][1]
    assert by_id['progress-status'][1].get('aria-live') == 'polite'
    assert by_id['interview-stepper'][1].get('aria-label')
    assert by_id['answer-input'][0] == 'textarea'
    assert by_id['audio-consent'][1].get('type') == 'checkbox'
