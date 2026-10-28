#include "nex/task_frontend.h"
#include "nex/task_ir.h"
#include "nex/task_machine.h"
#include "nex/task_reference.h"
#include <iostream>
#include <functional>
#include <algorithm>
using namespace nex;
namespace {
unsigned cases=0;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const char *code,F action){try{action();}catch(const Error &e){require(e.code==code,"wrong continuation rejection");++cases;return;}throw std::runtime_error("missing continuation rejection");}
Program source(const std::string &text){auto p=parseSourceExceptionTasksPrototype("module ir_exceptions;\n"+text,"ir-exceptions.nex");check(p);return p;}
}
int main(){try{
  static_assert(TaskInstruction::Eval==0&&TaskInstruction::Poll==10&&TaskInstruction::PushHandler==11);
  auto baseline=nexrt::liveObjects.load();
  {
    auto p=source(R"(fn main()->i64 !{task}{var value:i64=1;try{task_yield();value=42;throw("USER","payload");}catch(code,message){assert(code=="USER"&&message=="payload");return value;}})");
    auto ir=lowerTaskFunction(p,p.function("main"),false,true);validateTaskIR(ir);
    auto handler=std::find_if(ir.code.begin(),ir.code.end(),[](const auto &op){return op.kind==TaskInstruction::PushHandler;});
    require(handler!=ir.code.end(),"handler instruction missing");auto push=size_t(handler-ir.code.begin()),caught=handler->yes;
    require(ir.code[caught].kind==TaskInstruction::Catch&&handler->no>0,"handler cleanup floor missing");
    auto invalid=[&](const std::function<void(TaskFunctionIR&)> &edit){auto bad=ir;edit(bad);rejects("E_TASK_STATE",[&]{validateTaskIR(bad);});};
    invalid([&](auto &bad){bad.code[push].yes=bad.code.size();});
    invalid([&](auto &bad){bad.code[push].yes=push;});
    invalid([&](auto &bad){bad.code[push].no=bad.slots.size()+1;});
    invalid([&](auto &bad){bad.code[caught].bindings.pop_back();});
    invalid([&](auto &bad){bad.code[caught].bindings[1]=bad.code[caught].bindings[0];});
    invalid([&](auto &bad){bad.slots[bad.code[caught].bindings[0]].type=Type::I64;});
    invalid([&](auto &bad){auto raised=std::find_if(bad.code.begin(),bad.code.end(),[](const auto &op){return op.kind==TaskInstruction::Raise;});raised->inputs.pop_back();});
    invalid([&](auto &bad){bad.code[0].kind=static_cast<TaskInstruction::Kind>(31);});
    TaskMachine machine(p,"main");auto wait=machine.advance();require(wait.kind==TaskTransition::Waiting&&wait.operation=="task_yield","yield was not lowered");
    SourceException error("WRONG","ticket",{});
    rejects("E_TASK_STATE",[&]{machine.resumeSourceException(wait.ticket+1,error);});
    rejects("E_TASK_STATE",[&]{machine.advance();});
    machine.resume(wait.ticket);auto done=machine.advance();require(done.kind==TaskTransition::Done&&done.value.scalar==42,"outer assignment lost across handler");++cases;
    rejects("E_TASK_STATE",[&]{machine.resumeSourceException(wait.ticket,error);});
    rejects("E_TASK_STATE",[&]{machine.advance();});
    rejects("E_LIMIT",[&]{TaskMachine tiny(p,"main",{},1000,{},0,1);});
    rejects("E_TASK_STATE",[&]{TaskMachine deep(p,"main",{},1000,{},256);});
  }
  require(nexrt::liveObjects.load()==baseline,"normal catch retained values");
  {
    auto p=source(R"(fn main()->i64 !{task,throw}{try{return with_tasks(1,fn(s:task_scope)->i64{return 0;});}catch(code,message){assert(code=="E_LIMIT"&&message=="λ\u0000🙂");task_yield();throw;}})");
    TaskMachine machine(p,"main");auto wait=machine.advance();require(wait.operation=="with_tasks","missing group-close boundary");
    Span origin;origin.file="original-child.nex";origin.line=47;origin.column=9;origin.begin=10;origin.end=20;
    SourceException error("E_LIMIT",std::string("λ\0🙂",7),origin);
    machine.resumeSourceException(wait.ticket,error);
    rejects("E_TASK_STATE",[&]{machine.resumeSourceException(wait.ticket,error);});
    wait=machine.advance();require(wait.operation=="task_yield","catch did not survive another suspension");machine.resume(wait.ticket);
    bool raised=false;try{machine.advance();}catch(const SourceException &e){raised=true;require(e.code==error.code&&e.message==error.message&&e.span.file==origin.file&&e.span.line==47&&e.span.column==9&&e.span.begin==10&&e.span.end==20,"rethrow changed the original payload/span");}
    require(raised,"source-error response became a normal value");++cases;
  }
  require(nexrt::liveObjects.load()==baseline,"source-error response retained values");
  {
    auto p=parseTaskPrototype("module retained;fn main()->unit !{task}{task_yield();}","retained.nex");check(p);TaskMachine machine(p,"main");auto wait=machine.advance();
    rejects("E_TASK_STATE",[&]{machine.resumeSourceException(wait.ticket,SourceException("USER","private",{}));});machine.resume(wait.ticket);require(machine.advance().kind==TaskTransition::Done,"private rejection changed retained machine state");++cases;
    rejects("E_LANGUAGE_VERSION",[&]{evaluateSourceExceptionTaskIRPrototype(p);});
  }
  {
    auto p=source(R"(fn main()->i64 !{task}{var n:i64=0;while n<1000{try{let garbage:list<str>=["a","b","c"];task_yield();throw("LOOP",str(n));}catch(code,message){assert(code=="LOOP");}n=n+1;}return 42;})");
    TaskMachine machine(p,"main");size_t yields=0;int64_t peak=0;for(;;){auto next=machine.advance();peak=std::max<int64_t>(peak,nexrt::liveObjects.load()-baseline);if(next.kind==TaskTransition::Done){require(next.value.scalar==42,"loop result changed");break;}++yields;machine.resume(next.ticket);}
    require(yields==1000&&peak<100&&machine.pendingActions()==0,"loop accumulated handler frames or owned values");++cases;
  }
  require(nexrt::liveObjects.load()==baseline,"loop retained managed values");
  std::cout<<json(llvm::json::Object{{"ok",true},{"cases",cases},{"task_ir_machine",true},{"native_task_execution",false},{"physical_workers",false}})<<'\n';return 0;
}catch(const Error &e){std::cerr<<e.code<<": "<<e.what()<<" at "<<e.span.line<<'\n';}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';}return 1;}
