#include "nex/migration.h"
#include "nex/project.h"
#include "nex/task_reference.h"
#include "nex/task_native.h"
#include "nex/web.h"
#include "nex_source_error.h"
#include "llvm/Support/Error.h"
#include <sqlite3.h>
#include <filesystem>
#include <iostream>
using namespace nex;
namespace fs=std::filesystem;
namespace {
std::string field(const llvm::json::Object &o,const char *name){auto v=o.getString(name);if(!v)throw Error("E_OPTION",std::string("missing request field ")+name);return v->str();}
void backup(const fs::path &source,const fs::path &target){
  sqlite3 *from=nullptr,*to=nullptr;
  struct Close{sqlite3 *&p;~Close(){if(p)sqlite3_close(p);}} a{from},b{to};
  if(sqlite3_open_v2(source.string().c_str(),&from,SQLITE_OPEN_READONLY,nullptr)!=SQLITE_OK||sqlite3_open(target.string().c_str(),&to)!=SQLITE_OK)throw Error("E_TEST","cannot open race evidence");
  auto copy=sqlite3_backup_init(to,"main",from,"main");if(!copy)throw Error("E_TEST","cannot initialize race evidence");
  const auto step=sqlite3_backup_step(copy,-1),done=sqlite3_backup_finish(copy);
  if(step!=SQLITE_DONE||done!=SQLITE_OK)throw Error("E_TEST","cannot complete race evidence");
}
std::string entry(const Program &p){for(const auto &f:p.functions)if(f.localName=="main"||f.name=="main")return f.name;throw Error("E_ENTRY","missing main");}
llvm::json::Value evaluate(const Program &p,bool ir){
  const auto baseline=nexrt::liveObjects.load();llvm::json::Object result;
  {
    auto evaluated=ir?evaluateTaskIRReference(p,entry(p)):evaluateTaskReference(p,entry(p));
    if(evaluated.external.pending||evaluated.external.reservedBytes)throw Error("E_TEST","migration evaluation retained external work");
    result=llvm::json::Object{{"value",p.function(entry(p)).result==Type::Unit?llvm::json::Value(nullptr):llvm::json::Value(evaluated.value.scalar)},{"stdout",evaluated.output}};
  }
  if(nexrt::liveObjects.load()!=baseline)throw Error("E_TEST","migration evaluation retained managed values");return result;
}
}
int main(int argc,char **argv){try{
  if(argc!=2)throw Error("E_OPTION","expected one typed-error migration request JSON");
  auto value=llvm::json::parse(readFile(argv[1]));if(!value){llvm::consumeError(value.takeError());throw Error("E_OPTION","invalid migration request JSON");}
  const auto o=value->getAsObject();if(!o||o->getString("schema")!="nex.typed-error-migration-request/1")throw Error("E_OPTION","invalid migration request schema");
  const auto mode=field(*o,"mode");const fs::path project=field(*o,"project"),directory=project/".nex";
  if(mode=="inspect-versioned-source"){
    const auto sources=o->get("sources");if(!sources)throw Error("E_OPTION","missing versioned source bundle");
    auto p=loadVersionedBundle(*sources,project.string(),field(*o,"source_language"));
    std::cout<<json(llvm::json::Object{{"ok",true},{"language",programLanguage(p)},{"revision",revision(p)},
      {"ast",evaluate(p,false)},{"ir",evaluate(p,true)}})<<'\n';return 0;
  }
  if(mode=="evaluate"||mode=="emit"||mode=="build-native"){
    Program p;std::string selected;
    {Store store(directory,StoreOpenMode::ReadOnly);selected=field(*o,"revision");const auto language=store.revisionLanguage(selected);p=loadVersionedBundle(store.bundle(selected),project.string(),language);}
    if(revision(p)!=selected)throw Error("E_REVISION","stored migration revision failed recheck");
    if(mode=="build-native"){
      BuildOptions options;options.entry=entry(p);auto r=build(p,field(*o,"output"),options);
      auto metadata=llvm::json::parse(readFile((fs::path(r.executable).parent_path()/"build.json").string()));
      if(!metadata||!metadata->getAsObject())throw Error("E_TEST","missing stored-code native build record");
      std::cout<<json(llvm::json::Object{{"ok",true},{"language",programLanguage(p)},{"revision",selected},{"artifact",r.executable},{"execution_abi",metadata->getAsObject()->getInteger("task_execution_abi").value_or(0)}})<<'\n';return 0;
    }
    llvm::json::Object result{{"ok",true},{"language",programLanguage(p)},{"revision",selected},{"source_hash",hash(json(sourceBundle(p),false))},{"lock",dependencyLock(p)},{"ast",evaluate(p,false)},{"ir",evaluate(p,true)}};
    if(mode=="emit"){
      const fs::path output=field(*o,"output");auto native=emitTypedErrorTasksDevelopmentNative(p,entry(p),o->getBoolean("optimized").value_or(false));
      writeFile((output/"program.mlir").string(),native.mlir);writeFile((output/"program.ll").string(),lowerMLIRToLLVM(native.mlir,p.path,field(*o,"triple"),field(*o,"layout")));
      writeWebModule(emitTypeScript(p,{{"entry",entry(p)}}),output.string());result["descriptor_abi"]=native.descriptorABI;
    }
    std::cout<<json(std::move(result))<<'\n';return 0;
  }
  auto plan=preflightGraphMigration(directory,o->getString("origin_revision").value_or("HEAD").str(),field(*o,"expected_revision"),SourceLanguage::TypedErrors027,o->getObject("candidate"));
  if(mode=="plan"){
    std::cout<<json(llvm::json::Object{{"ok",true},{"origin_verified",plan.originVerified},{"origin_revision",plan.originRevision},{"origin_source_hash",plan.originSourceHash},{"target_revision",plan.targetRevision},{"source_hash",plan.targetSourceHash},{"namespace",plan.identityNamespace},{"language","0.27"},{"sources",plan.sources}})<<'\n';return 0;
  }
  if(mode=="race"){
    const auto other=o->get("race_sources");if(!other)throw Error("E_OPTION","missing race source bundle");auto program=preflightMigrationTarget(*other,project,SourceLanguage::TypedErrors027);
    {Store writer(directory);writer.save(program,plan.expectedHead,true,{"migrate","competing writer","test","",""},plan.identityNamespace);}
    backup(directory/"graph.db",project/"race-before-apply.db");
  }else if(mode=="namespace-race"){
    sqlite3 *db=nullptr;if(sqlite3_open((directory/"graph.db").string().c_str(),&db)!=SQLITE_OK)throw Error("E_TEST","cannot open namespace race");
    auto rc=sqlite3_exec(db,"UPDATE metadata SET value='00000000000000000000000000000000' WHERE key='identity_namespace'",nullptr,nullptr,nullptr);sqlite3_close(db);if(rc!=SQLITE_OK)throw Error("E_TEST","namespace race failed");backup(directory/"graph.db",project/"race-before-apply.db");
  }else if(mode=="unguarded"){
    auto p=loadVersionedBundle(plan.sources,project.string(),"0.27");Store store(directory);store.save(p);throw Error("E_TEST","unguarded source-version change was accepted");
  }else if(mode!="apply"&&mode!="tampered-plan")throw Error("E_OPTION","unknown migration request mode");
  if(mode=="tampered-plan")plan.targetRevision.assign(64,'0');
  auto result=applyGraphMigration(plan);
  if(auto output=o->getString("export")){
    exportProject(plan.sources,output->str(),"0.27");result["exported"]=output->str();
    auto exported=loadVersionedProgram((fs::path(output->str())/"main.nex").string(),output->str(),SourceLanguage::TypedErrors027);
    result["export_roundtrip"]=revision(exported)==plan.targetRevision;
  }
  std::cout<<json(std::move(result))<<'\n';return 0;
}catch(const Error &e){std::cout<<json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",e.what()}})<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
