#include "host_test.h"
#include "nex_task_session.h"
#include <filesystem>
#include <iostream>
#ifndef _WIN32
#include <dlfcn.h>
#endif

namespace {
using namespace nexrt;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F> void rejects(const std::string &code,F action){
  try{action();}catch(const Trap &error){require(error.code==code,("expected "+code+", got "+error.code+": "+std::string(trapMessage(error))).c_str());return;}
  throw std::runtime_error("expected image session failure "+code);
}
struct Image {
#ifdef _WIN32
  HMODULE value;
  explicit Image(const char *path):value(LoadLibraryW(platform::wide(path).c_str())){require(value,"cannot load session image");}
  ~Image(){FreeLibrary(value);}
  void *symbol(const char *name){auto p=GetProcAddress(value,name);require(p,"missing session export");return reinterpret_cast<void*>(p);}
#else
  void *value;
  explicit Image(const char *path):value(dlopen(path,RTLD_NOW|RTLD_LOCAL)){if(!value)throw std::runtime_error(dlerror());}
  ~Image(){dlclose(value);}
  void *symbol(const char *name){auto p=dlsym(value,name);if(!p)throw std::runtime_error(dlerror());return p;}
#endif
  const TaskCodeDescriptor &code(const char *name){return *reinterpret_cast<const TaskCodeDescriptor*(*)()>(symbol(name))();}
};
Value payloadCell(const NativeSourceException &error,const std::string &name){
  require(error.code==name&&error.payload,"wrong source error type or absent payload");
  const auto &value=error.payload->value;
  require(value.tag==Value::Object&&value.object&&value.object->kind==Data::Record&&value.object->values.size()==1,"source record payload differs");
  return value.object->values[0];
}
int images(int argc,char **argv){
  require(argc==21,"expected three images and seventeen checked task-code accessors");
  auto baseline=liveObjects.load();unsigned cases=0;
  // Images outlive all sessions, values and typed-error packets.
  Image core(argv[1]),mid(argv[2]),files(argv[3]);
  const auto &make=core.code(argv[4]),&get=core.code(argv[5]),&add=core.code(argv[6]),&fail=core.code(argv[7]),
    &snapshot=core.code(argv[8]),&cycle=core.code(argv[9]),&spin=core.code(argv[10]),&overflow=core.code(argv[11]),
    &twice=mid.code(argv[12]),&open=files.code(argv[13]),&read=files.code(argv[14]),&seek=files.code(argv[15]),
    &close=files.code(argv[16]),&fileError=files.code(argv[17]),&empty=files.code(argv[18]),&stash=files.code(argv[19]),&use=files.code(argv[20]);
  {
    NativeTaskSession session;
    auto value=session.invoke(make,{Value(40)});
    auto view=session.invoke(snapshot,{value});
    require(view.object->values[0].object==value.object&&view.object->values[1].object->text==std::string("\xd0\xaf\0\xf0\x9f\xa7\xa0",7),"snapshot identity or Unicode/NUL text differs");
    for(unsigned i=0;i<64;++i){session.invoke(twice,{value});auto alias=session.invoke(add,{value,Value(1)});require(alias.object==value.object,"returned source cell lost identity");}
    require(session.invoke(get,{value}).scalar==232,"cross-image persistent mutation differs");++cases;
    try{session.invoke(fail,{value});throw std::runtime_error("compiled source error disappeared");}
    catch(const NativeSourceException &error){require(payloadCell(error,"native_session_core::Fault").object==value.object,"typed error copied persistent cell");}
    require(!session.closed()&&session.invoke(get,{value}).scalar==233,"typed error damaged subsequent call");++cases;
    auto loop=session.invoke(cycle);WeakValueOwner<Data> weak=loop.object;loop=Value();
    require(session.collect().reclaimedCells==1&&weak.expired(),"compiled idle cycle was retained");++cases;
    auto stats=session.statistics();require(stats.heap.cells==1&&stats.sourceErrors==1&&stats.invocations>130,"compiled invocation statistics differ");
    session.finish();require(view.object->values[1].object->text.size()==7,"close damaged immutable retained view");++cases;
  }
  {
    NativeTaskSession session;auto value=session.invoke(make,{Value(0)});bool located=false;
    try{session.invoke(overflow,{value});throw std::runtime_error("compiled overflow did not fail");}
    catch(const LocatedTrap &error){require(error.code=="E_OVERFLOW"&&!error.source.empty(),"fatal compiled source attribution differs");located=true;}
    require(located&&session.closed()&&session.statistics().fatalExits==1,"fatal compiled call did not revoke owner");session.finish();++cases;
  }
  for(const auto &reason:{std::string("E_LIMIT"),std::string("E_TIMEOUT"),std::string("E_CANCELLED")}){
    NativeTaskSession session;auto value=session.invoke(make,{Value(0)});NativeTaskInvocationOptions options;unsigned polls=0;
    if(reason=="E_LIMIT")options.limits.steps=1000;
    if(reason=="E_TIMEOUT"){options.limits.steps=maximumTaskExecutionSteps;options.limits.timeoutMs=5;}
    if(reason=="E_CANCELLED")options.cancelled=[&]{return ++polls>30;};
    rejects(reason,[&]{session.invoke(spin,{value},options);});require(session.closed(),"compiled control exit left session open");session.finish();++cases;
  }
  {
    // The grant and its FileScope explicitly outlive the session. Source code
    // does not acquire authority from whichever environment happens to be live.
    FileScope grant(true);auto host=std::make_shared<TaskFrameHostContext>();
    host->fileReads=captureFileReadGrant(false);host->fileWrites=captureFileWriteGrant(false);
    auto cleanup=std::make_shared<ResourceExecutor>();host->fileCleanup=cleanup;
    {
      NativeTaskSession session({},host);auto value=session.invoke(open);
      require(session.invoke(read,{value}).object->text==std::string("A\xf0\x9f\x8c\x8d\0Z",7),"file owner or Unicode bytes failed across calls");
      require(session.invoke(read,{value}).object->text.empty(),"persistent file cursor reset between calls");
      session.invoke(seek,{value});require(session.invoke(read,{value}).object->text.size()==7,"persistent seek failed");session.invoke(close,{value});++cases;
      Value packet;
      try{session.invoke(fileError);throw std::runtime_error("file source error disappeared");}
      catch(const NativeSourceException &error){packet=payloadCell(error,"native_session_files::Fault");}
      require(session.invoke(read,{packet}).object->text.size()==7,"typed error failed to promote returned file owner");++cases;
      auto unreturned=session.invoke(empty);session.invoke(stash,{unreturned});
      rejects("E_RESOURCE_SCOPE",[&]{session.invoke(use,{unreturned});});
      require(!session.closed(),"invalid expired-resource preflight closed a healthy session");
      auto ordinary=session.invoke(make,{Value(17)});require(session.invoke(get,{ordinary}).scalar==17,"source retained file accidentally renewed authority");++cases;
      unreturned=Value();session.collect();session.finish();++cases;
    }
    cleanup->finish();
  }
  {NativeTaskSession session;rejects("E_TASK_HOST",[&]{session.invoke(open);});require(!session.closed(),"missing-host preflight ended healthy session");session.finish();++cases;}
  require(cases==13&&liveObjects.load()==baseline&&!inRequestScope(),"image session case count, objects or TLS differ");nex_runtime_finish();
  std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"live_delta\":0,\"source_error_continues\":true,\"file_return_promotion\":true,\"unreturned_resource_not_promoted\":true}\n";return 0;
}
}
int runNativeTaskSessionImages(int argc,char **argv){try{return images(argc,argv);}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
