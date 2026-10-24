#include "nex/project.h"
#include "nex/task_frontend.h"
#include "nex/task_reference.h"
#include <filesystem>
#include <iostream>
#include "llvm/Support/Error.h"

using namespace nex;
namespace {
std::string required(const llvm::json::Object &object,const char *key){
  auto value=object.getString(key);if(!value)throw Error("E_OPTION",std::string("missing string ")+key);return value->str();
}
}
int main(int argc,char **argv)try{
  if(argc!=2)throw Error("E_OPTION","expected one structured migration request file");
  auto requestPath=std::filesystem::absolute(argv[1]);
  auto parsed=llvm::json::parse(readFile(requestPath.string()));
  if(!parsed)throw Error("E_JSON",llvm::toString(parsed.takeError()));
  auto request=parsed->getAsObject();if(!request||required(*request,"schema")!="nex.private-task-migration-request/1")throw Error("E_OPTION","invalid private migration request");
  auto mode=required(*request,"mode"),language=required(*request,"language");
  if(mode!="inspect"&&mode!="migrate"&&mode!="run-reference")throw Error("E_OPTION","unsupported private migration mode");
  auto bundle=request->get("sources");if(!bundle)throw Error("E_BUNDLE","migration requires an explicit source bundle");
  // Parsing/checking/authority diagnostics precede opening any destination.
  // A failed recheck cannot initialize or upgrade a graph store.
  auto program=loadVersionedBundle(*bundle,requestPath.parent_path().string(),language);
  auto rev=revision(program);auto archive=sourceBundle(program);
  auto roundtrip=loadVersionedBundle(archive,requestPath.parent_path().string(),language);
  if(revision(roundtrip)!=rev)throw Error("E_REVISION","versioned archive failed its semantic roundtrip");
  llvm::json::Object result{{"schema","nex.private-task-migration/1"},{"ok",true},
    {"language",programLanguage(program)},{"installed_language",languageVersion},
    {"public_source_tasks",isPublicTaskLanguage(program)},{"supports_task_file_reads",supportsTaskFileReads(program)},
    {"revision",rev},{"roundtrip",true},
    {"source_hash",hash(json(archive,false))},{"lock",dependencyLock(program)}};
  if(mode=="run-reference"){
    auto entry=request->getString("entry");auto selected=entry?entry->str():"main";
    if(isPublicTaskLanguage(program)){
      auto evaluated=evaluateTaskReference(program,selected);
      result["representation"]=nexrt::representation(evaluated.value);result["stdout"]=evaluated.output;
    }else{
      auto evaluated=evaluate(program,selected);result["value"]=std::move(evaluated.value);result["stdout"]=evaluated.output;
    }
  }
  if(mode=="migrate"){
    auto directory=required(*request,"store_directory"),expected=required(*request,"expected_head");
    if(expected.empty())throw Error("E_OPTION","migration requires an explicit expected HEAD");
    {
      std::string previous;
      if(std::filesystem::exists(std::filesystem::path(directory)/"graph.db")){
        Store retained(directory,StoreOpenMode::ReadOnly);previous=retained.headRevision();
      }
      if(previous!=(expected=="EMPTY"?"":expected))throw Error("E_CONFLICT","graph HEAD changed before versioned migration");
    }
    std::string origin;
    if(auto original=request->getString("original_revision")){
      origin=original->str();Store retained(directory,StoreOpenMode::ReadOnly);
      auto oldLanguage=retained.revisionLanguage(origin);
      if(oldLanguage!="0.18"&&oldLanguage!="0.19"&&oldLanguage!="0.20"&&oldLanguage!="0.21")throw Error("E_LANGUAGE_VERSION","migration probe requires an explicit retained018,019,020 or021 origin");
      try{if(revision(loadVersionedBundle(retained.bundle(origin),directory,oldLanguage))!=origin)
        throw Error("E_REVISION","retained origin canonical revision differs");}
      catch(const Error &error){throw Error("E_REVISION",std::string("invalid retained migration origin: ")+error.what(),error.span);}
    }
    Store store(directory);
    auto saved=store.save(program,expected,true,{"migrate","private versioned source recheck","","",hash(json(*bundle,false))});
    if(saved!=rev||store.revisionLanguage(saved)!=language||revision(loadVersionedBundle(store.bundle(saved),directory,language))!=saved)
      throw Error("E_REVISION","stored versioned program failed its roundtrip");
    result["original_revision"]=origin;result["materialized"]=false;
    result["graph"]=store.graph(program);result["identities"]=store.identities(program,"all","",0,1000);
    result["changes"]=store.changes();
    if(auto target=request->getString("export_directory")){
      exportProject(archive,target->str(),language);result["exported"]=target->str();
    }
  }
  std::cout<<json(std::move(result))<<'\n';return 0;
}catch(const Error &error){
  std::cout<<json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",error.what()},
    {"line",int64_t(error.span.line)},{"file",error.span.file}})<<'\n';return 1;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
