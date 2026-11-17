#include "host_test.h"
#include "nex/managed_references.h"
#include "nex/backend.h"
#include "nex_cell_host.h"
#include "managed_reference_request_host.h"
#ifndef _WIN32
#include <dlfcn.h>
#endif
#include <filesystem>
#include <iostream>

using namespace nex;
unsigned testManagedReferenceRequests();
bool managedReferenceResourceCommand(int argc,char **argv,int &status);
int runManagedReferenceResourceImage(void *entry,bool request,const char *root,const char *catalogue,const char *report);
namespace {
unsigned destroyed=0,denied=0;
void *factory(void *){return new int(42);}
void destroy(void *value)noexcept;
void *otherFactory(void *){return new int(43);}
void destroy(void *value)noexcept{
  delete static_cast<int*>(value);++destroyed;
  try{(void)nexrt::managedReferenceContext(factory,nullptr,destroy);}catch(const nexrt::DataError &error){if(error.code=="E_CELL_CONTEXT")++denied;}
}
void *failedFactory(void *){throw std::bad_alloc();}
int64_t contextEntry(int64_t,const char *const*){
  try{(void)nexrt::managedReferenceContext(failedFactory,nullptr,destroy);}catch(const std::bad_alloc&){}
  auto first=nexrt::managedReferenceContext(factory,nullptr,destroy);
  if(first!=nexrt::managedReferenceContext(factory,nullptr,destroy))throw std::runtime_error("context owner was replaced");
  try{(void)nexrt::managedReferenceContext(otherFactory,nullptr,destroy);throw std::runtime_error("factory mismatch accepted");}catch(const nexrt::DataError &error){if(error.code!="E_CELL_CONTEXT")throw;}
  nex_runtime_finish();
  try{(void)nexrt::managedReferenceContext(factory,nullptr,destroy);throw std::runtime_error("ended context revived");}catch(const nexrt::DataError &error){if(error.code!="E_CELL_CONTEXT")throw;}
  return 0;
}
}
int main(int argc,char **argv){try{
  int resourceStatus=0;if(managedReferenceResourceCommand(argc,argv,resourceStatus))return resourceStatus;
  if(argc==2&&std::string(argv[1])=="context"){
    auto status=nex_application_run(reinterpret_cast<void*>(contextEntry),0,nullptr);
    if(status||destroyed!=1||denied!=1)throw std::runtime_error("reference context teardown/reentry differs");
    auto requests=testManagedReferenceRequests();
    unsigned gates=0;
    auto rejected=[&](const char *code,auto action){try{action();}catch(const Error &error){if(error.code==code){++gates;return;}throw;}throw std::runtime_error("expected private request entry rejection");};
    auto ordinary=parse("module old;fn main()->unit{}","old.nex");check(ordinary);
    rejected("E_LANGUAGE_VERSION",[&]{emitManagedReferencesPrototypeRequestMLIR(ordinary);});
    auto checked=[](const char *source){auto p=parseManagedReferencesPrototype(source,"request.nex");check(p);return p;};
    auto parameter=checked("module request;fn main(value:i64)->unit{}");rejected("E_CELL_ENTRY",[&]{emitManagedReferencesPrototypeRequestMLIR(parameter);});
    auto escaped=checked("module request;fn main()->cell<i64>!{state}{return cell_new(1);}");rejected("E_CELL_ENTRY",[&]{emitManagedReferencesPrototypeRequestMLIR(escaped);});
    auto client=checked("module request;client fn main()->unit{}");rejected("E_REALM",[&]{emitManagedReferencesPrototypeRequestMLIR(client);});
    auto entry=checked("module request;fn main()->unit{}");entry.functions[0].checked=false;rejected("E_CELL_STATE",[&]{emitManagedReferencesPrototypeRequestMLIR(entry);});entry.functions[0].checked=true;
    const auto emitted=emitManagedReferencesPrototypeRequestMLIR(entry);
    if(emitted.find("func.func @nex_private_reference_request")==std::string::npos||emitted.find("func.func @main(")!=std::string::npos||emitted.find("func.call @nex_runtime_finish")!=std::string::npos)throw std::runtime_error("request entry acquired an application/process lifetime");
    std::cout<<"{\"ok\":true,\"destroyed\":1,\"teardown_reentry_denied\":true,\"request_scenarios\":"<<requests<<",\"request_entry_gates\":"<<gates<<"}\n";return 0;
  }
  const bool requestRun=(argc==8||argc==11)&&std::string(argv[1])=="request-run";
  const bool resourceRun=argc==6&&(std::string(argv[1])=="resources-run"||std::string(argv[1])=="resources-request-run");
  const bool requestImage=requestRun||(resourceRun&&std::string(argv[1])=="resources-request-run");
  if((argc==3&&std::string(argv[1])=="run")||requestRun||resourceRun){
    const auto baseline=nexrt::liveObjects.load();
    // Pull/export this exact cohort's cell helpers as well as its base runtime.
    if(nexrt::inRequestScope())nex_cell_collect(0);
    nex_runtime_finish();
#ifdef _WIN32
    auto library=LoadLibraryW(std::filesystem::absolute(argv[2]).c_str());
    if(!library)throw std::runtime_error("cannot load managed fixture image: "+std::to_string(GetLastError()));
    struct CloseImage{HMODULE value;~CloseImage(){FreeLibrary(value);}} closeImage{library};
    auto address=reinterpret_cast<void*>(GetProcAddress(library,requestImage?"nex_private_reference_request":"main"));
    auto entry=reinterpret_cast<int(*)(int,const char *const*)>(address);
    if(!entry)throw std::runtime_error("cannot find managed fixture main: "+std::to_string(GetLastError()));
#else
    auto library=dlopen(argv[2],RTLD_NOW|RTLD_LOCAL);if(!library)throw std::runtime_error(dlerror());
    struct CloseImage{void *value;~CloseImage(){dlclose(value);}} closeImage{library};
    auto address=dlsym(library,requestImage?"nex_private_reference_request":"main");
    auto entry=reinterpret_cast<int(*)(int,const char *const*)>(address);if(!entry)throw std::runtime_error(dlerror());
#endif
    if(resourceRun)return runManagedReferenceResourceImage(address,requestImage,argv[3],argv[4],argv[5]);
    if(requestRun)return runManagedRequests(reinterpret_cast<ManagedRequestEntry>(address),std::stoul(argv[3]),2,{std::stoull(argv[4]),std::stoull(argv[5]),std::stoull(argv[6])},argv[7],argc==11?std::stoull(argv[8]):4000000,argc==11?std::stoul(argv[9]):0,argc==11?std::stoull(argv[10]):10000);
    auto status=entry(0,nullptr);
    if(nexrt::liveObjects.load()!=baseline)throw std::runtime_error("native reference context left live values");
    nex_runtime_finish();return status;
  }
  auto mode=argc>1?std::string(argv[1]):std::string{};
  const bool versioned=mode.starts_with("030-");if(versioned)mode.erase(0,4);
  const bool requestEmit=mode=="request-emit"||mode=="bundle-request-emit";
  const bool bundled=mode=="bundle-reference"||mode=="bundle-emit"||mode=="bundle-request-emit";
  const bool emit=mode=="emit"||mode=="bundle-emit"||requestEmit;
  if(versioned&&mode!="emit"&&mode!="bundle-emit")throw Error("E_OPTION","source030 native fixture supports ordinary emit modes only");
  if(!(((!emit&&(mode=="reference"||mode=="bundle-reference"))&&argc==6)||(emit&&argc==10)))throw std::runtime_error("expected [bundle-]reference input cells nodes edges, or [bundle-]emit input out triple layout optimized cells nodes edges");
  const auto start=emit?7:3;
  nexrt::CellHeapLimits limits{std::stoull(argv[start]),std::stoull(argv[start+1]),std::stoull(argv[start+2])};
  auto path=std::filesystem::absolute(argv[2]);Program p;
  if(bundled){auto value=llvm::json::parse(readFile(path.string()));if(!value)throw Error("E_BUNDLE","invalid source bundle JSON");p=versioned?loadVersionedBundle(*value,path.parent_path().string(),"0.30"):loadManagedReferencesPrototypeBundle(*value,path.parent_path().string());}
  else if(versioned){auto bundle=llvm::json::Value(llvm::json::Object{{"schema","nex.sources/1"},{"entry","main.nex"},{"files",llvm::json::Object{{"main.nex",readFile(path.string())}}}});p=loadVersionedBundle(bundle,path.parent_path().string(),"0.30");}
  else{p=parseManagedReferencesPrototype(readFile(path.string()),path.string());check(p);}
  if(!emit){
    const auto baseline=nexrt::liveObjects.load();
    try{
      auto result=evaluateManagedReferencesPrototype(p,"main",4000000,limits);
      auto stats=[](const nexrt::CellHeapStats &s){return llvm::json::Object{{"cells",int64_t(s.cells)},{"nodes",int64_t(s.nodes)},{"edges",int64_t(s.edges)},{"collections",int64_t(s.collections)}};};
      std::cout<<json(llvm::json::Object{{"kind","return"},{"value",std::move(result.evaluation.value)},{"output",result.evaluation.output},{"remaining_cells",int64_t(result.afterCollection.cells)},{"remaining_nodes",int64_t(result.afterCollection.nodes)},
        {"heap_before",stats(result.beforeCollection)},{"heap_after",stats(result.afterCollection)},{"live_delta",nexrt::liveObjects.load()-baseline}})<<'\n';
    }catch(const Error &error){
      llvm::json::Object result{{"kind","trap"},{"code",error.code},{"message",error.message},{"output",error.output},{"line",int64_t(error.span.line)},{"file",error.span.file},{"live_delta",nexrt::liveObjects.load()-baseline}};
      if(bundled){
        const Function *origin=nullptr;
        for(const auto &function:p.functions)if(!function.traitSignature&&function.span.file==error.span.file&&function.span.begin<=error.span.begin&&error.span.begin<function.span.end)
          if(!origin||function.span.end-function.span.begin<origin->span.end-origin->span.begin)origin=&function;
        if(!origin)throw std::runtime_error("module failure has no source function");
        result["origin"]=llvm::json::Object{{"function_hash",hash(json(canonical(*origin),false))},{"function_source_hash",hash(p.definition(*origin))}};
      }
      std::cout<<json(std::move(result))<<'\n';
    }
    return 0;
  }
  auto folder=std::filesystem::absolute(argv[3]);std::filesystem::create_directories(folder);
  auto mlir=versioned?emitMLIR(p,"main"):requestEmit?emitManagedReferencesPrototypeRequestMLIR(p,"main",std::string(argv[6])=="true"):emitManagedReferencesPrototypeMLIR(p,"main",std::string(argv[6])=="true",limits);
  writeFile((folder/"program.mlir").string(),mlir);
  writeFile((folder/"program.ll").string(),lowerMLIRToLLVM(mlir,path.string(),argv[4],argv[5]));return 0;
}catch(const Error &error){std::cerr<<error.code<<": "<<error.message<<" at "<<error.span.line<<":"<<error.span.column<<'\n';}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';}return 1;}
