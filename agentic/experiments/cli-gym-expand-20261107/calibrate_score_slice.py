"""Compare candidate-only native logprobs with a preserved full-score block.

Zero-generation requests only, through the selected global scoring allocator.
This finite calibration never changes production config or executes actions.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path

from append_rewrite.collect import dump
from append_rewrite.terminus.scoring import RenderedCandidate, analyze_native
from append_rewrite.terminus.suffix_score import NativeSuffixStreamClient, score_slot
from append_rewrite.terminus.tokenizer import PinnedTokenizer


def read(path):
    return json.loads(path.read_bytes() if path.exists()
                      else gzip.decompress(path.with_name(path.name + '.gz').read_bytes()))


def main():
    p = argparse.ArgumentParser(__doc__)
    for key in ['source-turn', 'config', 'tokenizer', 'output']:
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--reuse-score', type=Path)
    args = p.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    tok = PinnedTokenizer(args.tokenizer)
    client = NativeSuffixStreamClient(args.config)
    cached = read(args.reuse_score / 'score.json') if args.reuse_score else None

    def check(index):
        source = args.source_turn / f'score-{index}'
        request, old = read(source / 'request.json'), read(source / 'score.json')
        assert request['logprob_start_len'] == 0
        assert request['sampling_params']['max_new_tokens'] == 0
        text = request['text']
        assert hashlib.sha256(text.encode()).hexdigest() == old['rendered_text_sha256']
        assert tok.identity == old['tokenizer_identity']
        assert hashlib.sha256(tok.chat_template.encode()).hexdigest() == old['template_sha256']
        rendered = RenderedCandidate(
            text, tuple(tok.encode(text, add_special_tokens=False)),
            old['candidate_start'], old['history_sha256'], old['action_sha256'],
            tok.identity, old['template_sha256'],
        )
        rendered.validate()
        reused = cached and cached['rendered_text_sha256'] == old['rendered_text_sha256']
        if reused:
            intent = read(args.reuse_score / 'intent.json')
            assert intent['endpoint'] == client.endpoint
            assert intent['model_id'] == client.config['model_id']
            new = analyze_native(read(args.reuse_score / 'response.json'), rendered,
                                 logprob_start=rendered.candidate_start - 1)
            new['request_elapsed_sec'] = cached['request_elapsed_sec']
            wait = 0.0
            dump(args.output / f'reused-score-{index}.json', {
                'source': str(args.reuse_score), 'new_scoring_requests': 0,
            })
        else:
            with score_slot() as wait:
                new = client.score(rendered, journal=args.output / f'score-{index}')
        result = {
            'index': index, 'old_mean': old['mean_logprob'],
            'new_mean': new['mean_logprob'],
            'delta': new['mean_logprob'] - old['mean_logprob'],
            'action_sha256': old['action_sha256'],
            'full_input_tokens': len(rendered.input_ids),
            'returned_rows': len(rendered.input_ids) - rendered.candidate_start + 1,
            'candidate_tokens': new['token_count'],
            'queue_wait_sec': wait, 'request_sec': new['request_elapsed_sec'],
            'token_alignment_verified': new['input_token_alignment_verified'],
            'new_scoring_requests': 0 if reused else 1,
        }
        dump(args.output / f'comparison-{index}.json', result)
        return result

    # One complete pool, not a cherry-picked winner. Four threads also obey the
    # process-shared FIFO capacity used by production.
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(check, range(8)))
    old_winner = max(results, key=lambda x: x['old_mean'])
    new_winner = max(results, key=lambda x: x['new_mean'])
    report = {
        'passed': old_winner['action_sha256'] == new_winner['action_sha256']
                  and all(abs(x['delta']) < 1e-3 for x in results),
        'old_winner_index': old_winner['index'],
        'new_winner_index': new_winner['index'], 'results': results,
        'new_generation_requests': 0, 'production_changed': False,
        'note': 'One preserved block; no general equivalence or speedup claim.',
    }
    dump(args.output / 'result.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
