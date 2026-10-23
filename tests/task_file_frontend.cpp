#include "nex/task_frontend.h"
#include <iostream>
#include <stdexcept>

namespace {
unsigned cases=0;
nex::Program checked(const std::string &body,nex::SourceLanguage language=nex::SourceLanguage::TaskFiles020){
  auto p=nex::parseVersioned("module file_frontend;"+body,"file_frontend.nex",language);
  nex::check(p);return p;
}
void accepts(const std::string &body){checked(body);++cases;}
void rejects(const char *code,const std::string &body){
  try{checked(body);}catch(const nex::Error &e){
    if(e.code!=code)throw std::runtime_error(std::string("expected ")+code+", got "+e.code+": "+e.what());
    ++cases;return;
  }
  throw std::runtime_error(std::string("expected rejection ")+code);
}
}
int main()try{
  accepts(R"(
server fn read(path:str)->result<str> !{task,fs}{return file_read_text(path);}
server fn main()->result<str> !{task,fs}{
 return with_tasks(2,server fn(s:task_scope)->result<str> !{task,fs}{
  let p:str="input.txt";
  let t:task<result<str>>=task_spawn(s,server fn()->result<str> !{task,fs}{return read(p);});
  return task_wait(t);
 });
})");
  accepts(R"(
server fn delayed<T>(value:T)->T !{task,fs}{task_yield();return value;}
server fn main()->i64 !{task,fs}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{
 let t:task<i64>=task_spawn(s,server fn()->i64 !{task,fs}{return delayed(42);});return task_wait(t);
});}
)");
  accepts(R"(
server fn read()->result<bytes> !{fs}{return file_read_bytes("input.txt");}
server fn main()->result<bytes> !{fs}{return read();}
)");
  accepts(R"(
server fn run(f:server fn(str)->result<str> !{task,fs})->result<str> !{task,fs}{return f("input.txt");}
server fn read(path:str)->result<str> !{task,fs}{return file_read_text(path);}
server fn main()->result<str> !{task,fs}{return run(read);}
)");
  const std::string syncHelper=R"(
server fn read()->result<str> !{fs}{return file_read_text("input.txt");}
server fn main()->result<str> !{task,fs}{return read();}
)";
  rejects("E_EFFECT",syncHelper);
  // Retained019 checks the original contract before any020 migration.
  auto old=checked(syncHelper,nex::SourceLanguage::Tasks019);
  if(std::string(nex::programLanguage(old))!="0.19")throw std::runtime_error("retained019 relabeled");
  ++cases;
  rejects("E_EFFECT",R"(
server fn read()->result<str> !{fs}{return file_read_text("input.txt");}
server fn main()->result<str> !{task,fs}{let f:server fn()->result<str> !{fs}=read;return f();}
)");
  rejects("E_EFFECT",R"(
server fn wrap(f:server fn()->result<str> !{fs})->result<str> !{task,fs}{return f();}
)");
  rejects("E_EFFECT",R"(
server fn main()->i64 !{task}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{return 42;});}
)");
  rejects("E_EFFECT",R"(
server fn main()->i64 !{task,fs}{return with_tasks(1,server fn(s:task_scope)->i64 !{fs}{return 42;});}
)");
  for(const auto &effect:{"io","db","ffi"})rejects("E_EFFECT",
    std::string("server fn main(s:task_scope)->unit !{task,fs,")+effect+"}{task_spawn(s,server fn()->i64 !{task,fs,"+effect+"}{return 42;});}");
  rejects("E_EFFECT",R"(
server fn main()->result<str> !{task}{return file_read_text("input.txt");}
)");
  rejects("E_TYPE",R"(
server fn read()->result<str> !{fs}{return file_read_text("input.txt");}
server fn main()->unit !{task,fs}{let f:server fn()->result<str> !{task,fs}=read;}
)");
  rejects("E_TASK_TYPE",R"(
server fn main(s:task_scope,f:file)->unit !{task,fs}{
 task_spawn(s,server fn()->i64 !{task,fs}{let saved:file=f;return 42;});
}
)");
  auto modern=checked("fn main()->i64{return 42;}");
  auto retained=checked("fn main()->i64{return 42;}",nex::SourceLanguage::Tasks019);
  if(nex::revision(modern)==nex::revision(retained))throw std::runtime_error("019/020 revision collision");
  ++cases;
  std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"retained019\":true,\"exact_callable_effects\":true}\n";
  return 0;
}catch(const std::exception &error){std::cerr<<"after "<<cases<<" cases: "<<error.what()<<'\n';return 1;}
