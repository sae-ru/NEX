#include "nex/verification.h"
#include <z3++.h>
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <functional>
#include <optional>
#include <random>

namespace nex {
namespace {
using Object=llvm::json::Object;
using Array=llvm::json::Array;
using JSON=llvm::json::Value;
using Clock=std::chrono::steady_clock;
struct Stop {std::string status,message;Span span;};
void fields(const Object &object,std::initializer_list<std::string> allowed){
  std::set<std::string> names(allowed);for(const auto &[key,value]:object)if(!names.contains(key.str()))throw Error("E_CONTRACT","unknown contract field '"+key.str()+"'");
}
std::string required(const Object &object,const std::string &name){auto value=object.getString(name);if(!value)throw Error("E_CONTRACT","missing string '"+name+"'");return value->str();}
bool identifier(const std::string &name){
  if(name.empty()||!((name[0]>='a'&&name[0]<='z')||(name[0]>='A'&&name[0]<='Z')||name[0]=='_'))return false;
  return std::all_of(name.begin(),name.end(),[](char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_';});
}
std::vector<std::string> clauses(const Object &object,const std::string &key){
  auto array=object.getArray(key);if(!array||array->size()>64)throw Error("E_CONTRACT",key+" must be an array of at most 64 expressions");
  std::vector<std::string> values;for(const auto &item:*array){auto text=item.getAsString();if(!text||text->empty()||text->size()>4096)throw Error("E_CONTRACT","contract expressions must contain 1..4096 UTF-8 bytes");values.push_back(text->str());}return values;
}
Object location(Span span){return Object{{"file",span.file},{"line",span.line},{"column",span.column}};}
std::string sourcesHash(const Program &p){return hash(json(sourceBundle(p),false));}
std::string contentHash(const Function &f){return hash(json(canonical(f),false));}
using LoopKey=std::pair<unsigned,unsigned>;
struct Loop {std::vector<std::string> invariants;std::string decreases;};
struct Contract {std::string result;std::vector<std::string> pre,post;std::map<LoopKey,Loop> loops;};
using Contracts=std::map<std::string,Contract>;
void loops(const std::vector<S> &body,std::map<LoopKey,S> &found){for(auto s:body){if(s->kind==Stmt::While)found.emplace(LoopKey{s->span.line,s->span.column},s);childBlocks(s,[&](const auto &body){loops(body,found);});}}
Contracts contracts(const Program &p,const JSON &value){
  auto object=value.getAsObject();if(!object)throw Error("E_CONTRACT","contract must be an object");
  fields(*object,{"schema","language","expected_revision","source_hash","functions"});
  if(required(*object,"schema")!="nex.verification-contracts/1"||required(*object,"language")!=languageVersion)throw Error("E_CONTRACT","unsupported contract schema/language");
  if(required(*object,"expected_revision")!=revision(p)||required(*object,"source_hash")!=sourcesHash(p))throw Error("E_CONTRACT_STALE","contract revision or exact source bundle differs; review and regenerate the contract");
  auto functions=object->getArray("functions");if(!functions||functions->empty()||functions->size()>64)throw Error("E_CONTRACT","functions must contain 1..64 contracts");
  Contracts result;
  for(const auto &item:*functions){
    auto entry=item.getAsObject();if(!entry)throw Error("E_CONTRACT","function contract must be an object");fields(*entry,{"symbol","content_hash","returns","requires","ensures","loops"});
    auto symbol=required(*entry,"symbol");const auto &f=p.function(symbol);
    if(symbol!=f.name||required(*entry,"content_hash")!=contentHash(f))throw Error("E_CONTRACT_STALE","contract must name the exact qualified function and current content hash");
    Contract contract;contract.pre=clauses(*entry,"requires");contract.post=clauses(*entry,"ensures");contract.result=required(*entry,"returns");
    if(f.result==Type::Unit){if(!contract.result.empty())throw Error("E_CONTRACT","unit contract returns binding must be empty");}
    else if(!identifier(contract.result)||std::any_of(f.params.begin(),f.params.end(),[&](const auto &param){return param.name==contract.result;}))throw Error("E_CONTRACT","returns must be a fresh identifier distinct from parameters");
    auto annotations=entry->getArray("loops");if(!annotations||annotations->size()>64)throw Error("E_CONTRACT","loops must be an array of at most 64 annotations");
    std::map<LoopKey,S> actual;loops(f.body,actual);
    for(const auto &annotation:*annotations){
      auto loop=annotation.getAsObject();if(!loop)throw Error("E_CONTRACT","loop annotation must be an object");fields(*loop,{"line","column","invariants","decreases"});
      auto line=loop->getInteger("line"),column=loop->getInteger("column");if(!line||!column||*line<1||*column<1||*line>UINT32_MAX||*column>UINT32_MAX)throw Error("E_CONTRACT","loop line/column must be positive source coordinates");
      LoopKey key{unsigned(*line),unsigned(*column)};if(!actual.contains(key))throw Error("E_CONTRACT_STALE","loop annotation does not identify a while statement in the selected function");
      auto variant=required(*loop,"decreases");if(variant.size()>4096)throw Error("E_CONTRACT","decreases expression exceeds 4096 bytes");
      if(!contract.loops.emplace(key,Loop{clauses(*loop,"invariants"),variant}).second)throw Error("E_CONTRACT","duplicate loop annotation");
    }
    if(!result.emplace(symbol,std::move(contract)).second)throw Error("E_CONTRACT","duplicate function contract");
  }
  return result;
}
struct Sym {z3::expr value;Type type;Sym(z3::expr value,Type type):value(std::move(value)),type(std::move(type)){};};
struct State {
  z3::expr path;std::vector<std::map<std::string,Sym>> scopes;bool abstract=false;
  explicit State(z3::expr path):path(std::move(path)),scopes(1){}
  Sym &lookup(const std::string &name,Span span){for(auto i=scopes.rbegin();i!=scopes.rend();++i){auto value=i->find(name);if(value!=i->end())return value->second;}throw Error("E_CONTRACT_EXPRESSION","unknown contract variable '"+name+"'",span);}
};
struct Flow {State state;std::optional<Sym> result;bool returned=false;};
struct Obligation {
  std::string kind,function,code;Span span;z3::expr path,condition;State snapshot;
  Obligation(std::string kind,std::string function,std::string code,Span span,const State &state,z3::expr condition):kind(std::move(kind)),function(std::move(function)),code(std::move(code)),span(span),path(state.path),condition(std::move(condition)),snapshot(state){}
};
class Engine {
  const Program &p;const Contracts &specs;const VerificationOptions &options;Clock::time_point deadline;
  z3::context context;std::vector<Obligation> obligations;std::map<std::string,Sym> inputs;std::vector<const Function*> calls;
  unsigned serial=0,steps=0;std::optional<z3::expr> feasible;
  std::string phase;
  void poll(){if(++steps>50000)throw Stop{"unknown","symbolic execution step limit exceeded",{}};if(Clock::now()>=deadline)throw Stop{"timeout","verification wall-time budget exceeded",{}};}
  z3::expr integer(int64_t value){return context.int_val(std::to_string(value).c_str());}
  z3::expr range(const z3::expr &value){return value>=integer(INT64_MIN)&&value<=integer(INT64_MAX);}
  Sym fresh(Type type){auto name="nex_v"+std::to_string(serial++);return {type==Type::Bool?context.bool_const(name.c_str()):context.int_const(name.c_str()),type};}
  void typed(const Sym &value,Type expected,Span span){if(value.type!=expected)throw Error("E_CONTRACT_EXPRESSION","expected "+typeName(expected)+", found "+typeName(value.type),span);}
  void add(State &state,z3::expr condition,const std::string &kind,Span span,const std::string &code="",bool assume=false){
    poll();if(obligations.size()>=4096)throw Stop{"unknown","verification obligation limit exceeded",span};
    obligations.emplace_back(phase.empty()?kind:phase+"/"+kind,calls.back()->name,code,span,state,condition);
    if(assume)state.path=state.path&&condition;
  }
  Sym predicate(const std::string &text,State &state,Type type,const std::string &kind){
    auto previous=phase;phase=kind;Sym value(context.bool_val(false),Type::Bool);
    try{value=expression(parseExpression(text,"<contract:"+calls.back()->name+":"+kind+">"),state,true);typed(value,type,{});}catch(...){phase=previous;throw;}
    phase=previous;return value;
  }
  Sym expression(E e,State &state,bool spec=false){
    poll();if(!e)return {context.bool_val(true),Type::Unit};
    if(e->kind==Expr::Propagate)throw Stop{"unsupported","result propagation is outside scalar verification",e->span};
    if(e->kind==Expr::Match)throw Stop{"unsupported","match expressions are outside scalar verification",e->span};
    if(e->kind==Expr::Floating||e->type==Type::F64)throw Stop{"unsupported","f64 is outside integer/boolean verification",e->span};
    if(e->type==Type::Bytes)throw Stop{"unsupported","binary values are outside integer/boolean verification",e->span};
    if(e->kind==Expr::Invoke||e->kind==Expr::FunctionRef||e->kind==Expr::Lambda)throw Stop{"unsupported","function values are outside scalar verification",e->span};
    if(e->kind==Expr::Integer)return {integer(e->number),Type::I64};
    if(e->kind==Expr::Boolean)return {context.bool_val(e->number),Type::Bool};
    if(e->kind==Expr::Name)return state.lookup(e->text,e->span);
    if(e->kind==Expr::Unary){auto a=expression(e->args[0],state,spec);typed(a,e->text=="!"?Type(Type::Bool):Type(Type::I64),e->span);if(e->text=="!")return {!a.value,Type::Bool};auto result=-a.value;add(state,range(result),"checked_arithmetic",e->span,"E_OVERFLOW",true);return {result,Type::I64};}
    if(e->kind==Expr::Binary){
      auto a=expression(e->args[0],state,spec);const auto &op=e->text;
      if(op=="&&"||op=="||"){
        typed(a,Type::Bool,e->span);State right=state;right.path=right.path&&(op=="&&"?a.value:!a.value);auto b=expression(e->args[1],right,spec);typed(b,Type::Bool,e->span);
        state.path=(state.path&&(op=="&&"?!a.value:a.value))||right.path;state.abstract=state.abstract||right.abstract;
        return {op=="&&"?a.value&&b.value:a.value||b.value,Type::Bool};
      }
      auto b=expression(e->args[1],state,spec);typed(b,a.type,e->span);
      if(op=="=="||op=="!=")return {op=="=="?a.value==b.value:a.value!=b.value,Type::Bool};
      typed(a,Type::I64,e->span);
      if(op=="<")return {a.value<b.value,Type::Bool};if(op=="<=")return {a.value<=b.value,Type::Bool};if(op==">")return {a.value>b.value,Type::Bool};if(op==">=")return {a.value>=b.value,Type::Bool};
      z3::expr result=context.int_val(0);
      if(op=="+")result=a.value+b.value;else if(op=="-")result=a.value-b.value;else if(op=="*")result=a.value*b.value;
      else if(op=="/"||op=="%"){
        add(state,b.value!=integer(0),"division_nonzero",e->span,"E_DIV_ZERO",true);
        auto quotient=z3::ite(a.value>=integer(0),a.value,-a.value)/z3::ite(b.value>=integer(0),b.value,-b.value);
        quotient=z3::ite((a.value<integer(0))!=(b.value<integer(0)),-quotient,quotient);
        if(op=="/")add(state,!(a.value==integer(INT64_MIN)&&b.value==integer(-1)),"division_overflow",e->span,"E_OVERFLOW",true);
        result=op=="/"?quotient:a.value-quotient*b.value;
      }else throw Stop{"unsupported","unsupported scalar operator "+op,e->span};
      add(state,range(result),"checked_arithmetic",e->span,"E_OVERFLOW",true);return {result,Type::I64};
    }
    if(e->kind==Expr::Call&&!spec){
      std::vector<Sym> args;for(auto a:e->args)args.push_back(expression(a,state));
      if(e->text=="assert"){typed(args.at(0),Type::Bool,e->span);add(state,args[0].value,"assertion",e->span,"E_ASSERT",true);return {context.bool_val(true),Type::Unit};}
      if(builtinNames().contains(e->text)||p.hasStructure(e->text)||p.variant(e->text))throw Stop{"unsupported","only pure scalar function calls and assert are verified",e->span};
      return function(p.function(e->text),args,state,false);
    }
    throw Stop{"unsupported",spec?"contract predicates support scalar literals, variables and operators only":"heap values and this expression kind are outside the verified subset",e->span};
  }
  // Only assignments to bindings visible at the loop head are havoced. Local
  // shadows inside nested blocks cannot mutate those bindings in NEX.
  std::set<std::string> writes(const std::vector<S> &body,std::vector<std::set<std::string>> shadows={}){
    shadows.emplace_back();std::set<std::string> result;
    for(auto s:body){
      if(s->kind==Stmt::Let||s->kind==Stmt::Var)shadows.back().insert(s->name);
      if(s->kind==Stmt::Assign&&!std::any_of(shadows.begin(),shadows.end(),[&](const auto &scope){return scope.contains(s->name);}))result.insert(s->name);
      auto first=writes(s->body,shadows),second=writes(s->alternative,shadows);result.insert(first.begin(),first.end());result.insert(second.begin(),second.end());
    }
    return result;
  }
  std::vector<Flow> loop(S s,State incoming){
    auto found=specs.find(calls.back()->name);
    if(found==specs.end()||!found->second.loops.contains({s->span.line,s->span.column}))throw Stop{"unsupported","while requires an explicit invariant and decreases annotation",s->span};
    const auto &annotation=found->second.loops.at({s->span.line,s->span.column});
    if(annotation.invariants.empty()||annotation.decreases.empty())throw Stop{"unsupported","while requires nonempty invariants and a decreases expression",s->span};
    for(const auto &text:annotation.invariants){auto condition=predicate(text,incoming,Type::Bool,"invariant_initial");add(incoming,condition.value,"invariant_initial",s->span);}
    State head=incoming;head.abstract=true;
    for(const auto &name:writes(s->body)){auto &binding=head.lookup(name,s->span);binding=fresh(binding.type);if(binding.type==Type::I64)head.path=head.path&&range(binding.value);}
    for(const auto &text:annotation.invariants){auto condition=predicate(text,head,Type::Bool,"invariant_assumption");head.path=head.path&&condition.value;}
    auto condition=expression(s->expr,head);typed(condition,Type::Bool,s->span);
    State iteration=head;iteration.path=iteration.path&&condition.value;
    auto before=predicate(annotation.decreases,iteration,Type::I64,"decreases_defined");add(iteration,before.value>=integer(0),"decreases_nonnegative",s->span);
    auto paths=block(s->body,{{iteration,std::nullopt,false}},true);std::vector<Flow> result;
    for(auto &path:paths){
      if(path.returned){result.push_back(std::move(path));continue;}
      for(const auto &text:annotation.invariants){auto value=predicate(text,path.state,Type::Bool,"invariant_preserved");add(path.state,value.value,"invariant_preserved",s->span);}
      auto after=predicate(annotation.decreases,path.state,Type::I64,"decreases_defined");add(path.state,after.value<before.value,"decreases_strict",s->span);
    }
    head.path=head.path&&!condition.value;result.push_back({std::move(head),std::nullopt,false});return result;
  }
  std::vector<Flow> block(const std::vector<S> &body,std::vector<Flow> paths,bool scoped){
    if(scoped)for(auto &path:paths)path.state.scopes.emplace_back();
    for(auto s:body){
      std::vector<Flow> next;
      for(auto &path:paths){
        poll();if(path.returned){next.push_back(std::move(path));continue;}
        auto &state=path.state;
        switch(s->kind){
        case Stmt::Try:case Stmt::Throw:case Stmt::Finally:case Stmt::TypedThrow:case Stmt::TypedTry:case Stmt::CatchClause:throw Stop{"unsupported","source exception contracts require explicit verification semantics",s->span};
        case Stmt::Let:case Stmt::Var:{auto value=expression(s->expr,state);if(value.type!=Type::I64&&value.type!=Type::Bool)throw Stop{"unsupported","only scalar locals are verified",s->span};state.scopes.back().insert_or_assign(s->name,value);next.push_back(std::move(path));break;}
        case Stmt::Assign:{auto value=expression(s->expr,state);state.lookup(s->name,s->span)=value;next.push_back(std::move(path));break;}
        case Stmt::Expression:expression(s->expr,state);next.push_back(std::move(path));break;
        case Stmt::Return:path.result=expression(s->expr,state);path.returned=true;next.push_back(std::move(path));break;
        case Stmt::If:{
          auto condition=expression(s->expr,state);typed(condition,Type::Bool,s->span);State other=state;other.path=other.path&&!condition.value;state.path=state.path&&condition.value;
          auto yes=block(s->body,{{state,std::nullopt,false}},true),no=block(s->alternative,{{other,std::nullopt,false}},true);
          next.insert(next.end(),std::make_move_iterator(yes.begin()),std::make_move_iterator(yes.end()));next.insert(next.end(),std::make_move_iterator(no.begin()),std::make_move_iterator(no.end()));break;
        }
        case Stmt::Match:throw Stop{"unsupported","enum matching is outside scalar verification",s->span};
        case Stmt::While:{auto outcomes=loop(s,state);next.insert(next.end(),std::make_move_iterator(outcomes.begin()),std::make_move_iterator(outcomes.end()));break;}
        }
      }
      if(next.size()>256)throw Stop{"unknown","symbolic path limit exceeded",s->span};paths=std::move(next);
    }
    if(scoped)for(auto &path:paths)path.state.scopes.pop_back();return paths;
  }
  Sym function(const Function &f,const std::vector<Sym> &args,State &caller,bool root){
    poll();if(!f.effects.empty())throw Stop{"unsupported","effectful functions are outside the verified subset",f.span};
    if(f.result!=Type::I64&&f.result!=Type::Bool&&f.result!=Type::Unit)throw Stop{"unsupported","only i64/bool/unit function results are verified",f.span};
    if(calls.size()>=32||std::any_of(calls.begin(),calls.end(),[&](const auto *active){return active->name==f.name;}))throw Stop{"unsupported","recursive calls or call depth above 32 require an additional proof rule",f.span};
    calls.push_back(&f);State entry(caller.path);entry.abstract=caller.abstract;
    for(size_t i=0;i<f.params.size();++i){if(f.params[i].type!=Type::I64&&f.params[i].type!=Type::Bool)throw Stop{"unsupported","only scalar parameters are verified",f.params[i].span};entry.scopes.back().emplace(f.params[i].name,args[i]);}
    auto original=entry.scopes.back();auto contract=specs.find(f.name);
    if(contract!=specs.end())for(const auto &text:contract->second.pre){auto condition=predicate(text,entry,Type::Bool,"requires_defined");if(!root)add(entry,condition.value,"callee_requires",f.span);entry.path=entry.path&&condition.value;}
    if(root)feasible=entry.path;
    auto outcomes=block(f.body,{{entry,std::nullopt,false}},false);auto joined=context.bool_val(false);auto output=f.result==Type::Unit?Sym(context.bool_val(true),Type::Unit):fresh(f.result);bool abstract=caller.abstract;
    for(auto &path:outcomes){
      if(!path.returned&&f.result!=Type::Unit)throw Error("E_INTERNAL","checked function did not return",f.span);
      if(!path.result)path.result=Sym(context.bool_val(true),Type::Unit);
      if(contract!=specs.end()){
        State post(path.state.path);post.abstract=path.state.abstract;post.scopes.back()=original;
        if(f.result!=Type::Unit)post.scopes.back().emplace(contract->second.result,*path.result);
        for(const auto &text:contract->second.post){auto condition=predicate(text,post,Type::Bool,"ensures_defined");add(post,condition.value,"ensures",f.span);}
      }
      joined=joined||(path.state.path&&(f.result==Type::Unit?context.bool_val(true):output.value==path.result->value));abstract=abstract||path.state.abstract;
    }
    caller.path=joined;caller.abstract=abstract;calls.pop_back();return output;
  }
  JSON values(const z3::model &model,const std::map<std::string,Sym> &bindings){
    Object result;for(const auto &[name,value]:bindings){auto v=model.eval(value.value,true);if(value.type==Type::Bool)result[name]=v.is_true();else result[name]=std::string(Z3_get_numeral_string(context,v));}return result;
  }
  JSON locals(const z3::model &model,const State &state){
    std::map<std::string,Sym> visible;for(const auto &scope:state.scopes)for(const auto &[name,value]:scope)visible.insert_or_assign(name,value);return values(model,visible);
  }
public:
  Engine(const Program &p,const Contracts &specs,const VerificationOptions &options,Clock::time_point deadline):p(p),specs(specs),options(options),deadline(deadline){}
  JSON run(const Function &f,const std::filesystem::path &folder){
    Object report{{"symbol",f.name},{"content_hash",contentHash(f)},{"location",location(f.span)}};Array results;
    try{
      State initial(context.bool_val(true));std::vector<Sym> args;
      for(const auto &param:f.params){auto value=fresh(param.type);inputs.emplace(param.name,value);args.push_back(value);if(param.type==Type::I64)initial.path=initial.path&&range(value.value);}
      function(f,args,initial,true);
      if(!feasible)throw Error("E_INTERNAL","missing root precondition state");
      // Feasibility is checked separately so contradictory assumptions never
      // become a successful safety proof through vacuous implications.
      State entry(*feasible);Obligation consistency("preconditions_consistent",f.name,"",f.span,entry,context.bool_val(true));
      obligations.insert(obligations.begin(),std::move(consistency));std::string status="proven";unsigned index=0;
      for(const auto &obligation:obligations){
        poll();auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();
        auto effectiveTimeout=unsigned(std::max<int64_t>(1,std::min<int64_t>(options.solverTimeoutMs,remaining)));
        z3::solver solver(context);z3::params params(context);params.set("timeout",effectiveTimeout);params.set("rlimit",options.resourceLimit);solver.set(params);
        bool satisfiable=obligation.kind=="preconditions_consistent";
        solver.add(obligation.path&&(satisfiable?context.bool_val(true):!obligation.condition));
        auto basename=std::to_string(index++);auto query=folder/"queries"/(basename+".smt2");
        auto smt="(set-option :timeout "+std::to_string(effectiveTimeout)+")\n(set-option :rlimit "+std::to_string(options.resourceLimit)+")\n"+solver.to_smt2();
        if(smt.size()>8388608)throw Stop{"unknown","SMT query exceeds 8 MiB artifact limit",obligation.span};writeFile(query.string(),smt);
        auto answer=solver.check();std::string outcome;Object record{{"kind",obligation.kind},{"function",obligation.function},{"location",location(obligation.span)},{"runtime_code",obligation.code},{"query",query.string()},{"solver_timeout_ms",effectiveTimeout},{"solver_resource_limit",options.resourceLimit}};
        if(answer==z3::unknown){auto reason=solver.reason_unknown();outcome=reason.find("timeout")!=std::string::npos?"timeout":"unknown";record["reason"]=reason;if(status=="proven")status=outcome;}
        else if(satisfiable){outcome=answer==z3::sat?"consistent":"inconsistent_preconditions";if(answer==z3::unsat)status=outcome;}
        else if(answer==z3::unsat)outcome="proven";
        else{
          outcome="counterexample";status=outcome;auto model=solver.get_model();record["inputs"]=values(model,inputs);record["locals"]=locals(model,obligation.snapshot);
          record["counterexample_kind"]=obligation.snapshot.abstract?"inductive_state":"concrete_input";
          record["path"]=obligation.path.to_string();record["condition"]=obligation.condition.to_string();
        }
        record["status"]=outcome;writeFile((folder/"queries"/(basename+".json")).string(),json(JSON(Object(record)))+"\n");results.push_back(std::move(record));
      }
      report["status"]=status;
    }catch(const Stop &stop){report["status"]=stop.status;report["reason"]=stop.message;report["stopped_at"]=location(stop.span);}
    catch(const z3::exception &error){report["status"]="unknown";report["reason"]=std::string("solver exception: ")+error.msg();}
    report["generated_obligations"]=obligations.size();report["checked_obligations"]=results.size();report["obligations"]=std::move(results);return report;
  }
};
}

namespace {
// Serialize only the deliberately small scalar predicate grammar. Reusing the
// user's text here would let a trailing line comment swallow generated tokens.
std::string runtimePredicateText(const E &e,const std::map<std::string,Type> &locals,std::set<std::string> *used=nullptr){
  switch(e->kind){
  case Expr::Integer:return "("+std::to_string(e->number)+")";
  case Expr::Boolean:return e->number?"true":"false";
  case Expr::Name:
    if(!identifier(e->text)||!locals.contains(e->text)||
       (locals.at(e->text)!=Type::I64&&locals.at(e->text)!=Type::Bool))break;
    if(used)used->insert(e->text);
    return e->text;
  case Expr::Unary:
    if((e->text=="-"||e->text=="!")&&e->args.size()==1)
      return "("+e->text+runtimePredicateText(e->args[0],locals,used)+")";
    break;
  case Expr::Binary:
    if(e->args.size()==2&&std::set<std::string>{"+","-","*","/","%","<","<=",">",">=","==","!=","&&","||"}.contains(e->text))
      return "("+runtimePredicateText(e->args[0],locals,used)+" "+e->text+" "+runtimePredicateText(e->args[1],locals,used)+")";
    break;
  default:break;
  }
  throw Error("E_CONTRACT_EXPRESSION","runtime predicates support only scalar literals, visible i64/bool bindings and checked operators",e->span);
}
std::string runtimeScalarExpression(Program &p,const Function &f,const std::string &text,
                             const std::map<std::string,Type> &locals,const std::string &phase,
                             Type expected=Type::Bool,std::set<std::string> *used=nullptr){
  auto expression=parseExpression(text,"<contract:"+f.name+":"+phase+">",4096);
  auto source=runtimePredicateText(expression,locals,used);
  if(checkExpression(p,f.name,expression,locals)!=expected)
    throw Error("E_CONTRACT_EXPRESSION","runtime "+phase+" must return "+typeName(expected),expression->span);
  return source;
}
std::string runtimeValueExpression(const Program &original,const Function &f,const std::string &text,
                                 const std::map<std::string,Type> &locals,const std::string &phase,
                                 bool &valueChecks){
  auto expression=parseExpression(text,"<contract:"+f.name+":"+phase+">",4096);
  try{(void)runtimePredicateText(expression,locals);}
  catch(const Error &error){if(error.code!="E_CONTRACT_EXPRESSION")throw;valueChecks=true;}
  // Resolve in the root's actual module. The expression checker deliberately
  // removes the root's effects: neither direct nor indirect predicate calls
  // inherit its IO, file, task, foreign or source-error authority.
  // Each clause gets independent derived watch/generic metadata. In particular,
  // separate predicate lambdas must not reuse a previous clause's lifted name.
  auto p=original;bindExpression(p,f.name,expression);
  if(checkExpression(p,f.name,expression,locals)!=Type::Bool)
    throw Error("E_CONTRACT_EXPRESSION","runtime "+phase+" must return bool",expression->span);
  // Emit lexical tokens, never raw predicate text. This preserves the complete
  // checked expression grammar (including generic aliases and match/lambdas),
  // while stripping comments that could swallow generated assertion syntax.
  std::string source;
  for(const auto &token:sourceTokens(text,expression->span.file))source+=token.text+" ";
  return source;
}
struct RuntimeLoops {std::string body,helpers;Array coverage;};
RuntimeLoops runtimeLoops(Program &checked,const Function &f,const Contract &spec,
                         llvm::StringRef source,size_t begin,size_t end,
                         std::set<std::string> &names,std::set<std::string> &globalNames){
  RuntimeLoops result;result.body=source.substr(begin,end-begin).str();
  if(spec.loops.empty())return result;
  // Insertions retain the exact body and return/finally boundaries. A private
  // head helper checks each back edge before reevaluating the original condition;
  // there is no unreachable tail after an unconditional return and no closure.
  std::map<size_t,std::string> insertions;
  auto insert=[&](size_t at,const std::string &text){
    if(at<begin||at>end)throw Error("E_CONTRACT_RUNTIME","loop source interval lies outside its function",f.span);
    insertions[at]+=text;
  };
  auto fresh=[&](const std::string &stem){
    auto name=stem;for(unsigned suffix=1;names.contains(name)||globalNames.contains(name);++suffix)name=stem+"_"+std::to_string(suffix);
    names.insert(name);globalNames.insert(name);return name;
  };
  auto owner=f.name.substr(0,f.name.rfind("::"));
  using Locals=std::map<std::string,Type>;
  std::function<void(const std::vector<S>&,Locals)> visit;
  visit=[&](const std::vector<S> &body,Locals locals){
    for(const auto &statement:body){
      if(statement->kind==Stmt::Let||statement->kind==Stmt::Var){locals[statement->name]=statement->type;continue;}
      if(statement->kind==Stmt::While){
        auto annotation=spec.loops.find({statement->span.line,statement->span.column});
        if(annotation!=spec.loops.end()){
          const auto &rule=annotation->second;
          if(rule.invariants.empty()||rule.decreases.empty())
            throw Error("E_CONTRACT_RUNTIME","runtime loops require nonempty invariants and a decreases expression",statement->span);
          std::set<std::string> used;std::vector<std::string> predicates;
          for(const auto &text:rule.invariants)predicates.push_back(runtimeScalarExpression(checked,f,text,locals,"invariant",Type::Bool,&used));
          auto rank=runtimeScalarExpression(checked,f,rule.decreases,locals,"decreases",Type::I64,&used);
          const auto &range=statement->sourceRange;const auto &condition=statement->expr->sourceRange;
          if(!range.valid||!condition.valid||range.begin>=range.end||range.end>source.size()||
             condition.begin<=range.begin||condition.begin>=condition.end||condition.end>=range.end)
            throw Error("E_CONTRACT_RUNTIME","loop has no exact editable source interval",statement->span);
          auto tokens=sourceTokens(source.substr(range.begin,range.end-range.begin).str(),f.span.file);
          size_t open=std::string::npos;unsigned balance=0;
          for(auto i=tokens.rbegin();i!=tokens.rend();++i){
            auto raw=source.substr(range.begin+i->span.begin,i->span.end-i->span.begin);
            if(raw=="}")++balance;else if(raw=="{"&&balance&&!--balance){open=range.begin+i->span.begin;break;}
          }
          if(open==std::string::npos||condition.end>open)
            throw Error("E_CONTRACT_RUNTIME","cannot identify the exact loop body",statement->span);
          auto stem="nex_contract_loop_"+hash(f.name+contentHash(f)+":"+std::to_string(statement->span.line)+":"+std::to_string(statement->span.column)).substr(0,16);
          auto helper=fresh(stem),seen=fresh(stem+"_seen"),previous=fresh(stem+"_previous");
          std::string parameters,arguments;
          for(const auto &name:used){
            if(!parameters.empty()){parameters+=", ";arguments+=", ";}
            parameters+=name+": "+typeName(locals.at(name));arguments+=name;
          }
          if(!parameters.empty()){parameters+=", ";arguments+=", ";}
          parameters+=seen+": bool, "+previous+": i64";arguments+=seen+", "+previous;
          result.helpers+="\n\n"+f.realm+" fn "+helper+"("+parameters+") -> bool {\n";
          for(const auto &predicate:predicates)result.helpers+="  assert("+predicate+");\n";
          result.helpers+="  if "+seen+" { assert(("+rank+") < "+previous+"); }\n  return true;\n}\n";
          insert(range.begin,"\nvar "+seen+": bool = false;\nvar "+previous+": i64 = 0;\n");
          insert(condition.begin,helper+"("+arguments+") && (");insert(condition.end,")");
          insert(open+1,"\n"+previous+" = "+rank+";\nassert("+previous+" >= 0);\n"+seen+" = true;\n");
          result.coverage.push_back(Object{{"line",statement->span.line},{"column",statement->span.column},
            {"invariants",rule.invariants.size()},{"decreases",true},{"head_helper_symbol",owner+"::"+helper}});
        }
      }
      if(statement->kind==Stmt::Match){
        for(const auto &arm:statement->arms){auto armLocals=locals;for(const auto &binding:arm->bindings)armLocals[binding.name]=binding.type;visit(arm->body,std::move(armLocals));}
      }else if(statement->kind==Stmt::Try){
        visit(statement->body,locals);auto handler=locals;handler[statement->name]=Type::Str;handler[statement->catchMessage]=Type::Str;visit(statement->alternative,std::move(handler));
      }else if(statement->kind==Stmt::TypedTry){
        visit(statement->body,locals);
        for(const auto &clause:statement->alternative){
          auto handler=locals;handler[clause->name]=clause->type==Type::Unknown?Type(Type::Str):clause->type;
          if(clause->type==Type::Unknown)handler[clause->catchMessage]=Type::Str;
          visit(clause->body,std::move(handler));
        }
      }else{visit(statement->body,locals);visit(statement->alternative,locals);}
    }
  };
  Locals locals;for(const auto &parameter:f.params)locals[parameter.name]=parameter.type;
  visit(f.body,std::move(locals));
  if(result.coverage.size()!=spec.loops.size())throw Error("E_CONTRACT_RUNTIME","not every annotated loop has a lexical source projection",f.span);
  for(auto i=insertions.rbegin();i!=insertions.rend();++i)result.body.insert(i->first-begin,i->second);
  return result;
}
}
JSON runtimeContractCandidate(const Program &original,const JSON &contract,const std::string &root){
  auto parsed=contracts(original,contract);
  bool loopChecks=std::any_of(parsed.begin(),parsed.end(),[](const auto &item){return !item.second.loops.empty();});
  bool valueChecks=false;
  auto bundle=sourceBundle(original);auto files=bundle.getAsObject()->getObject("files");
  // The evidence and dependency lock must never overwrite a source member.
  for(const auto &name:{"runtime-contracts.receipt.json","nex.lock.json","nex.json"})
    for(const auto &[key,value]:*files)if(key==name||key.str().starts_with(std::string(name)+"/"))
      throw Error("E_CONTRACT_RUNTIME","source member conflicts with runtime contract export metadata");
  struct Edit {size_t begin,end;std::string text;};
  std::map<std::string,std::vector<Edit>> edits;
  std::map<std::string,std::string> implementations;
  std::map<std::string,std::set<std::string>> identifiers;
  std::set<std::string> globalNames;
  for(const auto &function:original.functions)globalNames.insert(function.localName);
  for(const auto &type:original.structures)globalNames.insert(type.localName);
  for(const auto &trait:original.traits)globalNames.insert(trait.localName);
  Array coverage;
  // Predicate checking may prepare derived frontend metadata. Keep it separate
  // from the immutable source snapshot and avoid holding vector references.
  auto checked=original;
  for(const auto &[symbol,spec]:parsed){
    const auto f=original.function(symbol);
    auto scalar=[](Type type){return type==Type::I64||type==Type::Bool;};
    if(f.foreign||f.test||f.closure||f.traitSignature||!f.traitOwner.empty()||
       !f.templateName.empty()||!f.typeParameters.empty()||!f.typeArguments.empty())
      throw Error("E_CONTRACT_RUNTIME","runtime contract roots must be ordinary concrete source functions",f.span);
    valueChecks|=!f.effects.empty()||(f.result!=Type::Unit&&!scalar(f.result))||
      std::any_of(f.params.begin(),f.params.end(),[&](const auto &param){return !scalar(param.type);});
    auto source=files->getString(f.unit);
    if(!source||f.span.begin>=f.span.end||f.span.end>source->size())
      throw Error("E_CONTRACT_RUNTIME","contract root has no exact editable source definition",f.span);
    auto definition=source->substr(f.span.begin,f.span.end-f.span.begin).str();
    auto tokens=sourceTokens(definition,f.span.file);size_t open=std::string::npos,close=0;unsigned balance=0;
    // Walk backwards from the declaration's final brace, distinguishing actual
    // punctuation from brace characters inside string literals and comments.
    for(auto i=tokens.rbegin();i!=tokens.rend();++i){
      auto raw=definition.substr(i->span.begin,i->span.end-i->span.begin);
      if(raw=="}"){if(!balance)close=i->span.begin;++balance;}
      else if(raw=="{"&&balance&&!--balance){open=i->span.begin;break;}
    }
    if(open==std::string::npos||definition.substr(close+1).find_first_not_of(" \r\n\t")!=std::string::npos)
      throw Error("E_CONTRACT_RUNTIME","cannot identify the exact source function body",f.span);
    std::map<std::string,Type> locals;for(const auto &param:f.params)locals[param.name]=param.type;
    auto checks=[&](const std::vector<std::string> &clauses,const std::string &phase){
      std::string out;size_t index=0;
      for(const auto &clause:clauses){
        auto predicate=runtimeValueExpression(checked,f,clause,locals,phase,valueChecks);
        out+="  // NEX runtime "+phase+" "+f.name+" #"+std::to_string(++index)+"\n  assert("+predicate+");\n";
      }
      return out;
    };
    auto replacement=checks(spec.pre,"requires");
    // A private ordinary function retains the original return boundary without
    // introducing a closure allocation. Original recursive references still
    // select the guarded source function, never the implementation name.
    if(!identifiers.contains(f.unit)){
      auto &names=identifiers[f.unit];names=globalNames;
      for(const auto &token:sourceTokens(source->str(),f.span.file))if(token.identifier)names.insert(token.text);
    }
    auto stem="nex_contract_body_"+hash(f.name+contentHash(f)).substr(0,16),implementation=stem;
    auto &names=identifiers.at(f.unit);
    for(unsigned suffix=1;names.contains(implementation)||globalNames.contains(implementation);++suffix)implementation=stem+"_"+std::to_string(suffix);
    names.insert(implementation);globalNames.insert(implementation);
    std::string arguments;
    for(const auto &param:f.params){
      if(!arguments.empty())arguments+=", ";
      arguments+=param.name;
    }
    auto projected=runtimeLoops(checked,f,spec,*source,f.span.begin+open+1,f.span.begin+close,names,globalNames);
    // Keep the parsed signature's spelling, rather than printing resolved
    // nominal types that may not be accessible through this module's aliases.
    auto header=definition.substr(0,open);size_t declaration=0;
    while(declaration<tokens.size()&&tokens[declaration].text!="fn")++declaration;
    if(declaration+1>=tokens.size()||tokens[declaration+1].text!=f.localName)
      throw Error("E_CONTRACT_RUNTIME","cannot identify the source function name",f.span);
    const auto &nameToken=tokens[declaration+1];header.replace(nameToken.span.begin,nameToken.span.end-nameToken.span.begin,implementation);
    if(!tokens.empty()&&tokens.front().text=="pub")header.erase(tokens.front().span.begin,tokens.front().span.end-tokens.front().span.begin);
    const auto &resultRange=f.resultTypeSource;
    if(!resultRange.valid||resultRange.begin<f.span.begin||resultRange.begin>=resultRange.end||resultRange.end>f.span.begin+open)
      throw Error("E_CONTRACT_RUNTIME","contract root has no exact return type spelling",f.span);
    auto resultType=source->substr(resultRange.begin,resultRange.end-resultRange.begin).str();
    implementations[f.unit]+="\n\n"+header+"{"+projected.body+"}\n"+projected.helpers;
    replacement+="  ";if(f.result!=Type::Unit)replacement+="let "+spec.result+": "+resultType+"\n = ";
    replacement+=implementation+"("+arguments+");\n";
    auto owner=f.name.substr(0,f.name.rfind("::"));
    auto implementationSymbol=owner+"::"+implementation;
    if(f.result!=Type::Unit)locals[spec.result]=f.result;
    replacement+=checks(spec.post,"ensures");
    replacement+=f.result==Type::Unit?"  return;\n":"  return "+spec.result+";\n";
    edits[f.unit].push_back({f.span.begin+open+1,f.span.begin+close,"\n"+replacement});
    Object covered{{"symbol",f.name},{"origin_content_hash",contentHash(f)},
      {"requires",spec.pre.size()},{"ensures",spec.post.size()},{"normal_returns_only",true},
      {"implementation_symbol",implementationSymbol}};
    if(loopChecks)covered["loops"]=std::move(projected.coverage);
    coverage.push_back(std::move(covered));
  }
  for(auto &[unit,changes]:edits){
    auto source=files->getString(unit)->str();
    std::sort(changes.begin(),changes.end(),[](const auto &a,const auto &b){return a.begin>b.begin;});
    size_t previous=source.size();for(const auto &edit:changes){
      if(edit.begin>edit.end||edit.end>previous)throw Error("E_CONTRACT_RUNTIME","overlapping source contract roots");
      source.replace(edit.begin,edit.end-edit.begin,edit.text);previous=edit.begin;
    }
    source+=implementations.at(unit);(*files)[unit]=std::move(source);
  }
  // Every generated expression/function is checked using the ordinary language,
  // realm, effect and lifetime rules before an output directory is created.
  auto candidate=loadBundle(bundle,root);
  for(auto &item:coverage){
    auto object=item.getAsObject();(*object)["content_hash"]=contentHash(candidate.function(required(*object,"symbol")));
    if(valueChecks){
      const auto &origin=original.function(required(*object,"symbol"));Array parameters,effects;
      for(const auto &param:origin.params)parameters.push_back(Object{{"name",param.name},{"type",typeName(param.type)}});
      for(const auto &effect:origin.effects)effects.push_back(effect);
      (*object)["realm"]=origin.realm;(*object)["parameters"]=std::move(parameters);
      (*object)["result_type"]=typeName(origin.result);(*object)["effects"]=std::move(effects);
      if(!object->getArray("loops"))(*object)["loops"]=Array{};
    }
    const auto &implementation=candidate.function(required(*object,"implementation_symbol"));
    if(implementation.exported||implementation.closure)throw Error("E_INTERNAL","runtime contract implementation must remain private and static");
    (*object)["implementation_content_hash"]=contentHash(implementation);
    if(auto annotations=object->getArray("loops"))for(auto &annotation:*annotations){
      auto loop=annotation.getAsObject();const auto &helper=candidate.function(required(*loop,"head_helper_symbol"));
      if(helper.exported||helper.closure||!helper.effects.empty())throw Error("E_INTERNAL","runtime loop helper must remain private static and pure");
      (*loop)["head_helper_content_hash"]=contentHash(helper);
    }
  }
  Object result{{"schema",valueChecks?"nex.runtime-contract-candidate/3":loopChecks?"nex.runtime-contract-candidate/2":"nex.runtime-contract-candidate/1"},{"language",languageVersion},
    {"origin_revision",revision(original)},{"origin_source_hash",sourcesHash(original)},
    {"revision",revision(candidate)},{"source_hash",sourcesHash(candidate)},
    {"contract_hash",hash(json(contract,false))},{"intent_hash",verificationIntentHash(contract)},
    {"failure_code","E_ASSERT"},{"loop_checks",loopChecks},{"proof_performed",false},
    {"functions",std::move(coverage)},{"bundle",sourceBundle(candidate)},
    {"origin_bundle",sourceBundle(original)},{"contracts",contract}};
  if(valueChecks)result["predicate_scope"]="pure_source_expressions";
  return result;
}

std::string verifierVersion(){return Z3_get_full_version();}
std::string verificationIntentHash(const JSON &value){
  auto object=value.getAsObject();if(!object||object->getString("schema")!="nex.verification-contracts/1"||object->getString("language")!=languageVersion)throw Error("E_CONTRACT","unsupported verification intent format/language");
  auto functions=object->getArray("functions");if(!functions||functions->empty()||functions->size()>64)throw Error("E_CONTRACT","verification intent requires 1..64 functions");Object intents;
  for(const auto &item:*functions){
    auto function=item.getAsObject();if(!function)throw Error("E_CONTRACT","invalid verification intent function");auto name=required(*function,"symbol");if(intents.get(name))throw Error("E_CONTRACT","duplicate verification intent function");
    Array pre,post;for(const auto &text:clauses(*function,"requires"))pre.push_back(text);for(const auto &text:clauses(*function,"ensures"))post.push_back(text);
    intents[name]=Object{{"returns",required(*function,"returns")},{"requires",std::move(pre)},{"ensures",std::move(post)}};
  }
  return hash(json(Object{{"schema","nex.verification-intent/1"},{"language",languageVersion},{"functions",std::move(intents)}},false));
}
JSON contractTemplate(const Program &p,const std::string &symbol){
  const auto &f=p.function(symbol);std::map<LoopKey,S> found;loops(f.body,found);Array annotations;
  for(const auto &[key,loop]:found)annotations.push_back(Object{{"line",key.first},{"column",key.second},{"invariants",Array{"true"}},{"decreases",""}});
  std::string result=f.result==Type::Unit?"":"result";while(std::any_of(f.params.begin(),f.params.end(),[&](const auto &param){return param.name==result;}))result+="_";
  return Object{{"schema","nex.verification-contracts/1"},{"language",languageVersion},{"expected_revision",revision(p)},{"source_hash",sourcesHash(p)},
    {"functions",Array{Object{{"symbol",f.name},{"content_hash",contentHash(f)},{"returns",result},{"requires",Array{}},{"ensures",Array{"true"}},{"loops",std::move(annotations)}}}}};
}
JSON verifyContracts(const Program &p,const JSON &contract,const JSON &graph,const VerificationOptions &options){
  auto parsed=contracts(p,contract);std::set<std::string> selected;
  if(options.symbol.empty())for(const auto &[symbol,spec]:parsed)selected.insert(symbol);
  else {auto symbol=p.function(options.symbol).name;if(!parsed.contains(symbol))throw Error("E_CONTRACT","selected function has no contract");selected.insert(symbol);}
  auto folder=std::filesystem::absolute(std::filesystem::path(options.directory)/("run-"+std::to_string(std::random_device{}())+"-"+std::to_string(std::random_device{}())));
  if(!std::filesystem::create_directories(folder))throw Error("E_FILE","verification run directory already exists");
  writeFile((folder/"contracts.json").string(),json(contract)+"\n");writeFile((folder/"source-bundle.json").string(),json(sourceBundle(p))+"\n");
  auto deadline=Clock::now()+std::chrono::seconds(options.totalTimeoutSeconds);Array reports;bool ok=true;
  for(const auto &symbol:selected){
    auto path=folder/hash(symbol);auto report=Engine(p,parsed,options,deadline).run(p.function(symbol),path);auto object=report.getAsObject();
    for(const auto &node:*graph.getAsObject()->getArray("nodes")){auto value=node.getAsObject();if(value->getString("name")==symbol){(*object)["node_id"]=value->getString("id")->str();break;}}
    if(object->getString("status")!="proven")ok=false;reports.push_back(std::move(report));
  }
  Object report{{"schema","nex.verification/1"},{"ok",ok},{"revision",revision(p)},{"source_hash",sourcesHash(p)},{"contract_hash",hash(json(contract,false))},{"intent_hash",verificationIntentHash(contract)},{"toolchain",NEX_VERSION},{"compiler_build",NEX_BUILD_ID},{"language",languageVersion},{"solver","Z3"},{"solver_version",verifierVersion()},
    {"limits",Object{{"solver_timeout_ms",options.solverTimeoutMs},{"solver_resource_limit",options.resourceLimit},{"total_timeout_seconds",options.totalTimeoutSeconds},{"obligations_per_function",4096},{"paths",256},{"call_depth",32},{"symbolic_steps",50000}}},
    {"coverage","pure i64/bool/unit functions; checked arithmetic/assertions; annotated while loops with inductive invariants and strict nonnegative i64 ranking; fully inlined nonrecursive callees"},
    {"trust_boundary","Z3 and NEX verification translation are trusted; no proof of compiler/native/TypeScript/runtime correctness, allocation/resource limits, external libraries or unsupported values/effects"},
    {"directory",folder.string()},{"output",(folder/"report.json").string()},{"functions",std::move(reports)}};
  writeFile((folder/"report.json").string(),json(JSON(Object(report)))+"\n");
  // All queries and results remain in the saved artifact; cap the CLI response.
  for(auto &function:*report.getArray("functions")){
    auto object=function.getAsObject();auto results=std::move(*object->getArray("obligations"));Array bounded;
    for(const auto &result:results)if(result.getAsObject()->getString("status")!="proven"&&result.getAsObject()->getString("status")!="consistent"&&bounded.size()<32)bounded.push_back(result);
    (*object)["obligations"]=std::move(bounded);
  }
  report["schema"]="nex.verification-session/1";return report;
}
}
