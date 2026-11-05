"""Validate paired JSONL, frozen tokenizer IDs and loss masks without training."""
import argparse
import hashlib
import json
from pathlib import Path


def validate(root, tokenizer=None):
    manifest = json.loads((root / 'manifest.json').read_text())
    identities = []
    summaries = {}
    for name in ['method-paired', 'expert-paired']:
        path = root / name / 'train.jsonl'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['files'][name + '/train.jsonl']['sha256']
        ids = []
        tokens = 0
        for line in path.open():
            row = json.loads(line)
            ids.append(row['provenance']['input_identity'])
            assert row['training_admitted']
            assert len(row['input_ids']) == len(row['labels']) == len(row['assistant_loss_mask']) == row['total_tokens']
            assert sum(row['assistant_loss_mask']) == row['supervised_tokens']
            assert all(label == (token if mask else -100) for token, label, mask in zip(row['input_ids'], row['labels'], row['assistant_loss_mask']))
            assert len(row['messages']) % 2 == 0
            for index, message in enumerate(row['messages']):
                assert message['role'] == ('user' if index % 2 == 0 else 'assistant')
                assert '<expert_reference>' not in message['content']
            if tokenizer is not None:
                assert tokenizer.identity == row['tokenizer_identity']
                rendered = tokenizer.apply_chat_template(row['messages'], tokenize=False, add_generation_prompt=False)
                assert tokenizer.encode(rendered) == row['input_ids']
            tokens += row['supervised_tokens']
        assert len(ids) == manifest['paired'] and len(ids) == len(set(ids))
        identities.append(ids)
        summaries[name] = {'rows': len(ids), 'supervised_tokens': tokens}
    assert identities[0] == identities[1], 'Pair ordering/identity mismatch'
    return {'passed': True, 'datasets': summaries, 'full_tokenizer_reencoded': tokenizer is not None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--tokenizer', type=Path)
    args = parser.parse_args()
    tokenizer = None
    if args.tokenizer:
        from append_rewrite.terminus.tokenizer import PinnedTokenizer
        tokenizer = PinnedTokenizer(args.tokenizer)
    print(json.dumps(validate(args.root, tokenizer), indent=2))
