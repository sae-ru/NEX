#include "nex/backend.h"
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
#include <filesystem>
#include <sstream>
#include <functional>
#include <random>
#include <tuple>

namespace nex {
namespace {
std::set<std::string> reachable(const Program &p,const std::string &entry){
  std::set<std::string> names;std::function<void(const Function&)> visit=[&](const Function &f){if(names.insert(f.name).second)for(const auto &name:f.dependencies)visit(p.function(name));};
  visit(p.function(entry));return names;
}
const Function &nativeEntry(const Program &p,const std::string &entry,bool testEntry,bool libraryEntry){
  const auto &main=p.function(entry);
  if(!main.typeParameters.empty()||std::any_of(main.typeArguments.begin(),main.typeArguments.end(),containsParameter))throw Error("E_GENERIC_ENTRY","entry must be a concrete generic specialization or a non-generic function",main.span);
  if(!libraryEntry&&(!main.params.empty()||(main.result!=Type::I64&&main.result!=Type::Unit)))throw Error("E_ENTRY","entry must take no arguments and return i64 or unit",main.span);
  if(main.realm=="client")throw Error("E_REALM","client entry cannot be built for a native server target",main.span);
  if(main.test!=testEntry)throw Error("E_ENTRY",testEntry?"entry is not a test":"test cannot be the application entry",main.span);
  return main;
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
class Emitter {
  const Program &p; DebugInfo debug; std::ostringstream out,globals; unsigned serial=0;bool prologue=false,profiling=false;
  std::vector<std::map<std::string,Value>> scopes;
  std::map<const Stmt*,std::string> slots;std::map<const Pattern*,std::string> patternSlots;std::map<const Expr*,std::string> shortSlots,matchSlots,matchResults;
  OperationIndex ownedSites;const OperationIndex &sites;std::string activeSite;
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
    std::string operands,types;
    for(const auto &a:args){if(!operands.empty()){operands+=", ";types+=", ";}operands+=a.name;types+=ty(a.type);}
    auto n=result==Type::Unit?"":fresh();
    line((n.empty()?"":n+" = ")+"func.call @"+name+"("+operands+") : ("+types+") -> "+ty(result),span);return {n,result};
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
  Value rawBytes(const std::string &text,Span span){
    static const char *hex="0123456789ABCDEF";std::string escaped;
    for(unsigned char c:text){escaped+='\\';escaped+=hex[c>>4];escaped+=hex[c&15];}
    escaped+="\\00";auto symbol="nex_bytes_"+std::to_string(serial++),n=fresh();
    globals<<"  llvm.mlir.global private constant @"<<symbol<<"(\""<<escaped<<"\")\n";
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
      line(function+" = func.constant @"+closureSymbol(target)+" : "+signature,e->span);line(pointer+" = builtin.unrealized_conversion_cast "+function+" : "+signature+" to !llvm.ptr",e->span);
      auto count=[&](int64_t value){return constant(value,Type::I64,e->span);};auto closure=call("nex_closure_new",{{pointer,Type::Str},count(e->args.size())},e->type,e->span);
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
      }else if(e->text=="print"){
        result=args[0].type.heap()?call("nex_print_heap",{args[0]},Type::Unit,e->span):args[0].type==Type::F64?call("nex_print_f64",{args[0]},Type::Unit,e->span):call(args[0].type==Type::Bool?"nex_print_bool":"nex_print_i64",{asI64(args[0],e->span)},Type::Unit,e->span);
      }else if(e->text=="assert")result=call("nex_assert",{asI64(args[0],e->span),c(e->span.line)},Type::Unit,e->span);
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
      else if(e->text=="file_read_text"||e->text=="file_write_text"||e->text=="file_read_bytes"||e->text=="file_write_bytes"){
        auto operands=args;operands.push_back(c(e->span.line));result=call("nex_"+e->text,operands,e->type,e->span);
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
    Value a=expression(e->args[0]);
    if(e->kind==Expr::Unary){
      if(e->text=="-")return call(a.type==Type::F64?"nex_f64_neg":"nex_neg",{a,constant(e->span.line,Type::I64,e->span)},a.type,e->span);
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
    if(arithmetic.contains(op))return call("nex_"+arithmetic.at(op),{a,b,constant(e->span.line,Type::I64,e->span)},Type::I64,e->span);
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
        Value value;if(s->expr)value=expression(s->expr);cleanupAll(s->span);
        if(profiling)call("nex_profile_leave",{},Type::Unit,s->span);
        line(!s->expr||value.type==Type::Unit?"func.return":"func.return "+value.name+" : "+ty(value.type),s->span);returned=true;break;
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
    out<<"  func.func private @"<<name<<"("<<arguments<<")"<<(result.empty()?"":" -> "+result)<<"\n";
  }
public:
  explicit Emitter(const Program &p,bool optimized=false,bool profiling=false,const OperationIndex *sharedSites=nullptr):p(p),debug(p,optimized),profiling(profiling),sites(sharedSites?*sharedSites:ownedSites){if(!sharedSites)for(const auto &f:p.functions)for(const auto &o:operationTree(p,f))if(o.ast)ownedSites[o.ast]=o.site;}
  std::string run(const std::string &entry,bool testEntry,bool libraryEntry,const std::set<std::string> *selected=nullptr){
    const auto &main=nativeEntry(p,entry,testEntry,libraryEntry);
    out<<"module {\n";
    for(auto name:{"add","sub","mul","div","mod"})declaration("nex_"+std::string(name),"i64, i64, i64","i64");
    for(auto name:{"add","sub","mul","div","mod"})declaration("nex_f64_"+std::string(name),"f64, f64, i64","f64");
    declaration("nex_f64_neg","f64, i64","f64");declaration("nex_f64_validate","f64, i64","f64");declaration("nex_f64_compare","f64, f64, i64, i64","i64");
    declaration("nex_as_f64","i64, i64","f64");declaration("nex_as_i64","f64, i64","!llvm.ptr");declaration("nex_print_f64","f64");
    declaration("nex_neg","i64, i64","i64");declaration("nex_print_i64","i64");declaration("nex_print_bool","i64");declaration("nex_assert","i64, i64");declaration("nex_match_fail","i64");
    declaration("nex_retain","!llvm.ptr","!llvm.ptr");declaration("nex_release","!llvm.ptr");declaration("nex_runtime_finish","");
    declaration("nex_poll","i64");
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
    for(auto name:{"bytes_from_integers","utf8_bytes","decode_utf8","encode_base64","decode_base64"})declaration("nex_"+std::string(name),"!llvm.ptr, i64","!llvm.ptr");
    auto names=reachable(p,entry);
    auto bridges=nativeFunctionBridges(p,names);
    if(selected){
      names=*selected;std::set<std::string> external;
      for(const auto &name:names)for(const auto &callee:p.function(name).dependencies)if(!names.contains(callee))external.insert(callee);
      for(const auto &name:external){
        const auto &f=p.function(name);std::string args;
        if(f.closure)args="!llvm.ptr";for(const auto &param:f.params){if(!args.empty())args+=", ";args+=ty(param.type);}
        declaration(nativeSymbol(f.name),args,f.result==Type::Unit?"":ty(f.result));
        if(!f.closure&&bridges.contains(f.name))declaration(closureSymbol(f),"!llvm.ptr"+(args.empty()?"":", "+args),f.result==Type::Unit?"":ty(f.result));
      }
    }
    for(const auto &f:p.functions)if(names.contains(f.name)){
      debug.scope=debug.function(f);
      scopes.clear();scopes.emplace_back();slots.clear();matchSlots.clear();patternSlots.clear();shortSlots.clear();out<<"  func.func @"<<nativeSymbol(f.name)<<"(";
      std::string environment;if(f.closure){environment=fresh();out<<environment<<": !llvm.ptr";}
      for(size_t i=0;i<f.params.size();++i){if(i||f.closure)out<<", ";auto n=fresh();out<<n<<": "<<ty(f.params[i].type);scopes.back()[f.params[i].name]={n,f.params[i].type};}
      out<<")";if(f.result!=Type::Unit)out<<" -> "<<ty(f.result);out<<" {\n";
      prologue=true;
      for(size_t i=0;i<f.params.size();++i){
        const auto &param=f.params[i];auto slot=allocateSlot(param.type,param.span);
        if(param.type==Type::F64)scopes.back()[param.name]=call("nex_f64_validate",{scopes.back().at(param.name),constant(param.span.line,Type::I64,param.span)},Type::F64,param.span);
        // Debug storage borrows the parameter and never participates in cleanup.
        writeSlot(scopes.back().at(param.name),slot,param.span);describeStorage(param.name,param.type,param.span,slot,i+1+(f.closure?1:0));
      }
      for(size_t i=0;i<f.captures.size();++i){const auto &capture=f.captures[i];auto slot=allocateSlot(capture.type,capture.span);auto value=call(capture.type.heap()?"nex_collection_get_heap":"nex_collection_get_i64",{{environment,Type::Str},constant(i,Type::I64,capture.span),constant(capture.span.line,Type::I64,capture.span)},capture.type.heap()?capture.type:Type(Type::I64),capture.span);value=fromScalar(value,capture.type,capture.span);writeSlot(value,slot,capture.span);describeStorage(capture.name,capture.type,capture.span,slot);scopes.back()[capture.name]={slot,capture.type,true};}
      allocate(f.body);prologue=false;
      if(profiling){auto name=rawBytes(f.name,f.span),file=rawBytes(p.location(f.span),f.span),content=rawBytes(hash(json(canonical(f),false)),f.span);call("nex_profile_enter",{name,file,constant(f.span.line,Type::I64,f.span),content},Type::Unit,f.span);}
      call("nex_poll",{constant(f.span.line,Type::I64,f.span)},Type::Unit,f.span);
      if(!statements(f.body,false)){if(profiling)call("nex_profile_leave",{},Type::Unit,f.span);line("func.return",f.span);}out<<"  }"<<loc(f.span)<<"\n";
      if(!f.closure&&bridges.contains(f.name)){debug.scope.clear();out<<"  func.func @"<<closureSymbol(f)<<"(%closure_environment: !llvm.ptr";std::vector<Value> args;for(const auto &param:f.params){auto name=fresh();out<<", "<<name<<": "<<ty(param.type);args.push_back({name,param.type});}out<<")"<<(f.result==Type::Unit?"":" -> "+ty(f.result))<<" {\n";auto value=call(nativeSymbol(f.name),args,f.result,f.span);line(value.type==Type::Unit?"func.return":"func.return "+value.name+" : "+ty(value.type),f.span);out<<"  }\n";}
    }
    debug.scope.clear();out<<globals.str();if(libraryEntry||!names.contains(main.name)){out<<"}\n";return debug.str()+out.str();}out<<"  func.func @main() -> i32 {\n";
    auto value=call(nativeSymbol(main.name),{},main.result,main.span);call("nex_runtime_finish",{},Type::Unit,main.span);
    if(main.result==Type::I64){auto n=fresh();line(n+" = arith.trunci "+value.name+" : i64 to i32",main.span);line("func.return "+n+" : i32",main.span);}
    else{auto n=fresh();line(n+" = arith.constant 0 : i32",main.span);line("func.return "+n+" : i32",main.span);}
    out<<"  }"<<loc(main.span)<<"\n}\n";return debug.str()+out.str();
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
ProcessResult capture(const std::vector<std::string> &args,unsigned timeoutSeconds) {
  if(args.empty())throw Error("E_PROCESS","empty command");
  auto program=llvm::sys::findProgramByName(args[0]);if(!program)throw Error("E_TOOL","cannot find executable "+args[0]);
  llvm::SmallString<128> temporary;
  if(auto ec=llvm::sys::fs::createUniqueDirectory("nex-process",temporary))throw Error("E_FILE",ec.message());
  std::filesystem::path folder(temporary.str().str());
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
std::string emitMLIR(const Program &p,const std::string &entry,bool testEntry,bool libraryEntry){return Emitter(p).run(entry,testEntry,libraryEntry);}
BuildResult build(const Program &p,const std::string &directory,const BuildOptions &options) {
  if(options.profile!="debug"&&options.profile!="profile"&&options.profile!="release")throw Error("E_OPTION","profile must be debug, profile or release");
  auto host=llvm::sys::getDefaultTargetTriple();
  auto toolchain=configureNative(options);auto target=toolchain.target;
  bool server=options.target=="server";
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
  if(!driverABI.isArch64Bit()||driverABI.getArch()!=requestedABI.getArch()||driverABI.getEnvironment()!=requestedABI.getEnvironment()||
     !(driverABI.getOS()==requestedABI.getOS()||(driverABI.isMacOSX()&&requestedABI.isMacOSX()))||wrongDeployment||dataLayout.empty()||probeModule->getDataLayout().getPointerSizeInBits()!=64||driverABI.getSubArch()!=requestedABI.getSubArch())
    throw Error("E_TARGET","native compiler target "+compilerTarget+" does not match configured target "+target+" or has no data layout");
  auto environment=[](const char *name){const char *v=std::getenv(name);return v?std::string(v):std::string();};
  // Keep semantic identity separate from toolchain and source-projection identity.
  bool wire=server,storage=server,files=false;auto names=reachable(p,options.entry);auto callableTargets=nativeFunctionBridges(p,names);
  std::function<void(E)> inspect=[&](E e){if(e){if(e->kind==Expr::Call){if(e->text=="encode_json"||e->text=="decode_json")wire=true;if(e->text.starts_with("store_"))storage=true;if(e->text=="file_read_text"||e->text=="file_write_text"||e->text=="file_read_bytes"||e->text=="file_write_bytes")files=true;}for(auto arg:e->args)inspect(arg);}};
  std::function<void(const std::vector<S>&)> inspectBlock=[&](const auto &body){for(auto s:body){inspect(s->expr);childBlocks(s,inspectBlock);}};
  for(const auto &f:p.functions)if(names.contains(f.name))inspectBlock(f.body);
  if(storage&&(toolchain.sqliteInclude.empty()||toolchain.sqliteLibrary.empty()))throw Error("E_TARGET_LIBRARY","target storage requires sqlite include/library paths in --toolchain FILE; host libraries cannot be used for another architecture");
  if(server&&(toolchain.opensslInclude.empty()||toolchain.opensslSSL.empty()||toolchain.opensslCrypto.empty()))throw Error("E_TARGET_LIBRARY","target server requires openssl include/ssl/crypto paths in --toolchain FILE");
  bool profiling=options.profile=="profile";
  std::vector<std::string> components={"runtime.cpp"},headers={"nex_value.h","nex_bytes.h","nex_file_resource.h","nex_resource.h","nex_error.h","nex_float.h","nex_host.h","nex_io.h","nex_profile.h","third_party/dragonbox/dragonbox.h","third_party/dragonbox/manifest.json","third_party/dragonbox/LICENSE-Apache2-LLVM"};
  if(profiling)components.insert(components.end(),{"nex_profile.cpp","third_party/tracy/public/TracyClient.cpp"});
  if(wire){components.insert(components.end(),{"nex_json.cpp","wire_runtime.cpp"});headers.insert(headers.end(),{"nex_json.h","third_party/json.hpp"});}
  if(storage)components.insert(components.end(),{"nex_store.cpp","store_runtime.cpp"});
  if(files){components.insert(components.end(),{"nex_files.cpp","files_runtime.cpp"});headers.insert(headers.end(),{"nex_files.h","nex_file_abi.h"});}
  if(server){components.push_back("http_main.cpp");headers.insert(headers.end(),{"third_party/httplib.h","nex_auth.h"});}
  std::map<std::string,std::string> runtimeFiles;
  for(const auto &file:components)runtimeFiles[file]=readFile(resourceFile("runtime/"+file));for(const auto &file:headers)runtimeFiles[file]=readFile(resourceFile("runtime/"+file));
  std::string notices;
  auto license=[&](const std::string &name,const std::string &file){
    auto text=readFile(resourceFile("runtime/third_party/"+file));
    runtimeFiles["third_party/"+file]=text;
    notices+=name+"\n\n"+text+"\n\n";
  };
  license("Dragonbox 1.1.3", "dragonbox/LICENSE-Boost");
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
  std::string runtimeIdentity;for(const auto &[file,source]:runtimeFiles)runtimeIdentity+=file+source;
  if(storage)runtimeIdentity+=std::string(toolchain.sqliteInclude)+toolchain.sqliteLibrary+hash(readFile(toolchain.sqliteLibrary))+hash(readFile((std::filesystem::path(toolchain.sqliteInclude)/"sqlite3.h").string()));
  if(server)runtimeIdentity+=std::string(toolchain.opensslInclude)+toolchain.opensslSSL+toolchain.opensslCrypto+hash(readFile(toolchain.opensslSSL))+hash(readFile(toolchain.opensslCrypto))+hash(readFile((std::filesystem::path(toolchain.opensslInclude)/"openssl/ssl.h").string()));
  auto formatter=readFile(resourceFile("debug/lldb_nex.py"));auto dapAdapter=readFile(resourceFile("debug/nex_dap.py"));
  std::string key=hash(revision(p)+json(sourceBundle(p),false)+p.path+options.profile+target+toolchain.identity+compilerTarget+dataLayout+options.entry+std::to_string(options.libraryEntry)+std::to_string(server)+NEX_BUILD_ID+LLVM_VERSION_STRING+compiler+identity.output+runtimeIdentity+hash(formatter)+hash(dapAdapter)+environment("SDKROOT")+environment("MACOSX_DEPLOYMENT_TARGET"));
  auto folder=std::filesystem::absolute(std::filesystem::path(directory)/key);
  auto buildRoot=std::filesystem::absolute(directory);auto plan=planNative(p,options.entry);
  BuildResult result{(folder/(options.libraryEntry?"libnex.a":"app")).string(),(folder/"program.mlir").string(),(folder/"program.ll").string(),key,false,notices.empty()?"":(folder/"THIRD_PARTY_NOTICES.txt").string(),(folder/"compilation.json").string(),0,0,target,compilerTarget,toolchain.hostCompatible};
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
    debugFunctions.push_back(llvm::json::Object{{"name",f.name},{"native_symbol",nativeSymbol(f.name)},{"callable_symbol",f.closure||callableTargets.contains(f.name)?closureSymbol(f):""},{"operation_sites",operationSites(f,operations)}});
  }
  for(auto &[unitKey,unit]:snapshot.units){
    auto sourceKey=hash(json(llvm::json::Object{{"schema","nex.native-source/1"},{"unit",unitKey},{"module",unit.module},{"source",unit.source}},false));
    auto original=unit.path;unit.path=(buildRoot/"source-cache"/sourceKey/(unitKey==snapshot.entryUnit?"source.nex":unitKey)).string();
    if(unitKey==snapshot.entryUnit)snapshot.path=unit.path;
    auto anchor=(buildRoot/"source-anchors"/hash(json(llvm::json::Array{unitKey,unit.module},false))/(unitKey==snapshot.entryUnit?"source.nex":unitKey)).string();
    debugAnchors[unitKey]=anchor;
    debugSourceMap.push_back(llvm::json::Array{std::filesystem::path(anchor).parent_path().string(),std::filesystem::path(unit.path).parent_path().string()});
    debugSources.push_back(llvm::json::Object{{"original",original},{"projection",unit.path},{"debug_path",anchor},{"hash",hash(unit.source)}});
  }
  if(snapshot.units.empty()){
    snapshot.path=(buildRoot/"source-cache"/hash(p.source)/"source.nex").string();
    debugAnchors[""]=(buildRoot/"source-anchors"/hash(p.module)/"source.nex").string();
    debugSourceMap.push_back(llvm::json::Array{std::filesystem::path(debugAnchors.at("")).parent_path().string(),std::filesystem::path(snapshot.path).parent_path().string()});
    debugSources.push_back(llvm::json::Object{{"original",p.path},{"projection",snapshot.path},{"debug_path",debugAnchors.at("")},{"hash",hash(p.source)}});
  }
  // Objects refer to stable virtual paths. A session maps these paths to its
  // immutable complete sources, so sibling edits need not invalidate DWARF.
  auto codeSnapshot=snapshot;
  for(auto &[unitKey,unit]:codeSnapshot.units)unit.path=debugAnchors.at(unitKey);
  codeSnapshot.path=debugAnchors.at(snapshot.units.empty()?"":snapshot.entryUnit);
  auto nativeSeed=json(llvm::json::Object{{"schema","nex.native-toolchain/1"},{"compiler_build",NEX_BUILD_ID},{"llvm",LLVM_VERSION_STRING},
    {"compiler",compiler},{"compiler_identity",identity.output},{"compiler_target",compilerTarget},{"data_layout",dataLayout},{"profile",options.profile},{"target",target},{"host",host},{"host_compatible",toolchain.hostCompatible},{"toolchain_inputs",toolchain.identity},
    {"sdkroot",environment("SDKROOT")},{"deployment",environment("MACOSX_DEPLOYMENT_TARGET")}},false);
  std::vector<std::string> unitKeys;std::vector<llvm::json::Value> unitInputs;std::vector<NativeArtifact> unitArtifacts(plan.units.size());
  bool nativeIntact=true;std::set<std::string> sourceUnits,compiledSourceUnits;
  for(size_t i=0;i<plan.units.size();++i){
    const auto &unit=plan.units[i];auto source=codeSnapshot.units.contains(unit.unit)?codeSnapshot.units.at(unit.unit).path:codeSnapshot.path;sourceUnits.insert(unit.unit);
    std::string runtimeABI;
    for(const auto &file:{"runtime.cpp","nex_value.h","nex_bytes.h","nex_file_resource.h","nex_resource.h","nex_error.h","nex_float.h","third_party/dragonbox/dragonbox.h","nex_host.h","nex_io.h","nex_profile.h"})runtimeABI+=file+hash(runtimeFiles.at(file));
    if(profiling)runtimeABI+="nex_profile.cpp"+hash(runtimeFiles.at("nex_profile.cpp"));
    if(unit.wire)for(const auto &file:{"wire_runtime.cpp","nex_json.h"})runtimeABI+=file+hash(runtimeFiles.at(file));
    if(unit.storage)runtimeABI+="store_runtime.cpp"+hash(runtimeFiles.at("store_runtime.cpp"));
    if(unit.files)for(const auto &file:{"files_runtime.cpp","nex_files.h","nex_file_abi.h"})runtimeABI+=file+hash(runtimeFiles.at(file));
    auto wrapper=!options.libraryEntry&&!server&&unit.functions.contains(p.function(options.entry).name)?p.function(options.entry).name:"";
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
  auto debugText=json(llvm::json::Object{{"schema","nex.debug/1"},{"toolchain",NEX_VERSION},{"language",languageVersion},{"runtime_view","nex.runtime-view/3"},{"expression_protocol","nex.debug-expression/3"},{"compiler_build",NEX_BUILD_ID},{"source_hash",hash(json(sourceBundle(p),false))},{"revision",revision(p)},{"build_key",key},{"program",result.executable},{"profile",options.profile},{ "target",target},{"compiler_target",compilerTarget},{"host_compatible",toolchain.hostCompatible},{"formatter",formatterFile},{"formatter_hash",hash(formatter)},{"dap_adapter",adapterFile},{"dap_adapter_hash",hash(dapAdapter)},{"heap_types",std::move(heapTypes)},{"sources",std::move(debugSources)},{"source_map",std::move(debugSourceMap)},{"functions",std::move(debugFunctions)}})+"\n";
  auto debugIntact=[&](){
    if(!std::filesystem::is_regular_file(debugFile)||readFile(debugFile)!=debugText||!std::filesystem::is_regular_file(formatterFile)||readFile(formatterFile)!=formatter||!std::filesystem::is_regular_file(adapterFile)||readFile(adapterFile)!=dapAdapter)return false;
    for(const auto &[unitKey,unit]:snapshot.units){
      auto mirror=unitKey==snapshot.entryUnit?folder/"source.nex":folder/"sources"/unitKey;
      if(!std::filesystem::is_regular_file(unit.path)||readFile(unit.path)!=unit.source||!std::filesystem::is_regular_file(mirror)||readFile(mirror.string())!=unit.source)return false;
    }
    if(snapshot.units.empty()&&(!std::filesystem::is_regular_file(snapshot.path)||readFile(snapshot.path)!=snapshot.source))return false;
    if(!options.libraryEntry&&driverABI.isOSDarwin()){
      auto symbols=result.executable+".dSYM/Contents/Resources/DWARF/app";auto marker=folder/"debug-symbols.complete";
      if(!std::filesystem::is_regular_file(symbols)||!std::filesystem::is_regular_file(marker)||readFile(marker.string())!=hash(readFile(symbols))+"\n")return false;
    }
    return true;
  };
  auto completion=[&](){
    std::string contents=key;
    for(const auto &file:{std::filesystem::path(result.executable),std::filesystem::path(result.mlir),std::filesystem::path(result.llvm),std::filesystem::path(result.compilation),folder/"build.json",folder/"source-bundle.json"})contents+=hash(readFile(file.string()));
    return hash(contents)+"\n";
  };
  auto buildIntact=[&](){try{return readFile((folder/"complete").string())==completion();}catch(const std::exception &){return false;}};
  if(buildIntact()&&(result.notices.empty()||(std::filesystem::is_regular_file(result.notices)&&readFile(result.notices)==notices))&&debugIntact()&&nativeIntact){result.cached=true;result.reusedModules=sourceUnits.size();result.reusedFunctions=plan.units.size();return result;}
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
  auto mlir=Emitter(snapshot,options.profile!="debug",profiling,&operationIndex).run(options.entry,options.testEntry,options.libraryEntry||server);writeFile(result.mlir,mlir);
  std::string optimization=options.profile=="debug"?"-O0":"-O2";
  auto link=toolchain.driver;llvm::json::Array compiledUnits;
  for(size_t i=0;i<plan.units.size();++i){
    const auto &unit=plan.units[i];auto &artifact=unitArtifacts[i];
    if(!artifact.reused){
      llvm::SmallString<128> temporary;
      if(auto ec=llvm::sys::fs::createUniqueDirectory("nex-native-unit",temporary))throw Error("E_FILE",ec.message());
      std::filesystem::path stage(temporary.str().str());
      try{
        auto unitSnapshot=codeSnapshot;if(unitSnapshot.units.contains(unit.unit))unitSnapshot.path=unitSnapshot.units.at(unit.unit).path;
        artifact.mlir=Emitter(unitSnapshot,options.profile!="debug",profiling,&operationIndex).run(options.entry,options.testEntry,options.libraryEntry||server,&unit.functions);
        writeFile((stage/"program.mlir").string(),artifact.mlir);artifact.llvm=lower(artifact.mlir,unitSnapshot.path,compilerTarget,dataLayout);writeFile((stage/"program.ll").string(),artifact.llvm);
        auto compile=command({"-c",(stage/"program.ll").string(),"-o",(stage/"program.o").string(),"-g",optimization});
        if(options.profile=="profile")compile.push_back("-fno-omit-frame-pointer");
        if(execute(compile)!=0)throw Error("E_LINK","native unit compiler failed");
        artifact.object=readFile((stage/"program.o").string());saveArtifact(buildRoot,unitKeys[i],artifact);std::filesystem::remove_all(stage);
      }catch(const Error &error){throw Error(error.code,std::string(error.what())+"; intermediate files retained at "+stage.string(),error.span);}
      ++result.compiledFunctions;compiledSourceUnits.insert(unit.unit);
    }else ++result.reusedFunctions;
    auto destination=folder/"units"/hash(unit.identity);writeFile((destination/"program.mlir").string(),artifact.mlir);writeFile((destination/"program.ll").string(),artifact.llvm);
    auto object=folder/("nex-unit-"+hash(unit.identity)+".o");writeFile(object.string(),artifact.object);link.push_back(object.string());
    llvm::json::Array functions;for(const auto &name:unit.functions)functions.push_back(name);
    compiledUnits.push_back(llvm::json::Object{{"identity",unit.identity},{"unit",unit.unit},{"module",unit.module},{"input_key",unitKeys[i]},{"artifact_key",artifact.id},{"reused",artifact.reused},
      {"inputs",std::move(unitInputs[i])},
      {"functions",std::move(functions)},{"object",object.string()},{"object_hash",hash(artifact.object)},{"mlir",(destination/"program.mlir").string()},{"llvm",(destination/"program.ll").string()},
      {"cache_record",(buildRoot/"native-cache"/(unitKeys[i]+".json")).string()},{"source",snapshot.units.contains(unit.unit)?snapshot.units.at(unit.unit).path:snapshot.path}});
  }
  result.compiledModules=compiledSourceUnits.size();result.reusedModules=sourceUnits.size()-compiledSourceUnits.size();
  writeFile(result.llvm,linkIR(unitArtifacts,snapshot.path));
  writeFile(result.compilation,json(llvm::json::Object{{"schema","nex.compilation/1"},{"granularity","function"},{"revision",revision(p)},{"build_key",key},
    {"compiled_modules",result.compiledModules},{"reused_modules",result.reusedModules},{"compiled_functions",result.compiledFunctions},{"reused_functions",result.reusedFunctions},{"units",std::move(compiledUnits)},{"dependencies",std::move(plan.dependencies)}})+"\n");
  for(const auto &component:components){
    auto source=(runtimeProjection/component).string();auto runtimeKey=hash("nex.runtime-object/2"+runtimeProjection.string()+runtimeIdentity+component+compiler+identity.output+optimization+options.profile+target+toolchain.identity+compilerTarget+dataLayout+environment("SDKROOT")+environment("MACOSX_DEPLOYMENT_TARGET"));
    auto cache=std::filesystem::absolute(std::filesystem::path(directory)/"runtime-cache"/runtimeKey);auto cached=cache/"runtime.o",marker=cache/"complete";
    std::filesystem::create_directories(cache);
    if(!std::filesystem::is_regular_file(cached)||!std::filesystem::is_regular_file(marker)||readFile(marker.string())!=hash(readFile(cached.string()))+"\n"){
      auto temporary=cache/("runtime-"+std::to_string(std::random_device{}())+".o");
      auto arguments=command({"-std=c++20","-c",source,"-I",runtimeProjection.string(),"-o",temporary.string(),"-g",optimization});
      if(component=="http_main.cpp")arguments.insert(arguments.end(),{"-I",toolchain.opensslInclude,"-pthread"});
      if(options.profile=="profile")arguments.push_back("-fno-omit-frame-pointer");
      if(profiling){
        arguments.insert(arguments.end(),{"-DNEX_PROFILE_ENABLED","-DTRACY_ENABLE","-DTRACY_ON_DEMAND","-DTRACY_DELAYED_INIT","-DTRACY_MANUAL_LIFETIME","-DTRACY_ONLY_LOCALHOST","-DTRACY_NO_BROADCAST","-DTRACY_NO_CODE_TRANSFER","-DTRACY_NO_CALLSTACK","-DTRACY_NO_SYSTEM_TRACING","-DTRACY_NO_SAMPLING","-DTRACY_NO_CRASH_HANDLER","-DTRACY_NO_FRAME_IMAGE","-pthread"});
      }
      if(execute(arguments)!=0)throw Error("E_LINK","runtime compilation failed; artifacts retained at "+cache.string());
      auto digest=hash(readFile(temporary.string()));std::filesystem::rename(temporary,cached);writeFile(marker.string(),digest+"\n");
    }
    auto destination=folder/std::filesystem::path(component).replace_extension(".o");
    std::filesystem::create_directories(destination.parent_path());
    copyFile(cached.string(),destination.string(),true);link.push_back(destination.string());
  }
  if(server){
    auto bridge=(folder/"server-bridge.cpp").string(),bridgeObject=(folder/"server-bridge.o").string();auto name=nativeSymbol(p.function(options.entry).name);
    writeFile(bridge,"#include \"nex_host.h\"\nextern \"C\" nexrt::Handle *"+name+"(nexrt::Handle*);\nextern \"C\" nexrt::Handle *nex_server_dispatch(nexrt::Handle *value){ return "+name+"(value); }\n");
    auto bridgeCompile=command({"-std=c++20","-c",bridge,"-I",runtimeProjection.string(),"-o",bridgeObject,"-g",optimization});
    if(profiling)bridgeCompile.push_back("-DNEX_PROFILE_ENABLED");
    if(execute(bridgeCompile)!=0)throw Error("E_LINK","HTTP bridge compilation failed");
    link.push_back(bridgeObject);link.push_back(toolchain.opensslSSL);link.push_back(toolchain.opensslCrypto);link.push_back("-pthread");
  }
  if(profiling){
    // Whole-build identity lives in a tiny link unit, preserving reuse of NEX
    // module objects across unrelated body edits and different entry programs.
    auto identity=json(llvm::json::Object{{"schema","nex.profile-build/1"},{"toolchain",NEX_VERSION},{"language",languageVersion},{"revision",revision(p)},{"build_key",key},{"entry",p.function(options.entry).name}},false);
    auto source=(folder/"profile-identity.cpp").string(),object=(folder/"profile-identity.o").string();
    writeFile(source,"extern \"C\" const char *nex_profile_build_info(){return "+json(identity,false)+";}\n");
    if(execute(command({"-std=c++20","-c",source,"-o",object,optimization}))!=0)throw Error("E_LINK","profile identity compilation failed");link.push_back(object);
  }
  if(profiling&&!options.libraryEntry){link.push_back("-pthread");if(driverABI.isOSLinux())link.push_back("-ldl");}
  // LLVM ELF/archive writers use '%' as a temporary-file template marker.
  // Stage their output in an independent directory so literal project paths
  // (including percent signs) are never interpreted as that template.
  std::filesystem::path linkStage;auto linkOutput=result.executable;
  if(driverABI.isOSLinux()||options.libraryEntry){
    llvm::SmallString<128> temporary;
    if(auto ec=llvm::sys::fs::createUniqueDirectory("nex-link",temporary))throw Error("E_FILE",ec.message());
    linkStage=temporary.str().str();linkOutput=(linkStage/std::filesystem::path(result.executable).filename()).string();
  }
  if(options.libraryEntry){
    std::vector<std::string> archive={toolchain.archiver,"rcs",linkOutput};archive.insert(archive.end(),link.begin()+toolchain.driver.size(),link.end());link=std::move(archive);
  }else {
    if(!toolchain.linker.empty())link.push_back("--ld-path="+toolchain.linker);
    if(storage)link.push_back(toolchain.sqliteLibrary);
    if(driverABI.isOSDarwin()||driverABI.isOSLinux()) {
      // Select configured dynamic dependencies at execution time as well as
      // link time. Separate arguments keep commas/Unicode literal.
      std::set<std::string> libraryPaths;
      if(storage)libraryPaths.insert(std::filesystem::path(toolchain.sqliteLibrary).parent_path().string());
      if(server)for(const auto &library:{toolchain.opensslSSL,toolchain.opensslCrypto})libraryPaths.insert(std::filesystem::path(library).parent_path().string());
      for(const auto &path:libraryPaths){
        if(driverABI.isOSLinux()&&path.find(':')!=std::string::npos)throw Error("E_TARGET_LIBRARY","ELF library directories cannot contain ':' (runtime search-path separator): "+path);
        link.insert(link.end(),{"-Xlinker","-rpath","-Xlinker",path});
      }
    }
    link.insert(link.end(),{"-o",linkOutput,"-g"});
  }
  if(execute(link)!=0)throw Error("E_LINK","native linker failed; intermediate files retained at "+folder.string()+(linkStage.empty()?"":"; link output at "+linkStage.string()));
  if(!linkStage.empty()){
    try{copyFile(linkOutput,result.executable,true);std::filesystem::remove_all(linkStage);}
    catch(const Error &e){throw Error(e.code,std::string(e.what())+"; link output retained at "+linkStage.string(),e.span);}
  }
  if(!options.libraryEntry&&driverABI.isOSDarwin()) {
    auto dsym=toolchain.debugPackager;
    if(execute({dsym,result.executable,"-o",result.executable+".dSYM"})!=0)throw Error("E_DEBUG","debug-symbol packaging failed");
    writeFile((folder/"debug-symbols.complete").string(),hash(readFile(result.executable+".dSYM/Contents/Resources/DWARF/app"))+"\n");
  }
  if(!result.notices.empty())writeFile(result.notices,notices);
  llvm::json::Array runtimeComponents;for(const auto &component:components)runtimeComponents.push_back(component);
  writeFile((folder/"build.json").string(),json(llvm::json::Object{{"schema","nex.build/1"},{"revision",revision(p)},{"key",key},{"compiler_build",NEX_BUILD_ID},{"profile",options.profile},{"target",target},{"host",host},{"host_compatible",toolchain.hostCompatible},{"toolchain_inputs",toolchain.identity},{"compiler_target",compilerTarget},{"data_layout",dataLayout},{"linker",toolchain.linker},{"kind",server?"http_server":options.libraryEntry?"static_library":"executable"},{"entry",options.entry},{"compiler",compiler},{"compiler_identity",identity.output},{"llvm",LLVM_VERSION_STRING},{"source_projection",snapshot.path},{"runtime_source_projection",runtimeProjection.string()},{"runtime_components",std::move(runtimeComponents)},{"notices",result.notices},{"compilation",result.compilation},{"compiled_modules",result.compiledModules},{"reused_modules",result.reusedModules}}));
  writeFile((folder/"complete").string(),completion());return result;
}
}
