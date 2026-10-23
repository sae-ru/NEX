#include "nex/task_ir.h"
#include "nex/task_frontend.h"
#include <algorithm>
#include <iostream>

using namespace nex;
namespace {
unsigned cases=0,assertions=0;
void require(bool value,const char *message){++assertions;if(!value)throw std::runtime_error(message);}
Program source(const std::string &body,SourceLanguage language=SourceLanguage::TaskFiles020){
  auto p=parseVersioned("module debug_meta;\n"+body,"debug-meta.nex",language);check(p);return p;
}
llvm::json::Value span(const Span &s){return llvm::json::Array{s.line,s.column,s.begin,s.end,s.file};}
llvm::json::Value atom(E e){
  if(!e)return nullptr;llvm::json::Array args;for(auto a:e->args)args.push_back(atom(a));
  return llvm::json::Object{{"kind",int(e->kind)},{"text",e->text},{"number",e->number},{"type",typeName(e->type)},
    {"span",span(e->span)},{"args",std::move(args)}};
}
llvm::json::Value execution(const TaskFunctionIR &ir){
  llvm::json::Array slots,code,parameters,captures;
  for(const auto &s:ir.slots)slots.push_back(llvm::json::Object{{"name",s.name},{"type",typeName(s.type)},{"span",span(s.span)},{"temporary",s.temporary}});
  for(const auto &op:ir.code){llvm::json::Array inputs,bindings;for(auto id:op.inputs)inputs.push_back(id);for(auto id:op.bindings)bindings.push_back(id);
    code.push_back(llvm::json::Object{{"kind",int(op.kind)},{"span",span(op.span)},{"output",op.output},{"inputs",std::move(inputs)},{"bindings",std::move(bindings)},
      {"yes",op.yes},{"no",op.no},{"atom",atom(op.atom)},{"pattern",op.pattern?canonicalPattern(op.pattern):llvm::json::Value(nullptr)},
      {"operation",op.operation},{"indirect",op.indirect},{"propagated_error",op.propagatedError}});
  }
  for(auto id:ir.parameters)parameters.push_back(id);for(auto id:ir.captures)captures.push_back(id);
  return llvm::json::Object{{"name",ir.name},{"result",typeName(ir.result)},{"slots",std::move(slots)},{"code",std::move(code)},{"parameters",std::move(parameters)},{"captures",std::move(captures)}};
}
TaskFunctionIR lowered(const Program &p,const std::string &name="main"){
  const auto &f=p.function(name);auto ordinary=lowerTaskFunction(p,f,true),debug=lowerTaskFunction(p,f,true,true);
  require(!ordinary.debug&&debug.debug.has_value(),"debug metadata was not opt-in");
  require(json(execution(ordinary),false)==json(execution(debug),false),"debug metadata changed execution IR or ordinals");
  for(size_t i=0;i<ordinary.code.size();++i)require(ordinary.code[i].source==debug.code[i].source,"debug metadata changed operation origins");
  require(!debug.debug->points.empty()&&debug.debug->points.front().kind==TaskDebugPointIR::Entry,"missing logical entry");
  return debug;
}
const TaskDebugPointIR &point(const TaskFunctionIR &ir,const void *source,TaskDebugPointIR::Kind kind){
  auto found=std::find_if(ir.debug->points.begin(),ir.debug->points.end(),[&](const auto &p){return p.source==source&&p.kind==kind;});
  require(found!=ir.debug->points.end(),"missing exact source point");return *found;
}
bool visible(const TaskDebugPointIR &point,uint32_t id){return std::find(point.visible.begin(),point.visible.end(),id)!=point.visible.end();}
void invalid(const TaskFunctionIR &ir){try{validateTaskIR(ir);}catch(const Error &e){require(e.code=="E_TASK_STATE","wrong invalid metadata diagnostic");return;}throw std::runtime_error("invalid metadata accepted");}
}
int main(){try{
  {
    auto p=source("fn main()->i64 !{task}{var n:i64=0;while n<2{task_yield();n=n+1;}return n;}");
    auto before=revision(p);auto ir=lowered(p);require(revision(p)==before,"metadata changed canonical revision");
    const auto &loop=point(ir,p.function("main").body[1]->expr.get(),TaskDebugPointIR::Loop);
    require(ir.code[loop.pc].kind==TaskInstruction::Poll,"loop point does not precede its existing poll");
    require(std::any_of(ir.code.begin(),ir.code.end(),[&](const auto &op){return op.kind==TaskInstruction::Jump&&op.yes==loop.pc;}),"loop revisit lost its stable point");
    for(const auto &entry:ir.debug->points)if(entry.kind==TaskDebugPointIR::Resume)
      require(entry.pc>0&&(ir.code[entry.pc-1].kind==TaskInstruction::Pause||ir.code[entry.pc-1].kind==TaskInstruction::Call),"resume did not follow an actual continuation boundary");
    ++cases;
  }
  {
    auto p=source("fn main()->i64 !{task}{let x:i64=10;if true{let x:i64=x+1;task_yield();}task_yield();return x;}");auto ir=lowered(p);
    const auto &f=p.function("main");auto outer=ir.debug->bindings[0].id,inner=ir.debug->bindings[1].id;
    auto &initial=point(ir,f.body[1]->body[0].get(),TaskDebugPointIR::Statement);
    require(visible(initial,outer)&&!visible(initial,inner),"inner name appeared during its initializer");
    auto &inside=point(ir,f.body[1]->body[1].get(),TaskDebugPointIR::Statement);
    require(visible(inside,outer)&&visible(inside,inner)&&inside.visible.back()==inner,"shadowed identities or lookup ordering lost");
    auto &outside=point(ir,f.body[2].get(),TaskDebugPointIR::Statement);
    require(visible(outside,outer)&&!visible(outside,inner),"retired block binding remained visible");++cases;
  }
  {
    auto p=source("fn gate(n:i64)->bool !{task}{task_yield();return n>0;}fn main()->i64 !{task}{match [0]{[x] if gate(x)=>{return x;},_=>{task_yield();return 42;}}}");auto ir=lowered(p);
    auto matched=ir.debug->bindings.front().id;const auto &match=p.function("main").body[0]->expr;
    auto &guard=point(ir,match->args[match->arms[0]->guard].get(),TaskDebugPointIR::Call);
    require(visible(guard,matched),"matched guard did not expose initialized pattern binding");
    auto &other=point(ir,match->arms[1]->body[0].get(),TaskDebugPointIR::Statement);
    require(!visible(other,matched),"failed guarded arm leaked pattern visibility");++cases;
  }
  {
    auto p=source("fn leaf(n:i64)->i64 !{task}{task_yield();return n;}fn main()->i64 !{task}{return leaf(leaf(42));}");auto ir=lowered(p);
    auto outer=p.function("main").body[0]->expr,inner=outer->args[0];
    require(point(ir,inner.get(),TaskDebugPointIR::Call).pc<point(ir,outer.get(),TaskDebugPointIR::Call).pc,"call points changed left-to-right argument evaluation");++cases;
  }
  {
    auto p=source("fn gate()->bool !{task}{task_yield();return true;}fn main()->i64 !{task}{if false&&gate(){return 0;}return 42;}");auto ir=lowered(p);
    auto call=p.function("main").body[0]->expr->args[1];auto pc=point(ir,call.get(),TaskDebugPointIR::Call).pc;
    require(std::any_of(ir.code.begin(),ir.code.begin()+pc,[&](const auto &op){return op.kind==TaskInstruction::Branch&&op.yes<=pc&&op.no>pc;}),"short-circuited call point is not on the skipped branch");++cases;
  }
  {
    auto p=source("fn inspect(scope:task_scope)->i64 !{task}{let safe:i64=42;task_yield();return safe;}");auto ir=lowered(p,"inspect");
    require(ir.debug->bindings[0].opaque&&!ir.debug->bindings[1].opaque,"authority opacity hid an unrelated scalar or exposed a capability");
    require(visible(ir.debug->points.front(),ir.debug->bindings[0].id)&&!visible(ir.debug->points.front(),ir.debug->bindings[1].id),"entry parameter/local initialization visibility wrong");++cases;
  }
  {
    auto p=source("fn inspect(offset:i64)->i64 !{task}{let callback:fn(i64)->i64=fn(n:i64)->i64{return n+offset;};task_yield();return callback(1);}");auto ir=lowered(p,"inspect");
    require(!ir.debug->bindings.back().opaque,"known resource-free closure was made opaque");++cases;
  }
  {
    auto p=source("fn main()->i64 !{task}{task_yield();return 42;}",SourceLanguage::Tasks019);auto before=revision(p);auto ir=lowered(p);
    auto metadata=taskDebugFunctionMetadata(p,p.function("main"),ir,"frozen-source.nex");auto rebuilt=taskDebugFunctionMetadata(p,p.function("main"),"frozen-source.nex");
    require(json(llvm::json::Value(std::move(metadata)),false)==json(llvm::json::Value(std::move(rebuilt)),false),"watch rederivation differs from emitted metadata");
    require(std::string(programLanguage(p))=="0.19"&&revision(p)==before,"explicit019 metadata was relabelled");++cases;
  }
  {
    auto p=source("fn main()->i64 !{task}{let n:i64=42;task_yield();return n;}");auto ir=lowered(p);auto corrupt=ir;corrupt.debug->points[0].pc=ir.code.size();invalid(corrupt);
    corrupt=ir;corrupt.debug->bindings[0].id=0;invalid(corrupt);
    corrupt=ir;corrupt.debug->points[0].visible={999};invalid(corrupt);++cases;
  }
  std::cout<<json(llvm::json::Object{{"ok",true},{"cases",cases},{"assertions",assertions},
    {"opt_in_metadata_only",true},{"unchanged_execution_ir",true},{"initialized_lexical_visibility",true},
    {"live_debugger_claim",false}})<<'\n';return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
