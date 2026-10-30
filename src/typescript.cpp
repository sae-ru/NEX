#include "nex/task_frontend.h"
#include "nex/task_typescript.h"
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
std::string typescriptType(const Type &t,bool tasks){
  switch(t.kind){
  case Type::I64:return "bigint";
  case Type::F64:return "number";
  case Type::Bool:return "boolean";
  case Type::Str:return "string";
  case Type::Bytes:return "nex.ByteBuffer";
  case Type::File:throw Error("E_REALM","file resources cannot enter a browser module");
  case Type::Unit:return "void";
  case Type::List:return "ReadonlyArray<"+typescriptType(*t.element,tasks)+">";
  case Type::Result:return "nex.Result<"+typescriptType(*t.element,tasks)+">";
  case Type::Record:return "T_"+symbol(t.name);
  case Type::Function:{std::string result="((";for(size_t i=0;i<t.arguments.size();++i){if(i)result+=", ";result+="argument"+std::to_string(i)+": "+typescriptType(t.arguments[i],tasks);}auto output=typescriptType(*t.element,tasks);return result+") => "+(tasks?"task.Call<"+output+">":output)+")";}
  case Type::TaskScope:if(tasks)return "task.Scope";break;
  case Type::Task:if(tasks)return "task.Future<"+typescriptType(*t.element,tasks)+">";break;
  case Type::Channel:if(tasks)return "task.Channel<"+typescriptType(*t.element,tasks)+">";break;
  default:throw Error("E_INTERNAL","unresolved TypeScript type");
  }
  throw Error("E_TASK_UNIMPLEMENTED","standalone synchronous TypeScript exports cannot carry task authority; emit a task-effect entry that owns the execution scope");
}
class Generator {
  const Program &p;
  bool taskMode=false;
  bool privateSource=false;
  bool exceptionPrototype=false;
  std::vector<std::string> caughtSourceErrors;
  std::set<std::string> functions,structures;
  std::vector<std::map<std::string,std::string>> scopes;
  unsigned unique=0,depth=0,line=1;
  bool parallelEnabled=false;
  std::ostringstream out;
  llvm::json::Array mappings;
  std::map<const void*,std::string> sites;
  std::string type(const Type &t){return typescriptType(t,taskMode);}
  std::pair<std::string,std::string> payloadShape(const Type &t){
    switch(t.kind){
    case Type::I64:return {"i64",""};case Type::Bool:return {"bool",""};case Type::F64:return {"f64",""};
    case Type::Str:return {"str",""};case Type::Bytes:return {"bytes",""};case Type::List:return {"list",""};
    case Type::Result:return {"result",""};
    case Type::Record:return {p.structure(t.name).enumeration?"enum":"record",t.name};
    default:throw Error("E_TYPED_EXCEPTION_AUTHORITY","typed TypeScript payload authority integration is pending");
    }
  }
  void write(const std::string &text){out<<text;line+=std::count(text.begin(),text.end(),'\n');}
  void statement(const std::string &text){write(std::string(depth*2,' ')+text+"\n");}
  std::string site(E e){const auto &s=e->span;return "["+quote(s.file)+", "+std::to_string(s.line)+", "+std::to_string(s.column)+", "+quote(sites.at(e.get()))+"]";}
  std::string site(S statement){const auto &s=statement->span;return "["+quote(s.file)+", "+std::to_string(s.line)+", "+std::to_string(s.column)+", "+quote(sites.at(statement.get()))+"]";}
  void needed(const Type &t){
    if(containsExternalResource(p,t))throw Error("E_REALM","external resource authority cannot enter a browser module");
    if(t.element)needed(*t.element);if(t.kind==Type::Function)for(const auto &argument:t.arguments)needed(argument);
    if(t.kind==Type::Record&&structures.insert(t.name).second)for(auto field:p.structure(t.name).members())needed(field->type);
  }
  void visit(const Function &f){
    if(p.sourceLanguage==SourceLanguage::SourceExceptions025Prototype&&(usesParallelMap(f)||std::any_of(f.effects.begin(),f.effects.end(),[&](const auto &effect){return effect!="io"&&effect!="throw"&&!(taskMode&&sourceExceptionTasksPrototype(p)&&effect=="task");})))throw Error("E_EXCEPTION_STAGE","TypeScript exception experiment supports pure/io/throw and dedicated task mode; parallel_map and host-resource effects remain pending",f.span);
    if(f.foreign)throw Error("E_REALM","external functions cannot enter a browser module",f.span);
    if(!f.typeParameters.empty()||std::any_of(f.typeArguments.begin(),f.typeArguments.end(),containsParameter))throw Error("E_GENERIC_ENTRY","browser entry/closure must be concrete",f.span);
    if(f.realm=="server")throw Error("E_REALM","server function cannot be emitted to the browser: "+f.name,f.span);
    if(!functions.insert(f.name).second)return;
    needed(f.result);for(const auto &param:f.params)needed(param.type);for(const auto &capture:f.captures)needed(capture.type);
    std::function<void(E)> expression=[&](E e){if(e){needed(e->type);for(auto a:e->args)expression(a);}};
    std::function<void(const std::vector<S>&)> block=[&](const auto &body){for(auto s:body){needed(s->type);expression(s->expr);childBlocks(s,block);}};
    block(f.body);for(const auto &name:f.dependencies)visit(p.function(name));
  }
  std::string local(const std::string &name){
    for(auto i=scopes.rbegin();i!=scopes.rend();++i)if(i->contains(name))return i->at(name);
    throw Error("E_INTERNAL","TypeScript local not found: "+name);
  }
  std::string declare(const std::string &name){auto result="v"+std::to_string(++unique)+"_"+name;scopes.back()[name]=result;return result;}
  std::string patternChild(P p,size_t index,const std::string &subject,const std::string &location){
    if(p->kind==Pattern::List)return "nex.index("+subject+", "+std::to_string(index)+"n, "+location+")";
    if(p->type.kind==Type::Result)return p->ordinal?"nex.unwrap("+subject+", "+location+")":std::string(index?"nex.errorMessage(":"nex.errorCode(")+subject+")";
    const auto &record=this->p.structure(p->type.name);const auto &fields=record.enumeration?record.variants.at(p->ordinal).fields:record.fields;
    return "(("+subject+")["+quote(fields.at(index).name)+"] as "+type(p->args[index]->type)+")";
  }
  std::string patternCondition(P p,const std::string &subject,const std::string &location){
    if(p->kind==Pattern::Binding||p->kind==Pattern::Wildcard)return "true";
    if(p->kind==Pattern::Integer)return "("+subject+" === ("+std::to_string(p->number)+"n))";
    if(p->kind==Pattern::Boolean)return "("+subject+" === "+(p->number?"true":"false")+")";
    if(p->kind==Pattern::String)return "nex.equal("+subject+", "+quote(p->text)+")";
    std::string test="true";
    if(p->kind==Pattern::List)test="(nex.length("+subject+") === "+std::to_string(p->args.size())+"n)";
    else if(p->type.kind==Type::Result)test=std::string(p->ordinal?"":"!")+"nex.isOk("+subject+")";
    else if(this->p.structure(p->type.name).enumeration)test="(("+subject+")[nex.CASE] === "+quote(this->p.structure(p->type.name).variants.at(p->ordinal).name)+")";
    for(size_t i=0;i<p->args.size();++i)if(p->args[i]->kind!=Pattern::Binding&&p->args[i]->kind!=Pattern::Wildcard)test+=" && "+patternCondition(p->args[i],patternChild(p,i,subject,location),location);
    return "("+test+")";
  }
  std::string patternBindings(P p,const std::string &subject,const std::string &location){
    if(p->kind==Pattern::Binding)return "const "+declare(p->text)+": "+type(p->type)+" = "+subject+"; ";
    std::string code;for(size_t i=0;i<p->args.size();++i)code+=patternBindings(p->args[i],patternChild(p,i,subject,location),location);return code;
  }
  std::string matchExpression(E e){
    auto subject="match_"+std::to_string(++unique),location=site(e);std::string code=taskMode?"(yield* (function* (): task.Step<"+type(e->type)+"> { const ":"((): "+type(e->type)+" => { const ";code+=subject+" = "+expr(e->args[0])+"; ";
    for(auto arm:e->arms){scopes.emplace_back();code+="if ("+patternCondition(arm->pattern,subject,location)+") { "+patternBindings(arm->pattern,subject,location);if(arm->guard)code+="if ("+expr(e->args[arm->guard])+") { ";code+="return "+expr(e->args[arm->value])+"; ";if(arm->guard)code+="} ";code+="} ";scopes.pop_back();}
    return code+"return nex.invalidEnum("+location+"); })()"+(taskMode?")":"");
  }
  std::string expr(E e){
    switch(e->kind){
    case Expr::FunctionRef:case Expr::Lambda:{
      const auto &fn=p.function(e->text);std::string captureParams,captureValues,parameters,arguments,captures;
      for(size_t i=0;i<e->args.size();++i){auto name="capture_"+std::to_string(++unique);if(i){captureParams+=", ";captureValues+=", ";arguments+=", ";captures+=", ";}captureParams+=name+": "+type(fn.captures[i].type);captureValues+=expr(e->args[i]);arguments+=name;captures+=name;}
      for(size_t i=0;i<fn.params.size();++i){auto name="argument_"+std::to_string(++unique);if(i)parameters+=", ";if(!arguments.empty())arguments+=", ";parameters+=name+": "+type(fn.params[i].type);arguments+=name;}
      auto invocation=symbol(fn.name)+"("+arguments+")";
      if(taskMode)invocation="task.call(() => "+invocation+")";
      return "(("+captureParams+"): "+type(e->type)+" => nex.captured(["+captures+"], ("+parameters+"): "+(taskMode?"task.Call<"+type(fn.result)+">":type(fn.result))+" => "+invocation+"))("+captureValues+")";
    }
    case Expr::Invoke:{auto text="("+expr(e->args[0])+")(";for(size_t i=1;i<e->args.size();++i){if(i>1)text+=", ";text+=expr(e->args[i]);}text+=")";return taskMode?"(yield* task.invoke("+text+", "+site(e)+"))":text;}
    case Expr::Propagate:return "nex.propagate("+expr(e->args[0])+")";
    case Expr::Match:return matchExpression(e);
    case Expr::Integer:return "("+std::to_string(e->number)+"n)";
    case Expr::Floating:return "("+floatLiteral(e->number)+")";
    case Expr::Boolean:return e->number?"true":"false";
    case Expr::String:return quote(e->text);
    case Expr::Name:return local(e->text);
    case Expr::List:{std::string text="nex.list<"+type(*e->type.element)+">([";for(size_t i=0;i<e->args.size();++i){if(i)text+=", ";text+=expr(e->args[i]);}return text+"])";}
    case Expr::Field:return "("+expr(e->args[0])+")["+quote(e->text)+"]";
    case Expr::Index:return "nex."+std::string(e->args[0]->type==Type::Str?"character":e->args[0]->type==Type::Bytes?"bytesIndex":"index")+"("+expr(e->args[0])+", "+expr(e->args[1])+", "+site(e)+")";
    case Expr::Unary:return e->text=="!"?"(!"+expr(e->args[0])+")":"nex."+std::string(e->type==Type::F64?"floatNeg":"neg")+"("+expr(e->args[0])+", "+site(e)+")";
    case Expr::Binary:{
      auto a=expr(e->args[0]),b=expr(e->args[1]);const auto &op=e->text;
      if(op=="=="||op=="!=")return (op=="!="?"!":"")+std::string("nex.equal(")+a+", "+b+")";
      if(op=="+"&&e->type==Type::Str)return "("+a+" + "+b+")";
      if(op=="+"&&e->type.kind==Type::List)return "nex.concat("+a+", "+b+")";
      if(op=="+"&&e->type==Type::Bytes)return "nex.bytesConcat("+a+", "+b+", "+site(e)+")";
      const std::map<std::string,std::string> arithmetic={{"+","add"},{"-","sub"},{"*","mul"},{"/","div"},{"%","rem"}};
      if(e->type==Type::F64){const std::map<std::string,std::string> floats={{"+","floatAdd"},{"-","floatSub"},{"*","floatMul"},{"/","floatDiv"},{"%","floatRem"}};return "nex."+floats.at(op)+"("+a+", "+b+", "+site(e)+")";}
      if(arithmetic.contains(op))return "nex."+arithmetic.at(op)+"("+a+", "+b+", "+site(e)+")";
      return "("+a+" "+op+" "+b+")";
    }
    case Expr::Call:{
      if(taskMode&&taskBuiltins().contains(e->text)){
        std::string args="[";for(size_t i=0;i<e->args.size();++i){if(i)args+=", ";args+=expr(e->args[i]);}
        return "((yield task.request("+quote(e->text)+", "+args+"], "+site(e)+")) as "+type(e->type)+")";
      }
      if(e->text=="parallel_map")return (taskMode?"(yield* task.parallelMap(":"nex.parallelMap(")+expr(e->args[0])+", "+expr(e->args[1])+", "+expr(e->args[2])+", "+site(e)+")"+(taskMode?")":"");
      const std::map<std::string,std::string> binary={{"bytes","bytesFromIntegers"},{"utf8_bytes","utf8Bytes"},{"decode_utf8","decodeUTF8"},{"encode_base64","encodeBase64"},{"decode_base64","decodeBase64"}};
      if(binary.contains(e->text))return "nex."+binary.at(e->text)+"("+expr(e->args[0])+(e->text=="utf8_bytes"?", "+site(e):"")+")";
      if((e->text=="push"||e->text=="set"||e->text=="slice")&&e->args[0]->type==Type::Bytes){
        std::string text="nex."+std::string(e->text=="push"?"bytesPush":e->text=="set"?"bytesSet":"bytesSlice")+"(";
        for(size_t i=0;i<e->args.size();++i){if(i)text+=", ";text+=expr(e->args[i]);}return text+", "+site(e)+")";
      }
      if(e->text=="as_f64"||e->text=="as_i64")return "nex."+std::string(e->text=="as_f64"?"asFloat":"asInteger")+"("+expr(e->args[0])+")";
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
      text+=")";
      return taskMode&&!builtins.contains(e->text)?"(yield* "+text+")":text;
    }
    }
    throw Error("E_INTERNAL","unsupported TypeScript expression");
  }
  void block(const std::vector<S> &body,bool scoped=true){
    if(scoped)scopes.emplace_back();
    for(auto s:body){
      auto start=line;
      if(taskMode)statement("yield* task.checkpoint("+site(s)+");");
      switch(s->kind){
      case Stmt::TypedThrow:{
        if(p.sourceLanguage!=SourceLanguage::TypedErrors027)throw Error("E_LANGUAGE_VERSION","typed raise requires language0.27",s->span);
        auto shape=payloadShape(s->type);
        statement("sourceException.raiseTyped("+quote(s->errorTypeKey)+", "+quote(typeName(s->type))+", "+expr(s->expr)+", "+quote(shape.first)+", "+quote(shape.second)+", "+site(s)+");");
        break;
      }
      case Stmt::TypedTry:{
        if(p.sourceLanguage!=SourceLanguage::TypedErrors027)throw Error("E_LANGUAGE_VERSION","typed handlers require language0.27",s->span);
        auto done="handler_done_"+std::to_string(++unique),error="source_error_"+std::to_string(++unique),payload="source_payload_"+std::to_string(++unique);
        statement(done+": {");++depth;statement("try {");++depth;block(s->body);--depth;statement("} catch ("+error+") {");++depth;
        statement("const "+payload+" = sourceException.details("+error+");");
        statement("if ("+payload+" === undefined) throw "+error+";");
        for(auto clause:s->alternative){
          bool typed=clause->type!=Type::Unknown;
          statement("if ("+(typed?"sourceException.matches("+payload+", "+quote(clause->errorTypeKey)+")":std::string("true"))+") {");++depth;scopes.emplace_back();
          auto name=declare(clause->name);
          if(typed){auto shape=payloadShape(clause->type);statement("const "+name+": "+type(clause->type)+" = sourceException.readTyped<"+type(clause->type)+">("+payload+", "+quote(clause->errorTypeKey)+", "+quote(shape.first)+", "+quote(shape.second)+", "+site(clause)+");");}
          else{statement("const "+name+": string = "+payload+".code;");auto message=declare(clause->catchMessage);statement("const "+message+": string = "+payload+".message;");}
          caughtSourceErrors.push_back(error);
          if(clause->expr){statement("if ("+expr(clause->expr)+") {");++depth;}
          block(clause->body,false);statement("break "+done+";");
          if(clause->expr){--depth;statement("}");}
          caughtSourceErrors.pop_back();scopes.pop_back();--depth;statement("}");
        }
        statement("throw "+error+";");--depth;statement("}");--depth;statement("}");break;
      }
      case Stmt::CatchClause:throw Error("E_INTERNAL","handler clause outside protected statement",s->span);
      case Stmt::Finally:{
        auto run="finally_run_"+std::to_string(++unique),error="finally_error_"+std::to_string(++unique),fatal="finally_fatal_"+std::to_string(++unique);
        statement("let "+run+" = true;");statement("let "+fatal+": unknown = undefined;");
        statement("try {");++depth;block(s->body);--depth;
        statement("} catch ("+error+") {");++depth;
        statement(run+" = sourceException.details("+error+") !== undefined || nex.propagatedFailure("+error+") !== undefined;");
        statement(fatal+" = "+error+";");statement("throw "+error+";");--depth;
        statement("} finally {");++depth;statement("if ("+run+(taskMode?" && task.finalizerEnabled()":"")+") {");++depth;
        block(s->alternative);--depth;statement("} else if (!"+run+") {");++depth;statement("throw "+fatal+";");--depth;statement("}");--depth;statement("}");break;
      }
      case Stmt::Try:{
        if(!exceptionPrototype)throw Error("E_EXCEPTION_BACKEND","private source exceptions require the experimental TypeScript emitter",s->span);
        auto error="source_error_"+std::to_string(++unique),payload="source_payload_"+std::to_string(++unique);
        statement("try {");++depth;block(s->body);--depth;statement("} catch ("+error+") {");++depth;
        statement("const "+payload+" = sourceException.details("+error+");");
        statement("if ("+payload+" === undefined) throw "+error+";");
        scopes.emplace_back();
        auto code=declare(s->name);statement("const "+code+": string = "+payload+".code;");
        auto message=declare(s->catchMessage);statement("const "+message+": string = "+payload+".message;");
        caughtSourceErrors.push_back(error);
        if(s->expr)statement("if (!("+expr(s->expr)+")) throw "+error+";");
        block(s->alternative,false);caughtSourceErrors.pop_back();scopes.pop_back();
        --depth;statement("}");break;
      }
      case Stmt::Throw:{
        if(!exceptionPrototype)throw Error("E_EXCEPTION_BACKEND","private source exceptions require the experimental TypeScript emitter",s->span);
        if(s->expr)statement("sourceException.raise("+expr(s->expr->args[0])+", "+expr(s->expr->args[1])+", "+site(s)+");");
        else{if(caughtSourceErrors.empty())throw Error("E_INTERNAL","rethrow lost its lexical TypeScript catch",s->span);statement("throw "+caughtSourceErrors.back()+";");}
        break;
      }
      case Stmt::Let:case Stmt::Var:{auto value=expr(s->expr);auto name=declare(s->name);statement(std::string(s->kind==Stmt::Let?"const ":"let ")+name+": "+type(s->type)+" = "+value+";");break;}
      case Stmt::Assign:statement(local(s->name)+" = "+expr(s->expr)+";");break;
      case Stmt::Expression:statement(expr(s->expr)+";");break;
      case Stmt::Return:statement(s->expr?"return "+expr(s->expr)+";":"return;");break;
      case Stmt::If:
        statement("if ("+expr(s->expr)+") {");++depth;block(s->body);--depth;
        if(!s->alternative.empty()){statement("} else {");++depth;block(s->alternative);--depth;}statement("}");break;
      case Stmt::Match:{
        auto e=s->expr;auto subject="match_"+std::to_string(++unique),end="match_end_"+std::to_string(++unique),location=site(e->args[0]);statement(end+": {");++depth;statement("const "+subject+" = "+expr(e->args[0])+";");
        for(auto arm:e->arms){statement("if ("+patternCondition(arm->pattern,subject,location)+") {");++depth;scopes.emplace_back();statement(patternBindings(arm->pattern,subject,location));if(arm->guard){statement("if ("+expr(e->args[arm->guard])+") {");++depth;}
          block(arm->body,false);statement("break "+end+";");if(arm->guard){--depth;statement("}");}scopes.pop_back();--depth;statement("}");}
        statement("nex.invalidEnum("+location+");");--depth;statement("}");break;
      }
      case Stmt::While:statement("while ("+expr(s->expr)+") {");++depth;if(taskMode)statement("yield* task.checkpoint("+site(s)+");");else if(parallelEnabled)statement("nex.parallelPoll("+site(s->expr)+");");block(s->body);--depth;statement("}");break;
      }
      mappings.push_back(llvm::json::Object{{"site",sites.at(s.get())},{"generated_line",int64_t(start)},{"file",s->span.file},{"line",int64_t(s->span.line)},{"column",int64_t(s->span.column)}});
    }
    if(scoped)scopes.pop_back();
  }
public:
  explicit Generator(const Program &p,bool tasks=false,bool staging=false,bool exceptions=false):p(p),taskMode(tasks),privateSource(staging),exceptionPrototype(exceptions||isPublicSourceExceptionLanguage(p.sourceLanguage)){
    if(p.sourceLanguage==SourceLanguage::TypedErrors027&&taskMode)throw Error("E_TYPED_EXCEPTION_TASK","language0.27 TypeScript task lowering is pending");
    if(p.sourceLanguage==SourceLanguage::SourceExceptions025Prototype&&!exceptionPrototype)throw Error("E_EXCEPTION_BACKEND","private source exceptions require the dedicated experimental TypeScript emitter");
    if(!privateSource){for(const auto &f:p.functions)for(const auto &o:operationTree(p,f))if(o.ast)sites[o.ast]=o.site;return;}
    size_t sequence=0;std::function<void(E)> expression;std::function<void(const std::vector<S>&)> body;
    body=[&](const auto &statements){for(auto s:statements){sites.try_emplace(s.get(),"private-"+std::to_string(++sequence));expression(s->expr);childBlocks(s,body);}};
    expression=[&](E e){if(!e)return;sites.try_emplace(e.get(),"private-"+std::to_string(++sequence));for(auto a:e->args)expression(a);for(auto arm:e->arms)body(arm->body);};
    for(const auto &f:p.functions)body(f.body);
  }
  WebModule run(const std::map<std::string,std::string> &entries){
    if(entries.empty())throw Error("E_ENTRY","TypeScript requires at least one entry");
    for(const auto &[alias,name]:entries){
      if(alias.empty()||!std::all_of(alias.begin(),alias.end(),[](unsigned char c){return std::isalnum(c)||c=='_';})||std::isdigit(static_cast<unsigned char>(alias[0])))throw Error("E_INTERNAL","invalid TypeScript export name");
      visit(p.function(name));
    }
    write("// Generated from checked NEX "+std::string(programLanguage(p))+"; edit NEX sources.\nimport * as nex from './nex-runtime.ts';\n\n");
    if(privateSource||p.sourceLanguage==SourceLanguage::SourceExceptions025Prototype)write("// Private staging only; this module has no public source revision.\n");
    if(exceptionPrototype)write("import * as sourceException from './nex-source-exception-runtime.ts';\n\n");
    if(taskMode)write("import * as task from './nex-task-runtime.ts';\n\n");
    for(const auto &name:functions)if(usesParallelMap(p.function(name)))parallelEnabled=true;
    for(const auto &name:structures){
      const auto &s=p.structure(name);
      if(s.opaqueResource)throw Error("E_REALM","opaque resource declarations cannot be emitted to the browser",s.span);
      if(s.enumeration){write("export type "+type(Type::record(name))+" =\n");for(size_t i=0;i<s.variants.size();++i){const auto &variant=s.variants[i];write("  "+std::string(i?"| ":"  ")+"(nex.RecordValue & { readonly [nex.TYPE]: "+quote(name)+"; readonly [nex.CASE]: "+quote(variant.name)+"; ");for(const auto &field:variant.fields)write("readonly "+quote(field.name)+": "+type(field.type)+"; ");write("})\n");}write(";\n\n");continue;}
      write("export type "+type(Type::record(name))+" = nex.RecordValue & {\n  readonly [nex.TYPE]: "+quote(name)+";\n");
      for(const auto &field:s.fields)write("  readonly "+quote(field.name)+": "+type(field.type)+";\n");write("};\n\n");
    }
    llvm::json::Array included;
    for(const auto &name:functions){
      const auto &f=p.function(name);scopes.clear();scopes.emplace_back();unique=0;caughtSourceErrors.clear();
      auto start=line;std::string signature=std::string("export function")+(taskMode?"* ":" ")+symbol(f.name)+"(";
      for(size_t i=0;i<f.captures.size();++i){if(i)signature+=", ";signature+=declare(f.captures[i].name)+": "+type(f.captures[i].type);}
      for(size_t i=0;i<f.params.size();++i){if(i||!f.captures.empty())signature+=", ";signature+=declare(f.params[i].name)+": "+type(f.params[i].type);}
      write(signature+"): "+(taskMode?"task.Step<"+type(f.result)+">":type(f.result))+" {\n");depth=1;
      if(taskMode){statement("task.enter(["+quote(f.span.file)+", "+std::to_string(f.span.line)+", "+std::to_string(f.span.column)+"]);");statement("try {");++depth;}
      else if(parallelEnabled){statement("nex.parallelEnter(["+quote(f.span.file)+", "+std::to_string(f.span.line)+", "+std::to_string(f.span.column)+"]);");statement("try {");++depth;}
      bool propagation=propagatesResult(f);
      if(propagation&&!taskMode){statement("return nex.resultScope<"+type(*f.result.element)+">((): "+type(f.result)+" => {");++depth;}
      block(f.body,false);
      // The checker proves non-unit source functions cannot fall through. JS
      // cancellation guards and branded throw helpers obscure that proof from
      // TypeScript's flow analysis. Keep an explicit fatal unreachable edge;
      // never fabricate a value or weaken the generated result type.
      if(f.result!=Type::Unit)statement("throw new nex.NexError(\"E_INTERNAL\", \"checked function completed without a result\", ["+quote(f.span.file)+", "+std::to_string(f.span.line)+", "+std::to_string(f.span.column)+"]);");
      if(propagation&&!taskMode){--depth;statement("});");}
      if(taskMode){--depth;if(propagation){statement("} catch (error) {");++depth;statement("const failure = nex.propagatedFailure(error);");statement("if (failure !== undefined) return failure;");statement("throw error;");--depth;}statement("} finally { task.leave(); }");}
      else if(parallelEnabled){--depth;statement("} finally { nex.parallelLeave(); }");}
      depth=0;write("}\n\n");
      if(privateSource)included.push_back(llvm::json::Object{{"name",name},{"file",f.unit},{"source_line",int64_t(f.span.line)},{"generated_start",int64_t(start)},{"generated_end",int64_t(line-1)},{"private_location_hash",hash(name+":"+f.span.file+":"+std::to_string(f.span.begin)+":"+std::to_string(f.span.end))}});
      else included.push_back(llvm::json::Object{{"name",name},{"file",f.unit},{"source_line",int64_t(f.span.line)},{"generated_start",int64_t(start)},{"generated_end",int64_t(line-1)},{"hash",hash(json(canonical(f),false))},{"operations",operationSites(p,f)}});
    }
    for(const auto &[alias,name]:entries)write("export { "+symbol(p.function(name).name)+" as "+alias+" };\n");
    if(p.sourceLanguage==SourceLanguage::SourceExceptions025Prototype)return {out.str(),llvm::json::Object{{"schema","nex.private-typescript-exception-map/1"},{"language",programLanguage(p)},{"source_support",false},{"public_revision",false},{"entry_text_hash",hash(p.source)},{"functions",std::move(included)},{"statements",std::move(mappings)},{"execution",taskMode?"task-generator":"synchronous"},{"task_source_exceptions",taskMode}},taskMode,true};
    if(privateSource)return {out.str(),llvm::json::Object{{"schema","nex.private-typescript-task-map/1"},{"language",programLanguage(p)},{"public_source_tasks",false},{"entry_text_hash",hash(p.source)},{"functions",std::move(included)},{"statements",std::move(mappings)}},taskMode};
    if(p.sourceLanguage==SourceLanguage::TypedErrors027)return {out.str(),llvm::json::Object{{"schema","nex.development-typescript/027-1"},{"language",programLanguage(p)},{"public_revision",false},{"source027_delivery_accepted",false},{"entry_text_hash",hash(p.source)},{"functions",std::move(included)},{"statements",std::move(mappings)},{"execution","synchronous"},{"source_exceptions","nex.source-errors/2"}},false,true};
    auto mapping=llvm::json::Object{{"schema","nex.typescript-map/1"},{"language",programLanguage(p)},{"revision",revision(p)},{"source_hash",hash(json(sourceBundle(p),false))},{"functions",std::move(included)},{"statements",std::move(mappings)},{"execution",taskMode?"task-generator":"synchronous"}};
    if(exceptionPrototype){mapping["source_exceptions"]="nex.source-errors/1";mapping["task_source_exceptions"]=taskMode;}
    return {out.str(),std::move(mapping),taskMode,exceptionPrototype};
  }
};
}
WebModule emitTypeScript(const Program &p,const std::map<std::string,std::string> &entries){

  if(p.sourceLanguage==SourceLanguage::SourceExceptions025Prototype)throw Error("E_EXCEPTION_BACKEND","private source exceptions require TypeScript lowering before publication");
  rejectUnloweredTasks(p,"TypeScript emission");
  bool tasks=false;
  if(isPublicTaskLanguage(p)){
    std::set<std::string> visited;
    std::function<void(const Function&)> visit=[&](const Function &function){
      if(!visited.insert(function.name).second)return;
      tasks|=function.effects.contains("task");
      for(const auto &dependency:function.dependencies)visit(p.function(dependency));
    };
    for(const auto &[alias,name]:entries){(void)alias;visit(p.function(name));}
  }
  return Generator(p,tasks).run(entries);
}
WebModule emitSourceExceptionsPrototypeTypeScript(const Program &p,const std::map<std::string,std::string> &entries){
  if(sourceExceptionTasksPrototype(p))throw Error("E_EXCEPTION_BACKEND","source task exceptions require generator/scheduler integration before TypeScript execution");
  if(p.sourceLanguage!=SourceLanguage::SourceExceptions025Prototype)throw Error("E_LANGUAGE_VERSION","experimental TypeScript exception emitter requires the private identity");
  return Generator(p,false,false,true).run(entries);
}
WebModule emitSourceExceptionTasksPrototypeTypeScript(const Program &p,const std::map<std::string,std::string> &entries){
  if(!sourceExceptionTasksPrototype(p))throw Error("E_LANGUAGE_VERSION","task exception TypeScript emitter requires the separate private task parser");
  return Generator(p,true,false,true).run(entries);
}
WebModule emitTaskTypeScript(const Program &p,const std::map<std::string,std::string> &entries){if(!p.taskPrototype)throw Error("E_TASK_STATE","private TypeScript tasks require checked prototype source");return Generator(p,true,true).run(entries);}
void writeWebModule(const WebModule &module,const std::string &directory){
  auto output=std::filesystem::path(directory);
  writeFile((output/"program.ts").string(),module.source);
  writeFile((output/"nex-runtime.ts").string(),readFile(resourceFile("web/nex-runtime.ts")));
  writeFile((output/"nex-bytes.ts").string(),readFile(resourceFile("web/nex-bytes.ts")));
  if(module.privateSourceExceptions)writeFile((output/"nex-source-exception-runtime.ts").string(),readFile(resourceFile("web/nex-source-exception-runtime.ts")));
  if(module.asynchronous)writeFile((output/"nex-task-runtime.ts").string(),readFile(resourceFile("web/nex-task-runtime.ts")));
  writeFile((output/"nex-map.json").string(),json(module.mapping)+"\n");
}
void writeTaskTypeScriptModule(const WebModule &module,const std::string &directory){
  writeWebModule(module,directory);
}
}
