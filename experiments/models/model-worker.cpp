#include "common.h"
#include "onnxruntime_c_api.h"
#include "zhouyi_provider_factory.h"
#include <cerrno>
#include <fcntl.h>
#include <iostream>
#include <memory>
#include <set>
#include <sys/resource.h>

static std::string boundedFile(const std::filesystem::path&path,uint64_t limit){
 auto size=std::filesystem::file_size(path);if(size>limit)throw Failure("E_MODEL_LIMIT","model/profile file exceeds its byte limit");
 std::ifstream file(path,std::ios::binary);if(!file)throw Failure("E_MODEL_ARTIFACT","cannot open model/profile file");std::string data(size,'\0');file.read(data.data(),data.size());if(!file)throw Failure("E_MODEL_ARTIFACT","truncated model/profile file");return data;
}
struct Observed {std::vector<std::vector<uint8_t>> outputs;JSON trace;};
class Session{
 std::unique_ptr<Library> library;const OrtApi*api=nullptr;OrtEnv*environment=nullptr;OrtSessionOptions*options=nullptr;OrtSession*session=nullptr;OrtMemoryInfo*memory=nullptr;OrtAllocator*allocator=nullptr;
 std::vector<OrtValue*> input,output;std::vector<char*> names;bool npu=false;
 void check(OrtStatus*status,const char*code="E_MODEL_RUNTIME"){
  if(!status)return;auto kind=api->GetErrorCode(status);std::string text=api->GetErrorMessage(status);api->ReleaseStatus(status);
  // This precise ORT assignment diagnostic describes a valid graph which the
  // selected EP cannot execute completely. Other parse/runtime faults retain
  // their own errors and cannot trigger the source library's CPU fallback.
  const bool assignedCPU=npu&&kind==ORT_FAIL&&std::string(code)=="E_MODEL_ARTIFACT"&&text=="This session contains graph nodes that are assigned to the default CPU EP, but fallback to CPU EP has been explicitly disabled by the user.";
  if(assignedCPU)trace(JSON{{"role","unsupported-placement"},{"backend","npu"},{"cpu_ep_fallback_disabled",true},{"model_sha256",config().at("sha256")},{"runtime_status",int(kind)}});
  throw Failure(npu&&(kind==ORT_NOT_IMPLEMENTED||assignedCPU)?"E_MODEL_UNSUPPORTED":code,text);
 }
 void ports(const char*direction){
  bool incoming=std::string(direction)=="inputs";const auto&ports=config().at(direction);size_t count=0;
  if(incoming)check(api->SessionGetInputCount(session,&count));else check(api->SessionGetOutputCount(session,&count));
  if(count!=ports.size())throw Failure("E_MODEL_ARTIFACT","runtime port count disagrees with prepared model");
  for(size_t i=0;i<count;++i){
   char*name=nullptr;if(incoming)check(api->SessionGetInputName(session,i,allocator,&name));else check(api->SessionGetOutputName(session,i,allocator,&name));names.push_back(name);
   if(std::string(name)!=ports[i].at("name").get<std::string>())throw Failure("E_MODEL_ARTIFACT","runtime port name/order disagrees with prepared model");
   OrtTypeInfo*info=nullptr;if(incoming)check(api->SessionGetInputTypeInfo(session,i,&info));else check(api->SessionGetOutputTypeInfo(session,i,&info));
   try{
    const OrtTensorTypeAndShapeInfo*shape=nullptr;check(api->CastTypeInfoToTensorInfo(info,&shape));if(!shape)throw Failure("E_MODEL_ARTIFACT","only dense tensor ports are supported");
    ONNXTensorElementDataType type;size_t rank=0;check(api->GetTensorElementType(shape,&type));check(api->GetDimensionsCount(shape,&rank));auto expected=ports[i].at("shape").get<std::vector<int64_t>>();
    if(uint32_t(type)!=dtype(ports[i])||rank!=expected.size())throw Failure("E_MODEL_ARTIFACT","runtime dtype/rank disagrees with prepared model");std::vector<int64_t>dims(rank);check(api->GetDimensions(shape,dims.data(),dims.size()));if(dims!=expected)throw Failure("E_MODEL_ARTIFACT","model ports require the exact declared static shapes");
   }catch(...){api->ReleaseTypeInfo(info);throw;}api->ReleaseTypeInfo(info);
  }
 }
public:
 ~Session(){
  if(!api)return;for(auto v:output)if(v)api->ReleaseValue(v);for(auto v:input)if(v)api->ReleaseValue(v);if(memory)api->ReleaseMemoryInfo(memory);
  if(session)api->ReleaseSession(session);if(allocator)for(auto p:names)allocator->Free(allocator,p);if(options)api->ReleaseSessionOptions(options);if(environment)api->ReleaseEnv(environment);
 }
 Observed run(std::vector<std::vector<uint8_t>>&values,uint32_t device,const std::filesystem::path&model){
  npu=device==1;if(npu&&!config().at("zhouyi").get<bool>())throw Failure("E_MODEL_UNSUPPORTED","bundle has no Zhouyi binding");
  if(npu){auto operators=config().at("operator_path").get<std::string>();if(operators.empty()||setenv("OPERATOR_PATH",operators.c_str(),1))throw Failure("E_MODEL_CONFIGURATION","explicit private operator path is required");}
  auto runtime=config().at("runtime").get<std::string>();library=std::make_unique<Library>(runtime.c_str(),RTLD_NOW|RTLD_LOCAL|RTLD_DEEPBIND|RTLD_NODELETE);
  auto base=library->symbol<decltype(&OrtGetApiBase)>("OrtGetApiBase")();api=base->GetApi(ORT_API_VERSION);if(!api)throw Failure("E_MODEL_ABI","ONNX Runtime API20 is unavailable");
  check(api->CreateEnv(ORT_LOGGING_LEVEL_WARNING,"nex-model",&environment));check(api->CreateSessionOptions(&options));check(api->SetIntraOpNumThreads(options,1));check(api->SetInterOpNumThreads(options,1));
  if(npu){check(api->AddSessionConfigEntry(options,"session.disable_cpu_ep_fallback","1"));auto append=library->symbol<decltype(&OrtSessionOptionsAppendExecutionProvider_Zhouyi)>("OrtSessionOptionsAppendExecutionProvider_Zhouyi");check(append(options));}
  auto stamp=std::to_string(getpid())+"-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());auto prefix=(std::filesystem::current_path()/("ort-"+stamp)).string();check(api->EnableProfiling(options,prefix.c_str()));
  auto bytes=boundedFile(model,33554432);if(bytes.empty())throw Failure("E_MODEL_ARTIFACT","empty model artifact");check(api->CreateSessionFromArray(environment,bytes.data(),bytes.size(),options,&session),"E_MODEL_ARTIFACT");
  check(api->GetAllocatorWithDefaultOptions(&allocator));names.reserve(config().at("inputs").size()+config().at("outputs").size()+1);ports("inputs");ports("outputs");
  check(api->CreateCpuMemoryInfo(OrtArenaAllocator,OrtMemTypeDefault,&memory));input.resize(values.size(),nullptr);output.resize(config().at("outputs").size(),nullptr);
  std::vector<const OrtValue*> tensors;std::vector<const char*> inputNames,outputNames;tensors.reserve(values.size());inputNames.reserve(values.size());outputNames.reserve(output.size());
  for(size_t i=0;i<values.size();++i){const auto&port=config().at("inputs")[i];auto dims=port.at("shape").get<std::vector<int64_t>>();check(api->CreateTensorWithDataAsOrtValue(memory,values[i].data(),values[i].size(),dims.data(),dims.size(),ONNXTensorElementDataType(dtype(port)),&input[i]));tensors.push_back(input[i]);inputNames.push_back(names[i]);}
  for(size_t i=0;i<output.size();++i)outputNames.push_back(names[input.size()+i]);
  auto start=std::chrono::steady_clock::now();check(api->Run(session,nullptr,inputNames.data(),tensors.data(),tensors.size(),outputNames.data(),output.size(),output.data()));auto hostNS=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
  Observed result;result.outputs.reserve(output.size());
  for(size_t i=0;i<output.size();++i){OrtTensorTypeAndShapeInfo*shape=nullptr;check(api->GetTensorTypeAndShape(output[i],&shape));
   try{
    ONNXTensorElementDataType type;size_t count=0,rank=0;check(api->GetTensorElementType(shape,&type));check(api->GetTensorShapeElementCount(shape,&count));check(api->GetDimensionsCount(shape,&rank));const auto&port=config().at("outputs")[i];auto expected=port.at("shape").get<std::vector<int64_t>>();
    if(uint32_t(type)!=dtype(port)||rank!=expected.size()||count!=tensorBytes(port)/(dtype(port)==1||dtype(port)==6?4:1))throw Failure("E_MODEL_OUTPUT","runtime output dtype/shape count differs");std::vector<int64_t>dims(rank);check(api->GetDimensions(shape,dims.data(),dims.size()));if(dims!=expected)throw Failure("E_MODEL_OUTPUT","runtime output shape differs");
    void*data=nullptr;check(api->GetTensorMutableData(output[i],&data));auto n=tensorBytes(port);if(!data&&n)throw Failure("E_MODEL_OUTPUT","null tensor output");result.outputs.emplace_back(static_cast<uint8_t*>(data),static_cast<uint8_t*>(data)+n);validateBytes(result.outputs.back(),port);
   }catch(...){api->ReleaseTensorTypeAndShapeInfo(shape);throw;}api->ReleaseTensorTypeAndShapeInfo(shape);
  }
  char*profileName=nullptr;check(api->SessionEndProfiling(session,allocator,&profileName));names.push_back(profileName);auto profile=boundedFile(profileName,4194304);auto events=JSON::parse(profile);if(!events.is_array())throw Failure("E_MODEL_PLACEMENT","invalid runtime profile");std::set<std::string>providers;uint32_t nodes=0;
  for(const auto&e:events){if(e.value("cat","")!="Node"||!e.contains("args")||!e["args"].contains("provider"))continue;providers.insert(e["args"]["provider"].get<std::string>());++nodes;}
  const std::string selected=npu?"ZhouyiExecutionProvider":"CPUExecutionProvider";
  if((npu&&providers.empty())||std::any_of(providers.begin(),providers.end(),[&](const auto&p){return p!=selected;}))throw Failure("E_MODEL_PLACEMENT","runtime profile contains a different or missing execution provider");
  bool aipu=false;for(const auto&e:std::filesystem::directory_iterator("/proc/self/fd")){std::error_code code;auto target=std::filesystem::read_symlink(e.path(),code);if(!code&&target=="/dev/aipu")aipu=true;}
  if(npu&&!aipu)throw Failure("E_MODEL_PLACEMENT","no actual AIPU device descriptor was observed");
  std::string copied;
  if(auto name=std::getenv("NEX_MODEL_TRACE_FILE")){auto target=std::filesystem::path(name).parent_path()/("model-profile-"+stamp+".json");std::ofstream file(target,std::ios::binary);if(!file)throw Failure("E_MODEL_TRACE","cannot retain runtime profile");file.write(profile.data(),profile.size());if(!file)throw Failure("E_MODEL_TRACE","cannot retain complete runtime profile");copied=target.string();}
  result.trace=JSON{{"backend",npu?"npu":"cpu"},{"provider",selected},{"observed_providers",providers},{"profile_nodes",nodes},{"profile",copied},{"aipu_open",aipu},{"cpu_ep_fallback_disabled",npu},{"runtime_version",base->GetVersionString()},{"runtime_library",runtime},{"model_sha256",config().at("sha256")},{"input_ports",input.size()},{"output_ports",output.size()},{"run_host_ns",hostNS},{"kernel_time_claim",false}};return result;
 }
};
static void writeAll(int fd,const void*data,size_t n){auto p=static_cast<const uint8_t*>(data);while(n){auto r=::write(fd,p,n);if(r<0&&errno==EINTR)continue;if(r<=0)throw std::runtime_error("model result write");p+=r;n-=r;}}
static void writeU32(int fd,uint32_t n){uint8_t b[4];for(int i=0;i<4;++i)b[i]=uint8_t(n>>(i*8));writeAll(fd,b,4);}
static uint32_t readU32(){uint8_t b[4];std::cin.read(reinterpret_cast<char*>(b),4);if(!std::cin)throw Failure("E_MODEL_PROTOCOL","truncated model input header");return uint32_t(b[0])|(uint32_t(b[1])<<8)|(uint32_t(b[2])<<16)|(uint32_t(b[3])<<24);}
int main(int argc,char**argv){
 int protocol=fcntl(STDOUT_FILENO,F_DUPFD_CLOEXEC,3);if(protocol<0||dup2(STDERR_FILENO,STDOUT_FILENO)<0)return 3;rlimit core{0,0};setrlimit(RLIMIT_CORE,&core);rlimit files{16777216,16777216};if(setrlimit(RLIMIT_FSIZE,&files))return 3;
 try{
  trace(JSON{{"role","worker-start"},{"pid",getpid()}});
  validateConfiguration();if(argc!=1)throw Failure("E_MODEL_PROTOCOL","model worker takes only the pinned binary frame");if(readU32()!=1)throw Failure("E_MODEL_PROTOCOL","unsupported model frame version");auto device=readU32();if(device>1)throw Failure("E_MODEL_DEVICE","invalid model device selection");auto n=readU32();if(n!=config().at("inputs").size())throw Failure("E_MODEL_PORT","input count disagrees with model");std::vector<std::vector<uint8_t>>inputs;inputs.reserve(n);
  for(uint32_t i=0;i<n;++i){auto size=readU32();if(size!=tensorBytes(config().at("inputs")[i]))throw Failure("E_MODEL_SIZE","input length disagrees with model");inputs.emplace_back(size);std::cin.read(reinterpret_cast<char*>(inputs.back().data()),size);if(!std::cin)throw Failure("E_MODEL_PROTOCOL","truncated model input");validateBytes(inputs.back(),config().at("inputs")[i]);}
  if(std::cin.peek()!=std::char_traits<char>::eof())throw Failure("E_MODEL_PROTOCOL","trailing model input bytes");
  auto model=std::filesystem::absolute(argv[0]).parent_path()/"model.onnx";Observed result;{Session session;result=session.run(inputs,device,model);}result.trace["session_released"]=true;result.trace["role"]="selected";result.trace["precision"]=config().at("precision");result.trace["cpu_reference_ran"]=false;
  if(device==1&&config().at("precision")=="match-cpu"){
   Observed reference;{Session session;reference=session.run(inputs,0,model);}reference.trace["session_released"]=true;reference.trace["role"]="precision-reference";trace(reference.trace);
   const bool same=result.outputs==reference.outputs;result.trace["cpu_reference_ran"]=true;result.trace["precision_matches_CPU"]=same;
   if(!same){trace(result.trace);throw Failure("E_MODEL_PRECISION","selected NPU output does not match the explicit bit-exact CPU reference policy");}
  }
  trace(result.trace);
  uint32_t size=8+4*result.outputs.size();for(const auto&v:result.outputs)size+=v.size();writeU32(protocol,0);writeU32(protocol,size);writeU32(protocol,1);writeU32(protocol,result.outputs.size());for(const auto&v:result.outputs){writeU32(protocol,v.size());writeAll(protocol,v.data(),v.size());}close(protocol);return 0;
 }catch(const std::exception&e){std::string text=e.what();for(auto&c:text)if(static_cast<unsigned char>(c)<32||static_cast<unsigned char>(c)>126)c='?';const auto*f=dynamic_cast<const Failure*>(&e);try{auto data=JSON{{"code",f?f->code:"E_MODEL_WORKER"},{"message",text.substr(0,2048)}}.dump();writeU32(protocol,1);writeU32(protocol,data.size());writeAll(protocol,data.data(),data.size());close(protocol);return 0;}catch(...){return 3;}}
}
