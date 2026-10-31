#include "nex/profiling.h"
#include "nex/task_frontend.h"
#include "nex/native_toolchain.h"
#include "nex/task_process.h"
#include <filesystem>
#include <iostream>
int main(int argc,char **argv){try{
  if(argc!=3)throw nex::Error("E_OPTION","versioned profile probe requires genuine019 fixture and owned output directory");
  auto parsed=llvm::json::parse(nex::readFile(argv[1]));auto metadata=parsed?parsed->getAsObject():nullptr;
  if(!metadata||metadata->getString("schema")!="nex.language-019-migration-fixture/1"||metadata->getString("language")!="0.19")
    throw nex::Error("E_OPTION","requires genuine SDK115019 fixture metadata");
  auto rows=metadata->getArray("revisions");if(!rows||rows->empty())throw nex::Error("E_OPTION","fixture omitted revisions");
  auto row=rows->back().getAsObject();auto bundle=row?row->get("bundle"):nullptr;auto expected=row?row->getString("revision"):std::nullopt;
  if(!bundle||!expected)throw nex::Error("E_OPTION","fixture omitted source/revision");
  std::filesystem::create_directories(argv[2]);
  auto program=nex::loadVersionedBundle(*bundle,argv[2],"0.19");
  if(nex::revision(program)!=expected||std::string(nex::programLanguage(program))!="0.19")throw nex::Error("E_REVISION","genuine019 revision changed");
  nex::BuildOptions options;options.profile="profile";options.taskLimits.workers=2;
  auto built=nex::build(program,(std::filesystem::path(argv[2])/"build").string(),options);
  llvm::json::Array nodes;for(const auto &f:program.functions)nodes.push_back(llvm::json::Object{{"name",f.name},{"hash",nex::hash(nex::json(nex::canonical(f),false))},{"file",f.unit},{"id",nullptr}});
  nex::ProfileOptions profile;profile.events=0;profile.output=(std::filesystem::path(argv[2])/"profile019.json").string();
  auto result=nex::profileNative(program,built,llvm::json::Object{{"nodes",std::move(nodes)}},profile);
  if(result.getAsObject()->getString("language")!="0.19"||result.getAsObject()->getString("revision")!=expected)throw nex::Error("E_PROFILE","report lost019 identity");
  if(result.getAsObject()->getString("stdout")!="42\n"||result.getAsObject()->getInteger("exit_code")!=0)
    throw nex::Error("E_PROFILE","genuine019 source behavior changed");
  auto saved=nex::parseTaskProfileRuntimeReport(nex::readFile(profile.output));
  for(const auto *name:{"installed_task_limits::main","installed_task_limits::solve"}){
    bool matched=false;for(const auto &item:*saved.getAsObject()->getArray("functions"))if(item.getAsObject()->getString("name")==name){
      matched=item.getAsObject()->getInteger("calls")==1&&item.getAsObject()->getInteger("completed")==1;}
    if(!matched)throw nex::Error("E_PROFILE","genuine019 source calls were not counted once");
  }
  // Feed corrupted raw reports through the same launcher, provenance checks
  // and graph attribution as production, without replacing the compiled image.
  auto raw=std::filesystem::path(argv[2])/"raw.json";
  auto process=nex::runTaskProcess({built.executable},std::filesystem::current_path().string(),{{"NEX_TRACY","0"},{"NEX_PROFILE_EVENTS","100000"},{"NEX_PROFILE_OUTPUT",raw.string()}},30,(std::filesystem::path(argv[2])/"raw-logs").string()).process;
  if(process.code)throw nex::Error("E_PROFILE","genuine019 profile image failed");
  auto rawValue=nex::parseTaskProfileRuntimeReport(nex::readFile(raw.string()));
  nex::writeFile((std::filesystem::path(argv[2])/"original-runtime.json").string(),nex::json(rawValue));
  auto folder=std::filesystem::path(built.executable).parent_path();auto wrapper=folder/
#ifdef _WIN32
    "report-wrapper.exe"
#else
    "report-wrapper"
#endif
    ,source=folder/"report-wrapper.cpp";
  nex::writeFile(source.string(),"#include <fstream>\n#include <cstdlib>\nint main(){std::ifstream in("+nex::json(raw.string(),false)+",std::ios::binary);std::ofstream out(std::getenv(\"NEX_PROFILE_OUTPUT\"),std::ios::binary);out<<in.rdbuf();return 0;}\n");
  auto tools=nex::configureNative(options);auto command=tools.driver;command.insert(command.end(),{"-std=c++20",source.string(),"-o",wrapper.string()});
#ifdef _WIN32
  command.push_back("-static");
#endif
  auto compiled=nex::capture(command);
  if(compiled.code)throw nex::Error("E_TOOL",compiled.errors);
  auto wrapped=built;wrapped.executable=wrapper.string();unsigned rejected=0;
  for(const auto *field:{"name","content_hash","file","line"}){
    auto corrupt=rawValue;auto &function=*corrupt.getAsObject()->getArray("functions")->front().getAsObject();
    if(std::string(field)=="line")function[field]=999999;
    else function[field]=std::string(field)=="content_hash"?std::string(64,'0'):std::string("foreign::site");
    nex::writeFile(raw.string(),nex::json(corrupt));
    nex::writeFile((std::filesystem::path(argv[2])/(std::string("corrupt-")+field+".json")).string(),nex::json(corrupt));
    try{(void)nex::profileNative(program,wrapped,llvm::json::Object{{"nodes",[&](){llvm::json::Array values;for(const auto &f:program.functions)values.push_back(llvm::json::Object{{"name",f.name},{"hash",nex::hash(nex::json(nex::canonical(f),false))},{"file",f.unit},{"id",nullptr}});return values;}()}},profile);}
    catch(const nex::Error &e){if(e.code=="E_PROFILE"){++rejected;continue;}throw;}
    throw nex::Error("E_PROFILE","corrupt site provenance accepted");
  }
  (*result.getAsObject())["provenance_rejections"]=rejected;
  std::cout<<nex::json(std::move(result))<<'\n';return 0;
}catch(const nex::Error &e){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",e.what()}})<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
