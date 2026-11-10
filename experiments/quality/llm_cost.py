#!/usr/bin/env python3
"""Summarize a pinned, local multi-model task ledger without calling any API."""
import argparse
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import re
import stat
import sys


class LedgerError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LedgerError(message)


def label(value):
    require(isinstance(value, str) and 0 < len(value) <= 512 and '\0' not in value,
            'expected a bounded nonempty label')
    value.encode('utf-8')
    return value


def count(value):
    require(type(value) is int and 0 <= value <= 10**12, 'expected a nonnegative integer count')
    return value


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'expected a SHA256 pin')
    return value


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(raw):
    def invalid(value):
        raise LedgerError('non-finite JSON value: ' + value)
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeError, ValueError) as error:
        raise LedgerError('invalid UTF-8 JSON: ' + str(error)) from error


def read(path, limit):
    require(stat.S_ISREG(path.stat().st_mode), 'evidence must be a regular file')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'evidence exceeds its byte budget')
    return raw


def ratio(numerator, denominator):
    if not denominator:
        return None
    value = Fraction(numerator, denominator)
    return {'numerator': value.numerator, 'denominator': value.denominator}


def median(values):
    if not values:
        return None
    values = sorted(values)
    center = len(values) // 2
    return ratio(values[center] + values[(len(values) - 1) // 2], 2)


def summarize(path):
    with localcontext() as context:
        context.prec = 64
        return _summarize(path)


def _summarize(path):
    path = Path(path).resolve(strict=True)
    raw = read(path, 16 * 1024**2)
    campaign = decode(raw)
    require(isinstance(campaign, dict) and campaign.get('schema') == 'nex.llm-cost-ledger/1',
            'expected nex.llm-cost-ledger/1')
    require(campaign.get('data_kind') in ('observed', 'synthetic'), 'declare observed or synthetic data')
    languages = ['nex', 'cpp', 'python']
    require(campaign.get('languages') == languages, 'the matched languages must be nex, cpp, python')
    repeats = count(campaign.get('repeats'))
    require(0 < repeats <= 1000, 'invalid repeat count')
    artifacts, bytes_read = {}, 0

    def artifact(reference):
        nonlocal bytes_read
        require(isinstance(reference, dict), 'expected an evidence reference')
        name = label(reference.get('path'))
        rel = Path(name)
        require(not rel.is_absolute() and rel.as_posix() == name and
                all(part not in ('', '.', '..') for part in name.split('/')) and '\\' not in name,
                'evidence paths must be relative portable paths')
        target = (path.parent / rel).resolve(strict=True)
        require(target.is_relative_to(path.parent), 'evidence must stay inside the ledger directory')
        expected = digest(reference.get('sha256'))
        if name not in artifacts:
            content = read(target, 32 * 1024**2)
            bytes_read += len(content)
            require(bytes_read <= 256 * 1024**2, 'campaign evidence exceeds its total byte budget')
            actual = hashlib.sha256(content).hexdigest()
            require(actual == expected, 'evidence SHA256 mismatch: ' + name)
            artifacts[name] = (actual, content)
        require(artifacts[name][0] == expected, 'conflicting evidence pins: ' + name)
        return artifacts[name][1]

    artifact(campaign.get('protocol'))
    models, identities = {}, set()
    require(isinstance(campaign.get('models'), list), 'models must be an array')
    for model in campaign['models']:
        require(isinstance(model, dict), 'invalid model')
        name = label(model.get('id'))
        require(name not in models, 'duplicate model')
        for field in ('provider', 'revision', 'tokenizer'):
            label(model.get(field))
        identity = (model['provider'], model['revision'])
        require(identity not in identities, 'model aliases do not count as independent revisions')
        identities.add(identity)
        digest(model.get('settings_sha256'))
        models[name] = {field: model[field] for field in
                        ('id', 'provider', 'revision', 'tokenizer', 'settings_sha256')}
    tasks = {}
    require(isinstance(campaign.get('tasks'), list), 'tasks must be an array')
    for task in campaign['tasks']:
        require(isinstance(task, dict), 'invalid task')
        name = label(task.get('id'))
        require(name not in tasks, 'duplicate task')
        tasks[name] = digest(task.get('contract_sha256'))
    require(models and tasks and len(models) * len(tasks) * repeats * 3 <= 100000,
            'expected a nonempty bounded campaign matrix')
    runs = campaign.get('runs')
    require(isinstance(runs, list) and len(runs) <= 100000, 'runs must be a bounded array')
    observed, trial_ids, requests = {}, set(), set()
    groups = {(model, language): [] for model in models for language in languages}
    for run in runs:
        require(isinstance(run, dict), 'invalid run')
        trial = label(run.get('id'))
        require(trial not in trial_ids, 'duplicate trial id')
        trial_ids.add(trial)
        model, task, language = run.get('model'), run.get('task'), run.get('language')
        repeat = count(run.get('repeat'))
        require(model in models and task in tasks and language in languages and repeat < repeats,
                'run is outside the declared campaign matrix')
        key = (model, task, repeat, language)
        require(key not in observed, 'duplicate matrix slot')
        status = run.get('status')
        require(status in ('accepted', 'failed', 'timeout', 'budget_exhausted'), 'invalid terminal status')
        acceptance = decode(artifact(run.get('acceptance')))
        require(isinstance(acceptance, dict) and acceptance.get('schema') == 'nex.llm-acceptance/1' and
                acceptance.get('trial_id') == trial and acceptance.get('contract_sha256') == tasks[task] and
                type(acceptance.get('passed')) is bool, 'acceptance receipt does not bind this trial/contract')
        checks = acceptance.get('checks')
        require(isinstance(checks, list) and 0 < len(checks) <= 10000, 'acceptance needs explicit checks')
        names = set()
        for check in checks:
            require(isinstance(check, dict), 'invalid acceptance check')
            name = label(check.get('name'))
            require(name not in names and type(check.get('exit_code')) is int, 'invalid acceptance check result')
            names.add(name)
        require(not acceptance['passed'] or all(check['exit_code'] == 0 for check in checks),
                'passed acceptance contains a failed check')
        require((status == 'accepted') == acceptance['passed'], 'status contradicts acceptance receipt')
        calls = run.get('calls')
        require(isinstance(calls, list) and 0 < len(calls) <= 10000, 'record every attempted model call')
        row = {'accepted': status == 'accepted', 'status': status, 'wall_ms': count(run.get('wall_ms')),
               'calls': len(calls), 'unknown_usage': 0, 'unknown_cache': 0,
               'input': 0, 'cached': 0, 'uncached': 0, 'output': 0,
               'costs': {}, 'unknown_cost': 0}
        call_ids = set()
        for call in calls:
            require(isinstance(call, dict), 'invalid model call')
            request = label(call.get('id'))
            identity = (models[model]['provider'], request)
            require(request not in call_ids and identity not in requests, 'duplicate provider request')
            call_ids.add(request)
            requests.add(identity)
            artifact(call.get('evidence'))
            usage = call.get('usage')
            if usage is None:
                row['unknown_usage'] += 1
                row['unknown_cache'] += 1
            else:
                require(isinstance(usage, dict), 'invalid token usage')
                incoming = count(usage.get('input_tokens'))
                outgoing = count(usage.get('output_tokens'))
                require('cached_input_tokens' in usage, 'declare cached input explicitly, using null when unknown')
                cached = usage['cached_input_tokens']
                if cached is None:
                    row['unknown_cache'] += 1
                else:
                    cached = count(cached)
                    require(cached <= incoming, 'cached input must be a subset of input tokens')
                    row['cached'] += cached;row['uncached'] += incoming - cached
                row['input'] += incoming;row['output'] += outgoing
            cost = call.get('confirmed_cost')
            if cost is None:
                row['unknown_cost'] += 1
            else:
                require(isinstance(cost, dict) and isinstance(cost.get('amount'), str) and
                        re.fullmatch('[A-Z]{3}', cost.get('currency', '')), 'invalid confirmed cost')
                require(re.fullmatch(r'[0-9]{1,12}(\.[0-9]{1,12})?', cost['amount']), 'invalid cost amount')
                amount = Decimal(cost['amount'])
                currency = cost['currency'];row['costs'][currency] = row['costs'].get(currency, Decimal(0)) + amount
        observed[key] = trial;groups[model, language].append(row)
    expected = set(itertools.product(models, tasks, range(repeats), languages))
    missing = sorted(expected - observed.keys())
    results = {}
    for (model, language), rows in groups.items():
        accepted = sum(row['accepted'] for row in rows)
        unknown = sum(row['unknown_usage'] for row in rows)
        tokens = sum(row['input'] + row['output'] for row in rows)
        costs = {}
        for row in rows:
            for currency, amount in row['costs'].items():
                costs[currency] = costs.get(currency, Decimal(0)) + amount
        complete = len(rows) == len(tasks) * repeats
        trials = [row['input'] + row['output'] for row in rows if not row['unknown_usage']]
        results.setdefault(model, {})[language] = {
            'attempted_trials': len(rows), 'accepted_trials': accepted,
            'terminal_statuses': {s: sum(row['status'] == s for row in rows)
                                  for s in ('accepted', 'failed', 'timeout', 'budget_exhausted')},
            'matrix_complete': complete, 'calls': sum(row['calls'] for row in rows),
            'calls_without_usage': unknown, 'usage_complete': not unknown,
            'calls_without_cache_usage': sum(row['unknown_cache'] for row in rows),
            'cache_usage_complete': not any(row['unknown_cache'] for row in rows),
            'known_input_tokens': sum(row['input'] for row in rows),
            'known_cached_input_tokens': sum(row['cached'] for row in rows),
            'known_uncached_input_tokens': sum(row['uncached'] for row in rows),
            'known_output_tokens': sum(row['output'] for row in rows), 'known_total_tokens': tokens,
            'all_tokens_per_accepted_trial': ratio(tokens, accepted) if complete and not unknown else None,
            'median_trial_tokens': median(trials) if complete and not unknown else None,
            'p95_trial_tokens': sorted(trials)[(95 * len(trials) + 99) // 100 - 1] if complete and trials and not unknown else None,
            'total_wall_ms': sum(row['wall_ms'] for row in rows),
            'confirmed_costs': {currency: str(amount) for currency, amount in sorted(costs.items())},
            'calls_without_confirmed_cost': sum(row['unknown_cost'] for row in rows)}
    comparisons = {}
    for model, rows in results.items():
        nex = rows['nex'];comparisons[model] = {}
        for language in ('cpp', 'python'):
            baseline = rows[language]
            comparable = all(row['matrix_complete'] and row['usage_complete'] and row['accepted_trials']
                             for row in (nex, baseline))
            comparisons[model][language] = {
                'nex_to_baseline_tokens_per_accepted_trial': ratio(
                    nex['known_total_tokens'] * baseline['accepted_trials'],
                    baseline['known_total_tokens'] * nex['accepted_trials']) if comparable else None,
                'nex_success_rate_at_least_baseline': nex['accepted_trials'] >= baseline['accepted_trials'] if comparable else None}
    usage_complete = all(row['calls_without_usage'] == 0 for rows in results.values() for row in rows.values())
    cache_complete = all(row['cache_usage_complete'] for rows in results.values() for row in rows.values())
    return {'schema': 'nex.llm-cost-summary/1', 'valid': True, 'data_kind': campaign['data_kind'],
            'ledger_sha256': hashlib.sha256(raw).hexdigest(), 'models': list(models.values()),
            'tasks': [{'id': name, 'contract_sha256': pin} for name, pin in tasks.items()],
            'repeats': repeats, 'matrix_complete': not missing, 'missing_trials': missing,
            'usage_complete_for_observed_calls': usage_complete,
            'cache_usage_complete_for_observed_calls': cache_complete, 'results': results, 'comparisons': comparisons,
            'eligible_for_comparison_review': campaign['data_kind'] == 'observed' and not missing and
                usage_complete and len(models) >= 3 and repeats >= 2,
            'artifact_hashes_verified': {name: value[0] for name, value in sorted(artifacts.items())},
            'provider_usage_and_billing_authenticity_verified': False,
            'acceptance_semantics_and_protocol_fairness_verified': False,
            'actual_multi_model_benchmark_completed_by_this_tool': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        require(sys.version_info >= (3, 10), 'LLM cost accounting requires Python 3.10+')
        result = summarize(args.ledger)
        code = 0 if result['matrix_complete'] and result['usage_complete_for_observed_calls'] else 1
        text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(text)
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout.buffer.write(text.encode('utf-8'))
        else:
            print(text, end='')
        return code
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation) as error:
        print(json.dumps({'schema': 'nex.llm-cost-summary/1', 'valid': False, 'error': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
