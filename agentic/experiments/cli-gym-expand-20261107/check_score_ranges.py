"""Offline numerical/transport check on a saved candidate; no action generation.

Four zero-generation requests share one existing score slot. Results do not
select a production scorer or change any original decision/trajectory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from append_rewrite.terminus.suffix_score import NativeSuffixStreamClient, NativeFullStreamClient, score_slot
from append_rewrite.terminus.scoring import render_candidate
from append_rewrite.terminus.tokenizer import PinnedTokenizer


def main(turn, output, config, tokenizer):
    output.mkdir(parents=True, exist_ok=False)
    pinned = PinnedTokenizer(tokenizer)
    original = json.loads((turn / 'decision.json').read_text())
    candidate = next(c for c in original['candidates'] if c['index'] == original['selected_index'])
    prefix = json.loads((turn / 'public-prefix.json').read_text())
    rendered = render_candidate(prefix, candidate['raw'], pinned, tokenizer_identity=pinned.identity)
    results = []
    with score_slot():
        for index, (name, client) in enumerate([
                ('full-a', NativeFullStreamClient(config)), ('suffix-a', NativeSuffixStreamClient(config)),
                ('full-b', NativeFullStreamClient(config)), ('suffix-b', NativeSuffixStreamClient(config))]):
            journal = output / name
            score = client.score(rendered, journal=journal, timeout=120)
            results.append({'mode': name, 'mean_logprob': score['mean_logprob'],
                'elapsed_sec': score['request_elapsed_sec'], 'token_count': score['token_count'],
                'response_bytes': (journal / 'response.json').stat().st_size,
                'returned_logprob_start': score['returned_logprob_start']})
            (output / 'progress.json').write_text(json.dumps(results, indent=2))
    report = {'at': time.time(), 'source_turn': str(turn),
        'source_decision_sha256': hashlib.sha256((turn / 'decision.json').read_bytes()).hexdigest(),
        'input_tokens': len(rendered.input_ids), 'results': results,
        'full_repeat_difference': abs(results[0]['mean_logprob'] - results[2]['mean_logprob']),
        'suffix_repeat_difference': abs(results[1]['mean_logprob'] - results[3]['mean_logprob']),
        'full_suffix_difference': abs(results[0]['mean_logprob'] - results[1]['mean_logprob']),
        'new_generation_requests': 0, 'original_files_changed': False, 'production_change': False}
    (output / 'complete.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    for name in ['turn', 'output', 'config', 'tokenizer']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    main(a.turn, a.output, a.config, a.tokenizer)
