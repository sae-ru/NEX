#include "nex/managed_references.h"
#include "nex/backend.h"
#include "nex/web.h"
#include <iostream>
#include <stdexcept>

using namespace nex;
namespace {
unsigned accepted=0,rejected=0;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const char *code,F body){
  try{body();}catch(const Error &error){if(error.code!=code)throw std::runtime_error(std::string("expected ")+code+", got "+error.code+": "+error.message);++rejected;return;}
  throw std::runtime_error(std::string("expected ")+code);
}
llvm::json::Object input(const std::string &entry,const std::string &provider){
  return llvm::json::Object{{"schema","nex.private-reference-sources/1"},{"entry","main.nex"},
    {"files",llvm::json::Object{{"main.nex",entry},{"provider.nex",provider}}}};
}
const std::string mainSource="module app;import \"./provider.nex\" as counter;fn main()->unit!{state,io}{let value:cell<i64>=counter::make();counter::change(value);cell_collect();print(cell_read(value));}";
const std::string providerSource="module counter;pub fn make()->cell<i64>!{state}{return cell_new(1);}pub fn change(value:cell<i64>)->unit!{state}{cell_write(value,42);}";
}
int main(){try{
  const auto baseline=nexrt::liveObjects.load();
  {
    auto source=input(mainSource,providerSource);
    auto p=loadManagedReferencesPrototypeBundle(llvm::json::Object(source),".");
    require(p.units.size()==2&&supportsManagedReferences(p),"module context did not retain its private identity");
    for(const auto &[key,unit]:p.units)require(unit.sourceLanguage==SourceLanguage::ManagedReferencesPrototype,"module lost its selected language");
    require(p.function("counter::make").checked&&p.function("main").name=="app::main","module functions were not bound/checked");
    auto result=evaluateManagedReferencesPrototype(p);
    require(result.evaluation.output=="42\n"&&result.afterCollection.nodes==0&&result.afterCollection.cells==0,"cross-unit state/cleanup differs");++accepted;
    rejects("E_CELL_MIGRATION",[&]{revision(p);});
    rejects("E_CELL_MIGRATION",[&]{sourceBundle(p);});
    rejects("E_CELL_MIGRATION",[&]{dependencyLock(p);});
    rejects("E_CELL_BACKEND",[&]{evaluate(p,"app::main");});
    rejects("E_CELL_BACKEND",[&]{emitMLIR(p);});
    rejects("E_CELL_BACKEND",[&]{emitTypeScript(p,{{"main","app::main"}});});
    rejects("E_BUNDLE",[&]{loadBundle(llvm::json::Object(source),".");});
    rejects("E_LANGUAGE_VERSION",[&]{loadVersionedBundle(llvm::json::Object(source),".","0.30-refs-prototype");});
    rejects("E_LANGUAGE_VERSION",[&]{loadVersionedProgram("main.nex",".",SourceLanguage::ManagedReferencesPrototype);});
    source["schema"]="nex.sources/1";
    rejects("E_BUNDLE",[&]{loadManagedReferencesPrototypeBundle(llvm::json::Object(source),".");});
  }
  auto bad=[&](const std::string &entry,const std::string &provider,const char *code){rejects(code,[&]{loadManagedReferencesPrototypeBundle(input(entry,provider),".");});};
  bad(mainSource,"module counter;fn make()->cell<i64>!{state}{return cell_new(1);}pub fn change(value:cell<i64>)->unit!{state}{}","E_VISIBILITY");
  bad("module app;import \"./provider.nex\" as counter;fn main()->unit{counter::make();}",providerSource,"E_EFFECT");
  bad("module app;import \"./provider.nex\" as counter;fn main()->unit!{state}{encode_json(counter::make());}",providerSource,"E_GENERIC_BOUND");
  bad("module app;import \"./provider.nex\" as counter;fn main()->unit{}","module counter;import \"./main.nex\" as app;","E_IMPORT_CYCLE");
  bad(mainSource,"module app;pub fn make()->cell<i64>!{state}{return cell_new(1);}","E_MODULE_DUPLICATE");
  bad("module app;import \"./provider.nex\" as counter;fn main()->unit{}","module counter;fn cell_new()->i64{return 1;}","E_DUPLICATE");
  bad("module app;import \"./provider.nex\" as counter;fn main()->unit{}","module counter;endpoint e(\"GET\",\"/api/e\")=handler;fn handler()->unit{}","E_CELL_STAGE");
  bad("module app;import \"./provider.nex\" as counter;fn main()->unit{}","module counter;server fn work()->unit!{fs}{}","E_CELL_STAGE");
  bad("module app;import \"./provider.nex\" as counter;fn main()->unit{}","module counter;server fn wrap(value:file)->cell<file>!{state}{return cell_new(value);}","E_CELL_VALUE");
  bad("module app;import \"./provider.nex\" as counter;fn main()->unit{}","module counter;fn transfer()->unit{parallel_map([1],fn(n:i64)->i64{return n;},1);}","E_CELL_STAGE");
  {
    auto source=input(mainSource,providerSource);(*source.getObject("files"))["unused.nex"]="module unused;fn unused()->unit{}";
    rejects("E_BUNDLE",[&]{loadManagedReferencesPrototypeBundle(llvm::json::Object(source),".");});
  }
  require(nexrt::liveObjects.load()==baseline,"module gates leaked runtime values");
  std::cout<<json(llvm::json::Object{{"ok",true},{"accepted",int64_t(accepted)},{"rejected",int64_t(rejected)},{"live_value_delta",nexrt::liveObjects.load()-baseline},{"public_source_enabled",false}},false)<<'\n';return 0;
}catch(const Error &error){std::cerr<<error.code<<": "<<error.message<<" at "<<error.span.file<<":"<<error.span.line<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
