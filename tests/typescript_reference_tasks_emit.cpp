#include "nex/managed_references.h"
#include "nex/web.h"
#include <filesystem>
#include <iostream>
int main(int argc,char **argv){
 using namespace nex;
 try{
  if(argc==2&&std::string(argv[1])=="gates"){
    unsigned rejected=0;
    auto parse030=[](std::string text){auto p=parseVersioned("module gates;"+text,"gates.nex",SourceLanguage::References030);check(p);return p;};
    auto rejects=[&](const std::string &code,auto action){try{action();throw std::runtime_error("missing rejection "+code);}catch(const Error &error){if(error.code!=code)throw; ++rejected;}};
    auto old=parseVersioned("module old;fn main()->unit{}","old.nex",SourceLanguage::Contracts029);check(old);
    rejects("E_LANGUAGE_VERSION",[&]{emitManagedReferenceTasksDevelopmentTypeScript(old);});
    auto p=parse030("fn main()->unit!{state,task}{}");
    rejects("E_CELL_LIMIT",[&]{emitManagedReferenceTasksDevelopmentTypeScript(p,"main",{0,8,16});});
    rejects("E_CELL_LIMIT",[&]{emitManagedReferenceTasksDevelopmentTypeScript(p,"main",{8,9007199254740992ULL,16});});
    p.functions[0].checked=false;rejects("E_CELL_STATE",[&]{emitManagedReferenceTasksDevelopmentTypeScript(p);});
    p=parse030("fn main(x:i64)->unit{}");rejects("E_CELL_ENTRY",[&]{emitManagedReferenceTasksDevelopmentTypeScript(p);});
    p=parse030("fn main()->cell<i64>!{state}{return cell_new(1);}");rejects("E_CELL_ENTRY",[&]{emitManagedReferenceTasksDevelopmentTypeScript(p);});
    p=parse030("server fn main()->unit!{state,task}{}");rejects("E_REALM",[&]{emitManagedReferenceTasksDevelopmentTypeScript(p);});
    p=parse030("fn main()->unit!{state,task}{let v:cell<i64>=cell_new(1);let values:list<i64>=parallel_map([1],fn(x:i64)->i64{return x;},1);}");rejects("E_CELL_CONCURRENCY",[&]{emitManagedReferenceTasksDevelopmentTypeScript(p);});
    p=parse030("server fn hidden()->str!{fs}{return unwrap(file_read_text(\"PRIVATE_SERVER_SENTINEL\"));}fn main()->unit{}");
    auto module=emitManagedReferenceTasksDevelopmentTypeScript(p);
    if(module.source.find("PRIVATE_SERVER_SENTINEL")!=std::string::npos||module.mapping.getAsObject()->getArray("functions")->size()!=1)throw std::runtime_error("private task emission leaked unreachable server code");
    std::cout<<json(llvm::json::Object{{"ok",true},{"rejected",int64_t(rejected)},{"reachable_only",true}})<<'\n';return 0;
  }
  if(argc!=6)throw Error("E_OPTION","expected source, output, cells, nodes, edges");
  auto source=std::filesystem::absolute(argv[1]),out=std::filesystem::absolute(argv[2]);
  auto p=parseVersioned(readFile(source.string()),source.string(),SourceLanguage::References030);check(p);
  auto module=emitManagedReferenceTasksDevelopmentTypeScript(p,"main",{std::stoull(argv[3]),std::stoull(argv[4]),std::stoull(argv[5])});
  if(!std::filesystem::create_directory(out))throw Error("E_OPTION","output directory must be new");
  writeWebModule(module,out.string());
  writeFile((out/"runtime-inputs.txt").string(),webRuntimeInputs(module));
  std::cout<<json(llvm::json::Object{{"ok",true},{"revision",revision(p)},{"asynchronous",module.asynchronous},{"managed_references",module.managedReferences},{"public_source_enabled",false}})<<'\n';
 }catch(const Error &error){std::cerr<<error.code<<": "<<error.message<<'\n';return 1;}
 catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
}
