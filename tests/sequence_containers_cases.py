"""Independent list/deque/heapq observations for persistent source containers."""
from collections import deque
import heapq
import json
import random


def literal(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def corpus():
    rng = random.Random(274)
    actions = []
    sequence = []
    expected = []
    popped = []
    for step in range(240):
        action = rng.randrange(5)
        value = rng.randrange(-50, 51)
        index = rng.randrange(-2, len(sequence) + 2)
        output = 0
        if action == 0:
            sequence.insert(0, value)
        elif action == 1:
            sequence.append(value)
        elif action == 2 and sequence:
            output = sequence.pop(0)
        elif action == 3 and sequence:
            output = sequence.pop()
        elif action == 4 and 0 <= index < len(sequence):
            sequence[index] = value
        actions.append(f'Action({action},{index},{value})')
        expected.append(list(sequence))
        popped.append(output)
    schedule = '[' + ','.join(actions) + ']'
    q = deque()
    stack = []
    queue_states, stack_states, ends, values = [], [], [], []
    for step in range(150):
        insert = rng.randrange(5) < 3
        value = rng.randrange(-100, 101)
        if insert:
            q.append(value)
            stack.append(value)
        elif q:
            q.popleft()
            stack.pop()
        ends.append(insert)
        values.append(value)
        queue_states.append(list(q))
        stack_states.append(stack[::-1])
    heap = []
    heap_actions, heap_values, heap_states, heap_popped = [], [], [], []
    for step in range(180):
        insert = rng.randrange(5) < 3
        value = rng.randrange(-40, 41)
        result = 0
        if insert:
            heapq.heappush(heap, value)
        elif heap:
            result = heapq.heappop(heap)
        heap_actions.append(insert)
        heap_values.append(value)
        heap_states.append(sorted(heap))
        heap_popped.append(result)
    source = '''module sequence_cases;
import "std/sequence.nex" as seq;
import "std/fifo.nex" as fifo;
import "std/lifo.nex" as lifo;
import "std/heap.nex" as heap;
import "std/list.nex" as lists;
struct Action{kind:i64;index:i64;value:i64;}
struct Job{priority:i64;serial:i64;label:str;}
fn job_compare(a:Job,b:Job)->i64{
 if a.priority<b.priority{return -1;}if a.priority>b.priority{return 1;}
 if a.serial<b.serial{return -1;}if a.serial>b.serial{return 1;}return 0;
}
fn boundaries()->unit{
 let empty:seq::Sequence<i64>=seq::empty();
 assert(seq::items(empty)==[]&&seq::size(empty)==0&&seq::height(empty)==0&&seq::validate(empty));
 assert(error_code(seq::get(empty,-9223372036854775808))=="E_BOUNDS");
 assert(error_code(seq::get(empty,9223372036854775807))=="E_BOUNDS");
 assert(error_code(seq::replace(empty,0,1))=="E_BOUNDS");
 assert(error_code(seq::pop_front(empty))=="E_EMPTY"&&error_code(seq::pop_back(empty))=="E_EMPTY");
 assert(error_code(seq::peek_front(empty))=="E_EMPTY"&&error_code(seq::peek_back(empty))=="E_EMPTY");
 assert(error_code(fifo::dequeue(fifo::empty<i64>()))=="E_EMPTY");
 assert(error_code(fifo::peek(fifo::empty<i64>()))=="E_EMPTY");
 assert(error_code(lifo::pop(lifo::empty<i64>()))=="E_EMPTY"&&error_code(lifo::peek(lifo::empty<i64>()))=="E_EMPTY");
 assert(error_code(heap::pop(heap::ascending<i64>()))=="E_EMPTY"&&error_code(heap::peek(heap::descending<i64>()))=="E_EMPTY");
 let text:seq::Sequence<str>=seq::push_back(seq::push_front(seq::empty<str>(),"λ\\u0000🙂"),"last");
 assert(seq::items(text)==["λ\\u0000🙂","last"]&&seq::validate(text));
 let next:seq::Sequence<str>=unwrap(seq::replace(text,1,"new"));
 assert(seq::items(text)==["λ\\u0000🙂","last"]&&seq::items(next)==["λ\\u0000🙂","new"]);
 // Valid four-element trees force each double rotation during end removal.
 let one:seq::Node<i64>=seq::Node(1,[],[],1,1);let two:seq::Node<i64>=seq::Node(2,[],[],1,1);
 let three:seq::Node<i64>=seq::Node(3,[],[],1,1);let four:seq::Node<i64>=seq::Node(4,[],[],1,1);
 let right:seq::Sequence<i64>=seq::Sequence([seq::Node(2,[one],[seq::Node(4,[three],[],2,2)],3,4)]);
 let left:seq::Sequence<i64>=seq::Sequence([seq::Node(3,[seq::Node(1,[],[two],2,2)],[four],3,4)]);
 assert(seq::validate(right)&&seq::validate(left));
 let after_right:seq::Sequence<i64>=unwrap(seq::pop_front(right)).sequence;
 let after_left:seq::Sequence<i64>=unwrap(seq::pop_back(left)).sequence;
 assert(seq::items(after_right)==[2,3,4]&&seq::height(after_right)==2&&seq::validate(after_right));
 assert(seq::items(after_left)==[1,2,3]&&seq::height(after_left)==2&&seq::validate(after_left));
}
fn sequence_trace()->unit{
 let actions:list<Action>=ACTIONS;let expected:list<list<i64>>=SEQ_EXPECTED;let popped:list<i64>=SEQ_POPPED;
 var state:seq::Sequence<i64>=seq::empty();var step:i64=0;
 while step<len(actions){
  let before:seq::Sequence<i64>=state;let old:list<i64>=seq::items(before);let action:Action=actions[step];
  if action.kind==0{state=seq::push_front(state,action.value);}
  if action.kind==1{state=seq::push_back(state,action.value);}
  if action.kind==2{let result:result<seq::Popped<i64>>=seq::pop_front(state);if len(old)==0{assert(error_code(result)=="E_EMPTY");}else{assert(unwrap(result).value==popped[step]);state=unwrap(result).sequence;}}
  if action.kind==3{let result:result<seq::Popped<i64>>=seq::pop_back(state);if len(old)==0{assert(error_code(result)=="E_EMPTY");}else{assert(unwrap(result).value==popped[step]);state=unwrap(result).sequence;}}
  if action.kind==4{let result:result<seq::Sequence<i64>>=seq::replace(state,action.index,action.value);if action.index<0||action.index>=len(old){assert(error_code(result)=="E_BOUNDS");}else{state=unwrap(result);}}
  assert(seq::items(before)==old&&seq::items(state)==expected[step]&&seq::size(state)==len(expected[step])&&seq::validate(state));
  var index:i64=0;while index<seq::size(state){assert(unwrap(seq::get(state,index))==expected[step][index]);index=index+1;}
  let front:seq::Sequence<i64>=seq::push_front(before,777);let back:seq::Sequence<i64>=seq::push_back(before,888);
  assert(seq::items(front)==[777]+old&&seq::items(back)==old+[888]&&seq::items(before)==old);
  if !seq::is_empty(state){assert(unwrap(seq::peek_front(state))==expected[step][0]);assert(unwrap(seq::peek_back(state))==expected[step][len(expected[step])-1]);}
  step=step+1;
 }
}
fn ends_trace()->unit{
 let inserts:list<bool>=END_ACTIONS;let values:list<i64>=END_VALUES;
 let expected_q:list<list<i64>>=FIFO_EXPECTED;let expected_s:list<list<i64>>=LIFO_EXPECTED;
 var q:fifo::Queue<i64>=fifo::empty();var s:lifo::Stack<i64>=lifo::empty();var step:i64=0;
 while step<len(inserts){
  let oldq:fifo::Queue<i64>=q;let olds:lifo::Stack<i64>=s;let qitems:list<i64>=fifo::items(q);let sitems:list<i64>=lifo::items(s);
  if inserts[step]{q=fifo::enqueue(q,values[step]);s=lifo::push_value(s,values[step]);}
  else{if !fifo::is_empty(q){assert(unwrap(fifo::dequeue(q)).value==qitems[0]);assert(unwrap(lifo::pop(s)).value==sitems[0]);q=unwrap(fifo::dequeue(q)).queue;s=unwrap(lifo::pop(s)).stack;}}
  assert(fifo::items(q)==expected_q[step]&&lifo::items(s)==expected_s[step]);
  assert(fifo::items(oldq)==qitems&&lifo::items(olds)==sitems&&fifo::validate(q)&&lifo::validate(s));
  assert(fifo::size(q)==len(expected_q[step])&&lifo::size(s)==len(expected_s[step]));
  if !fifo::is_empty(q){assert(unwrap(fifo::peek(q))==expected_q[step][0]&&unwrap(lifo::peek(s))==expected_s[step][0]);}
  step=step+1;
 }
}
fn heap_trace()->unit{
 let inserts:list<bool>=HEAP_ACTIONS;let values:list<i64>=HEAP_VALUES;let expected:list<list<i64>>=HEAP_EXPECTED;let popped:list<i64>=HEAP_POPPED;
 var state:heap::Heap<i64>=heap::ascending();var step:i64=0;
 while step<len(inserts){
  let before:heap::Heap<i64>=state;let old:list<i64>=heap::sorted(before);
  if inserts[step]{state=heap::push_value(state,values[step]);}
  else{let next:result<heap::Popped<i64>>=heap::pop(state);if len(old)==0{assert(error_code(next)=="E_EMPTY");}else{assert(unwrap(next).value==popped[step]);state=unwrap(next).heap;}}
  assert(heap::sorted(state)==expected[step]&&heap::sorted(before)==old&&heap::validate(state));
  assert(heap::size(state)==len(expected[step])&&lists::sort(heap::items(state))==expected[step]);
  if !heap::is_empty(state){assert(unwrap(heap::peek(state))==expected[step][0]);}
  step=step+1;
 }
}
fn heap_policies()->unit{
 var direction:i64=1;
 let policy:fn(Job,Job)->i64=fn(a:Job,b:Job)->i64{return direction*job_compare(a,b);};direction= -1;
 var jobs:heap::Heap<Job>=heap::empty(policy);
 jobs=heap::push_value(heap::push_value(heap::push_value(jobs,Job(2,0,"two")),Job(1,2,"second")),Job(1,1,"first"));
 let values:list<Job>=heap::sorted(jobs);assert(values[0].label=="first"&&values[1].label=="second"&&values[2].label=="two"&&heap::validate(jobs));
 let a:heap::Heap<i64>=heap::push_value(heap::push_value(heap::ascending<i64>(),-9223372036854775808),1);
 let b:heap::Heap<i64>=heap::push_value(heap::push_value(heap::descending<i64>(),9223372036854775807),0);
 let merged:heap::Heap<i64>=heap::merge(a,b);
 assert(heap::sorted(merged)==[-9223372036854775808,0,1,9223372036854775807]&&heap::validate(merged));
 assert(heap::sorted(a)==[-9223372036854775808,1]&&heap::sorted(b)==[9223372036854775807,0]);
 assert(heap::sorted(heap::merge(a,a))==[-9223372036854775808,-9223372036854775808,1,1]);
 let floats:heap::Heap<f64>=heap::push_value(heap::push_value(heap::push_value(heap::ascending<f64>(),1.5),-0.0),0.0);
 assert(heap::sorted(floats)==[0.0,0.0,1.5]&&heap::validate(floats));
}
fn bulk()->unit{
 var state:seq::Sequence<i64>=seq::empty();var index:i64=0;
 while index<1024{if index%2==0{state=seq::push_back(state,index);}else{state=seq::push_front(state,index);}index=index+1;}
 assert(seq::size(state)==1024&&seq::height(state)<20&&seq::validate(state));
 let old:seq::Sequence<i64>=state;let expected:list<i64>=seq::items(old);index=0;
 while index<1024{assert(unwrap(seq::pop_front(state)).value==expected[index]);state=unwrap(seq::pop_front(state)).sequence;index=index+1;}
 assert(seq::is_empty(state)&&seq::items(old)==expected&&seq::validate(old));
 var deep:lifo::Stack<i64>=lifo::empty();index=0;
 while index<16384{deep=lifo::push_value(deep,index);index=index+1;}
 assert(lifo::size(deep)==16384&&lifo::validate(deep));
 let saved:lifo::Stack<i64>=deep;let listed:list<i64>=lifo::items(deep);assert(listed[0]==16383&&listed[16383]==0);
 var sum:i64=0;while !lifo::is_empty(deep){let next:lifo::Popped<i64>=unwrap(lifo::pop(deep));sum=sum+next.value;deep=next.stack;}
 assert(sum==134209536&&lifo::size(saved)==16384&&lifo::validate(saved));
 var chain:heap::Heap<i64>=heap::ascending();index=4096;
 while index>0{chain=heap::push_value(chain,index);index=index-1;}
 assert(heap::size(chain)==4096&&heap::rank(chain)==1&&heap::validate(chain));
 assert(len(heap::items(chain))==4096);let sorted:list<i64>=heap::sorted(chain);assert(sorted[0]==1&&sorted[4095]==4096&&heap::size(chain)==4096);
}
fn representations()->unit{
 let leaf:seq::Node<i64>=seq::Node(1,[],[],1,1);
 assert(!seq::validate(seq::Sequence([leaf,leaf])));
 assert(!seq::validate(seq::Sequence([seq::Node(1,[],[],1,9223372036854775807)])));
 assert(!seq::validate(seq::Sequence([seq::Node(1,[],[],0,1)])));
 let link:lifo::Node<i64>=lifo::Node(1,[],1);
 assert(!lifo::validate(lifo::Stack([link,link])));
 assert(!lifo::validate(lifo::Stack([lifo::Node(1,[link],1)])));
 let heapnode:heap::Node<i64>=heap::Node(1,[],[],1,1);
 let base:heap::Heap<i64>=heap::ascending();
 assert(!heap::validate(heap::Heap([heapnode,heapnode],base.compare)));
 assert(!heap::validate(heap::Heap([heap::Node(1,[],[],64,1)],base.compare)));
 assert(!heap::validate(heap::Heap([heap::Node(2,[heapnode],[],1,2)],base.compare)));
 assert(!heap::validate(heap::Heap([heap::Node(1,[],[heapnode],2,2)],base.compare)));
 assert(!heap::validate(heap::Heap([heap::Node(1,[heapnode],[],1,-1)],base.compare)));
}
fn main()->unit!{io}{boundaries();sequence_trace();ends_trace();heap_trace();heap_policies();bulk();representations();print("sequence-oracle-ok");}
'''
    replacements = {'ACTIONS': schedule, 'SEQ_EXPECTED': literal(expected), 'SEQ_POPPED': literal(popped),
                    'END_ACTIONS': literal(ends), 'END_VALUES': literal(values), 'FIFO_EXPECTED': literal(queue_states),
                    'LIFO_EXPECTED': literal(stack_states), 'HEAP_ACTIONS': literal(heap_actions),
                    'HEAP_VALUES': literal(heap_values), 'HEAP_EXPECTED': literal(heap_states), 'HEAP_POPPED': literal(heap_popped)}
    # Replace longer placeholders first: ACTIONS is a suffix of HEAP_ACTIONS.
    for key in sorted(replacements, key=len, reverse=True):
        source = source.replace(key, replacements[key])
    return source, {'sequence_operations': 240, 'FIFO_LIFO_operations_each': 150,
                    'heap_operations': 180, 'AVL_bulk': 1024, 'deep_stack': 16384,
                    'heap_left_chain': 4096, 'malformed_representations': 10}
