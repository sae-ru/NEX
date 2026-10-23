#include "nex/task_frontend.h"
#include "nex/task_native.h"
#include "nex_task_protocol.h"
#include "nex_task_profile_site.h"
#include "nex_task_debug_site.h"
#include "nex/backend.h"
#include "nex/native_images.h"
#include "nex/native_toolchain.h"
#include "nex/incremental.h"
#include "nex/operations.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Verifier.h"
#include "llvm/IRReader/IRReader.h"
#include "llvm/Linker/Linker.h"
#include "llvm/Support/SourceMgr.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/TargetParser/Host.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/Support/Program.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/ADT/SmallString.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Support/SHA256.h"
#include "llvm/ADT/StringExtras.h"
#include "mlir/Conversion/Passes.h"
#include "mlir/Dialect/Arith/IR/Arith.h"
#include "mlir/Dialect/ControlFlow/IR/ControlFlow.h"
#include "mlir/Dialect/Func/IR/FuncOps.h"
#include "mlir/Dialect/LLVMIR/LLVMDialect.h"
#include "mlir/Dialect/LLVMIR/Transforms/Passes.h"
#include "mlir/Dialect/MemRef/IR/MemRef.h"
#include "mlir/IR/AsmState.h"
#include "mlir/IR/BuiltinOps.h"
#include "mlir/IR/Verifier.h"
#include "mlir/Parser/Parser.h"
#include "mlir/Pass/PassManager.h"
#include "mlir/Target/LLVMIR/Dialect/Builtin/BuiltinToLLVMIRTranslation.h"
#include "mlir/Target/LLVMIR/Dialect/LLVMIR/LLVMToLLVMIRTranslation.h"
#include "mlir/Target/LLVMIR/Export.h"
#include <cstdlib>
#include <array>
#include <filesystem>
#include <sstream>
#include <functional>
#include <random>
#include <tuple>
#include <limits>
#include <regex>
#include <variant>

