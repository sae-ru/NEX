#include "nex/wasm.h"
#include "nex/native_toolchain.h"
#include "nex/operations.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/Module.h"
#include "llvm/IRReader/IRReader.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/Program.h"
#include "llvm/Support/SHA256.h"
#include "llvm/Support/SourceMgr.h"
#include <cstdlib>
#include <filesystem>
#include <functional>
namespace nex {
namespace {
namespace fs=std::filesystem;
using Object=llvm::json::Object;
using Array=llvm::json::Array;
using JSON=llvm::json::Value;
std::string sha256(const std::string &text){
 auto bytes=llvm::ArrayRef(reinterpret_cast<const uint8_t*>(text.data()),text.size());
 auto digest=llvm::SHA256::hash(bytes);return llvm::toHex(llvm::ArrayRef(digest),true);
}
bool scalar(Type type){return type==Type::I64||type==Type::Bool||type==Type::Unit;}
std::set<std::string> validate(const Program &p,const std::string &entry){
 const auto &root=p.function(entry);
 if(root.test)throw Error("E_WASM_ENTRY","Wasm entry cannot be a test",root.span);
 std::set<std::string> selected;size_t operations=0;
 std::function<void(const Function&)> function;
 function=[&](const Function &f){
  if(!selected.insert(f.name).second)return;
  if(selected.size()>128)throw Error("E_WASM_LIMIT","scalar Wasm supports at most 128 reachable functions",f.span);
  if(f.realm=="server"||!f.effects.empty()||f.foreign)
   throw Error("E_WASM_REALM","Wasm functions must be pure shared/client NEX definitions",f.span);
  if(!f.typeParameters.empty()||f.closure||!f.captures.empty()||!scalar(f.result))
   throw Error("E_WASM_TYPE","Wasm requires concrete scalar functions without closures",f.span);
  auto count=operationTree(p,f).size();operations+=count;
  if(operations>8192)throw Error("E_WASM_LIMIT","scalar Wasm supports at most 8192 reachable operations",f.span);
  if(f.params.size()>32||count>512)
   throw Error("E_WASM_LIMIT","scalar Wasm supports at most 32 parameters and 512 operations per function",f.span);
  for(const auto &parameter:f.params)if(!scalar(parameter.type)||parameter.type==Type::Unit)
   throw Error("E_WASM_TYPE","Wasm parameters must be i64 or bool",parameter.span);
  std::function<void(const E&)> expression;
  std::function<void(const std::vector<S>&)> block;
  expression=[&](const E &e){
   if(!e)return;
   if(!scalar(e->type)||e->kind==Expr::Invoke||e->kind==Expr::Lambda||e->kind==Expr::FunctionRef)
    throw Error("E_WASM_TYPE","scalar Wasm supports only i64, bool and unit expressions",e->span);
   for(const auto &argument:e->args)expression(argument);
   for(const auto &arm:e->arms)block(arm->body);
  };
  block=[&](const std::vector<S> &statements){for(const auto &s:statements){
   if(s->kind==Stmt::Finally)throw Error("E_WASM_TYPE","finally is not supported by the scalar Wasm backend",s->span);
   if((s->kind==Stmt::Let||s->kind==Stmt::Var)&&!scalar(s->type))
    throw Error("E_WASM_TYPE","scalar Wasm locals must be i64 or bool",s->span);
   expression(s->expr);childBlocks(s,block);
  }};
  block(f.body);
  for(const auto &dependency:f.dependencies)function(p.function(dependency));
 };
 function(root);return selected;
}
std::string tool(const std::string &name){
 if(name.empty())throw Error("E_WASM_TOOLCHAIN","LLVM 22.1 clang and wasm-ld are required; configure NEX_WASM_LD when building the compiler or select it explicitly in the environment");
 auto found=llvm::sys::findProgramByName(name);
 if(!found)throw Error("E_WASM_TOOLCHAIN","cannot locate Wasm build tool: "+name);
 return (fs::weakly_canonical(fs::path(*found).parent_path())/fs::path(*found).filename()).string();
}
ProcessResult command(const std::vector<std::string> &args){
 auto selected=args;
 // LLVM substitutes '%' in temporary-file templates. Keep literal-percent
 // SDK work directories usable without changing their emitted artifact paths.
#ifndef _WIN32
 if(fs::canonical(fs::temp_directory_path()).string().find('%')!=std::string::npos){
  selected={"/usr/bin/env","TMPDIR=/tmp","TMP=/tmp","TEMP=/tmp","TEMPDIR=/tmp"};selected.insert(selected.end(),args.begin(),args.end());
 }
#endif
 auto result=captureNativeBuildTool(selected,300);
 if(result.code!=0)throw Error("E_WASM_BUILD","Wasm build tool failed: "+args[0]+"\n"+result.output+result.errors);
 return result;
}
std::string stamp(const fs::path &folder){
 std::string result;
 for(const auto &name:{"module.wasm","module.mjs","module.json","program.mlir","program.ll","THIRD_PARTY_NOTICES.txt"}){
  auto file=folder/name;if(!fs::is_regular_file(file))throw Error("E_WASM_CACHE","missing Wasm artifact");
  result+=std::string(name)+hash(readFile(file.string()));
 }
 return hash(result)+"\n";
}
}
JSON buildWasm(const Program &p,const std::string &directory,const std::string &requestedEntry,
               const std::string &profile,const std::string &outputDirectory){
 if(profile!="debug"&&profile!="release")throw Error("E_OPTION","scalar Wasm supports debug or release profiles");
 if(!outputDirectory.empty()){
  fs::path destination=fs::absolute(outputDirectory);
  if(fs::is_symlink(destination)||(fs::exists(destination)&&(!fs::is_directory(destination)||!fs::is_empty(destination))))
   throw Error("E_EXISTS","Wasm output requires a new or empty directory");
 }
 auto names=validate(p,requestedEntry);const auto &entry=p.function(requestedEntry);
 auto host=configureWasm();auto compiler=tool(host.compiler);
 auto override=std::getenv("NEX_WASM_LD");auto linker=tool(override?override:host.wasmLinker);
 auto compilerVersion=command({compiler,"--version"}).output,linkerVersion=command({linker,"--version"}).output;
 if(compilerVersion.find("clang version 22.1.")==std::string::npos||linkerVersion.find("LLD 22.1.")==std::string::npos)
  throw Error("E_WASM_TOOLCHAIN","scalar Wasm requires clang and wasm-ld from LLVM 22.1.x");
 std::map<std::string,std::string> inputs;
 inputs["wasm_runtime.c"]=readFile(resourceFile("runtime/wasm_runtime.c"));
 inputs["module-template.mjs"]=readFile(resourceFile("web/wasm_module.mjs"));
 for(const auto &name:{"multi3.c","int_lib.h","int_types.h","int_util.h","int_endianness.h","LICENSE.TXT","provenance.json"})
  inputs["compiler-rt/"+std::string(name)]=readFile(resourceFile("runtime/third_party/compiler-rt/"+std::string(name)));
 auto provenance=llvm::json::parse(inputs.at("compiler-rt/provenance.json"));
 if(!provenance){llvm::consumeError(provenance.takeError());throw Error("E_RESOURCE","invalid compiler-rt provenance");}
 auto record=provenance->getAsObject();auto files=record?record->getObject("file_sha256"):nullptr;
 if(!files||files->size()!=6||record->getString("commit")!="ca7933e47d3a3451d81e72ac174dcb5aa28b59d1")
  throw Error("E_RESOURCE","unsupported compiler-rt provenance");
 for(const auto &[name,digest]:*files){
  auto found=inputs.find("compiler-rt/"+name.str());
  if(found==inputs.end()||digest.getAsString()!=sha256(found->second))throw Error("E_RESOURCE","compiler-rt inventory differs");
 }
 Object resourceHashes;for(const auto &[name,contents]:inputs)resourceHashes[name]=hash(contents);
 JSON configuration=Object{{"schema","nex.wasm-inputs/1"},{"compiler_build",NEX_BUILD_ID},{"revision",revision(p)},
  {"source_bundle_hash",hash(json(sourceBundle(p),false))},{"entry_source_path",p.path},{"entry",entry.name},{"profile",profile},{"llvm",LLVM_VERSION_STRING},
  {"target","wasm32-unknown-unknown"},{"abi",1},{"compiler",compiler},{"compiler_hash",hash(readFile(compiler))},
  {"compiler_version",compilerVersion},{"linker",linker},{"linker_hash",hash(readFile(linker))},
  {"linker_version",linkerVersion},{"resources",std::move(resourceHashes)}};
 auto key=hash(json(configuration,false));auto folder=fs::absolute(fs::path(directory)/"wasm"/key);bool cached=false;
 auto invoke=[&](const std::vector<std::string> &args){
  try{return command(args);}
  catch(const Error &error){throw Error(error.code,error.message+"\nretained intermediate artifacts: "+folder.string(),error.span);}
 };
 try{
  auto parsed=llvm::json::parse(readFile((folder/"module.json").string()));
  if(parsed&&parsed->getAsObject()&&parsed->getAsObject()->getString("build_key")==key&&
     readFile((folder/"complete").string())==stamp(folder))cached=true;
  if(!parsed)llvm::consumeError(parsed.takeError());
 }catch(const std::exception&){}
 if(!cached){
  fs::create_directories(folder);
  for(const auto &[name,contents]:inputs)writeFile((folder/"inputs"/name).string(),contents);
  auto optimization=profile=="debug"?"-O0":"-O2";
  auto compile=[&](const std::string &source,const std::string &output,bool llvmIR=false){
   std::vector<std::string> args{compiler,"--target=wasm32-unknown-unknown","-ffreestanding","-fno-builtin","-fvisibility=hidden",optimization};
   if(llvmIR)args.insert(args.end(),{"-S","-emit-llvm"});else args.push_back("-c");
   if(!source.ends_with(".ll"))args.insert(args.end(),{"-x","c","-std=c11"});
   args.insert(args.end(),{source,"-o",output});invoke(args);
  };
  compile((folder/"inputs/wasm_runtime.c").string(),(folder/"runtime.ll").string(),true);
  llvm::LLVMContext context;llvm::SMDiagnostic diagnostic;
  auto runtime=llvm::parseIRFile((folder/"runtime.ll").string(),diagnostic,context);
  if(!runtime||runtime->getDataLayout().getPointerSizeInBits()!=32||!runtime->getTargetTriple().isWasm())
   throw Error("E_WASM_TOOLCHAIN","Wasm compiler did not provide the required 32-bit layout");
  auto mlir=emitWasmMLIR(p,entry.name,profile=="release");writeFile((folder/"program.mlir").string(),mlir);
  writeFile((folder/"program.ll").string(),lowerMLIRToLLVM(mlir,p.path,"wasm32-unknown-unknown",runtime->getDataLayoutStr()));
  compile((folder/"program.ll").string(),(folder/"program.o").string());
  compile((folder/"inputs/wasm_runtime.c").string(),(folder/"runtime.o").string());
  compile((folder/"inputs/compiler-rt/multi3.c").string(),(folder/"multi3.o").string());
  Array exports{nativeSymbol(entry.name),"memory","nex_wasm_reset","nex_wasm_error_code","nex_wasm_error_line","nex_wasm_error_site"};
  std::vector<std::string> link{linker,"--no-entry","--fatal-warnings","--stack-first","-z","stack-size=8388608", "--initial-memory=16777216","--max-memory=16777216"};
  for(const auto &value:exports)if(value.getAsString()!="memory")link.push_back("--export="+value.getAsString()->str());
  link.insert(link.end(),{(folder/"program.o").string(),(folder/"runtime.o").string(),(folder/"multi3.o").string(),"-o",(folder/"module.wasm").string()});
  // LLVM's FileOutputBuffer expands '%' throughout its temporary filename
  // model, including parent directories. Link in an owned physical temporary
  // directory, then publish the bytes into the requested cache path. Keep the
  // output basename stable because it is recorded in the Wasm name section.
  fs::path temporary(createTemporaryDirectory("nex-wasm-link"));
  auto linked=temporary/"module.wasm";link.back()=linked.string();
  std::string wasm;
  try{
   invoke(link);wasm=readFile(linked.string());
   writeFile((folder/"module.wasm").string(),wasm);fs::remove_all(temporary);
  }catch(...){fs::remove_all(temporary);throw;}
  if(wasm.size()<8||wasm.size()>8*1048576||wasm.substr(0,8)!=std::string("\0asm\1\0\0\0",8))throw Error("E_WASM_BUILD","invalid or oversized Wasm output");
  Array parameters,functions;for(const auto &parameter:entry.params)parameters.push_back(typeName(parameter.type));
  for(const auto &f:p.functions)if(names.contains(f.name))functions.push_back(Object{{"symbol",f.name},
   {"function_hash",hash(json(canonical(f),false))},{"source_hash",hash(p.definition(f))},{"operations",operationSites(p,f)}});
  JSON descriptor=Object{{"schema","nex.wasm-module/1"},{"toolchain",NEX_VERSION},{"language",programLanguage(p)},
   {"compiler_build",NEX_BUILD_ID},{"revision",revision(p)},{"build_key",key},{"entry",entry.name},
   {"target","wasm32-unknown-unknown"},{"abi",1},{"parameters",std::move(parameters)},{"result",typeName(entry.result)},
   {"native_symbol",nativeSymbol(entry.name)},{"module_sha256",sha256(wasm)},{"exports",std::move(exports)},
   {"functions",std::move(functions)},{"memory_bytes",16777216},{"max_call_depth",64},{"max_budget",10000000}};
  auto wrapper=inputs.at("module-template.mjs"),marker=std::string("__NEX_WASM_DESCRIPTOR__");auto position=wrapper.find(marker);
  if(position==std::string::npos||wrapper.find(marker,position+1)!=std::string::npos)throw Error("E_RESOURCE","Wasm wrapper requires one descriptor marker");
  wrapper.replace(position,marker.size(),json(descriptor,false));writeFile((folder/"module.mjs").string(),wrapper);
  writeFile((folder/"module.json").string(),json(descriptor)+"\n");
  writeFile((folder/"THIRD_PARTY_NOTICES.txt").string(),"LLVM compiler-rt 22.1.8 (__multi3), Apache-2.0 WITH LLVM-exception\nhttps://github.com/llvm/llvm-project/tree/ca7933e47d3a3451d81e72ac174dcb5aa28b59d1/compiler-rt\n\n"+inputs.at("compiler-rt/LICENSE.TXT"));
  writeFile((folder/"build-inputs.json").string(),json(configuration)+"\n");
  writeFile((folder/"complete").string(),stamp(folder));
 }
 auto destination=folder;
 if(!outputDirectory.empty()){
  destination=fs::absolute(outputDirectory);fs::create_directories(destination);
  for(const auto &name:{"module.wasm","module.mjs","module.json","THIRD_PARTY_NOTICES.txt"})
   copyFile((folder/name).string(),(destination/name).string(),false);
 }
 return Object{{"ok",true},{"schema","nex.wasm-build/1"},{"kind","scalar_wasm_module"},{"target","wasm32-unknown-unknown"},
  {"abi",1},{"cached",cached},{"revision",revision(p)},{"build_key",key},{"directory",destination.string()},
  {"module",(destination/"module.wasm").string()},{"wrapper",(destination/"module.mjs").string()},
  {"metadata",(destination/"module.json").string()},{"notices",(destination/"THIRD_PARTY_NOTICES.txt").string()},
  {"mlir",(folder/"program.mlir").string()},{"llvm",(folder/"program.ll").string()},{"reachable_functions",int64_t(names.size())}};
}
}
