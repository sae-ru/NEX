#include "host_test.h"
#include "nex_host.h"
#include "nex_cell_host.h"
#include <filesystem>
#include <iostream>
#include <thread>
#ifndef _WIN32
#include <dlfcn.h>
#endif

namespace {
using H=nexrt::Handle;using V=nexrt::Value;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
struct Image {
#ifdef _WIN32
  HMODULE value;
  explicit Image(const char *path):value(LoadLibraryW(nexrt::platform::wide(path).c_str())){require(value,"cannot load reference library");}
  ~Image(){FreeLibrary(value);}
  void *symbol(const char *name){auto p=GetProcAddress(value,name);require(p,"missing reference export");return reinterpret_cast<void*>(p);}
#else
  void *value;
  explicit Image(const char *path):value(dlopen(path,RTLD_NOW|RTLD_LOCAL)){if(!value)throw std::runtime_error(dlerror());}
  ~Image(){dlclose(value);}
  void *symbol(const char *name){auto p=dlsym(value,name);if(!p)throw std::runtime_error(dlerror());return p;}
#endif
};
}
int main(int argc,char **argv){try{
  require(argc==15,"expected two images and twelve verified native symbols");
  // Pull the host's complete cell bridge into the export table. Images contain
  // generated code only and must resolve every runtime call to this one host.
  if(nexrt::inRequestScope())nex_cell_collect(0);
  const auto baseline=nexrt::liveObjects.load();
  Image a(argv[1]),b(argv[2]);
  auto make=reinterpret_cast<H*(*)(int64_t)>(a.symbol(argv[3]));
  auto alias=reinterpret_cast<H*(*)(H*)>(a.symbol(argv[4]));
  auto snapshot=reinterpret_cast<H*(*)(H*)>(a.symbol(argv[5]));
  auto closure=reinterpret_cast<H*(*)(H*)>(a.symbol(argv[6]));
  auto cycle=reinterpret_cast<H*(*)()>(a.symbol(argv[7]));
  auto raise=reinterpret_cast<int64_t(*)(H*,H**)>(a.symbol(argv[8]));
  auto read=reinterpret_cast<int64_t(*)(H*)>(b.symbol(argv[9]));
  auto write=reinterpret_cast<void(*)(H*,int64_t)>(b.symbol(argv[10]));
  auto invoke=reinterpret_cast<int64_t(*)(H*)>(b.symbol(argv[11]));
  auto faultValue=reinterpret_cast<int64_t(*)(H*)>(b.symbol(argv[12]));
  auto collect=reinterpret_cast<void(*)()>(b.symbol(argv[13]));
  auto overflow=reinterpret_cast<int64_t(*)(H*)>(b.symbol(argv[14]));
  V retained,immutable;
  unsigned calls=0,cycles=0,packets=0;
  {
    nexrt::RequestScope scope(10000000,60000);
    for(unsigned repeat=0;repeat<64;++repeat){
      {
        auto *value=make(41),*copy=alias(value),*box=snapshot(value),*callback=closure(value);calls+=4;
        if(repeat==0){
          auto saved=nexrt::readHandle(value);std::exception_ptr failure;
          // Requests cannot nest. Keep the original owner live while a second
          // thread tries this Value in its independent request/context.
          std::thread unrelated([&]{try{
            try{nexrt::RequestScope scope;auto *foreign=nexrt::makeHandle(saved);(void)read(foreign);
              throw std::runtime_error("unrelated live context accepted a foreign cell");}
            catch(const nexrt::Trap &error){require(error.code=="E_CELL_HEAP","wrong unrelated-context diagnostic");}
          }catch(...){failure=std::current_exception();}});
          unrelated.join();if(failure)std::rethrow_exception(failure);
        }
        require(value!=copy&&nexrt::readHandle(value).object==nexrt::readHandle(copy).object,"alias did not return an independently owned handle");
        auto saved=nexrt::readHandle(box);
        require(saved.object->values[0].object==saved.object->values[1].object,"snapshot lost alias identity");
        require(saved.object->values[2].object->text==std::string("\xd0\xaf\0\xf0\x9f\xa7\xa0",7),"snapshot text changed");
        require(read(value)==41&&invoke(callback)==41,"cross-image initial read failed");calls+=2;
        write(copy,42);++calls;require(read(value)==42&&invoke(callback)==42,"cross-image mutation/capture failed");calls+=2;
        nex_release(value);nex_release(copy);collect();++calls;
        auto *borrow=nexrt::makeHandle(saved.object->values[0]);write(borrow,43);++calls;
        require(invoke(callback)==43,"collection lost a returned capture");++calls;
        nex_release(borrow);nex_release(box);nex_release(callback);
      }
      collect();++calls;
      {
        auto *value=cycle();++calls;nexrt::WeakValueOwner<nexrt::Data> weak=nexrt::readHandle(value).object;
        nex_release(value);collect();++calls;require(weak.expired(),"cross-image cycle did not retire");++cycles;
      }
      {
        auto *value=make(5);H *error=nullptr;++calls;
        require(raise(value,&error)==0&&error,"typed error output did not own its packet");++calls;
        auto source=nexrt::readSourceErrorHandle(error);
        require(source.code=="reference_library::Fault"&&source.payload,"source error identity changed");
        auto *payload=nexrt::makeHandle(source.payload->value);
        require(faultValue(payload)==5,"error payload lost its cell in the other image");++calls;
        write(value,7);++calls;require(faultValue(payload)==7,"error payload copied its cell identity");++calls;
        nex_release(payload);nex_release(error);nex_release(value);++packets;
      }
      collect();++calls;
    }
    auto *value=make(9);retained=nexrt::readHandle(value);immutable=nexrt::readHandle(snapshot(value));calls+=2;
  }
  require(immutable.object->values[2].object->text==std::string("\xd0\xaf\0\xf0\x9f\xa7\xa0",7),"context close changed immutable snapshot data");
  try{
    nexrt::RequestScope other;auto *value=nexrt::makeHandle(retained);(void)read(value);
    throw std::runtime_error("ended-context reference was accepted");
  }catch(const nexrt::Trap &error){require(error.code=="E_CELL_HEAP","wrong ended-context diagnostic");}
  retained=V();immutable=V();
  for(unsigned repeat=0;repeat<3;++repeat){
    try{nexrt::RequestScope doomed;(void)overflow(make(1));throw std::runtime_error("expected overflow");}
    catch(const nexrt::Trap &error){require(error.code=="E_OVERFLOW","wrong fatal library diagnostic");}
  }
  require(nexrt::liveObjects.load()==baseline,"library reference scopes retained values");
  nex_runtime_finish();
  std::cout<<"{\"ok\":true,\"related_calls\":"<<calls<<",\"cycles\":"<<cycles<<",\"source_packets\":"<<packets<<",\"unrelated_context_rejected\":true,\"ended_context_rejected\":true,\"fatal_contexts\":3,\"live_delta\":0}\n";
  return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
