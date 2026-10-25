#include "nex/migration.h"
#include "nex/project.h"
#include "nex/backend.h"
#include "nex/task_frontend.h"
#include <sqlite3.h>
#include <iostream>
#include <memory>

namespace fs=std::filesystem;
namespace {
std::string field(const llvm::json::Object &o,const char *name){auto v=o.getString(name);if(!v)throw nex::Error("E_OPTION",std::string("missing migration probe field ")+name);return v->str();}
llvm::json::Value decoded(const fs::path &path){auto parsed=llvm::json::parse(nex::readFile(path.string()));if(!parsed)throw nex::Error("E_BUNDLE","invalid migration candidate JSON");return std::move(*parsed);}
void backup(const fs::path &source,const fs::path &destination){
  sqlite3 *from=nullptr,*to=nullptr;
  struct Close {sqlite3 *&p;~Close(){if(p)sqlite3_close(p);}} closeFrom{from},closeTo{to};
  if(sqlite3_open_v2(source.string().c_str(),&from,SQLITE_OPEN_READONLY,nullptr)!=SQLITE_OK||sqlite3_open(destination.string().c_str(),&to)!=SQLITE_OK)
    throw nex::Error("E_STORE","cannot retain race snapshot");
  auto *copy=sqlite3_backup_init(to,"main",from,"main");if(!copy)throw nex::Error("E_STORE","cannot initialize race snapshot");
  const int code=sqlite3_backup_step(copy,-1),finished=sqlite3_backup_finish(copy);
  if(code!=SQLITE_DONE||finished!=SQLITE_OK)throw nex::Error("E_STORE","cannot complete race snapshot");
}
}
int main(int argc,char **argv){try{
  if(argc!=3)throw nex::Error("E_OPTION","migration probe requires request JSON and evidence directory");
  auto request=decoded(argv[1]);const auto *o=request.getAsObject();if(!o||o->getString("schema")!="nex.private-stream-migration-request/1")throw nex::Error("E_OPTION","invalid migration probe request");
  const fs::path root=field(*o,"project"),origin=o->getString("origin_project").value_or(root.string()).str(),output=argv[2];
  const auto expected=field(*o,"expected_revision");if(expected.empty())throw nex::Error("E_OPTION","migration requires a nonempty expected revision");
  const auto version=o->getString("target_language").value_or("0.24");
  if(version!="0.22"&&version!="0.23"&&version!="0.24")throw nex::Error("E_LANGUAGE_VERSION","unsupported explicit probe target");
  const auto target=version=="0.24"?nex::SourceLanguage::TaskStreams024:version=="0.23"?nex::SourceLanguage::TaskWrites023:nex::SourceLanguage::TaskForeign022;
  std::string previous;
  if(fs::is_regular_file(root/".nex/graph.db")){nex::Store destination(root/".nex",nex::StoreOpenMode::ReadOnly);previous=destination.headRevision();}
  if(previous!=(expected=="EMPTY"?"":expected))throw nex::Error("E_CONFLICT","graph HEAD changed; read context and retry");
  auto archive=std::make_unique<nex::Store>(origin/".nex",nex::StoreOpenMode::ReadOnly);
  auto selected=o->getString("origin_revision").value_or("HEAD").str();if(selected=="HEAD")selected=archive->headRevision();
  const auto language=o->getString("declared_language").value_or(archive->revisionLanguage(selected)).str();
  const auto original=o->getString("declared_revision").value_or(selected).str();auto bundle=archive->bundle(selected);
  const bool verified=nex::verifyMigrationOrigin(bundle,root,language,original,target);
  auto candidate=o->getString("candidate");if(candidate)bundle=decoded(candidate->str());
  auto program=nex::preflightMigrationTarget(bundle,root,target);const auto revision=nex::revision(program);archive.reset();
  if(auto race=o->getString("race_candidate")){
    auto other=nex::preflightMigrationTarget(decoded(race->str()),root,nex::SourceLanguage::TaskWrites023);
    {nex::Store writer(root/".nex");writer.save(other,expected,true,{"migrate","race","test","competing checked writer",""});}
    fs::create_directories(output);backup(root/".nex/graph.db",output/"race-before-planned-save.db");
  }
  std::string saved;
  const bool synchronize=o->getBoolean("unversioned_synchronize").value_or(false);
  {nex::Store store(root/".nex");saved=store.save(program,synchronize?"":expected,true,{synchronize?"synchronize":"migrate","explicit-private024","test","preserve genuine023 history",""});}
  if(saved!=revision)throw nex::Error("E_REVISION","migration saved another semantic revision");
  llvm::json::Object result{{"schema","nex.private-stream-migration/1"},{"ok",true},{"origin_verified",verified},
    {"origin_revision",original},{"origin_language",language},{"previous_revision",previous},{"revision",revision},
    {"language",nex::programLanguage(program)},{"public_default",nex::languageVersion},{"source_hash",nex::hash(nex::json(bundle,false))}};
  // A real retained archive must continue to parse/execute under its own rules.
  {nex::Store retained(root/".nex",nex::StoreOpenMode::ReadOnly);
    if(origin==root&&retained.containsRevision(original)){
      auto old=nex::loadVersionedBundle(retained.bundle(original),root.string(),language);
      if(nex::revision(old)!=original)throw nex::Error("E_REVISION","old revision identity changed after migration");
      try{auto value=nex::evaluate(old);result["old_value"]=std::move(value.value);result["old_stdout"]=value.output;}
      catch(const nex::Error &error){result["old_error"]=error.code;}
    }
  }
  if(o->getBoolean("execute").value_or(false)){
    auto evaluated=nex::evaluate(program);result["target_value"]=std::move(evaluated.value);result["target_stdout"]=evaluated.output;
    fs::create_directories(output);
    nex::BuildOptions options;options.profile="debug";if(nex::usesTaskEffects(program,"main"))options.taskLimits.workers=1;
    auto built=nex::build(program,(output/"native").string(),options);result["executable"]=built.executable;
  }
  std::cout<<nex::json(std::move(result))<<'\n';return 0;
}catch(const nex::Error &error){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",error.what()}})<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}}
