"""Deterministic command traces for the unmodified Java and manual NEX ports."""
import json
from pathlib import Path

ZERO = {'default', 'from_null', 'copy', 'alias', 'add_null', 'offer_null', 'clear',
        'peek', 'poll', 'remove', 'element', 'size', 'max_size', 'empty', 'full',
        'at_capacity', 'iterator', 'iterator_alias', 'has_next', 'next', 'next_alias',
        'iterator_remove', 'iterator_remove_alias', 'snapshot', 'saved', 'alias_items',
        'same_queue', 'same_iterator'}
ONE = {'new', 'add', 'offer', 'add_alias', 'get'}
def command(operation, *values):
    assert operation == 'from' or operation in ZERO and not values or operation in ONE and len(values) == 1
    assert all(type(v) is int and -(2**63) <= v < 2**63 for v in values)
    return {'operation':operation, 'values':list(values)}

def cases():
    c = command
    result = [
        {'name':'empty-and-invalid-construction', 'commands':[
            c('new',3), c('peek'), c('poll'), c('remove'), c('element'), c('get',-1),
            c('get',0), c('iterator'), c('iterator_remove'), c('has_next'), c('next'),
            c('new',0), c('new',-1), c('from'), c('from_null'), c('copy'), c('size'),
            c('max_size'), c('empty'), c('full'), c('at_capacity')]},
        {'name':'one-slot-and-null-before-eviction', 'commands':[
            c('new',1), c('add',-9223372036854775808), c('snapshot'), c('add_null'),
            c('offer_null'), c('element'), c('full'), c('at_capacity'),
            c('offer',9223372036854775807), c('saved'), c('get',0), c('get',1),
            c('poll'), c('poll'), c('remove'), c('clear'), c('add',0), c('remove')]},
        {'name':'queue-alias-snapshot-and-copy', 'commands':[
            c('from',1,2,3), c('alias'), c('same_queue'), c('snapshot'), c('add_alias',4),
            c('saved'), c('copy'), c('same_queue'), c('add_alias',5), c('alias_items'),
            c('peek'), c('add',6), c('alias_items'), c('clear'), c('copy'),
            c('from_null'), c('alias_items'), c('saved')]},
        {'name':'iterator-alias-and-last-successful-next', 'commands':[
            c('from',10,20,30), c('iterator'), c('iterator_alias'), c('same_iterator'),
            c('next_alias'), c('iterator_remove'), c('iterator_remove_alias'),
            c('next'), c('next_alias'), c('has_next'), c('next'),
            c('iterator_remove_alias'), c('iterator_remove'), c('iterator'), c('same_iterator')]},
        {'name':'default-capacity-and-reuse', 'commands':[
            c('default'), c('max_size'), *[c('offer',i) for i in range(40)],
            c('snapshot'), c('clear'), c('saved'), c('full'), c('at_capacity'),
            c('from',7,7,7), c('remove'), c('add',8), c('get',0), c('get',2)]},
    ]
    for capacity in range(1,7):
        for wrapped in (False,True):
            extra = capacity - 1 if wrapped else 0
            for removed in range(capacity):
                ops = [c('new',capacity)] + [c('add',i) for i in range(capacity+extra)]
                ops += [c('iterator'), c('has_next'), c('iterator_remove')]
                ops += [c('next') for _ in range(removed+1)]
                ops += [c('iterator_remove'), c('has_next')]
                ops += [c('next') for _ in range(capacity-removed-1)]
                ops += [c('has_next'), c('next'), c('iterator_remove'), c('iterator_remove')]
                result.append({'name':f'remove-{capacity}-{int(wrapped)}-{removed}', 'commands':ops})
    # Mutation through Iterator.remove repeatedly reaches the source's head fast
    # path; the matrix above also reaches contiguous and wrapped shifting paths.
    result.append({'name':'iterator-remove-every-element', 'commands':[
        c('from',1,2,3,4,5), c('iterator'),
        *[op for _ in range(5) for op in (c('next'),c('iterator_remove'))],
        c('has_next'), c('next'), c('poll'), c('clear'), c('add',42)]})
    return result

def protocol(traces=None):
    rows = []
    for trace in traces if traces is not None else cases():
        rows.append('trace\t'+trace['name'])
        for op in trace['commands']:
            rows.append('\t'.join([op['operation'],*map(str,op['values'])]))
    return '\n'.join(rows)+'\n'

def source(traces=None):
    traces = traces if traces is not None else cases()
    literal = lambda s: json.dumps(s,ensure_ascii=False)
    data = ',\n'.join('Trace('+literal(t['name'])+',['+','.join(
        'Command('+literal(c['operation'])+','+json.dumps(c['values'],separators=(',',':'))+')'
        for c in t['commands'])+'])' for t in traces)
    template = Path(__file__).parent/'fixtures/java-circular-fifo/driver.nex.in'
    return template.read_text().replace('@CASES@',data)