namespace nex {
namespace {
std::set<std::string> reachable(const Program &p,const std::string &entry){
  std::set<std::string> names;std::function<void(const Function&)> visit=[&](const Function &f){if(names.insert(f.name).second)for(const auto &name:f.dependencies)visit(p.function(name));};
  visit(p.function(entry));return names;
}
const Function &nativeEntry(const Program &p,const std::string &entry,bool testEntry,bool libraryEntry,bool wasm=false){
  const auto &main=p.function(entry);
  if(!main.typeParameters.empty()||std::any_of(main.typeArguments.begin(),main.typeArguments.end(),containsParameter))throw Error("E_GENERIC_ENTRY","entry must be a concrete generic specialization or a non-generic function",main.span);
  if(!libraryEntry&&(!main.params.empty()||(main.result!=Type::I64&&main.result!=Type::Unit)))throw Error("E_ENTRY","entry must take no arguments and return i64 or unit",main.span);
  if(!wasm&&main.realm=="client")throw Error("E_REALM","client entry cannot be built for a native server target",main.span);
  if(main.test!=testEntry)throw Error("E_ENTRY",testEntry?"entry is not a test":"test cannot be the application entry",main.span);
  return main;
}
bool usesNativeTasks(const Program &p,const std::string &entry){
  return isPublicTaskLanguage(p)&&usesTaskEffects(p,entry);
}
bool taskFileReadOperation(const std::string &name){return name=="file_read_text"||name=="file_read_bytes";}
void validateNativeTaskFunction(const Program &p,const Function &function){
  const bool reads=supportsTaskFileReads(p)&&function.realm=="server"&&function.effects.contains("task")&&function.effects.contains("fs");
  for(const auto &effect:function.effects)if(effect!="task"&&effect!="io"&&!(effect=="fs"&&reads)){
    if(effect=="fs"&&supportsTaskFileReads(p)&&!function.effects.contains("task"))throw Error("E_EFFECT","filesystem helpers in a task execution graph must explicitly declare task and fs",function.span);
    throw Error("E_TASK_UNIMPLEMENTED","compiled task application has no asynchronous host bridge for effect "+effect,function.span);
  }
  std::set<std::string> seen;
  std::function<void(const Type&)> checkType=[&](const Type &type){
    if(type.kind==Type::Function&&type.effects.contains("fs")&&!type.effects.contains("task"))throw Error("E_EFFECT","filesystem callables in a task execution graph must explicitly declare task and fs",function.span);
    if(type.element)checkType(*type.element);for(const auto &argument:type.arguments)checkType(argument);
    if(type.kind==Type::Record&&p.hasStructure(type.name)&&seen.insert(type.name).second)for(auto field:p.structure(type.name).members())checkType(field->type);
  };
  if(supportsTaskFileReads(p)){checkType(function.result);for(const auto &parameter:function.params)checkType(parameter.type);for(const auto &capture:function.captures)checkType(capture.type);}
  std::function<void(E)> expression=[&](E value){if(!value)return;
    const bool fileOperation=taskFileReadOperation(value->text)||value->text=="file_write_text"||value->text=="file_write_bytes"||streamFileBuiltins().contains(value->text);
    if(value->kind==Expr::Call&&fileOperation&&!(reads&&taskFileReadOperation(value->text)))throw Error("E_TASK_UNIMPLEMENTED","task filesystem support is limited to server task/fs file_read_text and file_read_bytes",value->span);
    for(auto argument:value->args)expression(argument);
  };
  std::function<void(const std::vector<S>&)> block=[&](const auto &body){for(auto statement:body){expression(statement->expr);childBlocks(statement,block);}};
  block(function.body);
}
llvm::json::Value taskLimitsJSON(const nexrt::TaskExecutionLimits &limits,bool tasks){
  if(!tasks)return nullptr;
  return llvm::json::Object{{"steps",int64_t(limits.steps)},{"timeout_ms",int64_t(limits.timeoutMs)},{"workers",int64_t(limits.workers)}};
}
// A native provider boundary needs both authority lifetime and callable
// suspension ABIs. Task effects alone do not grant authority, so this predicate
// stays local to native image validation rather than changing owner analysis.
bool unsupportedTaskBoundaryType(const Program &p,const Type &type){
  std::set<std::string> seen;
  std::function<bool(const Type&)> visit=[&](const Type &value){
    if(value.kind==Type::Task||value.kind==Type::Channel||value.kind==Type::TaskScope)return true;
    if(value.kind==Type::Function&&value.effects.contains("task"))return true;
    if(value.element&&visit(*value.element))return true;
    for(const auto &argument:value.arguments)if(visit(argument))return true;
    if(value.kind==Type::Record&&p.hasStructure(value.name)&&seen.insert(value.name).second){
      const auto &record=p.structure(value.name);
      for(const auto &argument:record.typeArguments)if(visit(argument))return true;
      for(auto field:record.members())if(visit(field->type))return true;
    }
    return false;
  };
  return visit(type);
}
using OperationIndex=std::map<const void*,std::string>;
std::string ty(Type t){return t.heap()?"!llvm.ptr":t==Type::I64?"i64":t==Type::F64?"f64":t==Type::Bool?"i1":"()";}
int64_t scalarTag(Type t){return t==Type::F64?2:t==Type::Bool?1:0;}
std::string callableType(const Type &type){std::string result="(!llvm.ptr";for(const auto &argument:type.arguments)result+=", "+ty(argument);return result+") -> "+ty(*type.element);}
std::string closureSymbol(const Function &function){return nativeSymbol(function.name)+(function.closure?"":"__closure_bridge");}
struct Value {std::string name;Type type;bool address=false;};
// Emit standard MLIR debug attributes alongside the checked source projection.
// Heap values keep their real handle representation; no fabricated record layout
// is presented as inline storage to the debugger.
class DebugInfo {
  const Program &p; bool optimized; unsigned serial=0;
  std::ostringstream attributes;
  std::map<std::string,std::string> files,types;
  std::string attribute(const std::string &value){auto name="#nex_di_"+std::to_string(serial++);attributes<<name<<" = "<<value<<"\n";return name;}
public:
  std::string scope,unit;
  DebugInfo(const Program &p,bool optimized):p(p),optimized(optimized){
    auto entry=file(p.path);
    unit=attribute("#llvm.di_compile_unit<id = distinct[0]<>, sourceLanguage = DW_LANG_C, file = "+entry+", producer = \"NEX " NEX_VERSION "\", isOptimized = "+(optimized?"true":"false")+", emissionKind = Full>");
  }
  std::string file(const std::string &path){
    if(files.contains(path))return files.at(path);
    auto location=std::filesystem::path(path);
    return files[path]=attribute("#llvm.di_file<"+json(location.filename().string(),false)+" in "+json(location.parent_path().string(),false)+">");
  }
  std::string type(Type t){
    auto name=typeName(t);if(types.contains(name))return types.at(name);
    std::string value;
    if(t==Type::Unit)value="#llvm.di_null_type";
    else if(t==Type::I64||t==Type::Bool||t==Type::F64){
      auto base=attribute("#llvm.di_basic_type<tag = DW_TAG_base_type, name = "+json(t==Type::Bool?"bool":t==Type::F64?"double":"long long",false)+", sizeInBits = "+(t==Type::Bool?"8":"64")+", encoding = "+(t==Type::Bool?"DW_ATE_boolean":t==Type::F64?"DW_ATE_float":"DW_ATE_signed")+">");
      value="#llvm.di_derived_type<tag = DW_TAG_typedef, name = "+json(name,false)+", baseType = "+base+">";
    }
    else {
      if(!types.contains("$handle")){
        auto opaque=attribute("#llvm.di_composite_type<tag = DW_TAG_structure_type, name = \"nex.heap\", flags = FwdDecl>");
        types["$handle"]=attribute("#llvm.di_derived_type<tag = DW_TAG_pointer_type, baseType = "+opaque+", sizeInBits = 64, alignInBits = 64>");
      }
      value="#llvm.di_derived_type<tag = DW_TAG_typedef, name = "+json(name,false)+", baseType = "+types.at("$handle")+">";
    }
    return types[name]=attribute(value);
  }
  std::string function(const Function &f){
    auto source=file(p.location(f.span));std::string signature=type(f.result);
    if(f.closure){type(Type::Str);signature+=", "+types.at("$handle");}
    for(const auto &param:f.params)signature+=", "+type(param.type);
    auto subroutine=attribute("#llvm.di_subroutine_type<callingConvention = DW_CC_normal, types = "+signature+">");
    // Each subprogram must be distinct, including functions sharing source lines.
    return attribute("#llvm.di_subprogram<id = distinct["+std::to_string(serial+1)+"]<>, compileUnit = "+unit+", scope = "+source+", name = "+json(f.name,false)+", linkageName = "+json(nativeSymbol(f.name),false)+", file = "+source+", line = "+std::to_string(f.span.line)+", scopeLine = "+std::to_string(f.span.line)+", subprogramFlags = "+json(optimized?"Definition|Optimized":"Definition",false)+", type = "+subroutine+">");
  }
  std::string block(Span span){return attribute("#llvm.di_lexical_block<scope = "+scope+", file = "+file(p.location(span))+", line = "+std::to_string(span.line)+", column = "+std::to_string(span.column)+">");}
  std::string variable(const std::string &name,Type t,Span span,unsigned argument=0){
    return attribute("#llvm.di_local_variable<scope = "+scope+", name = "+json(name,false)+", file = "+file(p.location(span))+", line = "+std::to_string(span.line)+", arg = "+std::to_string(argument)+", type = "+type(t)+">");
  }
  std::string location(Span span,const std::string &site="")const {
    auto point=json(p.location(span),false)+":"+std::to_string(span.line)+":"+std::to_string(span.column);
    if(!site.empty())point=json("nex.site."+site,false)+"("+point+")";
    return scope.empty()?" loc("+point+")":" loc(fused<"+scope+">["+point+"])";
  }
  std::string str()const{return attributes.str();}
};
// The checked closure is identical for every function object in one build.
// Keep its callable/worker analysis outside per-object IR generation. In
// particular, repeatedly resolving every function through Program::function
// made the old bridge discovery cubic on large source graphs.
struct NativeEmissionContext {
  const std::set<std::string> &bridges;
  bool parallel;
};
class Emitter {
  const Program &p; DebugInfo debug; std::ostringstream out,globals; unsigned serial=0;bool prologue=false,profiling=false,wasm=false,taskDebug=false;
  std::vector<std::map<std::string,Value>> scopes;
  std::map<const Stmt*,std::string> slots;std::map<const Pattern*,std::string> patternSlots;std::map<const Expr*,std::string> shortSlots,matchSlots,matchResults;
  OperationIndex ownedSites;const OperationIndex &sites;std::string activeSite;
  const NativeEmissionContext *context;
  Value ownedToken;
  bool parallelEnabled=false;
  std::map<std::string,std::string> taskCodes;
  const Function *selectedFunction=nullptr;
  struct ParallelThunk {const Function *owner;E expression;};
  std::map<std::string,ParallelThunk> parallelThunks;
  bool runtimeDeclarations=false;std::set<std::string> runtimeCalls;
  struct SiteDescription {std::string function,site,kind;int64_t begin,end;};
  std::map<std::string,SiteDescription> siteDescriptions;
  std::map<std::string,std::string> pathSites,byteGlobals,functionGlobals,siteGlobals;
  struct GlobalElement {std::string global,type;size_t index;};
  std::map<std::string,GlobalElement> globalElements;
  std::map<std::string,std::string> taskProfileSites;
  std::string taskProfileTable;
  std::string taskDebugTable;
  std::string rawGlobal(const std::string &text){
    auto [found,inserted]=byteGlobals.emplace(text,"nex_bytes_"+std::to_string(serial++));
    if(inserted){
      static const char *hex="0123456789ABCDEF";std::string escaped;
      for(unsigned char c:text){escaped+='\\';escaped+=hex[c>>4];escaped+=hex[c&15];}escaped+="\\00";
      globals<<"  llvm.mlir.global private constant @"<<found->second<<"(\""<<escaped<<"\")\n";
    }
    return found->second;
  }
  std::string structureGlobal(const std::string &prefix,const std::vector<std::string> &pointers,const std::vector<int64_t> &integers={}){
    std::string symbol=prefix+std::to_string(serial++),type="!llvm.struct<(";
    for(size_t i=0;i<pointers.size();++i){if(i)type+=", ";type+="!llvm.ptr";}
    for(size_t i=0;i<integers.size();++i){if(!pointers.empty()||i)type+=", ";type+="i64";}type+=")>";
    globals<<"  llvm.mlir.global private constant @"<<symbol<<"() : "<<type<<" {\n    %s0 = llvm.mlir.undef : "<<type<<"\n";
    unsigned n=1,position=0;std::string aggregate="%s0";
    for(const auto &pointer:pointers){auto value="%s"+std::to_string(n++),next="%s"+std::to_string(n++);
      if(pointer.empty())globals<<"    "<<value<<" = llvm.mlir.zero : !llvm.ptr\n";
      else if(auto element=globalElements.find(pointer);element!=globalElements.end()){
        auto base="%s"+std::to_string(n++);
        globals<<"    "<<base<<" = llvm.mlir.addressof @"<<element->second.global<<" : !llvm.ptr\n"
          <<"    "<<value<<" = llvm.getelementptr "<<base<<"[0, "<<element->second.index<<"] : (!llvm.ptr) -> !llvm.ptr, "<<element->second.type<<"\n";
      }else globals<<"    "<<value<<" = llvm.mlir.addressof @"<<pointer<<" : !llvm.ptr\n";
      globals<<"    "<<next<<" = llvm.insertvalue "<<value<<", "<<aggregate<<"["<<position++<<"] : "<<type<<"\n";aggregate=next;
    }
    for(auto integer:integers){auto value="%s"+std::to_string(n++),next="%s"+std::to_string(n++);
      globals<<"    "<<value<<" = llvm.mlir.constant("<<integer<<" : i64) : i64\n    "<<next<<" = llvm.insertvalue "<<value<<", "<<aggregate<<"["<<position++<<"] : "<<type<<"\n";aggregate=next;
    }
    globals<<"    llvm.return "<<aggregate<<" : "<<type<<"\n  }\n";return symbol;
  }
  void taskProfileMetadata(const std::vector<TaskFunctionIR> &functions){
    if(functions.empty()||functions.size()>nexrt::maximumTaskProfileCodeSites)
      throw Error("E_PROFILE_INIT","task profile reachable site count exceeds the bounded registry");
    struct Site {std::array<std::string,3> strings;int64_t line;};std::vector<Site> metadata;
    size_t textBytes=0;
    for(const auto &ir:functions){
      const auto &f=p.function(ir.name);auto file=p.location(f.span),content=hash(json(canonical(f),false));
      for(const auto &text:{f.name,file,content}){
        if(text.size()+1>nexrt::maximumTaskProfileCodeTextBytes-textBytes)
          throw Error("E_PROFILE_INIT","task profile immutable site text exceeds the bounded registry",f.span);
        textBytes+=text.size()+1;
      }
      metadata.push_back({{rawGlobal(f.name),rawGlobal(file),rawGlobal(content)},int64_t(f.span.line)});
    }
    auto siteType=std::string("!llvm.struct<(!llvm.ptr, !llvm.ptr, !llvm.ptr, i64)>");
    auto arrayType="!llvm.array<"+std::to_string(metadata.size())+" x "+siteType+">";
    taskProfileTable="nex_task_profile_sites_"+std::to_string(serial++);
    globals<<"  llvm.mlir.global private constant @"<<taskProfileTable<<"() : "<<arrayType<<" {\n"
      <<"    %p0 = llvm.mlir.undef : "<<arrayType<<"\n";
    unsigned n=1;std::string array="%p0";
    for(size_t i=0;i<metadata.size();++i){
      auto site="%p"+std::to_string(n++);globals<<"    "<<site<<" = llvm.mlir.undef : "<<siteType<<"\n";
      for(size_t field=0;field<3;++field){auto pointer="%p"+std::to_string(n++),next="%p"+std::to_string(n++);
        globals<<"    "<<pointer<<" = llvm.mlir.addressof @"<<metadata[i].strings[field]<<" : !llvm.ptr\n"
          <<"    "<<next<<" = llvm.insertvalue "<<pointer<<", "<<site<<"["<<field<<"] : "<<siteType<<"\n";site=next;
      }
      auto line="%p"+std::to_string(n++),complete="%p"+std::to_string(n++),next="%p"+std::to_string(n++);
      globals<<"    "<<line<<" = llvm.mlir.constant("<<metadata[i].line<<" : i64) : i64\n"
        <<"    "<<complete<<" = llvm.insertvalue "<<line<<", "<<site<<"[3] : "<<siteType<<"\n"
        <<"    "<<next<<" = llvm.insertvalue "<<complete<<", "<<array<<"["<<i<<"] : "<<arrayType<<"\n";array=next;
      auto reference="nex_task_profile_element_"+std::to_string(serial++);
      globalElements.emplace(reference,GlobalElement{taskProfileTable,arrayType,i});taskProfileSites.emplace(functions[i].name,reference);
    }
    globals<<"    llvm.return "<<array<<" : "<<arrayType<<"\n  }\n";
  }
  using MetadataField=std::variant<std::string,int64_t>;
  std::string metadataArray(const std::string &prefix,const std::string &recordType,const std::vector<std::vector<MetadataField>> &rows){
    if(rows.empty())return {};
    auto name=prefix+std::to_string(serial++),type="!llvm.array<"+std::to_string(rows.size())+" x "+recordType+">";
    globals<<"  llvm.mlir.global private constant @"<<name<<"() : "<<type<<" {\n    %d0 = llvm.mlir.undef : "<<type<<"\n";
    unsigned n=1;std::string array="%d0";
    for(size_t row=0;row<rows.size();++row){
      auto record="%d"+std::to_string(n++);globals<<"    "<<record<<" = llvm.mlir.undef : "<<recordType<<"\n";
      for(size_t column=0;column<rows[row].size();++column){
        auto value="%d"+std::to_string(n++),next="%d"+std::to_string(n++);
        if(auto pointer=std::get_if<std::string>(&rows[row][column])){
          if(pointer->empty())globals<<"    "<<value<<" = llvm.mlir.zero : !llvm.ptr\n";
          else globals<<"    "<<value<<" = llvm.mlir.addressof @"<<*pointer<<" : !llvm.ptr\n";
        }else globals<<"    "<<value<<" = llvm.mlir.constant("<<std::get<int64_t>(rows[row][column])<<" : i64) : i64\n";
        globals<<"    "<<next<<" = llvm.insertvalue "<<value<<", "<<record<<"["<<column<<"] : "<<recordType<<"\n";record=next;
      }
      auto next="%d"+std::to_string(n++);globals<<"    "<<next<<" = llvm.insertvalue "<<record<<", "<<array<<"["<<row<<"] : "<<type<<"\n";array=next;
    }
    globals<<"    llvm.return "<<array<<" : "<<type<<"\n  }\n";return name;
  }
  void taskDebugMetadata(const std::vector<TaskFunctionIR> &functions){
    std::vector<std::vector<MetadataField>> codes;
    for(const auto &ir:functions){
      const auto &function=p.function(ir.name);
      auto description=taskDebugFunctionMetadata(p,function,ir,p.location(function.span));
      std::vector<std::vector<MetadataField>> bindings,points;std::vector<int64_t> visible;
      for(const auto &value:*description.getArray("bindings")){const auto &binding=*value.getAsObject();
        bindings.push_back({*binding.getInteger("id"),rawGlobal(binding.getString("name")->str()),rawGlobal(binding.getString("type")->str()),*binding.getInteger("slot"),*binding.getInteger("scope")});
      }
      for(const auto &value:*description.getArray("points")){const auto &point=*value.getAsObject();auto begin=visible.size();
        for(const auto &id:*point.getArray("visible"))visible.push_back(*id.getAsInteger()-1);
        points.push_back({rawGlobal(point.getString("site")->str()),*point.getInteger("pc"),*point.getInteger("line"),*point.getInteger("column"),
          *point.getInteger("begin"),*point.getInteger("end"),*point.getInteger("kind"),int64_t(begin),int64_t(visible.size()-begin)});
      }
      auto pointArray=metadataArray("nex_task_debug_points_","!llvm.struct<(!llvm.ptr, i64, i64, i64, i64, i64, i64, i64, i64)>",points);
      auto bindingArray=metadataArray("nex_task_debug_bindings_","!llvm.struct<(i64, !llvm.ptr, !llvm.ptr, i64, i64)>",bindings);
      auto visibility=visible.empty()?std::string{}:taskArray(visible);
      codes.push_back({taskCodes.at(ir.name),rawGlobal(ir.name),rawGlobal(p.location(function.span)),rawGlobal(hash(p.definition(function))),rawGlobal(hash(json(canonical(function),false))),
        pointArray,bindingArray,visibility,int64_t(points.size()),int64_t(bindings.size()),int64_t(visible.size()),int64_t(ir.slots.size())});
    }
    taskDebugTable=metadataArray("nex_task_debug_codes_","!llvm.struct<(!llvm.ptr, !llvm.ptr, !llvm.ptr, !llvm.ptr, !llvm.ptr, !llvm.ptr, !llvm.ptr, !llvm.ptr, i64, i64, i64, i64)>",codes);
  }
  void selectFunction(const Function &function){
    selectedFunction=&function;
    siteDescriptions.clear();pathSites.clear();
    auto content=hash(json(canonical(function),false)),source=hash(p.definition(function)),key=content+source;
    auto entry=functionGlobals.find(key);
    if(entry==functionGlobals.end())entry=functionGlobals.emplace(key,structureGlobal("nex_site_function_",{rawGlobal(content),rawGlobal(source),rawGlobal(NEX_BUILD_ID)})).first;
    for(const auto &op:operationTree(p,function)){
      pathSites[op.path]=op.site;
      siteDescriptions.emplace(op.site,SiteDescription{entry->second,op.site,op.kind,int64_t(op.span.begin)-int64_t(function.span.begin),int64_t(op.span.end)-int64_t(function.span.begin)});
    }
    activeSite=pathSites.at("body");
  }
  Value siteAddress(const SiteDescription &site,Span span){
    auto key=site.function+site.site;auto entry=siteGlobals.find(key);
    if(entry==siteGlobals.end())entry=siteGlobals.emplace(key,structureGlobal("nex_site_",{site.function,rawGlobal(site.site),rawGlobal(site.kind)},{site.begin,site.end})).first;
    auto n=fresh();line(n+" = llvm.mlir.addressof @"+entry->second+" : !llvm.ptr",span);return {n,Type::Str};
  }
  struct SiteScope {std::string &value,old;SiteScope(std::string &value,std::string next):value(value),old(value){value=std::move(next);}~SiteScope(){value=std::move(old);}};
  std::string fresh(){return "%v"+std::to_string(serial++);}
  std::string label(){return "b"+std::to_string(serial++);}
  std::string loc(Span s)const{if(prologue){s.line=0;s.column=0;}return debug.location(s,prologue?"":activeSite);}
  void line(const std::string &s,Span span){out<<"    "<<s<<loc(span)<<"\n";}
  void blockLabel(const std::string &s){out<<"  ^"<<s<<":\n";}
  Value constant(int64_t value,Type type,Span span){
    auto n=fresh();line(n+" = arith.constant "+std::to_string(value)+" : "+ty(type),span);return {n,type};
  }
  Value null(Type type,Span span){auto n=fresh();line(n+" = llvm.mlir.zero : !llvm.ptr",span);return {n,type};}
  Value call(const std::string &name,const std::vector<Value> &args,Type result,Span span){
    auto operandsWithSite=args;auto target=name;
    if(runtimeCalls.contains(name)){
      auto site=siteDescriptions.find(activeSite);if(site==siteDescriptions.end())throw Error("E_INTERNAL","native runtime call has no checked operation site",span);
      operandsWithSite.push_back(siteAddress(site->second,span));target+="_at";
    }
    std::string operands,types;
    for(const auto &a:operandsWithSite){if(!operands.empty()){operands+=", ";types+=", ";}operands+=a.name;types+=ty(a.type);}
    auto n=result==Type::Unit?"":fresh();
    line((n.empty()?"":n+" = ")+"func.call @"+target+"("+operands+") : ("+types+") -> "+ty(result),span);return {n,result};
  }
  Value checkedInteger(const std::string &operation,Value a,Value b,Span span){
    // Successful integer arithmetic stays in SSA. Only the failure edge passes
    // diagnostic metadata to the unchanged checked runtime helper.
    auto bad=label(),good=label();Value result,invalid;
    bool negate=operation=="neg";
    if(operation=="add"||operation=="sub"||operation=="mul"||negate){
      auto intrinsic=negate?"sub":operation;auto pair=fresh(),value=fresh(),overflow=fresh();
      std::string structure="!llvm.struct<(i64, i1)>";
      line(pair+" = \"llvm.intr.s"+intrinsic+".with.overflow\"("+a.name+", "+b.name+") : (i64, i64) -> "+structure,span);
      line(value+" = llvm.extractvalue "+pair+"[0] : "+structure,span);
      line(overflow+" = llvm.extractvalue "+pair+"[1] : "+structure,span);
      result={value,Type::I64};invalid={overflow,Type::Bool};
    }else{
      auto zero=equalScalar(b,constant(0,Type::I64,span),span);
      auto minimum=equalScalar(a,constant(std::numeric_limits<int64_t>::min(),Type::I64,span),span);
      auto minusOne=equalScalar(b,constant(-1,Type::I64,span),span);auto corner=fresh();
      line(corner+" = arith.andi "+minimum.name+", "+minusOne.name+" : i1",span);
      if(operation=="div"){
        auto error=fresh();line(error+" = arith.ori "+zero.name+", "+corner+" : i1",span);invalid={error,Type::Bool};
      }else{
        // LLVM srem is undefined for MIN/-1. Language remainder is exactly zero;
        // selecting divisor one makes that case defined before optimization.
        auto one=constant(1,Type::I64,span);auto divisor=fresh();line(divisor+" = arith.select "+corner+", "+one.name+", "+b.name+" : i64",span);
        b={divisor,Type::I64};invalid=zero;
      }
    }
    line("cf.cond_br "+invalid.name+", ^"+bad+", ^"+good,span);
    blockLabel(bad);
    if(negate)call("nex_neg",{b,constant(span.line,Type::I64,span)},Type::I64,span);
    else call("nex_"+operation,{a,b,constant(span.line,Type::I64,span)},Type::I64,span);
    line("llvm.unreachable",span);blockLabel(good);
    if(operation=="div"||operation=="mod"){
      auto value=fresh();line(value+(operation=="div"?" = arith.divsi ":" = arith.remsi ")+a.name+", "+b.name+" : i64",span);result={value,Type::I64};
    }
    return result;
  }
  Value asI64(Value v,Span span){if(v.type==Type::I64)return v;auto n=fresh();line(n+(v.type==Type::F64?" = arith.bitcast ":" = arith.extui ")+v.name+" : "+ty(v.type)+" to i64",span);return {n,Type::I64};}
  Value asBool(Value v,Span span){auto n=fresh();line(n+" = arith.trunci "+v.name+" : i64 to i1",span);return {n,Type::Bool};}
  Value fromScalar(Value v,Type type,Span span){if(type==Type::Bool)return asBool(v,span);if(type!=Type::F64)return v;auto n=fresh();line(n+" = arith.bitcast "+v.name+" : i64 to f64",span);return {n,type};}
  void release(Value v,Span span){if(v.type.heap())call("nex_release",{v},Type::Unit,span);}
  Value lookup(const std::string &name){
    for(auto i=scopes.rbegin();i!=scopes.rend();++i)if(i->contains(name))return i->at(name);
    throw Error("E_INTERNAL","missing checked local");
  }
  Value load(Value v,Span span,bool retain=true){
    if(v.address){
      auto n=fresh();line(n+" = llvm.load "+v.name+" : !llvm.ptr -> "+ty(v.type),span);v={n,v.type};
    }
    if(retain&&v.type.heap())return call("nex_retain",{v},v.type,span);return v;
  }
  void writeSlot(Value value,const std::string &slot,Span span){
    line("llvm.store "+value.name+", "+slot+" : "+ty(value.type)+", !llvm.ptr",span);
  }
  void store(Value value,const std::string &slot,Span span){
    if(value.type.heap())release(load({slot,value.type,true},span,false),span);writeSlot(value,slot,span);
  }
  void describeStorage(const std::string &name,Type type,Span span,const std::string &slot,unsigned argument=0){
    line("llvm.intr.dbg.declare "+debug.variable(name,type,span,argument)+" = "+slot+" : !llvm.ptr",span);
  }
  std::string allocateSlot(Type type,Span span){
    auto count=constant(1,Type::I64,span);auto slot=fresh();
    line(slot+" = llvm.alloca "+count.name+" x "+ty(type)+" : (i64) -> !llvm.ptr",span);return slot;
  }
  void cleanup(const std::map<std::string,Value> &scope,Span span){
    for(const auto &[name,value]:scope)if(value.address&&value.type.heap()){
      release(load(value,span,false),span);writeSlot(null(value.type,span),value.name,span);
    }
  }
  void cleanupAll(Span span){for(auto i=scopes.rbegin();i!=scopes.rend();++i)cleanup(*i,span);}
  void leaveOwned(Value kept,Span span){
    if(!ownedToken.name.empty())call("nex_owned_leave",{ownedToken,kept.type.heap()?kept:null(Type::Str,span)},Type::Unit,span);
  }
  void returnValue(Value value,Span span){
    cleanupAll(span);leaveOwned(value,span);
    if(profiling)call("nex_profile_leave",{},Type::Unit,span);
    if(wasm)call("nex_wasm_leave",{},Type::Unit,span);
    if(parallelEnabled)call("nex_parallel_leave",{},Type::Unit,span);
    line(value.type==Type::Unit?"func.return":"func.return "+value.name+" : "+ty(value.type),span);
  }
  Value rawBytes(const std::string &text,Span span){
    auto symbol=rawGlobal(text),n=fresh();
    line(n+" = llvm.mlir.addressof @"+symbol+" : !llvm.ptr",span);return {n,Type::Str};
  }
  Value text(const std::string &text,Span span){
    auto bytes=rawBytes(text,span);return call("nex_string_new",{bytes,constant(text.size(),Type::I64,span),constant(span.line,Type::I64,span)},Type::Str,span);
  }
  void allocateExpr(E e){
    if(!e)return;
    if(e->kind==Expr::Binary&&(e->text=="&&"||e->text=="||")){
      shortSlots[e.get()]=allocateSlot(Type::Bool,e->span);
    }
    if(e->kind==Expr::Match){
      auto subject=e->args[0]->type;auto slot=allocateSlot(subject,e->span);matchSlots[e.get()]=slot;if(subject.heap())writeSlot(null(subject,e->span),slot,e->span);
      if(e->type!=Type::Unit){auto result=allocateSlot(e->type,e->span);matchResults[e.get()]=result;if(e->type.heap())writeSlot(null(e->type,e->span),result,e->span);}
      for(auto arm:e->arms)visitPattern(arm->pattern,[&](P pattern){if(pattern->kind!=Pattern::Wildcard){auto slot=allocateSlot(pattern->type,pattern->span);patternSlots[pattern.get()]=slot;if(pattern->type.heap())writeSlot(null(pattern->type,pattern->span),slot,pattern->span);}});
    }
    for(auto a:e->args)allocateExpr(a);
  }
  void allocate(const std::vector<S> &body){
    for(auto s:body){
      if(s->kind==Stmt::Let||s->kind==Stmt::Var){
        auto n=allocateSlot(s->type,s->span);slots[s.get()]=n;
        if(s->type.heap())writeSlot(null(s->type,s->span),n,s->span);
      }

      allocateExpr(s->expr);childBlocks(s,[&](const auto &body){allocate(body);});
    }
  }
  Value get(Value base,Value index,Type result,Span span){
    auto value=call(result.heap()?"nex_collection_get_heap":"nex_collection_get_i64",{base,index,constant(span.line,Type::I64,span)},result.heap()?result:Type(Type::I64),span);
    release(base,span);return fromScalar(value,result,span);
  }
  void patternBranch(Value condition,const std::string &failure,Span span){auto yes=label();line("cf.cond_br "+condition.name+", ^"+yes+", ^"+failure,span);blockLabel(yes);}
  Value equalScalar(Value a,Value b,Span span){auto value=fresh();line(value+" = arith.cmpi eq, "+a.name+", "+b.name+" : "+ty(a.type),span);return {value,Type::Bool};}
  void pattern(P p,Value input,const std::string &failure){
    auto span=p->span;if(p->kind==Pattern::Wildcard){release(input,span);return;}
    auto slot=Value{patternSlots.at(p.get()),p->type,true};store(input,slot.name,span);if(p->kind==Pattern::Binding)return;
    auto value=load(slot,span,false);
    if(p->kind==Pattern::Integer||p->kind==Pattern::Boolean){patternBranch(equalScalar(value,constant(p->number,p->type,span),span),failure,span);return;}
    if(p->kind==Pattern::String){auto literal=text(p->text,span);auto same=asBool(call("nex_heap_equal",{value,literal},Type::I64,span),span);release(literal,span);patternBranch(same,failure,span);return;}
    if(p->kind==Pattern::List)patternBranch(equalScalar(call("nex_length",{value},Type::I64,span),constant(p->args.size(),Type::I64,span),span),failure,span);
    else if(p->type.kind==Type::Result)patternBranch(equalScalar(call("nex_is_ok",{value},Type::I64,span),constant(p->ordinal,Type::I64,span),span),failure,span);
    else if(this->p.structure(p->type.name).enumeration){auto tag=call("nex_enum_tag",{value,constant(this->p.structure(p->type.name).variants.size(),Type::I64,span),constant(span.line,Type::I64,span)},Type::I64,span);patternBranch(equalScalar(tag,constant(p->ordinal,Type::I64,span),span),failure,span);}
    for(size_t i=0;i<p->args.size();++i){auto child=p->args[i];if(child->kind==Pattern::Wildcard)continue;Value field;
      if(p->type.kind==Type::Result){if(p->ordinal){field=call(child->type.heap()?"nex_unwrap_heap":"nex_unwrap_i64",{value,constant(span.line,Type::I64,span)},child->type.heap()?child->type:Type(Type::I64),span);field=fromScalar(field,child->type,span);}else field=call("nex_error_text",{value,constant(i==1,Type::I64,span)},Type::Str,span);}
      else field=get(load(slot,span),constant(i,Type::I64,span),child->type,span);
      pattern(child,field,failure);
    }
  }
  std::pair<Value,bool> matching(E e){
    auto subject=Value{matchSlots.at(e.get()),e->args[0]->type,true};store(expression(e->args[0]),subject.name,e->span);
    scopes.emplace_back();scopes.back()["$match"]=subject;
    Value output;if(e->type!=Type::Unit){output={matchResults.at(e.get()),e->type,true};scopes.back()["$result"]=output;}
    auto end=label();bool all=true;auto parentScope=debug.scope;
    for(size_t i=0;i<e->arms.size();++i){auto arm=e->arms[i];auto failure=label(),next=label();scopes.emplace_back();debug.scope=debug.block(arm->span);SiteScope site(activeSite,sites.at(arm.get()));
      visitPattern(arm->pattern,[&](P p){if(p->kind!=Pattern::Wildcard){auto slot=patternSlots.at(p.get());scopes.back()[p->kind==Pattern::Binding?p->text:"$pattern"+slot]={slot,p->type,true};}});
      pattern(arm->pattern,load(subject,arm->span),failure);
      visitPattern(arm->pattern,[&](P p){if(p->kind==Pattern::Binding)describeStorage(p->text,p->type,p->span,patternSlots.at(p.get()));});
      if(arm->guard)patternBranch(expression(e->args[arm->guard]),failure,arm->span);
      bool returns=false;if(e->statementMatch)returns=statements(arm->body,false);else {auto value=expression(e->args[arm->value]);if(e->type!=Type::Unit)store(value,output.name,arm->span);cleanup(scopes.back(),arm->span);}
      all=all&&returns;if(!returns)line("cf.br ^"+end,arm->span);
      bool canFail=bool(arm->guard);visitPattern(arm->pattern,[&](P p){if(p->kind==Pattern::Integer||p->kind==Pattern::Boolean||p->kind==Pattern::String||p->kind==Pattern::List||(p->kind==Pattern::Constructor&&(p->type.kind==Type::Result||this->p.structure(p->type.name).enumeration)))canFail=true;});
      if(canFail){blockLabel(failure);cleanup(scopes.back(),arm->span);if(i+1<e->arms.size()){line("cf.br ^"+next,arm->span);blockLabel(next);}else{call("nex_match_fail",{constant(arm->span.line,Type::I64,arm->span)},Type::Unit,arm->span);line("llvm.unreachable",arm->span);}}
      scopes.pop_back();debug.scope=parentScope;
    }
    Value result{"",Type::Unit};if(!all){blockLabel(end);if(e->type!=Type::Unit)result=load(output,e->span);cleanup(scopes.back(),e->span);}scopes.pop_back();return {result,all};
  }
  Value expression(E e){
    SiteScope site(activeSite,sites.at(e.get()));
    if(e->kind==Expr::FunctionRef||e->kind==Expr::Lambda){
      const auto &target=p.function(e->text);auto function=fresh(),pointer=fresh();auto signature=callableType(e->type);
      bool taskClosure=e->type.effects.contains("task");
      if(taskClosure)line(pointer+" = llvm.mlir.addressof @"+taskCodes.at(target.name)+" : !llvm.ptr",e->span);
      else{line(function+" = func.constant @"+closureSymbol(target)+" : "+signature,e->span);line(pointer+" = builtin.unrealized_conversion_cast "+function+" : "+signature+" to !llvm.ptr",e->span);}
      auto count=[&](int64_t value){return constant(value,Type::I64,e->span);};auto closure=call(taskClosure?"nex_task_closure_new":"nex_closure_new",{{pointer,Type::Str},count(e->args.size())},e->type,e->span);
      if(!taskClosure&&taskCodes.contains(target.name)){auto descriptor=fresh();line(descriptor+" = llvm.mlir.addressof @"+taskCodes.at(target.name)+" : !llvm.ptr",e->span);call("nex_task_closure_bind",{closure,{descriptor,Type::Str}},Type::Unit,e->span);}
      auto name=rawBytes(e->text,e->span);call("nex_record_name",{closure,name,count(e->text.size())},Type::Unit,e->span);
      for(size_t i=0;i<e->args.size();++i){auto value=expression(e->args[i]);auto name=rawBytes(target.captures[i].name,e->span);call("nex_record_field_name",{closure,count(i),name,count(target.captures[i].name.size())},Type::Unit,e->span);
        if(value.type.heap())call("nex_record_init_heap",{closure,count(i),value},Type::Unit,e->span);else call("nex_record_init_i64",{closure,count(i),asI64(value,e->span),count(scalarTag(value.type))},Type::Unit,e->span);release(value,e->span);
      }return closure;
    }
    if(e->kind==Expr::Invoke){
      auto closure=expression(e->args[0]);std::vector<Value> args{closure};for(size_t i=1;i<e->args.size();++i)args.push_back(expression(e->args[i]));
      auto pointer=call("nex_closure_code",{closure},Type::Str,e->span);std::string operands,types;for(const auto &argument:args){if(!operands.empty()){operands+=", ";types+=", ";}operands+=argument.name;types+=ty(argument.type);}
      auto name=e->type==Type::Unit?"":fresh();line((name.empty()?"":name+" = ")+"llvm.call "+pointer.name+"("+operands+") : !llvm.ptr, ("+types+") -> "+ty(e->type),e->span);for(auto argument:args)release(argument,e->span);return {name,e->type};
    }
    if(e->kind==Expr::Match)return matching(e).first;
    if(e->kind==Expr::Integer||e->kind==Expr::Boolean)return constant(e->number,e->type,e->span);
    if(e->kind==Expr::Floating)return fromScalar(constant(e->number,Type::I64,e->span),Type::F64,e->span);
    if(e->kind==Expr::String)return text(e->text,e->span);
    if(e->kind==Expr::Name)return load(lookup(e->text),e->span);
    if(e->kind==Expr::List){
      auto list=call("nex_list_new",{},e->type,e->span);
      for(auto item:e->args){
        auto value=expression(item);
        if(value.type.heap())call("nex_list_append_heap",{list,value},Type::Unit,item->span);
        else call("nex_list_append_i64",{list,asI64(value,item->span),constant(scalarTag(value.type),Type::I64,item->span)},Type::Unit,item->span);
        release(value,item->span);
      }
      return list;
    }
    if(e->kind==Expr::Field){auto base=expression(e->args[0]);return get(base,constant(e->number,Type::I64,e->span),e->type,e->span);}
    if(e->kind==Expr::Index){auto base=expression(e->args[0]);auto index=expression(e->args[1]);return get(base,index,e->type,e->span);}
    if(e->kind==Expr::Call){
      std::vector<Value> args;for(auto a:e->args)args.push_back(expression(a));Value result;
      auto c=[&](int64_t v){return constant(v,Type::I64,e->span);};
      if(auto variant=p.variant(e->text)){
        result=call("nex_enum_new",{c(variant->fields.size()),c(variant->ordinal)},e->type,e->span);
        auto name=rawBytes(e->text,e->span);call("nex_record_name",{result,name,c(e->text.size())},Type::Unit,e->span);
        for(size_t i=0;i<args.size();++i){const auto &field=variant->fields[i];auto name=rawBytes(field.name,e->span);call("nex_record_field_name",{result,c(i),name,c(field.name.size())},Type::Unit,e->span);
          if(args[i].type.heap())call("nex_record_init_heap",{result,c(i),args[i]},Type::Unit,e->span);else call("nex_record_init_i64",{result,c(i),asI64(args[i],e->span),c(scalarTag(args[i].type))},Type::Unit,e->span);}
      }else if(p.hasStructure(e->text)){
        const auto &s=p.structure(e->text);result=call("nex_record_new",{c(s.fields.size())},e->type,e->span);
        auto name=rawBytes(s.name,e->span);call("nex_record_name",{result,name,c(s.name.size())},Type::Unit,e->span);
        for(size_t i=0;i<args.size();++i){
          auto name=rawBytes(s.fields[i].name,e->span);call("nex_record_field_name",{result,c(i),name,c(s.fields[i].name.size())},Type::Unit,e->span);
          if(args[i].type.heap())call("nex_record_init_heap",{result,c(i),args[i]},Type::Unit,e->span);
          else call("nex_record_init_i64",{result,c(i),asI64(args[i],e->span),c(scalarTag(args[i].type))},Type::Unit,e->span);
        }
      }else if(e->text=="parallel_map"){
        auto symbol="nex_parallel_bridge_"+hash(selectedFunction->name+":"+sites.at(e.get()));
        parallelThunks.emplace(symbol,ParallelThunk{selectedFunction,e});
        auto function=fresh(),pointer=fresh();const std::string signature="(!llvm.ptr, i64, !llvm.ptr, !llvm.ptr) -> ()";
        line(function+" = func.constant @"+symbol+" : "+signature,e->span);
        line(pointer+" = builtin.unrealized_conversion_cast "+function+" : "+signature+" to !llvm.ptr",e->span);
        auto kind=[](const Type&t){return t.heap()?3:t==Type::F64?2:t==Type::Bool?1:0;};
        result=call("nex_parallel_map",{args[0],args[1],args[2],{pointer,Type::Str},c(kind(*e->args[0]->type.element)),c(kind(*e->type.element)),c(e->span.line)},e->type,e->span);
      }else if(e->text=="print"){
        result=args[0].type.heap()?call("nex_print_heap",{args[0]},Type::Unit,e->span):args[0].type==Type::F64?call("nex_print_f64",{args[0]},Type::Unit,e->span):call(args[0].type==Type::Bool?"nex_print_bool":"nex_print_i64",{asI64(args[0],e->span)},Type::Unit,e->span);
      }else if(e->text=="assert"){
        auto failure=label(),success=label();line("cf.cond_br "+args[0].name+", ^"+success+", ^"+failure,e->span);
        blockLabel(failure);call("nex_assert",{c(0),c(e->span.line)},Type::Unit,e->span);line("llvm.unreachable",e->span);
        blockLabel(success);result={"",Type::Unit};
      }
      else if(e->text=="len")result=call("nex_length",args,Type::I64,e->span);
      else if(e->text=="str")result=args[0].type.heap()?call("nex_format_heap",args,Type::Str,e->span):call("nex_format_i64",{asI64(args[0],e->span),c(scalarTag(args[0].type))},Type::Str,e->span);
      else if(e->text=="ok")result=args[0].type.heap()?call("nex_ok_heap",args,e->type,e->span):call("nex_ok_i64",{asI64(args[0],e->span),c(scalarTag(args[0].type))},e->type,e->span);
      else if(e->text=="as_f64"||e->text=="as_i64")result=call("nex_"+e->text,{args[0],c(e->span.line)},e->type,e->span);
      else if(e->text=="bytes"||e->text=="utf8_bytes"||e->text=="decode_utf8"||e->text=="encode_base64"||e->text=="decode_base64")result=call(e->text=="bytes"?"nex_bytes_from_integers":"nex_"+e->text,{args[0],c(e->span.line)},e->type,e->span);
      else if(e->text=="err")result=call("nex_err",args,e->type,e->span);
      else if(e->text=="is_ok")result=asBool(call("nex_is_ok",args,Type::I64,e->span),e->span);
      else if(e->text=="unwrap"){
        result=call(e->type.heap()?"nex_unwrap_heap":"nex_unwrap_i64",{args[0],c(e->span.line)},e->type.heap()?e->type:Type(Type::I64),e->span);
        result=fromScalar(result,e->type,e->span);
      }
      else if(e->text=="error_code"||e->text=="error_message")result=call("nex_error_text",{args[0],c(e->text=="error_message")},Type::Str,e->span);
      else if(e->text=="encode_json")result=args[0].type.heap()?call("nex_encode_json_heap",{args[0],c(e->span.line)},Type::Str,e->span):call("nex_encode_json_i64",{asI64(args[0],e->span),c(scalarTag(args[0].type)),c(e->span.line)},Type::Str,e->span);
      else if(e->text=="decode_json"){
        auto schema=json(wireSchema(p,e->annotation),false);auto bytes=rawBytes(schema,e->span);result=call("nex_decode_json",{args[0],bytes,c(schema.size()),c(e->span.line)},e->type,e->span);
      }
      else if(e->text=="read_env")result=call("nex_read_env",args,e->type,e->span);
      else if(e->text=="file_read_text"||e->text=="file_write_text"||e->text=="file_read_bytes"||e->text=="file_write_bytes"||streamFileBuiltins().contains(e->text)){
        auto operands=args;operands.push_back(c(e->span.line));bool scalar=e->type==Type::Bool;
        result=call("nex_"+e->text,operands,scalar?Type(Type::I64):e->type,e->span);if(scalar)result=asBool(result,e->span);
      }
      else if(e->text=="store_get"||e->text=="store_put"||e->text=="store_remove"||e->text=="store_keys"){
        auto operands=args;operands.push_back(c(e->span.line));result=call("nex_"+e->text,operands,e->type,e->span);
      }
      else if(e->text=="slice")result=call("nex_string_slice",{args[0],args[1],args[2],c(e->span.line)},e->type,e->span);
      else if(e->text=="contains")result=asBool(call("nex_string_contains",args,Type::I64,e->span),e->span);
      else if(e->text=="push"||e->text=="set"){
        bool set=e->text=="set";auto value=args.back(),index=set?args[1]:c(0);
        if(value.type.heap())result=call("nex_list_update_heap",{args[0],index,value,c(set),c(e->span.line)},e->type,e->span);
        else result=call("nex_list_update_i64",{args[0],index,asI64(value,e->span),c(scalarTag(value.type)),c(set),c(e->span.line)},e->type,e->span);
      }else result=call(nativeSymbol(e->text),args,e->type,e->span);
      for(auto a:args)release(a,e->span);return result;
    }
    if(e->kind==Expr::Propagate){
      auto result=expression(e->args[0]);auto valid=asBool(call("nex_is_ok",{result},Type::I64,e->span),e->span);
      auto success=label(),failure=label();line("cf.cond_br "+valid.name+", ^"+success+", ^"+failure,e->span);
      blockLabel(failure);returnValue(result,e->span);
      blockLabel(success);auto value=call(e->type.heap()?"nex_unwrap_heap":"nex_unwrap_i64",{result,constant(e->span.line,Type::I64,e->span)},e->type.heap()?e->type:Type(Type::I64),e->span);
      value=fromScalar(value,e->type,e->span);release(result,e->span);return value;
    }
    Value a=expression(e->args[0]);
    if(e->kind==Expr::Unary){
      if(e->text=="-")return a.type==Type::F64?call("nex_f64_neg",{a,constant(e->span.line,Type::I64,e->span)},a.type,e->span):checkedInteger("neg",constant(0,Type::I64,e->span),a,e->span);
      auto one=constant(1,Type::Bool,e->span);auto n=fresh();line(n+" = arith.xori "+a.name+", "+one.name+" : i1",e->span);return {n,Type::Bool};
    }
    const auto &op=e->text;
    if(op=="&&"||op=="||"){
      auto rhs=label(),shortcut=label(),end=label();auto slot=shortSlots.at(e.get());
      line("cf.cond_br "+a.name+", ^"+(op=="&&"?rhs:shortcut)+", ^"+(op=="&&"?shortcut:rhs),e->span);
      blockLabel(shortcut);store(constant(op=="||",Type::Bool,e->span),slot,e->span);line("cf.br ^"+end,e->span);
      blockLabel(rhs);store(expression(e->args[1]),slot,e->span);line("cf.br ^"+end,e->span);
      blockLabel(end);return load({slot,Type::Bool,true},e->span);
    }
    auto b=expression(e->args[1]);
    if(a.type.heap()){
      Value result;
      if(op=="+")result=call("nex_heap_concat",{a,b,constant(e->span.line,Type::I64,e->span)},e->type,e->span);
      else{
        result=asBool(call("nex_heap_equal",{a,b},Type::I64,e->span),e->span);
        if(op=="!="){auto one=constant(1,Type::Bool,e->span);auto n=fresh();line(n+" = arith.xori "+result.name+", "+one.name+" : i1",e->span);result={n,Type::Bool};}
      }
      release(a,e->span);release(b,e->span);return result;
    }
    static const std::map<std::string,std::string> arithmetic={{"+","add"},{"-","sub"},{"*","mul"},{"/","div"},{"%","mod"}};
    if(a.type==Type::F64){
      if(arithmetic.contains(op))return call("nex_f64_"+arithmetic.at(op),{a,b,constant(e->span.line,Type::I64,e->span)},Type::F64,e->span);
      const std::map<std::string,int64_t> comparisons={{"==",0},{"!=",1},{"<",2},{"<=",3},{">",4},{">=",5}};
      return asBool(call("nex_f64_compare",{a,b,constant(comparisons.at(op),Type::I64,e->span),constant(e->span.line,Type::I64,e->span)},Type::I64,e->span),e->span);
    }
    if(arithmetic.contains(op))return checkedInteger(arithmetic.at(op),a,b,e->span);
    static const std::map<std::string,std::string> predicates={{"==","eq"},{"!=","ne"},{"<","slt"},{"<=","sle"},{">","sgt"},{">=","sge"}};
    auto n=fresh();line(n+" = arith.cmpi "+predicates.at(op)+", "+a.name+", "+b.name+" : "+ty(a.type),e->span);return {n,Type::Bool};
  }
  bool statements(const std::vector<S> &body,bool scoped=true){
    auto previousDebugScope=debug.scope;
    if(scoped){scopes.emplace_back();if(!body.empty())debug.scope=debug.block(body.front()->span);}bool returned=false;
    for(auto s:body){
      SiteScope site(activeSite,sites.at(s.get()));
      switch(s->kind){
      case Stmt::Let:case Stmt::Var:{auto value=expression(s->expr);auto slot=slots.at(s.get());store(value,slot,s->span);
        // Initializers see the outer binding; the new scope begins afterwards.
        debug.scope=debug.block(s->span);describeStorage(s->name,s->type,s->span,slot);scopes.back()[s->name]={slot,s->type,true};break;}
      case Stmt::Assign:{auto value=expression(s->expr);store(value,lookup(s->name).name,s->span);break;}
      case Stmt::Expression:release(expression(s->expr),s->span);break;
      case Stmt::Return:{
        Value value{"",Type::Unit};if(s->expr)value=expression(s->expr);returnValue(value,s->span);returned=true;break;
      }
      case Stmt::If:{
        auto condition=expression(s->expr);auto yes=label(),no=label(),end=label();
        line("cf.cond_br "+condition.name+", ^"+yes+", ^"+no,s->span);
        blockLabel(yes);bool a=statements(s->body);if(!a)line("cf.br ^"+end,s->span);
        blockLabel(no);bool b=statements(s->alternative);if(!b)line("cf.br ^"+end,s->span);
        if(!(a&&b))blockLabel(end);returned=a&&b;break;
      }
      case Stmt::Match:returned=matching(s->expr).second;break;
      case Stmt::While:{
        auto condition=label(),bodyLabel=label(),end=label();line("cf.br ^"+condition,s->span);blockLabel(condition);call("nex_poll",{constant(s->span.line,Type::I64,s->span)},Type::Unit,s->span);
        auto value=expression(s->expr);line("cf.cond_br "+value.name+", ^"+bodyLabel+", ^"+end,s->span);
        blockLabel(bodyLabel);if(!statements(s->body))line("cf.br ^"+condition,s->span);blockLabel(end);break;
      }
      }
      if(returned)break;
    }
    if(!returned)cleanup(scopes.back(),body.empty()?Span():body.back()->span);
    if(scoped)scopes.pop_back();debug.scope=previousDebugScope;return returned;
  }
  void declaration(const std::string &name,const std::string &arguments,const std::string &result=""){
    bool located=runtimeDeclarations&&name!="nex_profile_enter"&&name!="nex_profile_leave"&&name!="nex_task_profile_prepare"&&name!="nex_wasm_leave";
    if(located)runtimeCalls.insert(name);
    out<<"  func.func private @"<<name<<(located?"_at":"")<<"("<<arguments<<(located?(arguments.empty()?"!llvm.ptr":", !llvm.ptr"):"")<<")"<<(result.empty()?"":" -> "+result)<<"\n";
  }
  std::string taskArray(const std::vector<int64_t> &values){
    auto symbol="nex_task_array_"+std::to_string(serial++);auto count=std::max(size_t(1),values.size());auto type="!llvm.array<"+std::to_string(count)+" x i64>";
    globals<<"  llvm.mlir.global private constant @"<<symbol<<"() : "<<type<<" {\n    %a0 = llvm.mlir.undef : "<<type<<"\n";
    for(size_t i=0;i<count;++i)globals<<"    %v"<<i<<" = llvm.mlir.constant("<<(i<values.size()?values[i]:0)<<" : i64) : i64\n    %a"<<i+1<<" = llvm.insertvalue %v"<<i<<", %a"<<i<<"["<<i<<"] : "<<type<<"\n";
    globals<<"    llvm.return %a"<<count<<" : "<<type<<"\n  }\n";return symbol;
  }
  void taskDeclarations(){
    declaration("nex_task_frame_pc","!llvm.ptr","i64");
    declaration("nex_task_frame_set_pc","!llvm.ptr, i64");
    declaration("nex_task_frame_get_i64","!llvm.ptr, i64, i64","i64");
    declaration("nex_task_frame_get_heap","!llvm.ptr, i64","!llvm.ptr");
    declaration("nex_task_frame_put_i64","!llvm.ptr, i64, i64, i64");
    declaration("nex_task_frame_put_heap","!llvm.ptr, i64, !llvm.ptr");
    declaration("nex_task_frame_drop","!llvm.ptr, i64");
    declaration("nex_task_frame_return_i64","!llvm.ptr, i64, i64");
    declaration("nex_task_frame_return_heap","!llvm.ptr, !llvm.ptr");
    declaration("nex_task_frame_return_unit","!llvm.ptr");
    declaration("nex_task_frame_bad_pc","!llvm.ptr");
    runtimeDeclarations=true;
    declaration("nex_task_frame_call","!llvm.ptr, !llvm.ptr, !llvm.ptr, !llvm.ptr, i64, i64");
    declaration("nex_task_frame_pause","!llvm.ptr, i64, !llvm.ptr, i64, i64, i64");
    declaration("nex_task_closure_new","!llvm.ptr, i64","!llvm.ptr");
    declaration("nex_task_closure_bind","!llvm.ptr, !llvm.ptr");
    runtimeDeclarations=false;
    if(taskDebug){declaration("nex_task_debug_prepare","!llvm.ptr, i64");declaration("nex_task_debug_checkpoint","!llvm.ptr, i64");}
  }
  void taskStep(const TaskFunctionIR &ir){
    const auto &function=p.function(ir.name);selectFunction(function);debug.scope.clear();
    out<<"  llvm.func @"<<nativeSymbol(ir.name)<<"__task_step(%task_frame: !llvm.ptr) -> i64 {\n";
    scopes.clear();scopes.emplace_back();patternSlots.clear();ownedToken={};
    ownedToken=call("nex_owned_enter",{},Type::I64,function.span);
    call("nex_parallel_enter",{},Type::Unit,function.span);
    for(const auto &op:ir.code)if(op.kind==TaskInstruction::Pattern)visitPattern(op.pattern,[&](P pat){if(pat->kind!=Pattern::Wildcard){auto slot=allocateSlot(pat->type,pat->span);patternSlots[pat.get()]=slot;if(pat->type.heap())writeSlot(null(pat->type,pat->span),slot,pat->span);}});
    Value frame{"%task_frame",Type::Str};
    auto c=[&](int64_t n,Span span){return constant(n,Type::I64,span);};
    auto read=[&](TaskSlotId id,Span span){auto type=ir.slots.at(id).type;return type.heap()?call("nex_task_frame_get_heap",{frame,c(id,span)},type,span):fromScalar(call("nex_task_frame_get_i64",{frame,c(id,span),c(scalarTag(type),span)},Type::I64,span),type,span);};
    auto put=[&](TaskSlotId id,Value value,Span span){if(id==noTaskSlot)return;if(value.type.heap())call("nex_task_frame_put_heap",{frame,c(id,span),value},Type::Unit,span);else call("nex_task_frame_put_i64",{frame,c(id,span),asI64(value,span),c(scalarTag(value.type),span)},Type::Unit,span);};
    auto finish=[&](int64_t transition,Span span){leaveOwned({},span);call("nex_parallel_leave",{},Type::Unit,span);line("llvm.return "+c(transition,span).name+" : i64",span);};
    auto pc=call("nex_task_frame_pc",{frame},Type::I64,function.span);
    std::string dispatch="cf.switch "+pc.name+" : i64, [default: ^task_invalid";
    for(size_t i=0;i<ir.code.size();++i)dispatch+=", "+std::to_string(i)+": ^task_"+std::to_string(i);
    dispatch+="]";line(dispatch,function.span);
    blockLabel("task_invalid");call("nex_task_frame_bad_pc",{frame},Type::Unit,function.span);line("llvm.unreachable",function.span);
    std::map<size_t,std::vector<size_t>> sourcePoints;
    if(taskDebug){if(!ir.debug)throw Error("E_TASK_STATE","task debugger metadata missing",function.span);
      for(size_t point=0;point<ir.debug->points.size();++point)sourcePoints[ir.debug->points[point].pc].push_back(point);
    }
    for(size_t i=0;i<ir.code.size();++i){
      const auto &op=ir.code[i];blockLabel("task_"+std::to_string(i));
      if(auto found=sourcePoints.find(i);found!=sourcePoints.end())for(auto point:found->second)
        call("nex_task_debug_checkpoint",{frame,c(point,ir.debug->points[point].span)},Type::Unit,ir.debug->points[point].span);
      auto site=sites.find(op.source);SiteScope taskSite(activeSite,site==sites.end()?pathSites.at("body"):site->second);
      auto next=[&]{line("cf.br ^task_"+std::to_string(i+1),op.span);};
      switch(op.kind){
      case TaskInstruction::Eval:{
        std::vector<Value> leases;scopes.back().clear();
        for(auto id:op.inputs){auto value=read(id,op.span);leases.push_back(value);scopes.back()[taskSlotName(id)]=value;}
        std::function<void(E)> assign=[&](E e){ownedSites[e.get()]=activeSite;for(auto child:e->args)assign(child);};assign(op.atom);
        auto value=expression(op.atom);put(op.output,value,op.span);release(value,op.span);for(auto lease:leases)release(lease,op.span);next();break;
      }
      case TaskInstruction::Copy:{auto value=read(op.inputs[0],op.span);put(op.output,value,op.span);release(value,op.span);next();break;}
      case TaskInstruction::Drop:call("nex_task_frame_drop",{frame,c(op.inputs[0],op.span)},Type::Unit,op.span);next();break;
      case TaskInstruction::Jump:line("cf.br ^task_"+std::to_string(op.yes),op.span);break;
      case TaskInstruction::Branch:{auto value=read(op.inputs[0],op.span);line("cf.cond_br "+value.name+", ^task_"+std::to_string(op.yes)+", ^task_"+std::to_string(op.no),op.span);break;}
      case TaskInstruction::Poll:call("nex_poll",{c(op.span.line,op.span)},Type::Unit,op.span);next();break;
      case TaskInstruction::Pause:{
        static const std::map<std::string,nexrt::TaskRequestKind> requests={
          {"task_yield",nexrt::TaskRequestKind::Yield},{"with_tasks",nexrt::TaskRequestKind::WithTasks},{"task_spawn",nexrt::TaskRequestKind::Spawn},{"task_wait",nexrt::TaskRequestKind::Wait},
          {"channel_new",nexrt::TaskRequestKind::ChannelNew},{"task_send",nexrt::TaskRequestKind::Send},{"task_recv",nexrt::TaskRequestKind::Receive},{"task_close",nexrt::TaskRequestKind::Close},{"task_cancel",nexrt::TaskRequestKind::Cancel},{"current_task_scope",nexrt::TaskRequestKind::CurrentScope},
          {"file_read_text",nexrt::TaskRequestKind::FileReadText},{"file_read_bytes",nexrt::TaskRequestKind::FileReadBytes}};
        auto arguments=call("nex_list_new",{},Type::list(Type::I64),op.span);
        for(auto id:op.inputs){auto value=read(id,op.span);if(value.type.heap())call("nex_list_append_heap",{arguments,value},Type::Unit,op.span);else call("nex_list_append_i64",{arguments,asI64(value,op.span),c(scalarTag(value.type),op.span)},Type::Unit,op.span);release(value,op.span);}
        auto type=op.operation=="channel_new"?*op.atom->type.element:op.atom->type;int64_t kind=type==Type::Unit?4:type.heap()?3:scalarTag(type);
        call("nex_task_frame_pause",{frame,c(int64_t(requests.at(op.operation)),op.span),arguments,c(op.output==noTaskSlot?-1:int64_t(op.output),op.span),c(kind,op.span),c(op.span.line,op.span)},Type::Unit,op.span);
        release(arguments,op.span);call("nex_task_frame_set_pc",{frame,c(i+1,op.span)},Type::Unit,op.span);finish(3,op.span);break;
      }
      case TaskInstruction::Return:{
        if(op.inputs.empty())call("nex_task_frame_return_unit",{frame},Type::Unit,op.span);
        else {auto value=read(op.inputs[0],op.span);if(value.type.heap())call("nex_task_frame_return_heap",{frame,value},Type::Unit,op.span);else call("nex_task_frame_return_i64",{frame,asI64(value,op.span),c(scalarTag(value.type),op.span)},Type::Unit,op.span);release(value,op.span);}
        finish(0,op.span);break;
      }
      case TaskInstruction::Pattern:{
        auto failed=label(),matched=label(),end=label();std::map<std::string,Value> local;
        bool canFail=false;visitPattern(op.pattern,[&](P pat){if(pat->kind==Pattern::Integer||pat->kind==Pattern::Boolean||pat->kind==Pattern::String||pat->kind==Pattern::List||(pat->kind==Pattern::Constructor&&(pat->type.kind==Type::Result||p.structure(pat->type.name).enumeration)))canFail=true;});
        visitPattern(op.pattern,[&](P pat){if(pat->kind!=Pattern::Wildcard){auto slot=patternSlots.at(pat.get());local[slot]={slot,pat->type,true};}});
        for(auto id:op.bindings)call("nex_task_frame_drop",{frame,c(id,op.span)},Type::Unit,op.span);
        pattern(op.pattern,read(op.inputs[0],op.span),failed);line("cf.br ^"+matched,op.span);
        blockLabel(matched);visitPattern(op.pattern,[&](P pat){if(pat->kind==Pattern::Binding){auto value=load({patternSlots.at(pat.get()),pat->type,true},op.span);put(TaskSlotId(pat->binding),value,op.span);release(value,op.span);}});
        put(op.output,constant(1,Type::Bool,op.span),op.span);cleanup(local,op.span);line("cf.br ^"+end,op.span);
        if(canFail){blockLabel(failed);put(op.output,constant(0,Type::Bool,op.span),op.span);cleanup(local,op.span);line("cf.br ^"+end,op.span);}blockLabel(end);next();break;
      }
      case TaskInstruction::Fail:call("nex_match_fail",{c(op.span.line,op.span)},Type::Unit,op.span);line("llvm.unreachable",op.span);break;
      case TaskInstruction::Call:{
        auto arguments=call("nex_list_new",{},Type::list(Type::I64),op.span);
        for(size_t j=op.indirect?1:0;j<op.inputs.size();++j){auto value=read(op.inputs[j],op.span);if(value.type.heap())call("nex_list_append_heap",{arguments,value},Type::Unit,op.span);else call("nex_list_append_i64",{arguments,asI64(value,op.span),c(scalarTag(value.type),op.span)},Type::Unit,op.span);release(value,op.span);}
        Value descriptor=null(Type::Str,op.span),environment=null(Type::Str,op.span);
        if(op.indirect)environment=read(op.inputs[0],op.span);
        else{auto pointer=fresh();line(pointer+" = llvm.mlir.addressof @"+taskCodes.at(op.operation)+" : !llvm.ptr",op.span);descriptor={pointer,Type::Str};}
        call("nex_task_frame_call",{frame,descriptor,environment,arguments,c(op.output==noTaskSlot?-1:int64_t(op.output),op.span),c(op.span.line,op.span)},Type::Unit,op.span);
        release(arguments,op.span);if(op.indirect)release(environment,op.span);
        call("nex_task_frame_set_pc",{frame,c(i+1,op.span)},Type::Unit,op.span);finish(2,op.span);break;
      }
      }
    }
    out<<"  }\n";ownedToken={};
  }
public:
  explicit Emitter(const Program &p,bool optimized=false,bool profiling=false,const OperationIndex *sharedSites=nullptr,bool wasm=false,const NativeEmissionContext *context=nullptr,bool taskDebug=false):p(p),debug(p,optimized),profiling(profiling),wasm(wasm),taskDebug(taskDebug),sites(sharedSites?*sharedSites:ownedSites),context(context){if(!sharedSites)for(const auto &f:p.functions)for(const auto &o:operationTree(p,f))if(o.ast)ownedSites[o.ast]=o.site;}
  std::string run(const std::string &entry,bool testEntry,bool libraryEntry,const std::set<std::string> *selected=nullptr,const std::set<std::string> *closure=nullptr,bool allCallableBridges=false,bool parallelScopes=false,const std::vector<TaskFunctionIR> *tasks=nullptr,const nexrt::TaskExecutionLimits &taskLimits={}){
    const auto &main=nativeEntry(p,entry,testEntry,libraryEntry,wasm);
    const auto computedNames=closure?std::set<std::string>{}:reachable(p,entry);
    const auto &completeNames=closure?*closure:computedNames;
    parallelEnabled=allCallableBridges||parallelScopes||(context&&context->parallel);
    if(!context)for(const auto &fn:p.functions)if(completeNames.contains(fn.name)&&usesParallelMap(fn))parallelEnabled=true;
    out<<"module {\n";runtimeDeclarations=true;
    for(auto name:{"add","sub","mul","div","mod"})declaration("nex_"+std::string(name),"i64, i64, i64","i64");
    for(auto name:{"add","sub","mul","div","mod"})declaration("nex_f64_"+std::string(name),"f64, f64, i64","f64");
    declaration("nex_f64_neg","f64, i64","f64");declaration("nex_f64_validate","f64, i64","f64");declaration("nex_f64_compare","f64, f64, i64, i64","i64");
    declaration("nex_as_f64","i64, i64","f64");declaration("nex_as_i64","f64, i64","!llvm.ptr");declaration("nex_print_f64","f64");
    declaration("nex_neg","i64, i64","i64");declaration("nex_print_i64","i64");declaration("nex_print_bool","i64");declaration("nex_assert","i64, i64");declaration("nex_match_fail","i64");
    declaration("nex_retain","!llvm.ptr","!llvm.ptr");declaration("nex_release","!llvm.ptr");declaration("nex_runtime_finish","");
    declaration("nex_poll","i64");
    if(parallelEnabled){
      declaration("nex_parallel_enter","");declaration("nex_parallel_leave","");
      declaration("nex_parallel_map","!llvm.ptr, !llvm.ptr, i64, !llvm.ptr, i64, i64, i64","!llvm.ptr");
      declaration("nex_parallel_return_i64","!llvm.ptr, i64, i64");declaration("nex_parallel_return_heap","!llvm.ptr, !llvm.ptr");
    }
    declaration("nex_owned_enter","","i64");declaration("nex_owned_leave","i64, !llvm.ptr");
    declaration("nex_application_run","!llvm.ptr, i64, !llvm.ptr","i64");
    if(tasks){
      declaration("nex_task_application_execute_limits","!llvm.ptr, i64, !llvm.ptr, i64, i64, i64","i64");
      if(profiling)declaration("nex_task_profile_prepare","!llvm.ptr, i64");
    }
    if(wasm){declaration("nex_wasm_enter","i64");declaration("nex_wasm_leave","");}
    declaration("nex_foreign_invoke","!llvm.ptr, i64, !llvm.ptr, i64","!llvm.ptr");declaration("nex_foreign_configure","i64, !llvm.ptr");
    if(profiling){declaration("nex_profile_enter","!llvm.ptr, !llvm.ptr, i64, !llvm.ptr");declaration("nex_profile_leave","");}
    declaration("nex_string_new","!llvm.ptr, i64, i64","!llvm.ptr");declaration("nex_list_new","","!llvm.ptr");declaration("nex_record_new","i64","!llvm.ptr");declaration("nex_enum_new","i64, i64","!llvm.ptr");declaration("nex_enum_tag","!llvm.ptr, i64, i64","i64");
    declaration("nex_closure_new","!llvm.ptr, i64","!llvm.ptr");declaration("nex_closure_code","!llvm.ptr","!llvm.ptr");
    declaration("nex_record_name","!llvm.ptr, !llvm.ptr, i64");declaration("nex_record_field_name","!llvm.ptr, i64, !llvm.ptr, i64");
    declaration("nex_list_append_i64","!llvm.ptr, i64, i64");declaration("nex_list_append_heap","!llvm.ptr, !llvm.ptr");
    declaration("nex_record_init_i64","!llvm.ptr, i64, i64, i64");declaration("nex_record_init_heap","!llvm.ptr, i64, !llvm.ptr");
    declaration("nex_collection_get_i64","!llvm.ptr, i64, i64","i64");declaration("nex_collection_get_heap","!llvm.ptr, i64, i64","!llvm.ptr");
    declaration("nex_list_update_i64","!llvm.ptr, i64, i64, i64, i64, i64","!llvm.ptr");declaration("nex_list_update_heap","!llvm.ptr, i64, !llvm.ptr, i64, i64","!llvm.ptr");
    declaration("nex_length","!llvm.ptr","i64");declaration("nex_heap_equal","!llvm.ptr, !llvm.ptr","i64");declaration("nex_heap_concat","!llvm.ptr, !llvm.ptr, i64","!llvm.ptr");
    declaration("nex_string_slice","!llvm.ptr, i64, i64, i64","!llvm.ptr");declaration("nex_string_contains","!llvm.ptr, !llvm.ptr","i64");
    declaration("nex_format_i64","i64, i64","!llvm.ptr");declaration("nex_format_heap","!llvm.ptr","!llvm.ptr");declaration("nex_print_heap","!llvm.ptr");
    declaration("nex_ok_i64","i64, i64","!llvm.ptr");declaration("nex_ok_heap","!llvm.ptr","!llvm.ptr");declaration("nex_err","!llvm.ptr, !llvm.ptr","!llvm.ptr");
    declaration("nex_is_ok","!llvm.ptr","i64");declaration("nex_unwrap_i64","!llvm.ptr, i64","i64");declaration("nex_unwrap_heap","!llvm.ptr, i64","!llvm.ptr");declaration("nex_error_text","!llvm.ptr, i64","!llvm.ptr");
    declaration("nex_encode_json_i64","i64, i64, i64","!llvm.ptr");declaration("nex_encode_json_heap","!llvm.ptr, i64","!llvm.ptr");declaration("nex_decode_json","!llvm.ptr, !llvm.ptr, i64, i64","!llvm.ptr");
    declaration("nex_read_env","!llvm.ptr","!llvm.ptr");declaration("nex_store_get","!llvm.ptr, i64","!llvm.ptr");declaration("nex_store_put","!llvm.ptr, !llvm.ptr, i64","!llvm.ptr");declaration("nex_store_remove","!llvm.ptr, i64","!llvm.ptr");declaration("nex_store_keys","!llvm.ptr, i64","!llvm.ptr");
    declaration("nex_file_read_text","!llvm.ptr, i64","!llvm.ptr");declaration("nex_file_write_text","!llvm.ptr, !llvm.ptr, i64","!llvm.ptr");
    declaration("nex_file_read_bytes","!llvm.ptr, i64","!llvm.ptr");declaration("nex_file_write_bytes","!llvm.ptr, !llvm.ptr, i64","!llvm.ptr");
    for(auto name:{"file_open_read","file_open_write","file_open_append","file_size","file_flush"})declaration("nex_"+std::string(name),"!llvm.ptr, i64","!llvm.ptr");
    for(auto name:{"file_read","file_seek"})declaration("nex_"+std::string(name),"!llvm.ptr, i64, i64","!llvm.ptr");
    declaration("nex_file_write","!llvm.ptr, !llvm.ptr, i64","!llvm.ptr");
    for(auto name:{"file_close","file_is_open"})declaration("nex_"+std::string(name),"!llvm.ptr, i64","i64");
    for(auto name:{"bytes_from_integers","utf8_bytes","decode_utf8","encode_base64","decode_base64"})declaration("nex_"+std::string(name),"!llvm.ptr, i64","!llvm.ptr");
    runtimeDeclarations=false;
    if(tasks){
      taskDeclarations();
      if(profiling)taskProfileMetadata(*tasks);
      const bool imageFileReads=std::any_of(tasks->begin(),tasks->end(),[](const auto &ir){return std::any_of(ir.code.begin(),ir.code.end(),[](const auto &op){return op.kind==TaskInstruction::Pause&&taskFileReadOperation(op.operation);});});
      for(const auto &ir:*tasks){
        std::vector<int64_t> kinds,parameters(ir.parameters.begin(),ir.parameters.end()),captures(ir.captures.begin(),ir.captures.end());
        for(const auto &slot:ir.slots)kinds.push_back(slot.type.heap()?3:scalarTag(slot.type));
        const auto &source=p.function(ir.name);int64_t requirements=0;
        if(source.effects.contains("task"))requirements|=nexrt::taskCodeDeclaredTask;
        if(source.realm=="server")requirements|=nexrt::taskCodeServer;
        if(source.effects.contains("fs"))requirements|=nexrt::taskCodeDeclaredFs;
        if(supportsTaskFileReads(p)&&(requirements&7)==7)requirements|=nexrt::taskCodeFileRead;
        if(imageFileReads)requirements|=nexrt::taskCodeImageFileRead;
        taskCodes[ir.name]=structureGlobal("nex_task_code_",{nativeSymbol(ir.name)+"__task_step",taskArray(kinds),taskArray(parameters),taskArray(captures),profiling?taskProfileSites.at(ir.name):""},
          {nexrt::taskCodeABI,int64_t(kinds.size()),int64_t(parameters.size()),int64_t(captures.size()),ir.result==Type::Unit?4:ir.result.heap()?3:scalarTag(ir.result),requirements});
      }
      if(taskDebug)taskDebugMetadata(*tasks);
    }
    const auto &names=selected?*selected:completeNames;
    auto ownedBridges=context?std::set<std::string>{}:nativeFunctionBridges(p,completeNames);
    if(!context&&allCallableBridges)for(const auto &name:completeNames)if(!p.function(name).closure)ownedBridges.insert(name);
    const auto &bridges=context?context->bridges:ownedBridges;
    if(selected){
      std::set<std::string> external;
      for(const auto &name:names)for(const auto &callee:p.function(name).dependencies)if(!names.contains(callee))external.insert(callee);
      for(const auto &name:external){
        const auto &f=p.function(name);std::string args;
        if(f.closure)args="!llvm.ptr";for(const auto &param:f.params){if(!args.empty())args+=", ";args+=ty(param.type);}
        declaration(nativeSymbol(f.name),args,f.result==Type::Unit?"":ty(f.result));
        if(!f.closure&&bridges.contains(f.name))declaration(closureSymbol(f),"!llvm.ptr"+(args.empty()?"":", "+args),f.result==Type::Unit?"":ty(f.result));
      }
    }
    for(const auto &f:p.functions)if(names.contains(f.name)){
      selectFunction(f);debug.scope=debug.function(f);
      scopes.clear();scopes.emplace_back();slots.clear();matchSlots.clear();patternSlots.clear();shortSlots.clear();out<<"  func.func @"<<nativeSymbol(f.name)<<"(";
      std::string environment;if(f.closure){environment=fresh();out<<environment<<": !llvm.ptr";}
      for(size_t i=0;i<f.params.size();++i){if(i||f.closure)out<<", ";auto n=fresh();out<<n<<": "<<ty(f.params[i].type);scopes.back()[f.params[i].name]={n,f.params[i].type};}
      out<<")";if(f.result!=Type::Unit)out<<" -> "<<ty(f.result);out<<" {\n";
      ownedToken={};prologue=true;
      if(propagatesResult(f))ownedToken=call("nex_owned_enter",{},Type::I64,f.span);
      for(size_t i=0;i<f.params.size();++i){
        const auto &param=f.params[i];SiteScope parameterSite(activeSite,pathSites.at("parameter/"+std::to_string(i)));auto slot=allocateSlot(param.type,param.span);
        if(param.type==Type::F64)scopes.back()[param.name]=call("nex_f64_validate",{scopes.back().at(param.name),constant(param.span.line,Type::I64,param.span)},Type::F64,param.span);
        // Debug storage borrows the parameter and never participates in cleanup.
        writeSlot(scopes.back().at(param.name),slot,param.span);describeStorage(param.name,param.type,param.span,slot,i+1+(f.closure?1:0));
      }
      for(size_t i=0;i<f.captures.size();++i){const auto &capture=f.captures[i];SiteScope captureSite(activeSite,pathSites.at("capture/"+std::to_string(i)));auto slot=allocateSlot(capture.type,capture.span);auto value=call(capture.type.heap()?"nex_collection_get_heap":"nex_collection_get_i64",{{environment,Type::Str},constant(i,Type::I64,capture.span),constant(capture.span.line,Type::I64,capture.span)},capture.type.heap()?capture.type:Type(Type::I64),capture.span);value=fromScalar(value,capture.type,capture.span);writeSlot(value,slot,capture.span);describeStorage(capture.name,capture.type,capture.span,slot);scopes.back()[capture.name]={slot,capture.type,true};}
      allocate(f.body);prologue=false;
      if(parallelEnabled)call("nex_parallel_enter",{},Type::Unit,f.span);
      if(wasm)call("nex_wasm_enter",{constant(f.span.line,Type::I64,f.span)},Type::Unit,f.span);
      if(profiling){auto name=rawBytes(f.name,f.span),file=rawBytes(p.location(f.span),f.span),content=rawBytes(hash(json(canonical(f),false)),f.span);call("nex_profile_enter",{name,file,constant(f.span.line,Type::I64,f.span),content},Type::Unit,f.span);}
      call("nex_poll",{constant(f.span.line,Type::I64,f.span)},Type::Unit,f.span);
      if(f.foreign){
        auto packed=call("nex_list_new",{},Type::list(Type::I64),f.span);
        for(const auto &parameter:f.params){auto value=scopes.back().at(parameter.name);if(value.type.heap())call("nex_list_append_heap",{packed,value},Type::Unit,parameter.span);else call("nex_list_append_i64",{packed,asI64(value,parameter.span),constant(scalarTag(value.type),Type::I64,parameter.span)},Type::Unit,parameter.span);}
        auto description=json(foreignBinding(p,f),false);auto resultBox=call("nex_foreign_invoke",{rawBytes(description,f.span),constant(description.size(),Type::I64,f.span),packed,constant(f.span.line,Type::I64,f.span)},Type::list(Type::I64),f.span);release(packed,f.span);Value value;
        if(f.result!=Type::Unit){value=call(f.result.heap()?"nex_collection_get_heap":"nex_collection_get_i64",{resultBox,constant(0,Type::I64,f.span),constant(f.span.line,Type::I64,f.span)},f.result.heap()?f.result:Type(Type::I64),f.span);value=fromScalar(value,f.result,f.span);}
        release(resultBox,f.span);if(profiling)call("nex_profile_leave",{},Type::Unit,f.span);if(parallelEnabled)call("nex_parallel_leave",{},Type::Unit,f.span);line(f.result==Type::Unit?"func.return":"func.return "+value.name+" : "+ty(f.result),f.span);
      }else if(!statements(f.body,false)){if(profiling)call("nex_profile_leave",{},Type::Unit,f.span);if(wasm)call("nex_wasm_leave",{},Type::Unit,f.span);if(parallelEnabled)call("nex_parallel_leave",{},Type::Unit,f.span);line("func.return",f.span);}out<<"  }"<<loc(f.span)<<"\n";
      if(!f.closure&&bridges.contains(f.name)){debug.scope.clear();out<<"  func.func @"<<closureSymbol(f)<<"(%closure_environment: !llvm.ptr";std::vector<Value> args;for(const auto &param:f.params){auto name=fresh();out<<", "<<name<<": "<<ty(param.type);args.push_back({name,param.type});}out<<")"<<(f.result==Type::Unit?"":" -> "+ty(f.result))<<" {\n";auto value=call(nativeSymbol(f.name),args,f.result,f.span);line(value.type==Type::Unit?"func.return":"func.return "+value.name+" : "+ty(value.type),f.span);out<<"  }\n";}
    }
    if(tasks){
      for(const auto &ir:*tasks)taskStep(ir);
      selectFunction(main);debug.scope.clear();auto pointer=fresh();
      out<<"  func.func @"<<nativeSymbol(main.name)<<"__task_code_address() -> !llvm.ptr {\n";
      line(pointer+" = llvm.mlir.addressof @"+taskCodes.at(main.name)+" : !llvm.ptr",main.span);line("func.return "+pointer+" : !llvm.ptr",main.span);out<<"  }\n";
    }
    for(const auto &[name,thunk]:parallelThunks){
      selectFunction(*thunk.owner);debug.scope.clear();auto e=thunk.expression;SiteScope site(activeSite,sites.at(e.get()));
      out<<"  func.func private @"<<name<<"(%parallel_environment: !llvm.ptr, %parallel_scalar: i64, %parallel_heap: !llvm.ptr, %parallel_result: !llvm.ptr) {\n";
      auto input=*e->args[0]->type.element,output=*e->type.element;
      Value argument=input.heap()?Value{"%parallel_heap",input}:fromScalar({"%parallel_scalar",Type::I64},input,e->span);
      auto pointer=call("nex_closure_code",{{"%parallel_environment",Type::Str}},Type::Str,e->span);auto result=fresh();
      line(result+" = llvm.call "+pointer.name+"(%parallel_environment, "+argument.name+") : !llvm.ptr, (!llvm.ptr, "+ty(input)+") -> "+ty(output),e->span);
      if(output.heap()){
        call("nex_parallel_return_heap",{{"%parallel_result",Type::Str},{result,output}},Type::Unit,e->span);release({result,output},e->span);
      }else call("nex_parallel_return_i64",{{"%parallel_result",Type::Str},asI64({result,output},e->span),constant(scalarTag(output),Type::I64,e->span)},Type::Unit,e->span);
      line("func.return",e->span);out<<"  }\n";
    }
    debug.scope.clear();if(libraryEntry||(!tasks&&!names.contains(main.name))){out<<globals.str()<<"}\n";return debug.str()+out.str();}
    selectFunction(main);
    auto all=reachable(p,entry);bool foreign=false;for(const auto &name:all)foreign|=p.function(name).foreign.has_value();
    // C++ owns the application boundary so a runtime failure can unwind host
    // temporaries and release every live managed handle, including caller scopes.
    out<<"  func.func private @nex_application_entry(%nex_argc64: i64, %nex_argv: !llvm.ptr) -> i64 {\n";
    if(tasks&&profiling){
      auto registry=fresh();line(registry+" = llvm.mlir.addressof @"+taskProfileTable+" : !llvm.ptr",main.span);
      call("nex_task_profile_prepare",{{registry,Type::Str},constant(tasks->size(),Type::I64,main.span)},Type::Unit,main.span);
    }
    if(tasks&&taskDebug){
      auto registry=fresh();line(registry+" = llvm.mlir.addressof @"+taskDebugTable+" : !llvm.ptr",main.span);
      call("nex_task_debug_prepare",{{registry,Type::Str},constant(tasks->size(),Type::I64,main.span)},Type::Unit,main.span);
    }
    if(foreign)call("nex_foreign_configure",{{"%nex_argc64",Type::I64},{"%nex_argv",Type::Str}},Type::Unit,main.span);
    Value value;
    if(tasks){
      auto descriptor=fresh();line(descriptor+" = llvm.mlir.addressof @"+taskCodes.at(main.name)+" : !llvm.ptr",main.span);
      auto steps=constant(taskLimits.steps,Type::I64,main.span),timeout=constant(taskLimits.timeoutMs,Type::I64,main.span),workers=constant(taskLimits.workers,Type::I64,main.span);
      value=call("nex_task_application_execute_limits",{{descriptor,Type::Str},{"%nex_argc64",Type::I64},{"%nex_argv",Type::Str},steps,timeout,workers},Type::I64,main.span);
    }else{
      value=call(nativeSymbol(main.name),{},main.result,main.span);
      if(main.result==Type::Unit)value=constant(0,Type::I64,main.span);
    }
    line("func.return "+value.name+" : i64",main.span);
    out<<"  }\n  func.func @main(%nex_argc: i32, %nex_argv: !llvm.ptr) -> i32 {\n";
    line("%nex_argc64 = arith.extsi %nex_argc : i32 to i64",main.span);
    auto function=fresh(),pointer=fresh();
    line(function+" = func.constant @nex_application_entry : (i64, !llvm.ptr) -> i64",main.span);
    line(pointer+" = builtin.unrealized_conversion_cast "+function+" : (i64, !llvm.ptr) -> i64 to !llvm.ptr",main.span);
    auto status=call("nex_application_run",{{pointer,Type::Str},{"%nex_argc64",Type::I64},{"%nex_argv",Type::Str}},Type::I64,main.span);
    auto process=fresh();line(process+" = arith.trunci "+status.name+" : i64 to i32",main.span);line("func.return "+process+" : i32",main.span);
    out<<"  }"<<loc(main.span)<<"\n"<<globals.str()<<"}\n";return debug.str()+out.str();
  }
};
std::string lower(const std::string &source,const std::string &sourcePath,const std::string &triple,const std::string &layout) {
  mlir::DialectRegistry registry;
  registry.insert<mlir::arith::ArithDialect,mlir::cf::ControlFlowDialect,mlir::func::FuncDialect,mlir::memref::MemRefDialect,mlir::LLVM::LLVMDialect>();
  mlir::registerBuiltinDialectTranslation(registry);mlir::registerLLVMDialectTranslation(registry);
  mlir::MLIRContext context(registry);
  auto module=mlir::parseSourceString<mlir::ModuleOp>(source,&context);
  if(!module)throw Error("E_MLIR","generated MLIR could not be parsed");
  module->getOperation()->setLoc(mlir::FileLineColLoc::get(&context,sourcePath,1,1));
  if(mlir::failed(mlir::verify(*module)))throw Error("E_MLIR","generated MLIR failed verification");
  mlir::registerConversionPasses();
  mlir::PassManager pm(&context);
  if(mlir::failed(mlir::parsePassPipeline("convert-arith-to-llvm,convert-func-to-llvm,finalize-memref-to-llvm,convert-cf-to-llvm,reconcile-unrealized-casts",pm)))throw Error("E_MLIR","cannot construct conversion pipeline");
  pm.addPass(mlir::LLVM::createDIScopeForLLVMFuncOpPass({mlir::LLVM::DIEmissionKind::Full}));
  if(mlir::failed(pm.run(*module)))throw Error("E_MLIR","MLIR to LLVM conversion failed");
  llvm::LLVMContext llvmContext;auto llvmModule=mlir::translateModuleToLLVMIR(*module,llvmContext,"NEX");
  if(!llvmModule)throw Error("E_LLVM","LLVM translation failed");
  if(llvm::verifyModule(*llvmModule,&llvm::errs()))throw Error("E_LLVM","translated LLVM IR failed verification");
  llvmModule->setSourceFileName(sourcePath);
  llvmModule->setTargetTriple(llvm::Triple(triple));llvmModule->setDataLayout(layout);
  for(auto &function:*llvmModule)if(!function.isDeclaration())function.setUWTableKind(llvm::UWTableKind::Default);
  std::string text;llvm::raw_string_ostream stream(text);llvmModule->print(stream,nullptr);return text;
}
void atomicWrite(const std::filesystem::path &path,const std::string &text){
  std::filesystem::create_directories(path.parent_path());
  auto temporary=path;temporary+=".tmp-"+std::to_string(std::random_device{}())+"-"+std::to_string(std::random_device{}());int fd=-1;
  if(auto ec=llvm::sys::fs::openFileForWrite(temporary.string(),fd,llvm::sys::fs::CD_CreateNew))throw Error("E_FILE",ec.message());
  try{
    {llvm::raw_fd_ostream output(fd,true);output<<text;output.close();if(output.has_error())throw Error("E_FILE","cannot write "+path.string());}
    std::filesystem::rename(temporary,path);
  }catch(...){std::filesystem::remove(temporary);throw;}
}
void captureFile(const std::filesystem::path &path,const std::string &text){
  if(!std::filesystem::is_regular_file(path)||readFile(path.string())!=text)atomicWrite(path,text);
}
bool digest(const std::string &value){return value.size()==64&&value.find_first_not_of("0123456789abcdef")==std::string::npos;}
struct NativeArtifact {std::string mlir,llvm,object,id;bool reused=false;};
std::string artifactID(const std::string &key,const NativeArtifact &artifact){return hash(key+hash(artifact.mlir)+hash(artifact.llvm)+hash(artifact.object));}
bool loadArtifact(const std::filesystem::path &root,const std::string &key,NativeArtifact &artifact){
  try{
    auto index=root/"native-cache"/(key+".json");
    if(!std::filesystem::is_regular_file(index)||std::filesystem::file_size(index)>65536)return false;
    auto value=llvm::json::parse(readFile(index.string()));
    if(!value){llvm::consumeError(value.takeError());return false;}
    auto record=value->getAsObject();
    if(!record||record->getString("schema")!="nex.native-object/1"||record->getString("input_key")!=key)return false;
    auto id=record->getString("artifact_key");if(!id||!digest(id->str()))return false;
    auto folder=root/"native-objects"/id->str();
    NativeArtifact candidate{readFile((folder/"program.mlir").string()),readFile((folder/"program.ll").string()),readFile((folder/"program.o").string()),id->str(),true};
    if(artifactID(key,candidate)!=candidate.id)return false;
    artifact=std::move(candidate);return true;
  }catch(const std::exception &){return false;}
}
void saveArtifact(const std::filesystem::path &root,const std::string &key,NativeArtifact &artifact){
  artifact.id=artifactID(key,artifact);auto folder=root/"native-objects"/artifact.id;
  captureFile(folder/"program.mlir",artifact.mlir);captureFile(folder/"program.ll",artifact.llvm);captureFile(folder/"program.o",artifact.object);
  // Publish the single index last. Concurrent writers may choose different
  // content objects for the same inputs; readers validate an entire snapshot.
  atomicWrite(root/"native-cache"/(key+".json"),json(llvm::json::Object{{"schema","nex.native-object/1"},{"input_key",key},{"artifact_key",artifact.id}})+"\n");
}
std::string linkIR(const std::vector<NativeArtifact> &artifacts,const std::string &source){
  llvm::LLVMContext context;std::unique_ptr<llvm::Module> combined;
  for(const auto &artifact:artifacts){
    llvm::SMDiagnostic diagnostic;auto buffer=llvm::MemoryBuffer::getMemBufferCopy(artifact.llvm,"NEX native unit");
    auto part=llvm::parseIR(buffer->getMemBufferRef(),diagnostic,context);
    if(!part){diagnostic.print("nex",llvm::errs());throw Error("E_LLVM","cannot read native unit IR");}
    if(!combined)combined=std::move(part);
    else if(llvm::Linker::linkModules(*combined,std::move(part)))throw Error("E_LLVM","cannot link native unit IR");
  }
  if(!combined||llvm::verifyModule(*combined,&llvm::errs()))throw Error("E_LLVM","combined native IR failed verification");
  combined->setSourceFileName(source);std::string text;llvm::raw_string_ostream stream(text);combined->print(stream,nullptr);return text;
}
}
int execute(const std::vector<std::string> &args) {
  if(args.empty())throw Error("E_PROCESS","empty command");
  auto program=llvm::sys::findProgramByName(args[0]);if(!program)throw Error("E_TOOL","cannot find executable "+args[0]);
  std::vector<llvm::StringRef> refs;for(const auto &a:args)refs.push_back(a);
  std::string error;bool failed=false;
  int status=llvm::sys::ExecuteAndWait(*program,refs,std::nullopt,{},0,0,&error,&failed);
  if(failed||status<0)throw Error("E_PROCESS",error.empty()?"process failed":error);return status;
}
int executeNativeBuildTool(const std::vector<std::string> &arguments){
  if(arguments.empty())throw Error("E_PROCESS","empty native build command");
  std::vector<llvm::StringRef> refs;size_t bytes=0;
  for(const auto &argument:arguments){
    if(argument.find('\0')!=std::string::npos)throw Error("E_PROCESS","native build argument contains NUL");
    refs.push_back(argument);bytes+=argument.size()+1;
  }
  auto command=arguments;std::filesystem::path response;
  if(bytes>65536||!llvm::sys::commandLineFitsWithinSystemLimits(arguments[0],refs)){
    response=std::filesystem::path(createTemporaryDirectory("nex-native-response"))/"arguments.rsp";
    std::filesystem::permissions(response.parent_path(),std::filesystem::perms::owner_all);
    std::string text;
    for(size_t i=1;i<arguments.size();++i){
      text+='"';
      for(char c:arguments[i]){if(c=='\\'||c=='"')text+='\\';text+=c;}
      text+="\"\n";
    }
    writeFile(response.string(),text);
    std::filesystem::permissions(response,std::filesystem::perms::owner_read|std::filesystem::perms::owner_write);
    command={arguments[0],"@"+response.string()};
  }
  // LLVM tools create their own temporary files too (notably dsymutil).
  // Scope the workaround to build tools; application environments stay intact.
  auto base=std::filesystem::canonical(std::filesystem::temp_directory_path());
  if(base.string().find('%')!=std::string::npos){
    std::vector<std::string> scoped{"/usr/bin/env","TMPDIR=/tmp","TMP=/tmp","TEMP=/tmp","TEMPDIR=/tmp"};
    scoped.insert(scoped.end(),command.begin(),command.end());command=std::move(scoped);
  }
  try{
    auto status=execute(command);
    if(!response.empty()){
      if(status!=0)throw Error("E_LINK","native build tool exited "+std::to_string(status)+"; response file retained at "+response.string());
      std::error_code ignored;std::filesystem::remove_all(response.parent_path(),ignored);
    }
    return status;
  }catch(const Error &error){
    if(response.empty()||error.code=="E_LINK")throw;
    throw Error(error.code,std::string(error.what())+"; response file retained at "+response.string(),error.span);
  }
}
std::string createTemporaryDirectory(const std::string &prefix,const std::string &directory){
  namespace fs=std::filesystem;
  auto base=fs::canonical(directory.empty()?fs::temp_directory_path():fs::path(directory));
  // LLVM expands '%' throughout temporary filename models, including parents.
  // Its object/archive writers also need a physical staging path without '%'.
  if(base.string().find('%')!=std::string::npos)base=fs::canonical("/tmp");
  llvm::SmallString<128> temporary;
  if(auto error=llvm::sys::fs::createUniqueDirectory((base/prefix).string(),temporary))throw Error("E_FILE",error.message());
  return temporary.str().str();
}
ProcessResult capture(const std::vector<std::string> &args,unsigned timeoutSeconds) {
  if(args.empty())throw Error("E_PROCESS","empty command");
  auto program=llvm::sys::findProgramByName(args[0]);if(!program)throw Error("E_TOOL","cannot find executable "+args[0]);
  std::filesystem::path folder(createTemporaryDirectory("nex-process"));
  try {
    auto stdoutPath=(folder/"stdout").string(),stderrPath=(folder/"stderr").string();
    std::vector<llvm::StringRef> refs;for(const auto &a:args)refs.push_back(a);
    std::optional<llvm::StringRef> redirects[]={llvm::StringRef(""),llvm::StringRef(stdoutPath),llvm::StringRef(stderrPath)};
    std::string error;bool failed=false;
    int status=llvm::sys::ExecuteAndWait(*program,refs,std::nullopt,redirects,timeoutSeconds,0,&error,&failed);
    if(failed||status<0)throw Error("E_PROCESS",error.empty()?"child process failed or timed out":error);
    ProcessResult result{status,readFile(stdoutPath),readFile(stderrPath)};std::filesystem::remove_all(folder);return result;
  }catch(...){std::filesystem::remove_all(folder);throw;}
}
namespace {
TaskNativeStep emitTaskNative(const Program &p,const std::string &entry,bool application,bool optimized=false,const nexrt::TaskExecutionLimits &taskLimits={},bool profiling=false,bool taskDebug=false){
  if(!p.taskPrototype)throw Error("E_TASK_STATE","native task steps require the private checked task frontend");
  const auto &function=p.function(entry);auto ir=lowerTaskFunction(p,function);
  if(!function.captures.empty()||function.realm=="client")throw Error("E_TASK_UNIMPLEMENTED","compiled task step entry cannot have captures or client realm",function.span);
  auto complete=reachable(p,entry),pure=complete;std::vector<TaskFunctionIR> tasks;
  for(const auto &name:complete){
    const auto &f=p.function(name);
    validateNativeTaskFunction(p,f);
    auto body=lowerTaskFunction(p,f,true,taskDebug);
    for(const auto &slot:body.slots)if(containsFile(p,slot.type))throw Error("E_TASK_UNIMPLEMENTED","compiled task step has no file authority bridge",slot.span);
    if(f.effects.contains("task"))pure.erase(name);
    tasks.push_back(std::move(body));
  }
  TaskNativeStep result;result.symbol=nativeSymbol(function.name)+"__task_step";result.descriptorSymbol=nativeSymbol(function.name)+"__task_code_address";result.parameters=ir.parameters;
  for(const auto &slot:ir.slots)result.slotKinds.push_back(slot.type.heap()?3:scalarTag(slot.type));
  result.mlir=Emitter(p,optimized,profiling,nullptr,false,nullptr,taskDebug).run(entry,function.test,!application,&pure,&complete,false,true,&tasks,taskLimits);return result;
}
}
TaskNativeStep emitTaskNativeStep(const Program &p,const std::string &entry){return emitTaskNative(p,entry,false);}
std::string emitMLIR(const Program &p,const std::string &entry,bool testEntry,bool libraryEntry){
  rejectUnloweredTasks(p,"MLIR emission");
  BuildOptions options;options.entry=entry;options.testEntry=testEntry;options.libraryEntry=libraryEntry;validateNativeBuildEntry(p,options);
  if(usesNativeTasks(p,entry)){
    return emitTaskNative(p,entry,true).mlir;
  }
  return Emitter(p).run(entry,testEntry,libraryEntry);
}
std::string emitWasmMLIR(const Program &p,const std::string &entry,bool optimized){
  rejectUnloweredTasks(p,"Wasm emission");
  if(usesNativeTasks(p,entry))throw Error("E_TASK_TARGET","task continuations require the standalone macOS/Linux native target",p.function(entry).span);
  return Emitter(p,optimized,false,nullptr,true).run(entry,false,true);
}
std::string lowerMLIRToLLVM(const std::string &source,const std::string &path,const std::string &triple,const std::string &layout){return lower(source,path,triple,layout);}
void validateNativeBuildEntry(const Program &p,const BuildOptions &options) {
  rejectUnloweredTasks(p,"native entry preparation");
  bool server=options.target=="server";
  bool tasks=usesNativeTasks(p,options.entry);
  for(const auto &entry:options.libraryExports)tasks|=usesNativeTasks(p,entry);
  if(options.taskDebug&&(!tasks||options.profile!="debug"))
    throw Error("E_OPTION","logical task debugging requires a task debug-profile application",p.function(options.entry).span);
  if(!nexrt::validTaskExecutionLimits(options.taskLimits))throw Error("E_OPTION","invalid task execution limits");
  if(!tasks&&(options.taskLimitsSpecified||options.taskLimits!=nexrt::TaskExecutionLimits{}))
    throw Error("E_OPTION","task execution limits require a reachable task effect",p.function(options.entry).span);
  // projectLibraryABI is also source-only application metadata. A real image
  // boundary comes from library exports/staging or linked provider archives.
  if(isPublicTaskLanguage(p)&&(options.libraryEntry||options.codeOnlyLibrary||options.deferredLink||options.functionsOnly||!options.libraries.empty()||!options.libraryExports.empty())){
    auto entries=options.libraryExports;entries.push_back(options.entry);
    for(const auto &entry:entries){
      const auto &function=p.function(entry);
      if(unsupportedTaskBoundaryType(p,function.result)||std::any_of(function.params.begin(),function.params.end(),[&](const auto &parameter){return unsupportedTaskBoundaryType(p,parameter.type);})||std::any_of(function.captures.begin(),function.captures.end(),[&](const auto &capture){return unsupportedTaskBoundaryType(p,capture.type);}))
        throw Error("E_TASK_PROVIDER","native binary entry signatures cannot carry task authority or task-effect callables; provider ABI/lifetime remains pending",function.span);
    }
  }
  if(tasks){
    if(server)throw Error("E_TASK_TARGET","task HTTP request integration remains pending; use a standalone native application",p.function(options.entry).span);
    if(options.libraryEntry||options.codeOnlyLibrary||options.deferredLink||options.functionsOnly||!options.libraries.empty()||!options.libraryExports.empty())
      throw Error("E_TASK_PROVIDER","task descriptors require one standalone image; native libraries, project providers and deferred linking remain pending",p.function(options.entry).span);
    for(const auto &name:reachable(p,options.entry)){
      const auto &function=p.function(name);
      validateNativeTaskFunction(p,function);
    }
  }
  if(options.deferredLink&&(!options.positionIndependent||!options.projectLibraryABI))
    throw Error("E_OPTION","deferred native linking requires PIC and the checked project ABI");
  if(options.functionsOnly&&(!options.deferredLink||options.libraryEntry))
    throw Error("E_OPTION","function-only staging requires a deferred executable");
  if(server){
    const auto &handler=p.function(options.entry);
    if(handler.realm!="server"||handler.test||handler.params.size()!=1||handler.params[0].type!=Type::record("std::http::Request")||handler.result!=Type::record("std::http::Response"))throw Error("E_HTTP_SIGNATURE","server entry must be server fn handle(std::http::Request) -> std::http::Response",handler.span);
    auto layout=[&](const std::string &name,const std::vector<std::pair<std::string,Type>> &fields){
      const auto &record=p.structure(name);bool valid=record.fields.size()==fields.size();if(valid)for(size_t i=0;i<fields.size();++i)if(record.fields[i].name!=fields[i].first||record.fields[i].type!=fields[i].second)valid=false;
      if(!valid)throw Error("E_HTTP_SIGNATURE","incompatible HTTP library type "+name,record.span);
    };
    layout("std::http::Request",{{"method",Type::Str},{"path",Type::Str},{"query",Type::Str},{"body",Type::Str},{"user",Type::Str},{"request_id",Type::Str}});
    layout("std::http::Response",{{"status",Type::I64},{"body",Type::Str},{"content_type",Type::Str}});
    if(options.libraryEntry)throw Error("E_OPTION","HTTP server target produces an executable; --library is for a native function archive");
  }
  // Entry validation is independent of emission, including warm cache hits.
  nativeEntry(p,options.entry,options.testEntry,options.libraryEntry||server);
  for(const auto &entry:options.libraryExports)nativeEntry(p,entry,false,true);
  if((options.codeOnlyLibrary&&!options.libraryEntry)||(!options.libraryExports.empty()&&!options.libraryEntry))
    throw Error("E_OPTION","additional library exports and code-only output require a native library");
}
std::vector<std::string> nativeCompletionInputs(const llvm::json::Object &metadata){
  auto schema=metadata.get("completion_schema"),inputs=metadata.get("completion_inputs");
  if(!schema&&!inputs)return {};
  auto values=inputs?inputs->getAsArray():nullptr;
  if(schema&&schema->getAsString()=="nex.native-completion/3"){
    auto invalid=[](){throw Error("E_CORE_BUILD","invalid native image completion input path/kind/order");};
    if(!values||values->size()<4||values->size()>1024)invalid();
    std::vector<std::string> result;size_t next=0;
    auto take=[&](const std::string &kind,const std::string &path){
      const auto *o=(*values)[next++].getAsObject();
      if(!o||o->size()!=2||o->getString("kind")!=kind||o->getString("path")!=path)invalid();
      result.push_back(path);
    };
    take("abi","library-abi.json");take("link_inputs","image-inputs.json");take("objects","objects.a");
    auto kind=[&](){auto *o=(*values)[next].getAsObject();return o?o->getString("kind").value_or(""):llvm::StringRef();};
    size_t archives=0;
    while(next<values->size()&&kind()=="static_library"){
      if(archives>=128)invalid();take("static_library","libraries/"+std::to_string(archives++)+".a");
    }
    static const std::regex image("images/(libnex_[A-Za-z_][A-Za-z_0-9]{0,63}_[0-9a-f]{64}\\.(so|dylib))");
    std::set<std::string> images;std::string previous;
    while(next<values->size()&&kind()=="owned_image"){
      auto path=(*values)[next].getAsObject()->getString("path");
      if(!path||!std::regex_match(path->str(),image)||path->str()<=previous||images.size()>=129)invalid();
      previous=path->str();images.insert(previous);take("owned_image",previous);
    }
    if(images.empty())invalid();previous.clear();
    while(next<values->size()){
      auto *o=(*values)[next].getAsObject();auto path=o?o->getString("path"):std::nullopt;
      if(!path||path->str()<=previous)invalid();previous=path->str();bool allowed=false;
      for(const auto &owned:images){
        if(!owned.ends_with(".dylib"))continue;
        auto prefix=owned+".dSYM/Contents/",basename=std::filesystem::path(owned).filename().string();
        allowed|=previous==prefix+"Info.plist"||previous==prefix+"Resources/DWARF/"+basename;
        auto relocation=prefix+"Resources/Relocations/";
        if(previous.starts_with(relocation)){
          auto tail=previous.substr(relocation.size());auto slash=tail.find('/');
          allowed|=slash!=std::string::npos&&slash>0&&tail.substr(slash+1)==basename+".yml"&&
            std::all_of(tail.begin(),tail.begin()+slash,[](char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_';});
        }
      }
      if(!allowed)invalid();take("owned_symbols",previous);
    }
    return result;
  }
  if(!schema||schema->getAsString()!="nex.native-completion/2"||!values||values->empty()||values->size()>129)
    throw Error("E_CORE_BUILD","invalid native completion input schema/limit");
  std::vector<std::string> result;
  for(size_t i=0;i<values->size();++i){
    auto expected=i?"libraries/"+std::to_string(i-1)+".a":"library-abi.json";
    if((*values)[i].getAsString()!=expected)throw Error("E_CORE_BUILD","invalid native completion input path/order");
    result.push_back(std::move(expected));
  }
  return result;
}
BuildResult build(const Program &p,const std::string &directory,const BuildOptions &options) {
  rejectUnloweredTasks(p,"native build");
  if(options.profile!="debug"&&options.profile!="profile"&&options.profile!="release")throw Error("E_OPTION","profile must be debug, profile or release");
  auto host=llvm::sys::getDefaultTargetTriple();
  auto toolchain=configureNative(options);auto target=toolchain.target;
  auto toolchainFingerprint=options.projectLibraryABI||options.deferredLink?inspectNativeToolchain(options).hash:std::string();
  auto verifyToolchain=[&](){if(!toolchainFingerprint.empty()&&inspectNativeToolchain(options).hash!=toolchainFingerprint)
    throw Error("E_PROJECT_INPUT_CHANGED","native toolchain changed while building checked project component");};
  bool server=options.target=="server";
  validateNativeBuildEntry(p,options);
  llvm::Triple configuredABI(toolchain.target);
  bool windows=configuredABI.isWindowsGNUEnvironment();
  const bool tasks=usesNativeTasks(p,options.entry);
  if(tasks&&!configuredABI.isMacOSX()&&!configuredABI.isOSLinux())throw Error("E_TASK_TARGET","compiled task applications currently require macOS or Linux; other task targets remain pending",p.function(options.entry).span);
  const bool objectArchive=options.libraryEntry||options.deferredLink;
  if(options.deferredLink&&!configuredABI.isMacOSX()&&!configuredABI.isOSLinux())
    throw Error("E_TARGET","deferred image staging currently supports macOS and Linux targets");
  if(windows&&(server||options.profile=="profile"))throw Error("E_TARGET","Windows core supports debug/release executables and archives; HTTP servers and profiling remain pending");
  if(configuredABI.getOS()==llvm::Triple::IOS&&(!options.libraryEntry||options.profile=="profile"))
    throw Error("E_TARGET","iOS currently supports --library with debug/release; application packaging and device/simulator execution remain pending");
  auto compiler=toolchain.compiler;
  auto command=[&](std::initializer_list<std::string> arguments){auto result=toolchain.driver;result.insert(result.end(),arguments);return result;};
  auto identity=capture({compiler,"--version"});if(identity.code!=0)throw Error("E_TOOL","cannot identify native compiler");
  // Probe the driver's actual IR ABI, including SDK/deployment normalization.
  // In particular Darwin host triples and macOS driver triples need not spell
  // the same OS version. Never silently cache code for a different host ABI.
  auto probe=capture(command({"-S","-emit-llvm","-x","c++","-","-o","-"}));
  if(probe.code!=0)throw Error("E_TOOL","cannot identify native compiler target: "+probe.errors);
  llvm::LLVMContext probeContext;llvm::SMDiagnostic probeDiagnostic;
  auto probeBuffer=llvm::MemoryBuffer::getMemBufferCopy(probe.output,"native compiler target probe");
  auto probeModule=llvm::parseIR(probeBuffer->getMemBufferRef(),probeDiagnostic,probeContext);
  if(!probeModule)throw Error("E_TOOL","native compiler did not produce readable LLVM target information");
  auto compilerTarget=probeModule->getTargetTriple().str(),dataLayout=probeModule->getDataLayoutStr();
  llvm::Triple driverABI(compilerTarget),requestedABI(target);
  llvm::VersionTuple requestedVersion,driverVersion;
  auto version=[](const llvm::VersionTuple &v){return std::tuple(v.getMajor(),v.getMinor().value_or(0),v.getSubminor().value_or(0));};
  bool deploymentSelected=(!options.target.empty()&&options.target!="server"&&options.target!="native")||!options.toolchain.empty();
  bool wrongDeployment=deploymentSelected&&requestedABI.getOS()==llvm::Triple::MacOSX&&requestedABI.getOSMajorVersion()!=0&&requestedABI.getMacOSXVersion(requestedVersion)&&driverABI.getMacOSXVersion(driverVersion)&&version(requestedVersion)!=version(driverVersion);
  if(requestedABI.getOS()==llvm::Triple::IOS)
    wrongDeployment=version(requestedABI.getOSVersion())!=version(driverABI.getOSVersion())||driverABI.getVendor()!=llvm::Triple::Apple;
  if(!driverABI.isArch64Bit()||driverABI.getArch()!=requestedABI.getArch()||driverABI.getEnvironment()!=requestedABI.getEnvironment()||
     !(driverABI.getOS()==requestedABI.getOS()||(driverABI.isMacOSX()&&requestedABI.isMacOSX()))||wrongDeployment||dataLayout.empty()||probeModule->getDataLayout().getPointerSizeInBits()!=64||driverABI.getSubArch()!=requestedABI.getSubArch())
    throw Error("E_TARGET","native compiler target "+compilerTarget+" does not match configured target "+target+" or has no data layout");
  if(windows){
    auto macros=capture(command({"-dM","-E","-x","c++","-include","_mingw.h","-"}));
    if(macros.code!=0||macros.output.find("#define __MINGW64__ 1\n")==std::string::npos||
       (macros.output.find("#define _UCRT\n")==std::string::npos&&macros.output.find("#define _UCRT \n")==std::string::npos))
      throw Error("E_TARGET","Windows compiler must select the configured 64-bit MinGW/UCRT headers: "+macros.errors);
  }
  auto environment=[](const char *name){const char *v=std::getenv(name);return v?std::string(v):std::string();};
  // Keep semantic identity separate from toolchain and source-projection identity.
  bool wire=server,storage=server,files=false,parallel=false;auto names=reachable(p,options.entry);
  for(const auto &entry:options.libraryExports){auto more=reachable(p,entry);names.insert(more.begin(),more.end());}
  auto callableTargets=nativeFunctionBridges(p,names);
  if(options.projectLibraryABI)for(const auto &name:names)if(!p.function(name).closure)callableTargets.insert(name);
  std::function<void(E)> inspect=[&](E e){if(e){if(e->kind==Expr::Call){if(e->text=="encode_json"||e->text=="decode_json")wire=true;if(e->text.starts_with("store_"))storage=true;if(e->text=="file_read_text"||e->text=="file_write_text"||e->text=="file_read_bytes"||e->text=="file_write_bytes"||streamFileBuiltins().contains(e->text))files=true;}for(auto arg:e->args)inspect(arg);}};
  std::function<void(const std::vector<S>&)> inspectBlock=[&](const auto &body){for(auto s:body){inspect(s->expr);childBlocks(s,inspectBlock);}};
  for(const auto &f:p.functions)if(names.contains(f.name))inspectBlock(f.body);
  for(const auto &f:p.functions)if(names.contains(f.name)&&usesParallelMap(f))parallel=true;
  for(const auto &library:options.libraries)parallel|=library.parallelCalls;
  bool foreign=false;for(const auto &name:names)foreign|=p.function(name).foreign.has_value();if(foreign){wire=true;files=true;}
  const bool taskFileReads=tasks&&files;
  if(windows&&(files||foreign))throw Error("E_TARGET","Windows filesystem/resource operations and source foreign modules remain pending native platform validation");
  if(configuredABI.getOS()==llvm::Triple::IOS&&foreign)
    throw Error("E_TARGET","iOS source foreign-library loading is not configured");
  if(parallel&&!configuredABI.isMacOSX()&&!configuredABI.isOSLinux())
    throw Error("E_TARGET","native parallel_map currently requires macOS or Linux; other CPU worker targets remain pending validation");
  if(storage&&(toolchain.sqliteInclude.empty()||toolchain.sqliteLibrary.empty()))throw Error("E_TARGET_LIBRARY","target storage requires sqlite include/library paths in --toolchain FILE; host libraries cannot be used for another architecture");
  if(server&&(toolchain.opensslInclude.empty()||toolchain.opensslSSL.empty()||toolchain.opensslCrypto.empty()))throw Error("E_TARGET_LIBRARY","target server requires openssl include/ssl/crypto paths in --toolchain FILE");
  if(foreign&&(toolchain.opensslInclude.empty()||toolchain.opensslCrypto.empty()))throw Error("E_TARGET_LIBRARY","foreign calls require target OpenSSL Crypto include/library paths");
  bool profiling=options.profile=="profile";
  std::vector<std::string> components={"runtime.cpp"},headers={"nex_value.h","nex_bytes.h","nex_file_resource.h","nex_resource.h","nex_error.h","nex_float.h","nex_host.h","nex_io.h","nex_platform.h","nex_profile.h","third_party/dragonbox/dragonbox.h","third_party/dragonbox/manifest.json","third_party/dragonbox/LICENSE-Apache2-LLVM"};
  if(profiling)components.insert(components.end(),{"nex_profile.cpp","third_party/tracy/public/TracyClient.cpp"});
  if(parallel||tasks)headers.insert(headers.end(),{"nex_parallel.h","nex_parallel_value.h"});
  if(tasks){
    components.insert(components.end(),{"nex_task_frame.cpp","nex_task_application.cpp","nex_task_external.cpp","nex_files.cpp"});
    headers.insert(headers.end(),{"nex_tasks.h","nex_tasks_impl.h","nex_task_external.h","nex_task_values.h","nex_task_values_impl.h","nex_task_protocol.h","nex_task_frame.h","nex_task_application.h","nex_task_limits.h","nex_task_profile_site.h","nex_files.h","nex_task_file_read.h"});
    if(profiling){components.push_back("nex_task_profile.cpp");headers.push_back("nex_task_profile.h");}
    if(options.taskDebug){components.push_back("nex_task_debug.cpp");headers.insert(headers.end(),{"nex_task_debug.h","nex_task_debug_site.h"});}
  }
  if(wire){components.insert(components.end(),{"nex_json.cpp","wire_runtime.cpp"});headers.insert(headers.end(),{"nex_json.h","third_party/json.hpp"});}
  if(storage)components.insert(components.end(),{"nex_store.cpp","store_runtime.cpp"});
  if(files){components.insert(components.end(),{"nex_files.cpp","files_runtime.cpp"});headers.insert(headers.end(),{"nex_files.h","nex_file_abi.h"});}
  if(foreign){components.insert(components.end(),{"foreign_runtime.cpp","nex_foreign.cpp","nex_ffi_loader.cpp","nex_ffi.cpp","nex_ffi_types.cpp"});headers.insert(headers.end(),{"nex_foreign.h","nex_foreign_abi.h","nex_ffi_loader.h","nex_ffi_module.h","nex_ffi.h","nex_ffi_host.h","nex_ffi_types.h"});}
  if(server){components.push_back("http_main.cpp");headers.insert(headers.end(),{"third_party/httplib.h","nex_auth.h"});}
  {std::set<std::string> seen;std::erase_if(components,[&](const auto &component){return !seen.insert(component).second;});}
  std::map<std::string,std::string> runtimeFiles;
  for(const auto &file:components)runtimeFiles[file]=readFile(resourceFile("runtime/"+file));for(const auto &file:headers)runtimeFiles[file]=readFile(resourceFile("runtime/"+file));
  std::string notices;
  auto license=[&](const std::string &name,const std::string &file){
    auto text=readFile(resourceFile("runtime/third_party/"+file));
    runtimeFiles["third_party/"+file]=text;
    notices+=name+"\n\n"+text+"\n\n";
  };
  license("Dragonbox 1.1.3", "dragonbox/LICENSE-Boost");
  if(windows){auto text=readFile(toolchain.windowsNotices);runtimeFiles["third_party/windows-runtime-notices.txt"]=text;notices+="Operator-supplied Windows UCRT/static C++ runtime notices\n\n"+text+"\n\n";}
  if(wire)license("nlohmann/json 3.12.0", "JSON-LICENSE.MIT");
  if(server)license("cpp-httplib 0.61.0", "HTTPLIB-LICENSE");
  if(profiling){
    license("Tracy 0.14.1 (client and embedded dependencies)","TRACY-NOTICES.txt");
    auto manifest=readFile(resourceFile("runtime/third_party/tracy/manifest.json"));runtimeFiles["third_party/tracy/manifest.json"]=manifest;
    auto parsed=llvm::json::parse(manifest);if(!parsed)throw Error("E_RESOURCE","invalid bundled Tracy manifest");
    auto object=parsed->getAsObject();auto files=object?object->getObject("files"):nullptr;
    if(!files)throw Error("E_RESOURCE","missing bundled Tracy inventory");
    for(const auto &[name,value]:*files){
      auto path=std::filesystem::path(name.str());if(path.is_absolute()||std::any_of(path.begin(),path.end(),[](const auto &part){return part=="..";}))throw Error("E_RESOURCE","invalid bundled Tracy path");
      runtimeFiles["third_party/tracy/"+name.str()]=readFile(resourceFile("runtime/third_party/tracy/"+name.str()));
    }
  }
  if(storage)runtimeFiles["sqlite3.h"]=readFile((std::filesystem::path(toolchain.sqliteInclude)/"sqlite3.h").string());
  if(!options.foreignCatalogue.empty()&&(!foreign||options.libraryEntry||options.foreignCatalogue!="../foreign/host.json"))
    throw Error("E_PACKAGE","invalid packaged foreign catalogue build configuration");
  std::string runtimeIdentity=options.foreignCatalogue+":parallel="+std::to_string(parallel)+":tasks="+std::to_string(tasks)+":task_debug="+std::to_string(options.taskDebug);for(const auto &[file,source]:runtimeFiles)runtimeIdentity+=file+source;
  if(storage)runtimeIdentity+=std::string(toolchain.sqliteInclude)+toolchain.sqliteLibrary+hash(readFile(toolchain.sqliteLibrary))+hash(readFile((std::filesystem::path(toolchain.sqliteInclude)/"sqlite3.h").string()));
  if(server)runtimeIdentity+=std::string(toolchain.opensslInclude)+toolchain.opensslSSL+toolchain.opensslCrypto+hash(readFile(toolchain.opensslSSL))+hash(readFile(toolchain.opensslCrypto))+hash(readFile((std::filesystem::path(toolchain.opensslInclude)/"openssl/ssl.h").string()));
  auto formatter=readFile(resourceFile("debug/lldb_nex.py"));auto dapAdapter=readFile(resourceFile("debug/nex_dap.py"));
  llvm::json::Array libraryInputs;std::map<std::string,std::string> externalContracts;std::vector<std::string> capturedLibraries;
  if(options.libraries.size()>128)throw Error("E_PROJECT_LIMIT","native build accepts at most128 dependency archives");
  for(const auto &library:options.libraries){
    auto bytes=readFile(library.path);if(hash(bytes)!=library.digest)throw Error("E_PROJECT_INPUT_CHANGED","native dependency archive changed: "+library.path);
    llvm::json::Object contracts;for(const auto &[name,contract]:library.contracts){
      if(auto old=externalContracts.find(name);old!=externalContracts.end()&&old->second!=contract)throw Error("E_PROJECT_ABI","conflicting native dependency definition: "+name);
      externalContracts[name]=contract;contracts[name]=contract;
    }
    capturedLibraries.push_back(std::move(bytes));libraryInputs.push_back(llvm::json::Object{{"path",library.path},{"hash",library.digest},{"abi",library.abi},{"contracts",std::move(contracts)},{"parallel",library.parallelCalls}});
  }
  auto buildRoot=std::filesystem::absolute(directory);
  auto sourcePaths=[&](const std::string &module,const std::string &source){
    auto sourceKey=hash(json(llvm::json::Object{{"schema","nex.native-source/2"},{"module",module},{"source",source}},false));
    auto projection=(buildRoot/"source-cache"/sourceKey/"source.nex").string();
    auto anchor=(buildRoot/"source-anchors"/hash(json(llvm::json::Array{"nex.native-source-anchor/2",module},false))/"source.nex").string();
    return std::pair{projection,anchor};
  };
  std::map<std::string,llvm::json::Object> taskDebugFunctions;
  llvm::json::Array debugRegistry;std::string taskDebugHash;
  if(options.taskDebug){
    if(names.size()>nexrt::maximumTaskDebugCodes)throw Error("E_DEBUG_INIT","task debugger code table exceeds its bound");
    size_t totalPoints=0,totalBindings=0,totalVisible=0,textBytes=0;
    auto text=[&](const std::string &value){if(value.size()+1>nexrt::maximumTaskDebugTextBytes-textBytes)throw Error("E_DEBUG_INIT","task debugger text exceeds its bound");textBytes+=value.size()+1;};
    for(const auto &name:names){
      const auto &function=p.function(name);auto module=p.units.contains(function.unit)?p.units.at(function.unit).module:p.module;
      auto source=p.units.contains(function.unit)?p.units.at(function.unit).source:p.source;
      auto file=sourcePaths(module,source).second;
      auto metadata=taskDebugFunctionMetadata(p,function,file);metadata["site_id"]=taskDebugFunctions.size()+1;
      auto points=metadata.getArray("points"),bindings=metadata.getArray("bindings");
      totalPoints+=points->size();totalBindings+=bindings->size();
      auto content=hash(p.definition(function)),canonicalHash=hash(json(canonical(function),false));
      for(const auto &value:{name,file,content,canonicalHash})text(value);
      for(const auto &value:*points){const auto &point=*value.getAsObject();totalVisible+=point.getArray("visible")->size();text(point.getString("site")->str());}
      for(const auto &value:*bindings){const auto &binding=*value.getAsObject();text(binding.getString("name")->str());text(binding.getString("type")->str());}
      if(totalPoints>nexrt::maximumTaskDebugPoints||totalBindings>nexrt::maximumTaskDebugBindings||totalVisible>nexrt::maximumTaskDebugVisibleBindings)
        throw Error("E_DEBUG_INIT","task debugger source table exceeds its bound",function.span);
      debugRegistry.push_back(llvm::json::Object{{"name",name},{"function_hash",canonicalHash},{"function_source_hash",content},{"task_debug",llvm::json::Object(metadata)}});
      taskDebugFunctions.emplace(name,std::move(metadata));
    }
    auto bytes=json(llvm::json::Value(std::move(debugRegistry)),false);
    auto storage=names.size()*sizeof(nexrt::TaskDebugCodeSite)+totalPoints*sizeof(nexrt::TaskDebugPoint)+totalBindings*sizeof(nexrt::TaskDebugBinding)+totalVisible*sizeof(int64_t)+textBytes;
    if(storage>nexrt::maximumTaskDebugMetadataBytes||bytes.size()>nexrt::maximumTaskDebugMetadataBytes)throw Error("E_DEBUG_INIT","task debugger metadata exceeds its storage bound");
    taskDebugHash=hash(bytes);
  }
  llvm::json::Array exportInputs;for(const auto &entry:options.libraryExports)exportInputs.push_back(entry);
  std::string linkageIdentity=json(llvm::json::Object{{"task_limits",taskLimitsJSON(options.taskLimits,tasks)},{"task_file_reads",taskFileReads},{"task_debug",options.taskDebug},{"task_debug_abi",options.taskDebug?int64_t(nexrt::taskDebugCatalogABI):0},{"task_debug_metadata_hash",taskDebugHash},{"task_limits_specified",options.taskLimitsSpecified},{"project_library_abi",options.projectLibraryABI},{"position_independent",options.positionIndependent},{"deferred_link",options.deferredLink},{"functions_only",options.functionsOnly},{"code_only",options.codeOnlyLibrary},{"exports",std::move(exportInputs)},{"libraries",llvm::json::Array(libraryInputs)}},false);
  std::string key=hash(revision(p)+json(sourceBundle(p),false)+p.path+options.profile+target+toolchain.identity+toolchainFingerprint+compilerTarget+dataLayout+options.entry+std::to_string(options.libraryEntry)+std::to_string(server)+NEX_BUILD_ID+LLVM_VERSION_STRING+compiler+identity.output+runtimeIdentity+hash(formatter)+hash(dapAdapter)+environment("SDKROOT")+environment("MACOSX_DEPLOYMENT_TARGET")+linkageIdentity);
  auto folder=std::filesystem::absolute(std::filesystem::path(directory)/key);
  auto plan=planNative(p,options.entry,options.libraryExports,options.projectLibraryABI);
  if(tasks){
    // Descriptors carry pointers into this image. Keep one checked continuation
    // object until a separately versioned provider/lifetime ABI exists.
    NativeUnit image;image.identity=p.function(options.entry).name;image.unit=p.function(options.entry).unit;image.module=p.module;image.functions=names;
    llvm::json::Array contracts,sources;
    for(const auto &unit:plan.units){contracts.push_back(unit.contract);sources.push_back(unit.source);}
    image.contract=json(llvm::json::Object{{"schema","nex.native-task-image/1"},{"language",programLanguage(p)},{"units",std::move(contracts)}},false);
    image.source=json(std::move(sources),false);plan.units={std::move(image)};
  }
  BuildResult result{(folder/(options.deferredLink?"objects.a":options.libraryEntry?"libnex.a":windows?"app.exe":"app")).string(),(folder/"program.mlir").string(),(folder/"program.ll").string(),key,false,notices.empty()?"":(folder/"THIRD_PARTY_NOTICES.txt").string(),(folder/"compilation.json").string(),0,0,target,compilerTarget,toolchain.hostCompatible,0,0,false,{},{}};
  result.foreignCalls=foreign;
  result.parallelCalls=parallel;
  auto snapshot=p;
  llvm::json::Array debugSources,debugFunctions,heapTypes,debugSourceMap;std::set<std::string> debugTypes;
  OperationIndex operationIndex;
  std::map<std::string,std::string> debugAnchors;
  std::function<void(Type)> collectType=[&](Type type){
    if(!type.heap()||!debugTypes.insert(typeName(type)).second)return;
    heapTypes.push_back(typeName(type));
    if(type.element)collectType(*type.element);
    if(type.kind==Type::Function)for(const auto &argument:type.arguments)collectType(argument);
    if(type.kind==Type::Record)for(auto field:p.structure(type.name).members())collectType(field->type);
  };
  std::function<void(const std::vector<S>&)> collectLocals=[&](const auto &body){for(auto s:body){collectType(s->type);childBlocks(s,collectLocals);}};
  for(const auto &f:p.functions)if(names.contains(f.name)){
    collectType(f.result);for(const auto &param:f.params)collectType(param.type);for(const auto &capture:f.captures)collectType(capture.type);collectLocals(f.body);
    auto operations=operationTree(p,f);for(const auto &operation:operations)if(operation.ast)operationIndex[operation.ast]=operation.site;
    auto function=llvm::json::Object{{"name",f.name},{"function_hash",hash(json(canonical(f),false))},{"function_source_hash",hash(p.definition(f))},{"native_symbol",nativeSymbol(f.name)+(tasks&&f.effects.contains("task")?"__task_step":"")},{"callable_symbol",tasks&&f.effects.contains("task")?"":f.closure||callableTargets.contains(f.name)?closureSymbol(f):""},{"task_continuation_symbol",tasks?nativeSymbol(f.name)+"__task_step":""},{"operation_sites",operationSites(f,operations)}};
    if(options.taskDebug)function["task_debug"]=llvm::json::Object(taskDebugFunctions.at(f.name));
    debugFunctions.push_back(std::move(function));
  }
  for(auto &[unitKey,unit]:snapshot.units){
    auto [projection,anchor]=sourcePaths(unit.module,unit.source);
    auto original=unit.path;unit.path=projection;
    if(unitKey==snapshot.entryUnit)snapshot.path=unit.path;
    debugAnchors[unitKey]=anchor;
    debugSourceMap.push_back(llvm::json::Array{std::filesystem::path(anchor).parent_path().string(),std::filesystem::path(unit.path).parent_path().string()});
    debugSources.push_back(llvm::json::Object{{"original",original},{"projection",unit.path},{"debug_path",anchor},{"hash",hash(unit.source)}});
  }
  if(snapshot.units.empty()){
    auto [projection,anchor]=sourcePaths(p.module,p.source);
    snapshot.path=projection;debugAnchors[""]=anchor;
    debugSourceMap.push_back(llvm::json::Array{std::filesystem::path(debugAnchors.at("")).parent_path().string(),std::filesystem::path(snapshot.path).parent_path().string()});
    debugSources.push_back(llvm::json::Object{{"original",p.path},{"projection",snapshot.path},{"debug_path",debugAnchors.at("")},{"hash",hash(p.source)}});
  }
  // Objects refer to stable virtual paths. A session maps these paths to its
  // immutable complete sources, so sibling edits need not invalidate DWARF.
  auto codeSnapshot=snapshot;
  for(auto &[unitKey,unit]:codeSnapshot.units)unit.path=debugAnchors.at(unitKey);
  codeSnapshot.path=debugAnchors.at(snapshot.units.empty()?"":snapshot.entryUnit);
  auto nativeSeed=json(llvm::json::Object{{"schema","nex.native-toolchain/1"},{"compiler_build",NEX_BUILD_ID},{"llvm",LLVM_VERSION_STRING},
    {"position_independent",options.positionIndependent},{"parallel_call_scopes",parallel||options.projectLibraryABI||tasks},{"task_continuations",tasks},{"task_profiling",tasks&&profiling},{"task_debug",options.taskDebug},{"task_debug_metadata_hash",taskDebugHash},{"task_debug_abi",options.taskDebug?int64_t(nexrt::taskDebugCatalogABI):0},{"task_limits",taskLimitsJSON(options.taskLimits,tasks)},{"task_file_reads",taskFileReads},{"toolchain_fingerprint",toolchainFingerprint},{"compiler",compiler},{"compiler_identity",identity.output},{"compiler_target",compilerTarget},{"data_layout",dataLayout},{"profile",options.profile},{"target",target},{"host",host},{"host_compatible",toolchain.hostCompatible},{"toolchain_inputs",toolchain.identity},
    {"sdkroot",environment("SDKROOT")},{"deployment",environment("MACOSX_DEPLOYMENT_TARGET")}},false);
  std::string coreABI;for(const auto &file:{"runtime.cpp","nex_host.h","nex_value.h","nex_bytes.h","nex_file_resource.h","nex_resource.h","nex_error.h","nex_float.h","nex_io.h","nex_platform.h","nex_profile.h"})coreABI+=file+hash(runtimeFiles.at(file));
  result.libraryABI=hash(nativeSeed+coreABI+(tasks?runtimeIdentity:std::string()));
  for(const auto &library:options.libraries)if(library.abi!=result.libraryABI)throw Error("E_PROJECT_ABI","native dependency target/toolchain/runtime ABI differs: "+library.path);
  std::set<std::string> localNames=names;
  for(const auto &unit:plan.units){
    auto contract=llvm::json::parse(unit.contract);if(!contract)throw Error("E_INTERNAL","invalid native contract");
    // A physical package alias may spell the same checked source unit differently.
    contract->getAsObject()->erase("unit");auto digest=hash(json(*contract,false));
    result.functionContracts[unit.identity]=digest;
    if(auto found=externalContracts.find(unit.identity);found!=externalContracts.end()){
      if(found->second!=digest)throw Error("E_PROJECT_ABI","native dependency function/type context differs: "+unit.identity);
      localNames.erase(unit.identity);
    }
  }
  std::erase_if(plan.units,[&](const auto &unit){return !localNames.contains(unit.identity);});
  std::vector<std::string> unitKeys;std::vector<llvm::json::Value> unitInputs;std::vector<NativeArtifact> unitArtifacts(plan.units.size());
  bool nativeIntact=true;std::set<std::string> sourceUnits,compiledSourceUnits;
  if(tasks)for(const auto &name:names)sourceUnits.insert(p.function(name).unit);
  for(size_t i=0;i<plan.units.size();++i){
    const auto &unit=plan.units[i];auto source=codeSnapshot.units.contains(unit.unit)?codeSnapshot.units.at(unit.unit).path:codeSnapshot.path;sourceUnits.insert(unit.unit);
    std::string runtimeABI;
    for(const auto &file:{"runtime.cpp","nex_value.h","nex_bytes.h","nex_file_resource.h","nex_resource.h","nex_error.h","nex_float.h","third_party/dragonbox/dragonbox.h","nex_host.h","nex_io.h","nex_platform.h","nex_profile.h"})runtimeABI+=file+hash(runtimeFiles.at(file));
    if(profiling)runtimeABI+="nex_profile.cpp"+hash(runtimeFiles.at("nex_profile.cpp"));
    if(unit.wire)for(const auto &file:{"wire_runtime.cpp","nex_json.h"})runtimeABI+=file+hash(runtimeFiles.at(file));
    if(unit.storage)runtimeABI+="store_runtime.cpp"+hash(runtimeFiles.at("store_runtime.cpp"));
    if(unit.foreign)for(const auto &file:{"foreign_runtime.cpp","nex_foreign.cpp","nex_ffi_loader.cpp","nex_ffi.cpp","nex_ffi_types.cpp","nex_foreign.h","nex_foreign_abi.h","nex_ffi_loader.h","nex_ffi_module.h","nex_ffi.h","nex_ffi_host.h","nex_ffi_types.h"})runtimeABI+=file+hash(runtimeFiles.at(file));
    if(unit.files)for(const auto &file:{"files_runtime.cpp","nex_files.h","nex_file_abi.h"})runtimeABI+=file+hash(runtimeFiles.at(file));
    if(tasks)runtimeABI+=runtimeIdentity;
    auto wrapper=!options.libraryEntry&&!server&&!options.functionsOnly&&unit.functions.contains(p.function(options.entry).name)?p.function(options.entry).name:"";
    unitInputs.push_back(llvm::json::Object{{"schema","nex.native-unit/2"},{"toolchain_key",hash(nativeSeed)},{"semantic_key",hash(unit.contract)},
      {"source_hash",hash(unit.source)},{"debug_path",source},{"runtime_abi_key",hash(runtimeABI)},{"wrapper_entry",wrapper}});
    auto unitKey=hash(json(unitInputs.back(),false));unitKeys.push_back(unitKey);
    if(!loadArtifact(buildRoot,unitKey,unitArtifacts[i]))nativeIntact=false;
    else{
      auto local=folder/"units"/hash(unit.identity),object=folder/("nex-unit-"+hash(unit.identity)+".o");
      if(!std::filesystem::is_regular_file(object)||readFile(object.string())!=unitArtifacts[i].object||
         !std::filesystem::is_regular_file(local/"program.mlir")||readFile((local/"program.mlir").string())!=unitArtifacts[i].mlir||
         !std::filesystem::is_regular_file(local/"program.ll")||readFile((local/"program.ll").string())!=unitArtifacts[i].llvm)nativeIntact=false;
    }
  }
  auto debugFile=(folder/"debug.json").string(),formatterFile=(folder/"debugger/lldb_nex.py").string(),adapterFile=(folder/"debugger/nex_dap.py").string();
  llvm::json::Array completionInputs;completionInputs.push_back("library-abi.json");
  for(size_t i=0;i<capturedLibraries.size();++i)completionInputs.push_back("libraries/"+std::to_string(i)+".a");
  auto debugRecord=llvm::json::Object{{"schema",options.taskDebug?"nex.debug/2":"nex.debug/1"},{"toolchain",NEX_VERSION},{"language",programLanguage(p)},{"runtime_view","nex.runtime-view/3"},{"expression_protocol",options.taskDebug?"nex.task-debug-expression/1":"nex.debug-expression/3"},{"compiler_build",NEX_BUILD_ID},{"source_hash",hash(json(sourceBundle(p),false))},{"revision",revision(p)},{"build_key",key},{"program",result.executable},{"profile",options.profile},{ "target",target},{"compiler_target",compilerTarget},{"host_compatible",toolchain.hostCompatible},{"formatter",formatterFile},{"formatter_hash",hash(formatter)},{"dap_adapter",adapterFile},{"dap_adapter_hash",hash(dapAdapter)},{"heap_types",std::move(heapTypes)},{"sources",std::move(debugSources)},{"source_map",std::move(debugSourceMap)},{"functions",std::move(debugFunctions)}};
  if(options.taskDebug)debugRecord["task_debug"]=llvm::json::Object{{"schema","nex.task-debug-view/1"},{"abi",nexrt::taskDebugCatalogABI},
    {"catalog_symbol","nex_task_debug_catalog_v1"},{"marker_symbol","nex_task_debug_stop_marker"},{"metadata_hash",taskDebugHash},
    {"image_sha256",""},{"image_uuid",""},{"deadline_advances_while_stopped",true},
    {"maximum_codes",nexrt::maximumTaskDebugCodes},{"maximum_points",nexrt::maximumTaskDebugPoints},
    {"maximum_bindings",nexrt::maximumTaskDebugBindings},{"maximum_visible_bindings",nexrt::maximumTaskDebugVisibleBindings}};
  auto debugTextFor=[&]{auto record=llvm::json::Object(debugRecord);
    if(options.taskDebug&&!objectArchive&&std::filesystem::is_regular_file(result.executable))try{
      auto data=readFile(result.executable);auto &task=*record.getObject("task_debug");
      task["image_sha256"]=llvm::toHex(llvm::SHA256::hash(llvm::arrayRefFromStringRef(data)),true);
      task["image_uuid"]=nativeImageUUID(result.executable);
    }catch(const Error &){} // A corrupted cached image is repaired below.
    return json(llvm::json::Value(std::move(record)))+"\n";
  };
  auto debugText=debugTextFor();
  auto debugIntact=[&](){
    if(!std::filesystem::is_regular_file(debugFile)||readFile(debugFile)!=debugText||!std::filesystem::is_regular_file(formatterFile)||readFile(formatterFile)!=formatter||!std::filesystem::is_regular_file(adapterFile)||readFile(adapterFile)!=dapAdapter)return false;
    for(const auto &[unitKey,unit]:snapshot.units){
      auto mirror=unitKey==snapshot.entryUnit?folder/"source.nex":folder/"sources"/unitKey;
      if(!std::filesystem::is_regular_file(unit.path)||readFile(unit.path)!=unit.source||!std::filesystem::is_regular_file(mirror)||readFile(mirror.string())!=unit.source)return false;
    }
    if(snapshot.units.empty()&&(!std::filesystem::is_regular_file(snapshot.path)||readFile(snapshot.path)!=snapshot.source))return false;
    if(!objectArchive&&driverABI.isOSDarwin()){
      auto symbols=result.executable+".dSYM/Contents/Resources/DWARF/app";auto marker=folder/"debug-symbols.complete";
      if(!std::filesystem::is_regular_file(symbols)||!std::filesystem::is_regular_file(marker)||readFile(marker.string())!=hash(readFile(symbols))+"\n")return false;
    }
    return true;
  };
  auto completion=[&](){
    std::string contents=key;
    for(const auto &file:{std::filesystem::path(result.executable),std::filesystem::path(result.mlir),std::filesystem::path(result.llvm),std::filesystem::path(result.compilation),folder/"build.json",folder/"source-bundle.json"})contents+=hash(readFile(file.string()));
    for(const auto &file:completionInputs)contents+=hash(readFile((folder/file.getAsString()->str()).string()));
    return hash(contents)+"\n";
  };
  auto buildIntact=[&](){try{return readFile((folder/"complete").string())==completion();}catch(const std::exception &){return false;}};
  if(buildIntact()&&(result.notices.empty()||(std::filesystem::is_regular_file(result.notices)&&readFile(result.notices)==notices))&&debugIntact()&&nativeIntact){verifyToolchain();result.cached=true;result.reusedModules=sourceUnits.size();result.reusedFunctions=tasks?names.size():plan.units.size();return result;}
  std::filesystem::create_directories(folder);
  // Compile the exact captured runtime inputs, even if a development checkout changes meanwhile.
  auto runtimeProjection=std::filesystem::absolute(std::filesystem::path(directory)/"runtime-inputs"/hash(runtimeIdentity));
  for(const auto &[file,source]:runtimeFiles){
    auto target=runtimeProjection/file;
    if(!std::filesystem::is_regular_file(target)||readFile(target.string())!=source){
      auto temporary=target;temporary+=".tmp."+std::to_string(std::random_device{}());writeFile(temporary.string(),source);std::filesystem::rename(temporary,target);
    }
  }
  // Debuggers refer to an immutable projection, not a subsequently edited working file.
  for(const auto &[unitKey,unit]:snapshot.units){captureFile(unit.path,unit.source);writeFile((unitKey==snapshot.entryUnit?folder/"source.nex":folder/"sources"/unitKey).string(),unit.source);}
  if(snapshot.units.empty()){captureFile(snapshot.path,snapshot.source);writeFile((folder/"source.nex").string(),snapshot.source);}
  writeFile(debugFile,debugText);writeFile(formatterFile,formatter);writeFile(adapterFile,dapAdapter);
  writeFile((folder/"source-bundle.json").string(),json(sourceBundle(p))+"\n");
  const NativeEmissionContext emissionContext{callableTargets,parallel};
  auto mlir=tasks?emitTaskNative(snapshot,options.entry,true,options.profile!="debug",options.taskLimits,profiling,options.taskDebug).mlir:Emitter(snapshot,options.profile!="debug",profiling,&operationIndex,false,&emissionContext).run(options.entry,options.testEntry,options.libraryEntry||server||options.functionsOnly,&localNames,&names,options.projectLibraryABI,parallel);writeFile(result.mlir,mlir);
  std::string optimization=options.profile=="debug"?"-O0":"-O2";
  auto link=toolchain.driver;llvm::json::Array compiledUnits;
  for(size_t i=0;i<plan.units.size();++i){
    const auto &unit=plan.units[i];auto &artifact=unitArtifacts[i];
    if(!artifact.reused){
      std::filesystem::path stage(createTemporaryDirectory("nex-native-unit"));
      try{
        auto unitSnapshot=codeSnapshot;if(unitSnapshot.units.contains(unit.unit))unitSnapshot.path=unitSnapshot.units.at(unit.unit).path;
        artifact.mlir=tasks?emitTaskNative(unitSnapshot,options.entry,true,options.profile!="debug",options.taskLimits,profiling,options.taskDebug).mlir:Emitter(unitSnapshot,options.profile!="debug",profiling,&operationIndex,false,&emissionContext).run(options.entry,options.testEntry,options.libraryEntry||server||options.functionsOnly,&unit.functions,&names,options.projectLibraryABI,parallel);
        writeFile((stage/"program.mlir").string(),artifact.mlir);artifact.llvm=lower(artifact.mlir,unitSnapshot.path,compilerTarget,dataLayout);writeFile((stage/"program.ll").string(),artifact.llvm);
        auto compile=command({"-c",(stage/"program.ll").string(),"-o",(stage/"program.o").string(),"-g",optimization});
        if(options.profile=="profile")compile.push_back("-fno-omit-frame-pointer");
        if(options.positionIndependent)compile.push_back("-fPIC");
        if(executeNativeBuildTool(compile)!=0)throw Error("E_LINK","native unit compiler failed");
        artifact.object=readFile((stage/"program.o").string());saveArtifact(buildRoot,unitKeys[i],artifact);std::filesystem::remove_all(stage);
      }catch(const Error &error){throw Error(error.code,std::string(error.what())+"; intermediate files retained at "+stage.string(),error.span);}
      result.compiledFunctions+=tasks?unit.functions.size():1;
      if(tasks)for(const auto &name:unit.functions)compiledSourceUnits.insert(p.function(name).unit);
      else compiledSourceUnits.insert(unit.unit);
    }else result.reusedFunctions+=tasks?unit.functions.size():1;
    auto destination=folder/"units"/hash(unit.identity);writeFile((destination/"program.mlir").string(),artifact.mlir);writeFile((destination/"program.ll").string(),artifact.llvm);
    auto object=folder/("nex-unit-"+hash(unit.identity)+".o");writeFile(object.string(),artifact.object);link.push_back(object.string());
    llvm::json::Array functions;for(const auto &name:unit.functions)functions.push_back(name);
    compiledUnits.push_back(llvm::json::Object{{"identity",unit.identity},{"unit",unit.unit},{"module",unit.module},{"input_key",unitKeys[i]},{"artifact_key",artifact.id},{"reused",artifact.reused},
      {"inputs",std::move(unitInputs[i])},
      {"functions",std::move(functions)},{"object",object.string()},{"object_hash",hash(artifact.object)},{"mlir",(destination/"program.mlir").string()},{"llvm",(destination/"program.ll").string()},
      {"cache_record",(buildRoot/"native-cache"/(unitKeys[i]+".json")).string()},{"source",snapshot.units.contains(unit.unit)?snapshot.units.at(unit.unit).path:snapshot.path}});
  }
  result.compiledModules=compiledSourceUnits.size();result.reusedModules=sourceUnits.size()-compiledSourceUnits.size();
  writeFile(result.llvm,unitArtifacts.empty()&&options.functionsOnly?lower(mlir,snapshot.path,compilerTarget,dataLayout):linkIR(unitArtifacts,snapshot.path));
  writeFile(result.compilation,json(llvm::json::Object{{"schema","nex.compilation/1"},{"granularity",tasks?"continuation_image":"function"},{"revision",revision(p)},{"build_key",key},
    {"compiled_modules",result.compiledModules},{"reused_modules",result.reusedModules},{"compiled_functions",result.compiledFunctions},{"reused_functions",result.reusedFunctions},{"units",std::move(compiledUnits)},{"dependencies",std::move(plan.dependencies)},{"static_libraries",llvm::json::Array(libraryInputs)}})+"\n");
  for(const auto &component:components){
    if(options.codeOnlyLibrary||options.deferredLink)continue;
    auto source=(runtimeProjection/component).string();auto runtimeKey=hash("nex.runtime-object/2"+runtimeProjection.string()+runtimeIdentity+component+compiler+identity.output+optimization+options.profile+std::to_string(options.positionIndependent)+target+toolchain.identity+toolchainFingerprint+compilerTarget+dataLayout+environment("SDKROOT")+environment("MACOSX_DEPLOYMENT_TARGET"));
    auto cache=std::filesystem::absolute(std::filesystem::path(directory)/"runtime-cache"/runtimeKey);auto cached=cache/"runtime.o",marker=cache/"complete";
    std::filesystem::create_directories(cache);
    if(!std::filesystem::is_regular_file(cached)||!std::filesystem::is_regular_file(marker)||readFile(marker.string())!=hash(readFile(cached.string()))+"\n"){
      auto temporary=cache/("runtime-"+std::to_string(std::random_device{}())+".o");
      auto arguments=command({"-std=c++20","-c",source,"-I",runtimeProjection.string(),"-o",temporary.string(),"-g",optimization});
      if(foreign)arguments.insert(arguments.end(),{"-I",toolchain.opensslInclude,"-pthread","-DNEX_FOREIGN_ENABLED"});
      if(parallel||tasks)arguments.insert(arguments.end(),{"-pthread","-DNEX_STRUCTURED_WORKERS"});
      if(tasks)arguments.push_back("-DNEX_ASYNC_TASKS");
      if(options.taskDebug)arguments.push_back("-DNEX_TASK_DEBUG_ENABLED");
      if(!options.foreignCatalogue.empty())arguments.push_back("-DNEX_FOREIGN_DEFAULT="+json(options.foreignCatalogue,false));
      if(component=="http_main.cpp")arguments.insert(arguments.end(),{"-I",toolchain.opensslInclude,"-pthread"});
      if(options.profile=="profile")arguments.push_back("-fno-omit-frame-pointer");
      if(options.positionIndependent)arguments.push_back("-fPIC");
      if(profiling){
        arguments.insert(arguments.end(),{"-DNEX_PROFILE_ENABLED","-DTRACY_ENABLE","-DTRACY_ON_DEMAND","-DTRACY_DELAYED_INIT","-DTRACY_MANUAL_LIFETIME","-DTRACY_ONLY_LOCALHOST","-DTRACY_NO_BROADCAST","-DTRACY_NO_CODE_TRANSFER","-DTRACY_NO_CALLSTACK","-DTRACY_NO_SYSTEM_TRACING","-DTRACY_NO_SAMPLING","-DTRACY_NO_CRASH_HANDLER","-DTRACY_NO_FRAME_IMAGE","-pthread"});
        if(tasks)arguments.push_back("-DNEX_TASK_PROFILE_ENABLED");
      }
      if(executeNativeBuildTool(arguments)!=0)throw Error("E_LINK","runtime compilation failed; artifacts retained at "+cache.string());
      auto digest=hash(readFile(temporary.string()));std::filesystem::rename(temporary,cached);writeFile(marker.string(),digest+"\n");
    }
    auto destination=folder/std::filesystem::path(component).replace_extension(".o");
    std::filesystem::create_directories(destination.parent_path());
    copyFile(cached.string(),destination.string(),true);link.push_back(destination.string());
  }
  if(server&&!options.deferredLink){
    auto bridge=(folder/"server-bridge.cpp").string(),bridgeObject=(folder/"server-bridge.o").string();auto name=nativeSymbol(p.function(options.entry).name);
    writeFile(bridge,"#include \"nex_host.h\"\nextern \"C\" nexrt::Handle *"+name+"(nexrt::Handle*);\nextern \"C\" nexrt::Handle *nex_server_dispatch(nexrt::Handle *value){ return "+name+"(value); }\n");
    auto bridgeCompile=command({"-std=c++20","-c",bridge,"-I",runtimeProjection.string(),"-o",bridgeObject,"-g",optimization});
    if(profiling)bridgeCompile.push_back("-DNEX_PROFILE_ENABLED");
    if(tasks&&profiling)bridgeCompile.push_back("-DNEX_TASK_PROFILE_ENABLED");
    if(options.taskDebug)bridgeCompile.push_back("-DNEX_TASK_DEBUG_ENABLED");
    if(options.positionIndependent)bridgeCompile.push_back("-fPIC");
    if(executeNativeBuildTool(bridgeCompile)!=0)throw Error("E_LINK","HTTP bridge compilation failed");
    link.push_back(bridgeObject);link.push_back(toolchain.opensslSSL);link.push_back(toolchain.opensslCrypto);link.push_back("-pthread");
  }
  if(!objectArchive){
    // Whole-program provenance is linked separately from reusable function objects.
    auto identity=json(llvm::json::Object{{"schema","nex.native-application/1"},{"toolchain",NEX_VERSION},{"language",programLanguage(p)},
      {"revision",revision(p)},{"source_hash",hash(json(sourceBundle(p),false))},{"build_key",key},{"compiler_build",NEX_BUILD_ID},{"task_limits",taskLimitsJSON(options.taskLimits,tasks)},{"task_file_reads",taskFileReads}},false);
    auto source=(folder/"application-identity.cpp").string(),object=(folder/"application-identity.o").string();
    writeFile(source,"extern \"C\" const char *nex_application_identity()noexcept{return "+json(identity,false)+";}\n");
    if(executeNativeBuildTool(command({"-std=c++20","-c",source,"-o",object,optimization}))!=0)throw Error("E_LINK","application identity compilation failed");link.push_back(object);
  }
  if(profiling&&!options.codeOnlyLibrary&&!options.deferredLink){
    // Whole-build identity lives in a tiny link unit, preserving reuse of NEX
    // module objects across unrelated body edits and different entry programs.
    auto identity=json(llvm::json::Object{{"schema","nex.profile-build/1"},{"toolchain",NEX_VERSION},{"language",programLanguage(p)},{"revision",revision(p)},{"build_key",key},{"entry",p.function(options.entry).name},
      {"compiler_build",NEX_BUILD_ID},{"source_hash",hash(json(sourceBundle(p),false))},{"task_limits",taskLimitsJSON(options.taskLimits,tasks)}},false);
    auto source=(folder/"profile-identity.cpp").string(),object=(folder/"profile-identity.o").string();
    writeFile(source,"extern \"C\" const char *nex_profile_build_info(){return "+json(identity,false)+";}\n");
    if(executeNativeBuildTool(command({"-std=c++20","-c",source,"-o",object,optimization}))!=0)throw Error("E_LINK","profile identity compilation failed");link.push_back(object);
  }
  if(foreign&&!objectArchive){link.push_back(toolchain.opensslCrypto);link.push_back("-pthread");if(driverABI.isOSLinux())link.push_back("-ldl");}
  if(profiling&&!objectArchive){link.push_back("-pthread");if(driverABI.isOSLinux())link.push_back("-ldl");}
  if((parallel||tasks)&&!objectArchive)link.push_back("-pthread");
  // LLVM ELF/archive writers use '%' as a temporary-file template marker.
  // Stage their output in an independent directory so literal project paths
  // (including percent signs) are never interpreted as that template.
  std::filesystem::path linkStage;auto linkOutput=result.executable;
  for(size_t i=0;i<capturedLibraries.size();++i)writeFile((folder/"libraries"/(std::to_string(i)+".a")).string(),capturedLibraries[i]);
  if(driverABI.isOSLinux()||windows||objectArchive){
    linkStage=createTemporaryDirectory("nex-link");linkOutput=(linkStage/std::filesystem::path(result.executable).filename()).string();
  }
  if(objectArchive){
    std::vector<std::string> archive={toolchain.archiver,"rcs",linkOutput};archive.insert(archive.end(),link.begin()+toolchain.driver.size(),link.end());link=std::move(archive);
  }else {
    for(size_t i=0;i<capturedLibraries.size();++i)link.push_back((folder/"libraries"/(std::to_string(i)+".a")).string());
    if(windows)link.push_back("-static");
    if(!toolchain.linker.empty())link.push_back("--ld-path="+toolchain.linker);
    if(options.taskDebug&&driverABI.isOSLinux())link.push_back("-Wl,--build-id=sha1");
    if(storage)link.push_back(toolchain.sqliteLibrary);
    if(driverABI.isOSDarwin()||driverABI.isOSLinux()) {
      // Select configured dynamic dependencies at execution time as well as
      // link time. Separate arguments keep commas/Unicode literal.
      std::set<std::string> libraryPaths;
      if(storage)libraryPaths.insert(std::filesystem::path(toolchain.sqliteLibrary).parent_path().string());
      if(server)for(const auto &library:{toolchain.opensslSSL,toolchain.opensslCrypto})libraryPaths.insert(std::filesystem::path(library).parent_path().string());
      if(foreign)libraryPaths.insert(std::filesystem::path(toolchain.opensslCrypto).parent_path().string());
      for(const auto &path:libraryPaths){
        if(driverABI.isOSLinux()&&path.find(':')!=std::string::npos)throw Error("E_TARGET_LIBRARY","ELF library directories cannot contain ':' (runtime search-path separator): "+path);
        link.insert(link.end(),{"-Xlinker","-rpath","-Xlinker",path});
      }
    }
    link.insert(link.end(),{"-o",linkOutput,"-g"});
  }
  if(executeNativeBuildTool(link)!=0)throw Error("E_LINK","native linker failed; intermediate files retained at "+folder.string()+(linkStage.empty()?"":"; link output at "+linkStage.string()));
  if(!linkStage.empty()){
    try{copyFile(linkOutput,result.executable,true);std::filesystem::remove_all(linkStage);}
    catch(const Error &e){throw Error(e.code,std::string(e.what())+"; link output retained at "+linkStage.string(),e.span);}
  }
  if(!objectArchive&&driverABI.isOSDarwin()) {
    auto dsym=toolchain.debugPackager;
    if(executeNativeBuildTool({dsym,result.executable,"-o",result.executable+".dSYM"})!=0)throw Error("E_DEBUG","debug-symbol packaging failed");
    writeFile((folder/"debug-symbols.complete").string(),hash(readFile(result.executable+".dSYM/Contents/Resources/DWARF/app"))+"\n");
  }
  if(!result.notices.empty())writeFile(result.notices,notices);
  if(options.taskDebug){
    debugText=debugTextFor();auto verified=llvm::json::parse(debugText);auto image=verified->getAsObject()->getObject("task_debug");
    if(image->getString("image_sha256")->empty()||image->getString("image_uuid")->empty())throw Error("E_DEBUG_INIT","linked task debug image has no verified identity");
    writeFile(debugFile,debugText);
  }
  llvm::json::Array runtimeComponents;for(const auto &component:components)runtimeComponents.push_back(component);
  llvm::json::Object runtimeInputs;for(const auto &[file,contents]:runtimeFiles)runtimeInputs[file]=hash(contents);
  llvm::json::Object functionContracts;for(const auto &[name,digest]:result.functionContracts)functionContracts[name]=digest;
  writeFile((folder/"library-abi.json").string(),json(llvm::json::Object{{"schema","nex.native-library-abi/1"},{"abi",result.libraryABI},{"compiler_build",NEX_BUILD_ID},{"target",target},{"code_only",options.codeOnlyLibrary},{"function_contracts",std::move(functionContracts)},{"static_libraries",llvm::json::Array(libraryInputs)}})+"\n");
  writeFile((folder/"build.json").string(),json(llvm::json::Object{{"schema","nex.build/1"},{"task_limits",taskLimitsJSON(options.taskLimits,tasks)},{"task_file_reads",taskFileReads},{"task_debug",options.taskDebug},{"task_debug_metadata_hash",taskDebugHash},{"task_limits_specified",options.taskLimitsSpecified},{"revision",revision(p)},{"key",key},{"compiler_build",NEX_BUILD_ID},{"profile",options.profile},{"target",target},{"host",host},{"host_compatible",toolchain.hostCompatible},{"toolchain_inputs",toolchain.identity},{"compiler_target",compilerTarget},{"data_layout",dataLayout},{"linker",toolchain.linker},{"kind",options.deferredLink?"object_archive":server?"http_server":options.libraryEntry?"static_library":"executable"},{"final_kind",server?"http_server":options.libraryEntry?"static_library":"executable"},{"position_independent",options.positionIndependent},{"deferred_link",options.deferredLink},{"entry",options.entry},{"foreign_catalogue",options.foreignCatalogue},{"compiler",compiler},{"compiler_identity",identity.output},{"llvm",LLVM_VERSION_STRING},{"source_projection",snapshot.path},{"runtime_source_projection",runtimeProjection.string()},{"toolchain_fingerprint",toolchainFingerprint},{"runtime_components",std::move(runtimeComponents)},{"runtime_inputs",std::move(runtimeInputs)},{"runtime_requirements",llvm::json::Object{{"wire",wire},{"storage",storage},{"files",files},{"foreign",foreign},{"profiling",profiling},{"parallel",parallel},{"tasks",tasks},{"task_file_reads",taskFileReads},{"task_debug",options.taskDebug}}},{"notices",result.notices},{"compilation",result.compilation},{"compiled_modules",result.compiledModules},{"reused_modules",result.reusedModules},{"completion_schema","nex.native-completion/2"},{"completion_inputs",llvm::json::Array(completionInputs)}}));
  verifyToolchain();writeFile((folder/"complete").string(),completion());return result;
}
}
