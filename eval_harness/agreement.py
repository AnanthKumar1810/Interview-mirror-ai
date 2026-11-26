"""Descriptive paired-score agreement. Correlation is not correctness."""
from __future__ import annotations

from collections import Counter
import math
import statistics


def _numeric(values):
    values = list(values)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in values):
        raise ValueError("Scores must be finite numbers")
    return values


def _pearson(a, b):
    if len(a) < 2:
        return None
    x = [v - statistics.mean(a) for v in a]
    y = [v - statistics.mean(b) for v in b]
    denominator = math.sqrt(sum(v*v for v in x) * sum(v*v for v in y))
    return max(-1.0, min(1.0, sum(u*v for u, v in zip(x, y))/denominator)) if denominator else None


def _ranks(values):
    positions = {}
    for rank, value in enumerate(sorted(values), 1):
        positions.setdefault(value, []).append(rank)
    return [statistics.mean(positions[v]) for v in values]


def paired_score_metrics(predicted, reference):
    predicted, reference = _numeric(predicted), _numeric(reference)
    if len(predicted) != len(reference):
        raise ValueError("Paired arrays must have equal length")
    errors = [a-b for a, b in zip(predicted, reference)]
    return {
        "n_pairs": len(errors),
        "mae": statistics.mean(abs(e) for e in errors) if errors else None,
        "signed_bias": statistics.mean(errors) if errors else None,
        "pearson": _pearson(predicted, reference),
        "spearman": _pearson(_ranks(predicted), _ranks(reference)),
        "interpretation": "descriptive_only; undefined correlations are null; correlation does not measure absolute agreement",
    }


def cohen_kappa(first, second):
    first, second = list(first), list(second)
    if len(first) != len(second):
        raise ValueError("Paired arrays must have equal length")
    if any(not isinstance(v, str) or not v.strip() for v in first+second):
        raise ValueError("Verdicts must be nonempty strings")
    if not first:
        return None
    n = len(first)
    a, b = Counter(first), Counter(second)
    expected = sum(a[key]*b[key] for key in a.keys() | b.keys()) / (n*n)
    observed = sum(x == y for x, y in zip(first, second)) / n
    return (observed-expected)/(1-expected) if expected < 1 else None


def gold_agreement(dataset):
    """Compare matching reviewer identities; never combine unrelated raters."""
    from itertools import combinations
    from eval_harness.gold_workflow import validate_dataset
    summary = validate_dataset(dataset)
    pairs = {}
    for case in dataset.cases:
        for a, b in combinations(sorted(case.reviewers, key=lambda r: r.reviewer_id), 2):
            pairs.setdefault((a.reviewer_id, b.reviewer_id), []).append((a, b))
    output = []
    for ids, ratings in sorted(pairs.items()):
        output.append({
            'reviewer_ids': list(ids),
            'scores': paired_score_metrics([a.total_score for a,b in ratings],
                                          [b.total_score for a,b in ratings]),
            'verdict_kappa': cohen_kappa([a.verdict for a,b in ratings],
                                         [b.verdict for a,b in ratings]),
        })
    return {'dataset_id':dataset.dataset_id, 'dataset_status':summary['status'],
            'gold_examples_count':summary['gold_examples_count'],
            'reviewer_pairs':output, 'status':'measured_descriptively' if output else 'unmeasured',
            'limitations':['No fabricated reviewer labels.',
                           'Rater agreement is not proof of scorer accuracy or independent reviewer qualification.',
                           'Small samples and correlated question families limit interpretation.']}


def main():
    import argparse
    import json
    from pathlib import Path
    from eval_harness.gold_workflow import load_dataset
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = gold_agreement(load_dataset(args.dataset))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(f"Reviewer agreement: {result['status']} | reviewer pairs: {len(result['reviewer_pairs'])}")


if __name__ == '__main__':
    main()
