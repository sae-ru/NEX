#include "nex/managed_references.h"
#include "nex/web.h"
#include "llvm/Support/SHA256.h"
#include "llvm/ADT/StringExtras.h"
#include <filesystem>
#include <iostream>
#include <stdexcept>

using namespace nex;
namespace {
template<class F>void rejects(const char *code,F action){
  try{action();}catch(const Error &error){if(error.code==code)return;throw std::runtime_error(std::string("expected ")+code+", got "+error.code);}
  throw std::runtime_error(std::string("expected ")+code);
}
Program checked(const std::string &source){auto p=parseManagedReferencesPrototype("module gate;"+source,"gate.nex");check(p);return p;}
}
int main(int argc,char **argv){try{
  if(argc==2&&std::string(argv[1])=="value-gates"){
    auto ordinary=parse("module old;fn main()->unit{}","old.nex");check(ordinary);
    rejects("E_LANGUAGE_VERSION",[&]{emitManagedReferencesValueTypeScript(ordinary,{{"main","main"}});});
    auto p=checked("fn main()->unit!{state}{let value:cell<i64>=cell_new(1);}");
    rejects("E_CELL_LIMIT",[&]{emitManagedReferencesValueTypeScript(p,{{"main","main"}},{0,8,16});});
    rejects("E_CELL_LIMIT",[&]{emitManagedReferencesValueTypeScript(p,{{"main","main"}},{8,9007199254740992ULL,16});});
    p.functions[0].checked=false;rejects("E_CELL_STATE",[&]{emitManagedReferencesValueTypeScript(p,{{"main","main"}});});
    auto input=checked("fn main(value:cell<i64>)->unit{}");rejects("E_CELL_ENTRY",[&]{emitManagedReferencesValueTypeScript(input,{{"main","main"}});});
    auto closure=checked("fn main(value:fn()->i64)->unit{}");rejects("E_CELL_ENTRY",[&]{emitManagedReferencesValueTypeScript(closure,{{"main","main"}});});
    auto output=checked("fn main()->cell<i64>!{state}{return cell_new(1);}");rejects("E_CELL_ENTRY",[&]{emitManagedReferencesValueTypeScript(output,{{"main","main"}});});
    auto server=checked("server fn main()->unit{}");rejects("E_REALM",[&]{emitManagedReferencesValueTypeScript(server,{{"main","main"}});});
    auto empty=checked("fn main()->unit{}");rejects("E_ENTRY",[&]{emitManagedReferencesValueTypeScript(empty,{});});
    for(const auto &alias:{std::string("class"),std::string("host"),std::string("bad-name"),nativeSymbol("main")})rejects("E_ENTRY",[&]{emitManagedReferencesValueTypeScript(empty,{{alias,"main"}});});
    auto nested=checked("struct Box{value:cell<i64>;}fn main(value:Box)->unit{}");rejects("E_CELL_ENTRY",[&]{emitManagedReferencesValueTypeScript(nested,{{"main","main"}});});
    std::cout<<"{\"ok\":true,\"rejected\":14}\n";return 0;
  }
  if(argc==2&&std::string(argv[1])=="gates"){
    auto ordinary=parse("module old;fn main()->unit{}","old.nex");check(ordinary);
    rejects("E_LANGUAGE_VERSION",[&]{emitManagedReferencesPrototypeTypeScript(ordinary);});
    auto p=checked("fn main()->unit!{state}{let value:cell<i64>=cell_new(1);}");
    rejects("E_CELL_BACKEND",[&]{emitTypeScript(p,{{"main","main"}});});
    rejects("E_CELL_LIMIT",[&]{emitManagedReferencesPrototypeTypeScript(p,"main",{0,8,16});});
    rejects("E_CELL_LIMIT",[&]{emitManagedReferencesPrototypeTypeScript(p,"main",{8,9007199254740992ULL,16});});
    p.functions[0].checked=false;rejects("E_CELL_STATE",[&]{emitManagedReferencesPrototypeTypeScript(p);});
    auto args=checked("fn main(value:i64)->unit{}");rejects("E_CELL_ENTRY",[&]{emitManagedReferencesPrototypeTypeScript(args);});
    auto escaped=checked("fn main()->cell<i64>!{state}{return cell_new(1);}");rejects("E_CELL_ENTRY",[&]{emitManagedReferencesPrototypeTypeScript(escaped);});
    auto server=checked("server fn main()->unit{}");rejects("E_REALM",[&]{emitManagedReferencesPrototypeTypeScript(server);});
    auto files=checked("server fn main()->unit!{fs,state}{let value:cell<str>=cell_new(unwrap(file_read_text(\"input\")));}");rejects("E_REALM",[&]{emitManagedReferencesPrototypeTypeScript(files);});
    auto foreign=checked("server fn main()->unit!{ffi,state}{let value:cell<i64>=cell_new(1);}");rejects("E_REALM",[&]{emitManagedReferencesPrototypeTypeScript(foreign);});
    rejects("E_REALM",[&]{checked("fn main()->unit!{state}{let value:cell<list<file>>=cell_new<list<file>>([]);}");});
    auto bounded=checked("server fn hidden()->str!{fs}{return unwrap(file_read_text(\"UNREACHABLE_SERVER_TEXT\"));}fn main()->unit{}");
    auto module=emitManagedReferencesPrototypeTypeScript(bounded);
    if(module.source.find("UNREACHABLE_SERVER_TEXT")!=std::string::npos||module.mapping.getAsObject()->getArray("functions")->size()!=1)
      throw std::runtime_error("managed client included unreachable server code");
    std::cout<<"{\"ok\":true,\"rejected\":11,\"reachable_only\":true}\n";return 0;
  }
  const std::string mode=argc>1?argv[1]:"";
  const bool values=mode=="value-emit"||mode=="value-bundle-emit";
  const bool bundled=mode=="bundle-emit"||mode=="value-bundle-emit";
  if((argc!=7&&!(values&&argc==8))||(!values&&!bundled&&mode!="emit"))throw std::runtime_error("expected [value-][bundle-]emit input directory cells nodes edges [entries JSON], or gates");
  auto source=std::filesystem::absolute(argv[2]),output=std::filesystem::absolute(argv[3]);
  Program p;
  if(bundled){auto value=llvm::json::parse(readFile(source.string()));if(!value)throw Error("E_BUNDLE","invalid private source bundle JSON");p=loadManagedReferencesPrototypeBundle(*value,source.parent_path().string());}
  else{p=parseManagedReferencesPrototype(readFile(source.string()),source.string());check(p);}
  nexrt::CellHeapLimits limits{std::stoull(argv[4]),std::stoull(argv[5]),std::stoull(argv[6])};
  std::map<std::string,std::string> entries{{"main","main"}};
  if(argc==8){auto parsed=llvm::json::parse(argv[7]);if(!parsed)throw Error("E_ENTRY","invalid entry JSON");auto object=parsed->getAsObject();if(!object)throw Error("E_ENTRY","entries must be an object");entries.clear();for(const auto &[alias,value]:*object){auto name=value.getAsString();if(!name)throw Error("E_ENTRY","entry must name a function");entries.emplace(alias.str(),name->str());}}
  auto module=values?emitManagedReferencesValueTypeScript(p,entries,limits):emitManagedReferencesPrototypeTypeScript(p,"main",limits);
  std::filesystem::create_directories(output);writeWebModule(module,output.string());
  const auto inputs=webRuntimeInputs(module);
  writeFile((output/"runtime-inputs.sha256").string(),llvm::toHex(llvm::SHA256::hash(llvm::arrayRefFromStringRef(inputs)),true)+"\n");
  std::cout<<json(llvm::json::Object{{"ok",true},{"language",programLanguage(p)},{"managed_references",module.managedReferences},{"public_source_enabled",false}},false)<<'\n';return 0;
}catch(const Error &error){std::cerr<<error.code<<": "<<error.message<<" at "<<error.span.line<<":"<<error.span.column<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
