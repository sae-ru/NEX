#include "nex/task_frontend.h"
#include "nex/task_machine.h"
#include <iostream>
#include <chrono>
#include <filesystem>
#include <thread>

using namespace nex;
namespace {
unsigned cases=0,scenarios=0;
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const char *code,F action){try{action();}catch(const Error &error){require(error.code==code,std::string("expected ")+code+", got "+error.code+": "+error.what());++cases;return;}throw std::runtime_error(std::string("expected ")+code);}
Program source(const std::string &body){auto p=parseTaskPrototype("module continuation;\n"+body,"continuation.nex");check(p);return p;}
void replace(std::string &text,const std::string &from,const std::string &to){for(size_t at=0;(at=text.find(from,at))!=std::string::npos;at+=to.size())text.replace(at,from.size(),to);}
Program oracle(std::string body){replace(body,"task_yield();","");replace(body,"!{task,io}","!{io}");replace(body,"!{task}","");auto p=parse("module continuation;\n"+body,"continuation.nex");check(p);return p;}
void agrees(const std::string &body,unsigned expectedYields,bool transferThread=false){
  auto before=nexrt::liveObjects.load();
  {
    auto p=source(body),reference=oracle(body);auto expected=evaluate(reference);TaskMachine machine(p,"main");unsigned yields=0;TaskTransition transition;
    for(;;){
      if(transferThread){std::exception_ptr failure;std::thread worker([&]{try{transition=machine.advance();}catch(...){failure=std::current_exception();}});worker.join();if(failure)std::rethrow_exception(failure);}
      else transition=machine.advance();
      if(transition.kind==TaskTransition::Done)break;
      require(transition.operation=="task_yield"&&transition.result==Type::Unit&&transition.arguments.empty(),"unexpected wait descriptor");++yields;
      auto ticket=transition.ticket;rejects("E_TASK_STATE",[&]{machine.advance();});rejects("E_TASK_STATE",[&]{machine.resume(ticket+1);});machine.resume(ticket);rejects("E_TASK_STATE",[&]{machine.resume(ticket);});
    }
    require(machine.finished()&&yields==expectedYields,"yield sequence differs: "+std::to_string(yields));
    if(p.function("main").result!=Type::Unit){auto value=llvm::json::parse(nexrt::representation(transition.value));require(bool(value)&&*value==expected.value,"continuation value differs from independent AST interpreter");}
    require(machine.output()==expected.output,"left-to-right output differs from AST interpreter");rejects("E_TASK_STATE",[&]{machine.advance();});
  }
  require(nexrt::liveObjects.load()==before,"continuation leaked managed objects");++cases;++scenarios;
}
void trapAgrees(const std::string &body){
  auto p=source(body),reference=oracle(body);std::string code,expectedOutput;unsigned line=0;
  try{evaluate(reference);}catch(const Error &error){code=error.code;line=error.span.line;expectedOutput=error.output;}
  require(!code.empty(),"oracle did not trap");auto before=nexrt::liveObjects.load();
  {
    TaskMachine machine(p,"main");bool trapped=false;
    try{for(;;){auto step=machine.advance();if(step.kind==TaskTransition::Done)break;machine.resume(step.ticket);}}
    catch(const Error &error){trapped=true;require(error.code==code&&error.span.line==line,"continuation trap code/source line differs: "+error.code+"/"+std::to_string(error.span.line)+" vs "+code+"/"+std::to_string(line));require(error.output==expectedOutput&&machine.output()==expectedOutput,"output before a checked trap was lost");}
    require(trapped,"continuation did not trap");rejects("E_TASK_STATE",[&]{machine.advance();});
  }
  require(nexrt::liveObjects.load()==before,"trap left retained continuation objects");++cases;++scenarios;
}
}
int main()try{
  agrees(R"(
fn main()->i64 !{task}{var i:i64=0;var total:i64=0;while i<21{task_yield();total=total+2;i=i+1;}return total;}
)",21,true);
  agrees(R"(
fn factorial(n:i64)->i64 !{task}{task_yield();if n==0{return 1;}return n*factorial(n-1);}
fn main()->i64 !{task}{return factorial(8);}
)",9);
  agrees(R"(
fn mark(n:i64)->i64 !{task,io}{task_yield();print(n);return n;}
fn sum(a:i64,b:i64)->i64 !{task,io}{task_yield();print(a+b);return a+b;}
fn main()->i64 !{task,io}{return sum(mark(1),mark(2))+mark(39);}
)",4);
  agrees(R"(
fn flag(value:bool)->bool !{task,io}{task_yield();print(value);return value;}
fn main()->i64 !{task,io}{
 let a:bool=flag(false)&&flag(true);let b:bool=flag(true)||flag(false);
 let c:bool=flag(true)&&flag(true);let d:bool=flag(false)||flag(true);
 assert(!a&&b&&c&&d);return 42;
}
)",6);
  agrees(R"(
fn main()->i64 !{task}{var offset:i64=40;let compute:fn(i64)->i64 !{task}=fn(x:i64)->i64 !{task}{task_yield();return offset+x;};offset=100;return compute(2);}
)",1,true);
  agrees(R"(
fn fetch()->result<i64> !{task}{task_yield();return ok(42);}
fn main()->result<str> !{task}{let number:i64=fetch()?;task_yield();return ok(str(number));}
)",2);
  agrees(R"(
fn fetch()->result<i64> !{task}{task_yield();return err<i64>("E_SAMPLE","bad");}
fn main()->result<str> !{task}{let number:i64=fetch()?;task_yield();return ok(str(number));}
)",1);
  agrees(R"(
fn main()->i64 !{task}{
 let fetch:fn()->result<i64> !{task}=fn()->result<i64> !{task}{task_yield();let value:i64=err<i64>("E_INNER","inner")?;return ok(value);};
 let value:result<i64>=fetch();assert(!is_ok(value));return 42;
}
)",1);
  agrees(R"(
enum Reply{Ready(items:list<i64>);Empty();}
fn gate(value:i64)->bool !{task}{task_yield();return value>0;}
fn main()->i64 !{task}{let item:Reply=Reply::Ready([0,42]);return match item{
 Reply::Ready([x,y]) if gate(x)=>x,
 Reply::Ready([_,y]) if gate(y)=>y,
 _=>1
};}
)",2);
  agrees(R"(
fn gate(value:i64)->bool !{task}{task_yield();return value>0;}
fn main()->i64 !{task}{match [0]{[x] if gate(x)=>{return x;},_=>{task_yield();return 42;}}}
)",2);
  agrees(R"(
struct Box{items:list<str>;}
fn main()->i64 !{task,io}{let box:Box=Box(["A🧠\u0000Б","x"]);task_yield();print(box.items[0]);
 return len(box.items[0])+38;
}
)",1);
  agrees(R"(
fn main()->unit !{task,io}{var i:i64=0;while i<3{let text:str="temporary"+str(i);task_yield();print(text);i=i+1;}}
)",3,true);
  agrees(R"(
fn echo<T>(value:T)->T !{task}{task_yield();return value;}
fn main()->str !{task}{return echo("🧠");}
)",1);
  agrees(R"(
fn build(offset:i64)->(fn(i64)->i64 !{task}) !{task}{task_yield();return fn(value:i64)->i64 !{task}{task_yield();return offset+value;};}
fn main()->i64 !{task}{let callback:fn(i64)->i64 !{task}=build(40);return callback(2);}
)",2);
  agrees(R"(
fn fetch()->result<str> !{task}{task_yield();return err<str>("E_PARTIAL","failed");}
fn main()->result<list<str>> !{task}{return ok(["owned before suspension",fetch()?]);}
)",1);
  agrees(R"(
fn fetch()->f64 !{task}{task_yield();return 1.5;}
fn main()->str !{task}{let value:f64=fetch();task_yield();return str(value+0.5);}
)",2);
  trapAgrees(R"(
fn main()->i64 !{task}{let saved:list<str>=["owned"];task_yield();return 9223372036854775807+len(saved);}
)");
  trapAgrees(R"(
fn main()->i64 !{task}{let saved:list<str>=["owned"];task_yield();return unwrap(err<i64>("E_BAD","failure"));}
)");
  trapAgrees(R"(
fn main()->i64 !{task}{let saved:list<str>=["owned"];task_yield();return len(saved[3]);}
)");
  trapAgrees(R"(
fn fail()->i64 !{io}{print("inner");assert(false);return 0;}
fn main()->i64 !{task,io}{print("outer");task_yield();return fail();}
)");
  auto before=nexrt::liveObjects.load();
  {
    auto p=source("fn main()->unit !{task}{let held:list<str>=[\"owned while parked\"];task_yield();assert(len(held)==1);}");
    TaskMachine machine(p,"main");auto paused=machine.advance();require(paused.kind==TaskTransition::Waiting&&nexrt::liveObjects.load()>before,"parked values were not retained");
  }
  require(nexrt::liveObjects.load()==before,"abandoned parked frame leaked values");++cases;++scenarios;
  {
    auto p=source("fn main()->unit !{task}{while true{task_yield();}}");TaskMachine machine(p,"main",{},100);
    rejects("E_LIMIT",[&]{for(;;){auto paused=machine.advance();machine.resume(paused.ticket);}});
    rejects("E_TASK_STATE",[&]{machine.advance();});
    ++scenarios;
  }
  {
    auto p=source("fn recurse()->unit !{task}{recurse();} fn main()->unit !{task}{recurse();}");TaskMachine machine(p,"main");rejects("E_LIMIT",[&]{machine.advance();});++scenarios;
  }
  {
    auto p=source("fn main(s:task_scope,p:task<i64>,q:channel<i64>)->i64 !{task}{current_task_scope();let other:channel<i64>=channel_new<i64>(s,1);task_close(other);task_cancel(p);task_send(q,1);return task_wait(p)+unwrap(task_recv(q));}");
    auto ir=lowerTaskFunction(p,p.function("main"));std::vector<std::string> operations;
    for(const auto &op:ir.code)if(op.kind==TaskInstruction::Pause)operations.push_back(op.operation);
    require(operations==std::vector<std::string>{"current_task_scope","channel_new","task_close","task_cancel","task_send","task_wait","task_recv"},"source wait operations lost evaluation order");++cases;++scenarios;
  }
  {
    auto p=source("fn main()->i64 !{task}{return 42;}");auto ir=lowerTaskFunction(p,p.function("main"));ir.code.back().kind=TaskInstruction::Jump;ir.code.back().yes=ir.code.size();rejects("E_TASK_STATE",[&]{validateTaskIR(ir);});
    rejects("E_TASK_UNIMPLEMENTED",[&]{evaluate(p);});rejects("E_TASK_UNIMPLEMENTED",[&]{revision(p);});
    ++scenarios;
  }
  {
    auto directory=std::filesystem::temp_directory_path()/("nex-task-ir-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));require(std::filesystem::create_directory(directory),"temporary module directory already exists");
    try{
      writeFile((directory/"worker.nex").string(),"module worker; pub fn work(value:i64)->i64 !{task}{task_yield();return value+2;}");
      writeFile((directory/"main.nex").string(),"module app; import \"./worker.nex\" as w; fn main()->i64 !{task}{return w::work(40);}");
      auto p=loadTaskPrototype((directory/"main.nex").string(),directory.string());TaskMachine machine(p,"app::main");auto paused=machine.advance();require(paused.kind==TaskTransition::Waiting,"imported task did not suspend");machine.resume(paused.ticket);auto done=machine.advance();require(done.kind==TaskTransition::Done&&done.value.scalar==42,"module-qualified continuation call failed");++cases;++scenarios;
      std::filesystem::remove_all(directory);
    }catch(...){std::filesystem::remove_all(directory);throw;}
  }
  {
    auto p=source("server fn main()->unit !{task,fs}{task_yield();}");rejects("E_TASK_UNIMPLEMENTED",[&]{TaskMachine machine(p,"main");});++scenarios;
  }
  std::cout<<"{\"ok\":true,\"source_scenarios\":"<<scenarios<<",\"checks_including_repeated_resume_protocol\":"<<cases<<",\"native_task_execution\":false,\"public_source_tasks\":false}\n";return 0;
}catch(const std::exception &error){std::cerr<<"after "<<cases<<" cases: "<<error.what()<<'\n';return 1;}
