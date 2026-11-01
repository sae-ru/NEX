# Source contracts: explicit language028 development

This is the development contract for the version-selected C++ frontend. Ordinary
CLI projects still use language0.27. An installed0.156 compiler does not accept
this syntax. Public028 CLI/project/SDK delivery and matching platform acceptance
are required before advertising028 as the ordinary language.

An ordinary named source function can declare ordered clauses after its effects:

~~~nex
fn increment(x:i64)->i64
  requires(x>=0)
  ensures(value=>value==x+1)
{ return x+1; }

fn observe(text:str)->unit !{io}
  requires(len(text)>0)
  ensures(len(text)>0)
{ print(text); }
~~~

For a non-unit result, each ensures clause introduces its own immutable result
binding before =>. It cannot shadow a parameter. A unit ensures clause has no
result binder. Clauses see original immutable parameters and the final normal
result, not body locals. Requires and ensures expressions must be pure bool
expressions. They retain the declaration's generic bounds, constructor kinds,
realm, lexical type aliases and visibility. They do not inherit its effects.
Unused generic declarations must also check parametrically.

The frontend uses private static helpers and ordinary checked assertions.
Preconditions execute before the original body. A separate ordinary call retains
the body's return, Result propagation and finally boundary. Postconditions run
after normal finalizers and return replacement. A Result error is a completed
result and reaches postconditions. An escaping source error, trap, cancellation
or deadline skips them. A false clause traps with E_ASSERT at its clause source location. Ordinary predicate
overflow/division/bounds traps retain their diagnostics. Checks remain in release
code. Recursive calls, indirect references and future generic instantiations use
the guarded declaration. This is runtime checking; Z3 proof support is unchanged.

Annotated loops require one or more invariants and one i64 ranking:

~~~nex
var i:i64=0;
var values:list<str>=[];
while i<3
  invariant(i>=0 && i<=3)
  invariant(len(values)==i)
  decreases(3-i)
{
  values=values+["item"];
  i=i+1;
}
~~~

Invariants run at entry, even when the first condition is false, and after each
normally completed body, before the next condition. The ranking is saved once
after a true condition and must be nonnegative. The next normal back edge must
strictly decrease it, including an edge whose following condition is false.
A negative final ranking can therefore be accepted when that condition is false.
Initial false conditions do not evaluate the ranking. Checks observe enclosing
bindings; body-local shadows do not replace them. Normal body finalizers run
before back-edge observations. Early returns and escaping source errors bypass
the back edge. Loop observations can use ordinary pure values; direct Result
propagation cannot escape the observation's independent non-returning boundary.
The existing JSON runtime projection keeps its documented scalar loop subset.

requires, ensures, invariant and decreases remain ordinary identifiers outside
these positions. No extern, trait-signature or lambda contract inheritance is
introduced. Each list has at most64 clauses, each expression at most4096 UTF-8
bytes, in addition to ordinary parser/type/execution limits. Generated helper
names avoid every identifier in their unit. Their bodies have no editable
physical declaration; source edits target the original declaration.

Language028 uses nex.program/16. New contract declarations/helpers extend their
function identity with nex.function/14; loop purity markers also participate
in canonical identity. Retained027 keeps its parser and nex.program/15.
The default compiler remains027 during this development stage. Explicit
preflightGraphMigration/applyGraphMigration can recheck an archived027 origin
with target Contracts028 and an optional reviewed nex.migration-candidate/1.
They retain old revisions, namespaces and local IDs; replacing a version field
does not migrate a graph. Physical export remains separate.

The implementation is undergoing observable native/reference/TaskIR/TypeScript,
rejected-source and genuine027 history checks. Full regression, source-free SDK,
debug/profile/operation editing, project/provider/browser integration and
Windows/Linux/device acceptance remain separate gates. Generated calls and
assertions affect source profiles and execution budgets; no zero-cost claim is made.
