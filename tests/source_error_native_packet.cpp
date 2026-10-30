#include "nex_host.h"
#include <bit>
#include <cstdio>
#include <limits>
#include <map>
#include <thread>

using namespace nexrt;
extern "C" {
Handle *nex_source_error_new_at(Handle*,Handle*,int64_t,const NativeSite*);
Handle *nex_source_error_code(Handle*);
Handle *nex_source_error_message(Handle*);
void nex_source_error_unhandled_at(Handle*,const NativeSite*);
}
namespace {
std::map<const void*,int> allocations;
bool failHandle=false;
unsigned cases=0;
const std::string key(64,'a'),other(64,'b');
const std::string text("secret λ\0🙂",14);
const std::string site="{\"site\":\"original\"}";
void require(bool yes,const char *message){if(!yes)throw std::runtime_error(message);}
template<class F>void rejected(const char *code,F action){
  try{action();}catch(const DataError &e){require(e.code==code,"incorrect packet rejection code");++cases;return;}
  throw std::runtime_error("invalid packet accepted");
}
NativeSourceException packet(Value value){
  return {"LoadError","typed source error",site,47,std::make_shared<const SourceErrorPayload>(key,std::move(value))};
}
void empty(){require(liveObjects.load()==0&&allocations.empty(),"packet/handle retained an owned allocation");}
}
extern "C" void nex_profile_enter(const char*,const char*,int64_t,const char*){}
extern "C" void nex_profile_leave(){}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *p,size_t,int pool){
  if(pool==0&&failHandle){failHandle=false;throw std::bad_alloc();}
  require(allocations.emplace(p,pool).second,"allocation registered twice");
}
extern "C" void nex_profile_free(const void *p){require(allocations.erase(p)==1,"unregistered packet allocation freed");}

