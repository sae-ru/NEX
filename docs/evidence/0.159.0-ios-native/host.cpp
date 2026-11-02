#include "nex_host.h"
#include "third_party/json.hpp"
#include <Availability.h>
#include <TargetConditionals.h>
#include <mach-o/dyld.h>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <limits>
extern "C" int64_t nex_13_ios_native159_4_step(int64_t,nexrt::Handle **);
extern "C" void nex_source_error_unhandled(nexrt::Handle *);
static int64_t invoke(int64_t value){
 nexrt::Handle *source_error=nullptr;
 auto result=nex_13_ios_native159_4_step(value,&source_error);
 if(source_error)nex_source_error_unhandled(source_error);
 return result;
}
using json=nlohmann::json;
struct Case {const char *name;int64_t arg;const char *error;int64_t value;};
int main(){
 try {
  const Case cases[]={{"normal0",0,nullptr,1},{"normal41",41,nullptr,42},{"recovered",7,nullptr,8},
   {"pre",-1,"E_ASSERT",0},{"post",9,"E_ASSERT",0},{"escaped",13,"E_SOURCE_EXCEPTION",0},
   {"overflow",std::numeric_limits<int64_t>::max(),"E_OVERFLOW",0}};
  json results=json::array();int cleanups=0;
  for(int repetition=0;repetition<100;++repetition)for(const auto &test:cases){
   json observed={{"name",test.name},{"argument",test.arg}};
   {
    nexrt::RequestScope scope(100000,5000);
    try {observed["value"]=invoke(test.arg);observed["outcome"]="value";}
    catch(const nexrt::NativeSourceException &error){
     observed["outcome"]="E_SOURCE_EXCEPTION";observed["typed_payload"]=bool(error.payload);
     if(error.payload){
      observed["type_key"]=error.payload->typeKey;
      const auto &value=error.payload->value;
      if(value.tag!=nexrt::Value::Object||!value.object||value.object->kind!=nexrt::Data::Record||value.object->values.size()!=1)throw std::runtime_error("typed record layout differs");
      const auto &list=value.object->values[0];
      if(list.tag!=nexrt::Value::Object||!list.object||list.object->kind!=nexrt::Data::List||list.object->values.size()!=2)throw std::runtime_error("typed list payload differs");
      const auto &text=list.object->values[0];
      if(text.tag!=nexrt::Value::Object||!text.object||text.object->kind!=nexrt::Data::String||text.object->text!=std::string("Я\0🧠",7))throw std::runtime_error("typed Unicode/NUL bytes differ");
      observed["payload_first"]=text.object->text;
     }
    }
    catch(const nexrt::Trap &error){observed["outcome"]=error.code;observed["line"]=error.line;}
   }
   nex_runtime_finish();++cleanups;
   if(test.error){if(observed["outcome"]!=test.error)throw std::runtime_error("error outcome differs: "+observed.dump());}
   else if(observed["outcome"]!="value"||observed["value"]!=test.value)throw std::runtime_error("normal result differs: "+observed.dump());
   if(std::string(test.name)=="escaped"&&(!observed.value("typed_payload",false)||observed.value("type_key",std::string()).size()!=64))throw std::runtime_error("owned typed payload missing");
   if(repetition==0)results.push_back(observed);
  }
  json images=json::array();for(uint32_t i=0;i<_dyld_image_count();++i)images.push_back(_dyld_get_image_name(i));
  const char *root=std::getenv("SIMULATOR_ROOT"),*udid=std::getenv("SIMULATOR_UDID"),*resources=std::getenv("NEX_RESOURCE_DIR");
  std::cout<<json{{"ok",true},{"cases",results},{"executions",cleanups},{"owned_cleanup_checks",cleanups},
   {"compiled_for_simulator",bool(TARGET_OS_SIMULATOR)},{"deployment",__IPHONE_OS_VERSION_MIN_REQUIRED},
   {"simulator_root",root?root:""},{"simulator_udid",udid?udid:""},{"NEX_RESOURCE_DIR",resources?resources:""},{"loaded_images",images}}.dump()<<std::endl;
  return 0;
 }catch(const std::exception &error){std::cerr<<error.what()<<std::endl;return 1;}
}
