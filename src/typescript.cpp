#include "nex/web.h"
#include "nex/operations.h"
#include <algorithm>
#include <functional>
#include <filesystem>
#include <cctype>
#include <sstream>

namespace nex {
namespace {
std::string quote(const std::string &text){return json(llvm::json::Value(text),false);}
std::string symbol(const std::string &name){return nativeSymbol(name);}
std::string type(const Type &t){
  switch(t.kind){
  case Type::I64:return "bigint";
  case Type::Bool:return "boolean";
  case Type::Str:return "string";
  case Type::Unit:return "void";
  case Type::List:return "ReadonlyArray<"+type(*t.element)+">";
  case Type::Result:return "nex.Result<"+type(*t.element)+">";
  case Type::Record:return "T_"+symbol(t.name);
  default:throw Error("E_INTERNAL","unresolved TypeScript type");
  }
}
class Generator {
  const Program &p;
  std::set<std::string> functions,structures;
  std::vector<std::map<std::string,std::string>> scopes;
  unsigned unique=0,depth=0,line=1;
  std::ostringstream out;
  llvm::json::Array mappings;
  std::map<const void*,std::string> sites;
  void write(const std::string &text){out<<text;line+=std::count(text.begin(),text.end(),'\n');}
  void statement(const std::string &text){write(std::string(depth*2,' ')+text+"\n");}
  std::string site(E e){const auto &s=e->span;return "["+quote(s.file)+", "+std::to_string(s.line)+", "+std::to_string(s.column)+", "+quote(sites.at(e.get()))+"]";}
  void needed(const Type &t){
    if(t.kind==Type::List||t.kind==Type::Result)needed(*t.element);
    if(t.kind==Type::Record&&structures.insert(t.name).second)for(auto field:p.structure(t.name).members())needed(field->type);
  }
  void visit(const Function &f){
    if(f.realm=="server")throw Error("E_REALM","server function cannot be emitted to the browser: "+f.name,f.span);
    if(!functions.insert(f.name).second)return;
    needed(f.result);for(const auto &param:f.params)needed(param.type);
    std::function<void(E)> expression=[&](E e){if(e){needed(e->type);for(auto a:e->args)expression(a);}};
    std::function<void(const std::vector<S>&)> block=[&](const auto &body){for(auto s:body){needed(s->type);expression(s->expr);childBlocks(s,block);}};
    block(f.body);for(const auto &name:f.dependencies)visit(p.function(name));
  }
  std::string local(const std::string &name){
    for(auto i=scopes.rbegin();i!=scopes.rend();++i)if(i->contains(name))return i->at(name);
    throw Error("E_INTERNAL","TypeScript local not found: "+name);
  }
  std::string declare(const std::string &name){auto result="v"+std::to_string(++unique)+"_"+name;scopes.back()[name]=result;return result;}
  std::string expr(E e){
    switch(e->kind){
    case Expr::Integer:return "("+std::to_string(e->number)+"n)";
    case Expr::Boolean:return e->number?"true":"false";
    case Expr::String:return quote(e->text);
    case Expr::Name:return local(e->text);
    case Expr::List:{std::string text="nex.list<"+type(*e->type.element)+">([";for(size_t i=0;i<e->args.size();++i){if(i)text+=", ";text+=expr(e->args[i]);}return text+"])";}
    case Expr::Field:return "("+expr(e->args[0])+")["+quote(e->text)+"]";
    case Expr::Index:return "nex."+std::string(e->args[0]->type==Type::Str?"character":"index")+"("+expr(e->args[0])+", "+expr(e->args[1])+", "+site(e)+")";
    case Expr::Unary:return e->text=="!"?"(!"+expr(e->args[0])+")":"nex.neg("+expr(e->args[0])+", "+site(e)+")";
    case Expr::Binary:{
      auto a=expr(e->args[0]),b=expr(e->args[1]);const auto &op=e->text;
      if(op=="=="||op=="!=")return (op=="!="?"!":"")+std::string("nex.equal(")+a+", "+b+")";
      if(op=="+"&&e->type==Type::Str)return "("+a+" + "+b+")";
      if(op=="+"&&e->type.kind==Type::List)return "nex.concat("+a+", "+b+")";
      const std::map<std::string,std::string> arithmetic={{"+","add"},{"-","sub"},{"*","mul"},{"/","div"},{"%","rem"}};
      if(arithmetic.contains(op))return "nex."+arithmetic.at(op)+"("+a+", "+b+", "+site(e)+")";
      return "("+a+" "+op+" "+b+")";
    }
    case Expr::Call:{
      if(e->text=="err")return "nex.err<"+type(*e->type.element)+">("+expr(e->args[0])+", "+expr(e->args[1])+")";
      if(e->text=="decode_json")return "nex.decodeJSON<"+type(e->annotation)+">("+expr(e->args[0])+", "+json(wireSchema(p,e->annotation),false)+")";
      if(const Structure *owner=nullptr;auto variant=p.variant(e->text,&owner)){
        std::string text="nex.enumeration<"+type(e->type)+">("+quote(owner->name)+", "+quote(variant->name)+", [";
        for(size_t i=0;i<e->args.size();++i){if(i)text+=", ";text+="["+quote(variant->fields[i].name)+", "+expr(e->args[i])+"]";}return text+"])";
      }
      if(p.hasStructure(e->text)){
        const auto &s=p.structure(e->text);std::string text="nex.record<"+type(e->type)+">("+quote(s.name)+", [";
        for(size_t i=0;i<e->args.size();++i){if(i)text+=", ";text+="["+quote(s.fields[i].name)+", "+expr(e->args[i])+"]";}return text+"])";
      }
      const std::map<std::string,std::string> builtins={{"print","print"},{"assert","assert"},{"len","length"},{"str","str"},{"push","push"},{"set","set"},{"slice","slice"},{"contains","contains"},{"ok","ok"},{"is_ok","isOk"},{"unwrap","unwrap"},{"error_code","errorCode"},{"error_message","errorMessage"},{"encode_json","encodeJSON"}};
      std::string text=(builtins.contains(e->text)?"nex."+builtins.at(e->text):symbol(e->text))+"(";
      for(size_t i=0;i<e->args.size();++i){if(i)text+=", ";text+=expr(e->args[i]);}
      if(e->text=="assert"||e->text=="set"||e->text=="slice"||e->text=="unwrap"||e->text=="encode_json")text+=", "+site(e);
      return text+")";
    }
    }
    throw Error("E_INTERNAL","unsupported TypeScript expression");
  }
  void block(const std::vector<S> &body,bool scoped=true){
    if(scoped)scopes.emplace_back();
    for(auto s:body){
      auto start=line;
      switch(s->kind){
      case Stmt::Let:case Stmt::Var:{auto value=expr(s->expr);auto name=declare(s->name);statement(std::string(s->kind==Stmt::Let?"const ":"let ")+name+": "+type(s->type)+" = "+value+";");break;}
      case Stmt::Assign:statement(local(s->name)+" = "+expr(s->expr)+";");break;
      case Stmt::Expression:statement(expr(s->expr)+";");break;
      case Stmt::Return:statement(s->expr?"return "+expr(s->expr)+";":"return;");break;
      case Stmt::If:
        statement("if ("+expr(s->expr)+") {");++depth;block(s->body);--depth;
        if(!s->alternative.empty()){statement("} else {");++depth;block(s->alternative);--depth;}statement("}");break;
      case Stmt::Match:{
        auto subject="match_"+std::to_string(++unique);statement("{");++depth;statement("const "+subject+" = "+expr(s->expr)+";");statement("switch ("+subject+"[nex.CASE]) {");++depth;
        for(auto arm:s->arms){auto variant=p.variant(arm->variant);statement("case "+quote(variant->name)+": {");++depth;scopes.emplace_back();
          for(size_t i=0;i<arm->bindings.size();++i){const auto &binding=arm->bindings[i];if(binding.name!="_")statement("const "+declare(binding.name)+": "+type(binding.type)+" = "+subject+"["+quote(variant->fields[i].name)+"];");}
          block(arm->body,false);statement("break;");scopes.pop_back();--depth;statement("}");
        }
        statement("default: nex.invalidEnum("+site(s->expr)+");");--depth;statement("}");--depth;statement("}");break;
      }
      case Stmt::While:statement("while ("+expr(s->expr)+") {");++depth;block(s->body);--depth;statement("}");break;
      }
      mappings.push_back(llvm::json::Object{{"site",sites.at(s.get())},{"generated_line",int64_t(start)},{"file",s->span.file},{"line",int64_t(s->span.line)},{"column",int64_t(s->span.column)}});
    }
    if(scoped)scopes.pop_back();
  }
public:
  explicit Generator(const Program &p):p(p){for(const auto &f:p.functions)for(const auto &o:operationTree(p,f))if(o.ast)sites[o.ast]=o.site;}
  WebModule run(const std::map<std::string,std::string> &entries){
    if(entries.empty())throw Error("E_ENTRY","TypeScript requires at least one entry");
    for(const auto &[alias,name]:entries){
      if(alias.empty()||!std::all_of(alias.begin(),alias.end(),[](unsigned char c){return std::isalnum(c)||c=='_';})||std::isdigit(static_cast<unsigned char>(alias[0])))throw Error("E_INTERNAL","invalid TypeScript export name");
      visit(p.function(name));
    }
    write("// Generated from checked NEX "+std::string(languageVersion)+"; edit NEX sources.\nimport * as nex from './nex-runtime.ts';\n\n");
    for(const auto &name:structures){
      const auto &s=p.structure(name);
      if(s.enumeration){write("export type "+type(Type::record(name))+" =\n");for(size_t i=0;i<s.variants.size();++i){const auto &variant=s.variants[i];write("  "+std::string(i?"| ":"  ")+"(nex.RecordValue & { readonly [nex.TYPE]: "+quote(name)+"; readonly [nex.CASE]: "+quote(variant.name)+"; ");for(const auto &field:variant.fields)write("readonly "+quote(field.name)+": "+type(field.type)+"; ");write("})\n");}write(";\n\n");continue;}
      write("export type "+type(Type::record(name))+" = nex.RecordValue & {\n  readonly [nex.TYPE]: "+quote(name)+";\n");
      for(const auto &field:s.fields)write("  readonly "+quote(field.name)+": "+type(field.type)+";\n");write("};\n\n");
    }
    llvm::json::Array included;
    for(const auto &name:functions){
      const auto &f=p.function(name);scopes.clear();scopes.emplace_back();unique=0;
      auto start=line;std::string signature="export function "+symbol(f.name)+"(";
      for(size_t i=0;i<f.params.size();++i){if(i)signature+=", ";signature+=declare(f.params[i].name)+": "+type(f.params[i].type);}
      write(signature+"): "+type(f.result)+" {\n");depth=1;block(f.body,false);depth=0;write("}\n\n");
      included.push_back(llvm::json::Object{{"name",name},{"file",f.unit},{"source_line",int64_t(f.span.line)},{"generated_start",int64_t(start)},{"generated_end",int64_t(line-1)},{"hash",hash(json(canonical(f),false))},{"operations",operationSites(p,f)}});
    }
    for(const auto &[alias,name]:entries)write("export { "+symbol(p.function(name).name)+" as "+alias+" };\n");
    return {out.str(),llvm::json::Object{{"schema","nex.typescript-map/1"},{"language",languageVersion},{"revision",revision(p)},{"source_hash",hash(json(sourceBundle(p),false))},{"functions",std::move(included)},{"statements",std::move(mappings)}}};
  }
};
}
WebModule emitTypeScript(const Program &p,const std::map<std::string,std::string> &entries){return Generator(p).run(entries);}
void writeWebModule(const WebModule &module,const std::string &directory){
  auto output=std::filesystem::path(directory);
  writeFile((output/"program.ts").string(),module.source);
  writeFile((output/"nex-runtime.ts").string(),readFile(resourceFile("web/nex-runtime.ts")));
  writeFile((output/"nex-map.json").string(),json(module.mapping)+"\n");
}
}