int main(){try{
  {
    RequestScope request;
    auto code=makeHandle(Value(string(std::string("C\0D",3))));auto message=makeHandle(Value(string(text)));
    auto handle=nex_source_error_new_at(code,message,19,nullptr);
    const auto record=readHandle(handle);
    require(record.object->text==sourceErrorRecordV1&&record.object->values.size()==2&&record.object->ordinal==19,
        "legacy representation changed");
    auto decoded=readSourceErrorHandle(handle);
    require(decoded.code==std::string("C\0D",3)&&decoded.message==text&&!decoded.payload&&decoded.source.empty(),"legacy roundtrip changed");
    require(!sourceErrorRecordMatches(record,key),"legacy error acquired a type");
    rejected("E_SOURCE_TYPE",[&]{(void)sourceErrorRecordPayload(record,key);});
  }empty();++cases;
  for(auto value:{Value(int64_t(-42)),Value(int64_t(1),true),Value::floating(-0.0),Value::floating(1.25)}){
    auto before=value;
    auto record=nativeSourceErrorRecord(packet(std::move(value)));
    auto after=nativeSourceErrorException(record);
    require(after.payload&&after.payload->getScalar(key,before.tag).scalar==before.scalar,"scalar payload changed its tag/bits");
    require(after.line==47&&after.source==site,"scalar payload lost original source");
    require(sourceErrorRecordMatches(record,key)&&!sourceErrorRecordMatches(record,other)&&!sourceErrorRecordMatches(record,"invalid"),"typed match changed");
    rejected("E_SOURCE_TYPE",[&]{(void)after.payload->getScalar(key,Value::Object);});
    rejected("E_SOURCE_TYPE",[&]{(void)after.payload->getScalar(other,before.tag);});
    rejected("E_SOURCE_TYPE",[&]{(void)after.payload->getScalar(key,before.tag==Value::Integer?Value::Boolean:Value::Integer);});
    rejected("E_SOURCE_TYPE",[&]{(void)after.payload->getObject(key,Data::String);});
    ++cases;
  }empty();
  std::weak_ptr<Data> retained;
  std::exception_ptr escaped;
  {
    RequestScope request;
    auto parent=nex_owned_enter(),child=nex_owned_enter();
    auto nested=std::make_shared<Data>(Data::Record);nested->text="LoadError::Missing";
    nested->values={Value(string(text)),Value(int64_t(42))};retained=nested;
    auto original=packet(Value(nested));auto handle=makeSourceErrorHandle(original);
    original.payload.reset();nested.reset();
    // Generated callees keep the error handle while retiring their frame.
    nex_owned_leave(child,handle);
    auto body=nativeSourceErrorException(readHandle(handle));
    require(body.payload->getObject(key,Data::Record).object==retained.lock(),"managed packet cloned/lost its owned aggregate");
    rejected("E_SOURCE_TYPE",[&]{(void)body.payload->getObject(key,Data::List);});
    for(int observation=0;observation<2;++observation){
      auto code=nex_source_error_code(handle),message=nex_source_error_message(handle);
      require(readHandle(code).object->text=="LoadError"&&readHandle(message).object->text=="typed source error",
          "legacy view formatted the secret payload");
      nex_release(code);nex_release(message);
      try{nex_source_error_unhandled_at(handle,nullptr);}
      catch(const NativeSourceException &e){
        require(e.payload&&e.payload->value.object==retained.lock()&&e.line==47&&e.source==site,"native boundary discarded payload or original site");
        escaped=std::current_exception();
      }
      require(bool(escaped),"native error was not thrown");
    }
    nex_owned_leave(parent,nullptr);
    require(!retained.expired(),"frame cleanup dropped the retained exception value");
  }
  require(!retained.expired(),"request cleanup dropped the retained exception value");
  // Copy through exception_ptr and another thread, then encode in a new request.
  std::exception_ptr delivered;
  std::thread receiver([&]{
    try{std::rethrow_exception(escaped);}catch(const NativeSourceException &e){
      RequestScope request;
      auto handle=makeSourceErrorHandle(e);
      try{nex_source_error_unhandled_at(handle,nullptr);}catch(...){delivered=std::current_exception();}
    }
  });receiver.join();
  require(bool(delivered),"native thread handoff lost error");
  escaped=nullptr;require(!retained.expired(),"last native error did not retain its payload");
  delivered=nullptr;require(retained.expired(),"last native error leaked payload");empty();++cases;
  {
    auto original=packet(Value(string(text)));auto handleValue=nativeSourceErrorRecord(original);
    auto replacement=nativeSourceErrorRecord(NativeSourceException("OTHER","replacement",site,51));
    original.payload.reset();handleValue={};
    require(!nativeSourceErrorException(replacement).payload,"replacement inherited the old payload");
  }empty();++cases;
  {
    auto original=packet(Value(string(text)));auto value=nativeSourceErrorRecord(original);
    // Matching keys alone never authorize an unsafe scalar/object cast.
    rejected("E_SOURCE_TYPE",[&]{(void)sourceErrorRecordPayload(value,key).getScalar(key,Value::Integer);});
    rejected("E_SOURCE_TYPE",[&]{(void)sourceErrorRecordPayload(value,other);});
    rejected("E_SOURCE_TYPE",[&]{(void)sourceErrorRecordPayload(value,key).getObject(key,Data::Bytes);});
    const auto payload=sourceErrorRecordPayload(value,key).getObject(key,Data::String);
    require(payload.object->text==text,"checked handler changed Unicode/NUL bytes");
  }empty();++cases;
  // Reject malformed trusted-host records before field access or kind casts.
  rejected("E_RUNTIME",[]{(void)nativeSourceErrorException(Value(int64_t(1)));});
  rejected("E_RUNTIME",[]{(void)nativeSourceErrorException(Value(std::shared_ptr<Data>()));});
  {
    auto record=nativeSourceErrorRecord(packet(Value(int64_t(1))));
    record.object->values[0]=Value(int64_t(3));
    rejected("E_RUNTIME",[&]{(void)nativeSourceErrorException(record);});
    record.object->values[0]=Value(string("CODE"));record.object->values[2]=Value(string("invalid"));
    rejected("E_SOURCE_TYPE",[&]{(void)nativeSourceErrorException(record);});
    record.object->values[2]=Value(int64_t(0));
    rejected("E_SOURCE_TYPE",[&]{(void)nativeSourceErrorException(record);});
    record.object->values[2]=Value(string(key));record.object->values[3]=Value(int64_t(2),true);
    rejected("E_SOURCE_TYPE",[&]{(void)nativeSourceErrorException(record);});
    record.object->values[3].tag=Value::Floating;record.object->values[3].scalar=std::bit_cast<int64_t>(std::numeric_limits<double>::infinity());
    rejected("E_FLOAT",[&]{(void)nativeSourceErrorException(record);});
    record.object->values.pop_back();
    rejected("E_RUNTIME",[&]{(void)nativeSourceErrorException(record);});
  }empty();
  {
    RequestScope request;
    rejected("E_RUNTIME",[]{(void)readSourceErrorHandle(nullptr);});
    auto invalid=std::make_shared<Data>(Data::Record);invalid->text=sourceErrorRecordV1;
    invalid->values={Value(int64_t(0)),Value(string("message"))};
    auto handle=makeHandle(Value(invalid));
    try{(void)nex_source_error_code(handle);throw std::runtime_error("malformed legacy code accepted");}
    catch(const Trap &e){require(e.code=="E_RUNTIME","malformed record changed fatal kind");}
    try{nex_source_error_unhandled_at(handle,nullptr);throw std::runtime_error("malformed source record accepted");}
    catch(const Trap &e){require(e.code=="E_RUNTIME","malformed record became a source error");}
  }empty();++cases;
  {
    RequestScope request;auto original=packet(Value(string(text)));failHandle=true;
    try{(void)makeSourceErrorHandle(original);throw std::runtime_error("handle allocation fault not consumed");}
    catch(const std::bad_alloc&){}
    require(!failHandle&&allocations.size()==1,"failed packet creation retained an allocation");
  }empty();++cases;
  std::printf("{\"ok\":true,\"cases\":%u,\"native_boundary\":true,\"physical_retirement\":true}\n",cases);return 0;
}catch(const std::exception &e){std::fprintf(stderr,"native source packet: %s\n",e.what());return 1;}}
