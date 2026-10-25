#include "nex/task_frontend.h"
#include "nex/task_lifetime.h"
#include "nex/language.h"
#include "nex/frontend_diagnostics.h"
#include "nex/traits.h"
#include "llvm/Support/BLAKE3.h"
#include "llvm/ADT/APFloat.h"
#include "llvm/Support/FormatVariadic.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"
#include <algorithm>
#include <array>
#include <charconv>
#include <cctype>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <sstream>
#include <cstdlib>
#include <functional>
#include "nex_value.h"
#include "llvm/Support/Error.h"

namespace nex {
std::string floatLiteral(int64_t bits){return nexrt::formatFloat(nexrt::floatValue(bits));}
std::string typeName(Type t) {
  switch (t.kind) { case Type::I64: return "i64"; case Type::Bool: return "bool";
    case Type::F64:return "f64";case Type::Bytes:return "bytes";case Type::File:return "file";
    case Type::Unit: return "unit";case Type::Str:return "str";
    case Type::List:return "list<"+typeName(*t.element)+">";
    case Type::Result:return "result<"+typeName(*t.element)+">";
    case Type::Task:return "task<"+typeName(*t.element)+">";
    case Type::Channel:return "channel<"+typeName(*t.element)+">";
    case Type::TaskScope:return "task_scope";
    case Type::Function:{std::string result=t.realm=="shared"?"fn(":t.realm+" fn(";for(size_t i=0;i<t.arguments.size();++i){if(i)result+=",";result+=typeName(t.arguments[i]);}result+=")->"+(t.element->kind==Type::Function?"("+typeName(*t.element)+")":typeName(*t.element));if(!t.effects.empty()){result+="!{";for(const auto &effect:t.effects){if(result.back()!='{')result+=",";result+=effect;}result+="}";}return result;}
    case Type::Record:return t.arguments.empty()?t.name:genericName(t.name,t.arguments);
    case Type::Parameter:return t.arguments.empty()?"$"+t.name:genericName("$"+t.name,t.arguments);
    case Type::Projection:return genericName(t.name,t.arguments);
    case Type::Constructor:return t.name;
    default: return "unknown"; }
}
const std::set<std::string> &builtinNames(bool tasks,bool resources){
  static const std::set<std::string> names=[] {
    std::set<std::string> result={"as_f64","as_i64","print","assert","len","str","push","set","slice","contains","ok","err","is_ok","unwrap","error_code","error_message","encode_json","decode_json","read_env","store_get","store_put","store_remove","store_keys","file_read_text","file_write_text","bytes","utf8_bytes","decode_utf8","encode_base64","decode_base64","file_read_bytes","file_write_bytes","file"};
    result.insert("parallel_map");result.insert(streamFileBuiltins().begin(),streamFileBuiltins().end());return result;
  }();
  static const std::set<std::string> extended=[&]{auto result=names;result.insert(taskBuiltins().begin(),taskBuiltins().end());result.insert({"task","channel","task_scope"});return result;}();
  static const std::set<std::string> owned=[&]{auto result=names;result.insert(externalResourceBuiltins().begin(),externalResourceBuiltins().end());return result;}();
  static const std::set<std::string> all=[&]{auto result=extended;result.insert(externalResourceBuiltins().begin(),externalResourceBuiltins().end());return result;}();
  return resources?(tasks?all:owned):(tasks?extended:names);
}
const std::set<std::string> &externalResourceBuiltins(){static const std::set<std::string> names={"resource_close","resource_is_open"};return names;}
bool supportsExternalResources(const Program &p){return p.sourceLanguage==SourceLanguage::OwnedResources021||p.sourceLanguage==SourceLanguage::TaskForeign022||p.sourceLanguage==SourceLanguage::TaskWrites023;}
const std::set<std::string> &streamFileBuiltins(){
  static const std::set<std::string> names={"file_open_read","file_open_write","file_open_append","file_read","file_write","file_seek","file_size","file_flush","file_close","file_is_open"};return names;
}
std::string readFile(const std::string &path) {
  std::unique_ptr<std::FILE,decltype(&std::fclose)> in(std::fopen(path.c_str(),"rb"),&std::fclose);
  if (!in) throw Error("E_FILE", "cannot read " + path);
  // Read raw bytes without requiring a seekable file or trusting its reported
  // size. Cache artifacts are large; per-character iterator work is expensive
  // in development compilers. A short final block still contributes its bytes.
  std::array<char,64*1024> buffer;
  std::string text;
  while(true){
    auto count=std::fread(buffer.data(),1,buffer.size(),in.get());
    if(std::ferror(in.get()))throw Error("E_FILE","cannot read "+path);
    text.append(buffer.data(),count);
    if(std::feof(in.get()))return text;
    if(!count)throw Error("E_FILE","cannot read "+path);
  }
}
void writeFile(const std::string &path, const std::string &text) {
  auto parent = std::filesystem::path(path).parent_path();
  if (!parent.empty()) std::filesystem::create_directories(parent);
  std::ofstream out(path, std::ios::binary);
  if (!out || !(out << text)) throw Error("E_FILE", "cannot write " + path);
}
void copyFile(const std::string &source,const std::string &destination,bool overwrite) {
  namespace fs=std::filesystem;
  if(!fs::is_regular_file(source))throw Error("E_FILE","copy source is not a regular file: "+source);
  if(fs::exists(destination)&&fs::equivalent(source,destination))throw Error("E_FILE","copy source and destination are the same file");
  auto permissions=fs::status(source).permissions();auto bytes=readFile(source);int descriptor=-1;
  auto error=llvm::sys::fs::openFileForWrite(destination,descriptor,overwrite?llvm::sys::fs::CD_CreateAlways:llvm::sys::fs::CD_CreateNew);
  if(error)throw Error("E_FILE","cannot create "+destination+": "+error.message());
  // Stream bytes rather than relying on copy_file_range/sendfile support in a
  // mounted filesystem. In particular Docker's shared mounts can reject those.
  llvm::raw_fd_ostream output(descriptor,true);output.write(bytes.data(),bytes.size());output.close();
  if(output.has_error()){auto failure=output.error();output.clear_error();throw Error("E_FILE","cannot copy to "+destination+": "+failure.message());}
  fs::permissions(destination,permissions);
}
std::string resourceFile(const std::string &relative) {
  std::vector<std::filesystem::path> roots;
  if(auto explicitRoot=std::getenv("NEX_RESOURCE_DIR"))roots.emplace_back(explicitRoot);
  else {
    auto executable=llvm::sys::fs::getMainExecutable(nullptr,nullptr);
    if(!executable.empty())roots.push_back(std::filesystem::path(executable).parent_path().parent_path()/"share/nex");
    roots.emplace_back(NEX_RESOURCE_ROOT);
  }
  for(const auto &root:roots)if(std::filesystem::is_regular_file(root/relative))return (root/relative).string();
  throw Error("E_RESOURCE","cannot find NEX resource "+relative+"; check installation or NEX_RESOURCE_DIR");
}
std::string json(const llvm::json::Value &v, bool pretty) {
  return pretty ? llvm::formatv("{0:2}", v).str() : llvm::formatv("{0}", v).str();
}
std::string hash(const std::string &text) {
  llvm::BLAKE3 h; h.update(llvm::StringRef(text)); auto digest = h.final();
  const char *hex = "0123456789abcdef"; std::string out;
  for (auto c : digest) { out += hex[c >> 4]; out += hex[c & 15]; }
  return out;
}
static bool localSymbol(const std::string &name){auto separator=name.find("::"),arguments=name.find('<');return separator==std::string::npos||(arguments!=std::string::npos&&arguments<separator);}
const Function &Program::function(const std::string &name,Span span) const {
  for (const auto &f : functions) if (f.name == name || (localSymbol(name)&&f.owner==module&&f.localName==name)) return f;
  throw Error("E_NAME", "unknown function '" + name + "'",span);
}
const Structure &Program::structure(const std::string &name) const {
  for(const auto &s:structures)if(s.name==name||(localSymbol(name)&&s.owner==module&&s.localName==name))return s;
  throw Error("E_TYPE","unknown structure '"+name+"'");
}
bool Program::hasStructure(const std::string &name)const {
  return std::any_of(structures.begin(),structures.end(),[&](const auto &s){return s.name==name||(localSymbol(name)&&s.owner==module&&s.localName==name);});
}
const Variant *Program::variant(const std::string &name,const Structure **owner)const {
  auto separator=name.rfind("::");if(separator==std::string::npos)return nullptr;
  auto nominal=name.substr(0,separator),tag=name.substr(separator+2);
  for(const auto &type:structures)if(type.enumeration&&(type.name==nominal||(type.owner==module&&type.localName==nominal)))for(const auto &value:type.variants)if(value.name==tag){if(owner)*owner=&type;return &value;}return nullptr;
}
std::string Program::definition(const Function &f)const {
  const auto &text=units.contains(f.unit)?units.at(f.unit).source:source;return text.substr(f.span.begin,f.span.end-f.span.begin);
}
std::string Program::definition(const Structure &s)const {
  const auto &text=units.contains(s.unit)?units.at(s.unit).source:source;return text.substr(s.span.begin,s.span.end-s.span.begin);
}
std::string Program::definition(const Endpoint &e)const {
  const auto &text=units.contains(e.unit)?units.at(e.unit).source:source;return text.substr(e.span.begin,e.span.end-e.span.begin);
}
std::string Program::definition(const Trait &value)const {const auto &text=units.contains(value.unit)?units.at(value.unit).source:source;return text.substr(value.span.begin,value.span.end-value.span.begin);}
std::string Program::definition(const Implementation &value)const {const auto &text=units.contains(value.unit)?units.at(value.unit).source:source;return text.substr(value.span.begin,value.span.end-value.span.begin);}
bool propagatesResult(const Function &function){
  bool found=false;
  std::function<void(E)> expression;
  std::function<void(const std::vector<S>&)> block;
  expression=[&](E e){if(!e||found)return;if(e->kind==Expr::Propagate){found=true;return;}
    for(auto a:e->args)expression(a);for(auto arm:e->arms)block(arm->body);};
  block=[&](const std::vector<S> &body){for(auto s:body){
    if(found)return;
    expression(s->expr);
    // A statement match aliases its arms through Expr::Match as well. The
    // expression traversal already visited them; visiting both is exponential.
    if(s->kind!=Stmt::Match)childBlocks(s,block);
  }};
  block(function.body);return found;
}
bool usesParallelMap(const Function &function){
  bool found=false;std::function<void(E)> expression;std::function<void(const std::vector<S>&)> block;
  expression=[&](E e){if(!e||found)return;if(e->kind==Expr::Call&&e->text=="parallel_map"){found=true;return;}
    for(auto a:e->args)expression(a);for(auto arm:e->arms)block(arm->body);};
  block=[&](const std::vector<S>&body){for(auto s:body){if(found)return;expression(s->expr);if(s->kind!=Stmt::Match)childBlocks(s,block);}};
  block(function.body);return found;
}
std::string Program::location(const Span &span)const {
  if(units.contains(span.file))return units.at(span.file).path;return span.file.empty()?path:span.file;
}
std::string nativeSymbol(const std::string &name){
  if(name.find('<')!=std::string::npos||name.find('$')!=std::string::npos)return "nex_inst_"+hash(name);
  if(name.find("::")==std::string::npos)return "nex_user_"+name;
  std::string result="nex";size_t begin=0;
  for(;;){auto end=name.find("::",begin);auto part=name.substr(begin,end==std::string::npos?end:end-begin);result+="_"+std::to_string(part.size())+"_"+part;if(end==std::string::npos)break;begin=end+2;}
  return result;
}
namespace {
struct Token { std::string text; Span span; enum Kind { Id, Num, Symbol, End, String, Float } kind; };
class Lexer {
  const std::string &source; std::string file;size_t i = 0; unsigned line = 1, column = 1;
  char peek(size_t n = 0) const { return i+n < source.size() ? source[i+n] : '\0'; }
  char advance() { char c = source[i++]; if (c == '\n') { ++line; column = 1; } else ++column; return c; }
public:
  Lexer(const std::string &s,std::string file) : source(s),file(std::move(file)) {}
  Token next() {
    for (;;) {
      while (i < source.size() && std::isspace(static_cast<unsigned char>(peek()))) advance();
      if (peek() == '/' && peek(1) == '/') { while (i < source.size() && peek() != '\n') advance(); }
      else break;
    }
    Span s{line, column, i, i,file};
    if (i == source.size()) return {"<eof>", s, Token::End};
    char c = peek(); Token::Kind kind = Token::Symbol;
    if(c=='"') {
      kind=Token::String;advance();bool closed=false;
      while(i<source.size()) {auto ch=advance();if(ch=='"'){closed=true;break;}if(ch=='\\'&&i<source.size())advance();}
      if(!closed)throw Error("E_STRING","unterminated string literal",s);
    } else if (std::isalpha(static_cast<unsigned char>(c)) || c == '_') {
      kind = Token::Id;
      while (std::isalnum(static_cast<unsigned char>(peek())) || peek() == '_') advance();
    } else if (std::isdigit(static_cast<unsigned char>(c))) {
      kind = Token::Num; while (std::isdigit(static_cast<unsigned char>(peek()))) advance();
      if(peek()=='.'&&std::isdigit(static_cast<unsigned char>(peek(1)))){
        kind=Token::Float;advance();while(std::isdigit(static_cast<unsigned char>(peek())))advance();
      }
      if(peek()=='e'||peek()=='E'){
        kind=Token::Float;advance();if(peek()=='+'||peek()=='-')advance();
        if(!std::isdigit(static_cast<unsigned char>(peek())))throw Error("E_FLOAT_LITERAL","floating exponent requires decimal digits",s);
        while(std::isdigit(static_cast<unsigned char>(peek())))advance();
      }
      if(kind==Token::Float&&i-s.begin>4096)throw Error("E_FLOAT_LITERAL","floating literal exceeds 4096 bytes",s);
    } else {
      std::string pair = source.substr(i, 2);
      if (pair == "=>" || pair == "->" || pair == "==" || pair == "!=" || pair == "<=" || pair == ">=" || pair == "&&" || pair == "||" || pair=="::") { advance(); advance(); }
      else if (std::string("(){}[]:;.,+-*/%<>=!?").find(c) != std::string::npos) advance();
      else throw Error("E_LEX", "unexpected character", s);
    }
    s.end = i; return {source.substr(s.begin, i-s.begin), s, kind};
  }
};
class Parser {
  Program p; std::string inputKind; std::vector<Token> tokens; size_t i = 0; unsigned typeDepth=0,lambdaCounter=0,lambdaDepth=0,syntaxDepth=0;std::map<std::string,unsigned> parameters;
  bool captureNames=false,captureDetails=false;std::map<std::string,Span> parameterOrigins;
  void editorName(std::string kind,const std::string &name,Span span,std::optional<Span> target={}){
    if(!captureNames)return;
    if(p.editorNames.size()>=200000)throw Error("E_ANALYSIS_LIMIT","editor names exceed 200000 entries",span);
    p.editorNames.push_back({std::move(kind),name,"",std::move(span),std::move(target)});
  }
  Span head(Span start)const{start.end=tokens.at(i-1).span.end;return start;}
  void clearParameters(){parameters.clear();parameterOrigins.clear();}
  struct SyntaxDepth {
    unsigned &depth;
    SyntaxDepth(unsigned &value,const Span &span):depth(value){if(depth>=256)throw Error("E_PARSE_LIMIT","syntax recursion exceeds 256 levels",span);++depth;}
    ~SyntaxDepth(){--depth;}
  };
  void annotate(Error &error)const{attachFrontendDiagnostic(error,{{p.path,p.source}},p.path,inputKind,"parse",true);}
  const Token &peek(size_t n=0) const { return tokens.at(std::min(i+n,tokens.size()-1)); }
  Token take() { return tokens.at(i++); }
  SourceRange syntaxRange(size_t begin)const{return {begin,tokens.at(i-1).span.end,true};}
  void boundExpression(const E &value){
    value->syntaxHeight=1;
    for(const auto &child:value->args){
      if(child->syntaxHeight>=256)throw Error("E_PARSE_LIMIT","expression tree exceeds 256 levels",value->span);
      value->syntaxHeight=std::max(value->syntaxHeight,child->syntaxHeight+1);
    }
  }
  bool accept(const std::string &s) { if (peek().text == s) { take(); return true; } return false; }
  Token expect(const std::string &s) {
    if (peek().text != s) throw Error("E_PARSE", "expected '"+s+"', found '"+peek().text+"'", peek().span);
    return take();
  }
  Token name() {
    static const std::set<std::string> reserved = {"module","fn","test","let","var","return","if","else","while","true","false","client","server","shared","i64","f64","bool","unit","str","list","struct","pub","import","as"};
    if (peek().kind != Token::Id || reserved.contains(peek().text))
      throw Error("E_PARSE", "expected identifier", peek().span);
    return take();
  }
  std::string qualified(){auto result=name().text;while(accept("::"))result+="::"+name().text;return result;}
  void typeEnd(){if(peek().text==">="){tokens[i].text="=";++tokens[i].span.begin;++tokens[i].span.column;}else expect(">");}
  unsigned constructorArity(){
    if(!accept("<"))return 0;unsigned count=0;
    do{expect("_");if(++count>64)throw Error("E_GENERIC_LIMIT","constructor arity exceeds64",peek().span);}while(accept(","));typeEnd();return count;
  }
  std::set<std::string> constraintNames(){
    std::set<std::string> result;
    do{auto span=peek().span;auto value=qualified();if(!std::set<std::string>{"add","ordered","integer","number","wire"}.contains(value))editorName("trait",value,head(span));else if(captureDetails)editorName("builtin_bound",value,head(span));if(!result.insert(value).second)throw Error("E_GENERIC_BOUND","duplicate generic constraint '"+value+"'",span);}while(accept("+"));return result;
  }
  std::vector<std::string> templateParameters(TypeBounds &bounds,std::vector<unsigned> &arities,bool keep=false){
    if(!keep)clearParameters();bounds.clear();arities.clear();std::vector<std::string> result;if(!accept("<"))return result;
    do{auto parameter=name();auto arity=constructorArity();
      if(parameter.text=="bytes"||parameter.text=="file"||(p.taskPrototype&&std::set<std::string>{"task","channel","task_scope"}.contains(parameter.text))||!parameters.emplace(parameter.text,arity).second)throw Error("E_DUPLICATE","duplicate or reserved generic parameter",parameter.span);
      if(result.size()>=64)throw Error("E_GENERIC_LIMIT","generic declarations support at most64 parameters",parameter.span);
      if(captureNames){parameterOrigins[parameter.text]=parameter.span;editorName("parameter_declaration",parameter.text,parameter.span,parameter.span);}
      result.push_back(parameter.text);arities.push_back(arity);bounds.emplace_back();if(accept(":"))bounds.back()=constraintNames();
    }while(accept(","));typeEnd();return result;
  }
  std::vector<Type> typeArguments(){std::vector<Type> result;expect("<");do{if(result.size()>=64)throw Error("E_GENERIC_LIMIT","generic calls support at most 64 arguments",peek().span);result.push_back(type());}while(accept(","));typeEnd();return result;}
  std::set<std::string> effects(){std::set<std::string> result;if(accept("!")){expect("{");if(!accept("}")){do{auto effect=name();if(!result.insert(effect.text).second)throw Error("E_EFFECT","duplicate effect",effect.span);}while(accept(","));expect("}");}}return result;}
  Type type() {
    if(typeDepth>=128)throw Error("E_GENERIC_LIMIT","source type nesting exceeds limit",peek().span);
    struct Depth {unsigned &value;Depth(unsigned &v):value(v){++value;}~Depth(){--value;}} guard(typeDepth);
    auto t = take();
    if(captureDetails&&(std::set<std::string>{"i64","f64","bool","unit","str","list"}.contains(t.text)||
        ((t.text=="bytes"||t.text=="file")&&peek().text!="::")||(t.text=="result"&&peek().text=="<")))editorName("builtin_type",t.text,t.span);
    if(t.text=="("){auto result=type();expect(")");return result;}
    if(t.text=="fn"||t.text=="shared"||t.text=="client"||t.text=="server"){
      auto realm=t.text=="fn"?"shared":t.text;if(t.text!="fn")expect("fn");std::vector<Type> args;expect("(");if(!accept(")")){do{if(args.size()>=1024)throw Error("E_FUNCTION_LIMIT","function type exceeds 1024 parameters",peek().span);args.push_back(type());}while(accept(","));expect(")");}expect("->");auto result=type();return Type::function(std::move(args),std::move(result),realm,effects());
    }
    if (t.text=="i64") return Type::I64; if (t.text=="bool") return Type::Bool; if(t.text=="unit")return Type::Unit;if(t.text=="str")return Type::Str;
    if(t.text=="f64")return Type::F64;
    if(t.text=="bytes"&&peek().text!="::")return Type::Bytes;
    if(t.text=="file"&&peek().text!="::")return Type::File;
    if(p.taskPrototype&&t.text=="task_scope"&&peek().text!="::")return Type::TaskScope;
    if(p.taskPrototype&&(t.text=="task"||t.text=="channel")&&peek().text!="::"){
      if(peek().text!="<")return Type::constructor(t.text,1);
      expect("<");auto item=type();typeEnd();
      return t.text=="task"?Type::task(std::move(item)):Type::channel(std::move(item));
    }
    if(t.text=="list"||(t.text=="result"&&peek().text=="<")) {
      if(t.text=="list"&&peek().text!="<")return Type::constructor("list",1);
      expect("<");auto item=type();
      typeEnd();
      return t.text=="list"?Type::list(std::move(item)):Type::result(std::move(item));
    }
    if(t.kind==Token::Id){auto text=t.text;while(accept("::"))text+="::"+name().text;auto value=Type::record(text);if(parameters.contains(text))value.kind=Type::Parameter;editorName(value.kind==Type::Parameter?"parameter":"type",text,head(t.span),parameterOrigins.contains(text)?std::optional<Span>(parameterOrigins.at(text)):std::nullopt);if(peek().text=="<")value.arguments=typeArguments();return value;}
    throw Error("E_TYPE", "unknown type '"+t.text+"'",t.span);
  }
  static int precedence(const std::string &op) {
    if(op=="||")return 1; if(op=="&&")return 2;
    if(op=="=="||op=="!=")return 3; if(op=="<"||op=="<="||op==">"||op==">=")return 4;
    if(op=="+"||op=="-")return 5; if(op=="*"||op=="/"||op=="%")return 6; return 0;
  }
  bool genericAhead()const{
    if(peek().text!="<")return false;unsigned depth=0;
    for(size_t n=0;i+n<tokens.size();++n){
      const auto &text=peek(n).text;if(text=="!"&&peek(n+1).text=="{"){n+=2;while(i+n<tokens.size()&&peek(n).text!="}"){if(peek(n).text==";"||peek(n).text=="{")return false;++n;}if(i+n==tokens.size())return false;continue;}if(text=="<")++depth;
      else if(text==">"){if(--depth==0){auto after=peek(n+1).text;return after=="("||after=="::"||after==","||after==";"||after==")"||after=="]"||after=="}";}}
      else if(text==";"||text=="{"||text=="}"||text=="=")break;
    }
    return false;
  }
  P pattern(unsigned depth,unsigned &nodes){
    if(depth>64||++nodes>10000)throw Error("E_MATCH_LIMIT","pattern exceeds its node/depth budget",peek().span);
    auto token=take();auto value=std::make_shared<Pattern>();value->span=token.span;
    if(token.text=="["||token.kind==Token::Id){
      if(token.text=="true"||token.text=="false"){value->kind=Pattern::Boolean;value->number=token.text=="true";value->sourceRange=syntaxRange(token.span.begin);return value;}
      bool list=token.text=="[";if(!list){--i;token=name();value->text=token.text;while(accept("::"))value->text+="::"+name().text;}
      if(!list&&value->text.find("::")!=std::string::npos)editorName("value",value->text,head(token.span));
      if(list||accept("(")){value->kind=list?Pattern::List:Pattern::Constructor;auto end=list?"]":")";if(!accept(end)){do{if(value->args.size()>=1024)throw Error("E_MATCH_LIMIT","pattern payload exceeds 1024 entries",peek().span);value->args.push_back(pattern(depth+1,nodes));}while(accept(","));expect(end);}}
      else{if(value->text.find("::")!=std::string::npos)throw Error("E_PARSE","constructor pattern requires parentheses",token.span);value->kind=value->text=="_"?Pattern::Wildcard:Pattern::Binding;}
    }else if(token.kind==Token::String){value->kind=Pattern::String;try{value->text=nexrt::decodeLiteral(token.text);}catch(const nexrt::DataError &err){throw Error(err.code,err.what(),token.span);}}
    else if(token.kind==Token::Num||token.text=="-"){
      auto text=token.text;if(token.text=="-"){auto number=take();if(number.kind!=Token::Num)throw Error("E_PARSE","negative pattern requires an integer literal",number.span);text+=number.text;}
      value->kind=Pattern::Integer;auto result=std::from_chars(text.data(),text.data()+text.size(),value->number);if(result.ec!=std::errc())throw Error("E_RANGE","integer pattern is outside i64",token.span);
    }else throw Error("E_PARSE","expected a pattern",token.span);value->sourceRange=syntaxRange(token.span.begin);return value;
  }
  E matchValue(Span span){
    auto value=std::make_shared<Expr>();value->kind=Expr::Match;value->span=span;value->args.push_back(expression(1,true));expect("{");unsigned nodes=0;bool first=true;
    while(!accept("}")){
      if(value->arms.size()>=4096)throw Error("E_MATCH_LIMIT","match exceeds 4096 arms",peek().span);
      auto arm=std::make_shared<MatchArm>();arm->span=peek().span;arm->pattern=pattern(0,nodes);
      if(accept("if")){arm->guard=value->args.size();value->args.push_back(expression());}
      expect("=>");bool blocks=peek().text=="{";
      if(first){value->statementMatch=blocks;first=false;}else if(blocks!=value->statementMatch)throw Error("E_PARSE","match cannot mix block and expression arms",peek().span);
      if(blocks)arm->body=block();else{arm->value=value->args.size();value->args.push_back(expression());}
      value->arms.push_back(std::move(arm));if(blocks)accept(",");else if(peek().text!="}")expect(",");
    }
    value->span.end=tokens.at(i-1).span.end;return value;
  }
  E expression(int minimum=1,bool subject=false) {
    SyntaxDepth depth(syntaxDepth,peek().span);unsigned chain=0;
    bool matching=matchAhead()&&peek(1).text!="::"&&!(subject&&peek(1).kind==Token::Symbol&&peek(1).text!="!");E e; auto token=take();
    if(matching)e=matchValue(token.span);
    else if(token.text=="fn"||((token.text=="shared"||token.text=="client"||token.text=="server")&&peek().text=="fn")){
      if(lambdaDepth>=64)throw Error("E_FUNCTION_LIMIT","closure nesting exceeds 64",token.span);struct LambdaDepth{unsigned &value;LambdaDepth(unsigned &value):value(value){++value;}~LambdaDepth(){--value;}} depth(lambdaDepth);
      e=std::make_shared<Expr>();e->kind=Expr::Lambda;e->span=token.span;e->number=lambdaCounter++;e->lambda=std::make_shared<Function>();auto &fn=*e->lambda;fn.span=token.span;if(token.text!="fn"){fn.realm=token.text;expect("fn");}
      expect("(");if(!accept(")")){do{auto parameter=name();expect(":");fn.params.push_back({parameter.text,type(),parameter.span});if(fn.params.size()>1024)throw Error("E_FUNCTION_LIMIT","closure exceeds 1024 parameters",parameter.span);}while(accept(","));expect(")");}expect("->");fn.result=type();fn.effects=effects();fn.body=block();fn.span.end=e->span.end=tokens.at(i-1).span.end;
    }
    else if(token.kind==Token::String) {
      e=std::make_shared<Expr>();e->kind=Expr::String;e->span=token.span;
      try{e->text=nexrt::decodeLiteral(token.text);}catch(const nexrt::DataError &err){throw Error(err.code,err.what(),token.span);}
    } else if(token.text=="[") {
      e=std::make_shared<Expr>();e->kind=Expr::List;e->span=token.span;
      if(!accept("]")){do{e->args.push_back(expression());}while(accept(","));expect("]");}
    } else if(token.text=="-" || token.text=="!") {
      if(token.text=="-" && peek().text=="9223372036854775808") {
        take(); e=std::make_shared<Expr>(); e->kind=Expr::Integer; e->number=std::numeric_limits<int64_t>::min(); e->span=token.span;
      } else { e=std::make_shared<Expr>(); e->kind=Expr::Unary; e->text=token.text; e->span=token.span; e->args={expression(7)}; }
    } else if(token.text=="(") { e=expression(); expect(")"); }
    else if(token.kind==Token::Float){
      llvm::APFloat value(llvm::APFloat::IEEEdouble());
      auto converted=value.convertFromString(token.text,llvm::APFloat::rmNearestTiesToEven);
      if(!converted){llvm::consumeError(converted.takeError());throw Error("E_FLOAT_LITERAL","invalid f64 literal",token.span);}
      if(!value.isFinite())throw Error("E_RANGE","floating literal is outside finite f64",token.span);
      e=std::make_shared<Expr>();e->kind=Expr::Floating;e->span=token.span;
      e->number=value.isZero()?0:std::bit_cast<int64_t>(value.bitcastToAPInt().getZExtValue());
    }
    else if(token.kind==Token::Num) {
      e=std::make_shared<Expr>(); e->kind=Expr::Integer; e->span=token.span;
      auto result=std::from_chars(token.text.data(), token.text.data()+token.text.size(), e->number);
      if(result.ec!=std::errc())throw Error("E_RANGE","integer literal is outside i64",token.span);
    } else if(token.text=="true" || token.text=="false") {
      e=std::make_shared<Expr>(); e->kind=Expr::Boolean; e->span=token.span; e->number=token.text=="true";
    } else if(token.kind==Token::Id) {
      e=std::make_shared<Expr>(); e->kind=Expr::Name; e->span=token.span; e->text=token.text;
      while(accept("::"))e->text+="::"+name().text;
      if(genericAhead()){
        e->typeArguments=typeArguments();
        if(e->text=="decode_json"||e->text=="err"){if(e->typeArguments.size()!=1)throw Error("E_GENERIC_ARITY","builtin requires one type argument",e->span);e->annotation=e->typeArguments[0];e->typeArguments.clear();}
        while(accept("::"))e->text+="::"+name().text;
        if(genericAhead())e->methodArguments=typeArguments();
      }
      if(e->text.find("::")!=std::string::npos)editorName(peek().text=="("?"value_call":"value",e->text,head(token.span));
      if(accept("(")) {
        e->kind=Expr::Call;
        if(!accept(")")) { do {e->args.push_back(expression());}while(accept(",")); expect(")"); }
      }
    } else throw Error("E_PARSE","expected expression, found '"+token.text+"'",token.span);
    e->sourceRange=syntaxRange(token.span.begin);boundExpression(e);
    while(peek().text=="."||peek().text=="["||peek().text=="("||peek().text=="?") {
      if(++chain>256)throw Error("E_PARSE_LIMIT","expression chain exceeds 256 operations",peek().span);
      auto op=take();auto b=std::make_shared<Expr>();b->span=op.span;b->args={e};
      if(op.text=="?"){b->kind=Expr::Propagate;b->text="?";}
      else if(op.text=="."){b->kind=Expr::Field;b->text=name().text;}
      else if(op.text=="("){b->kind=Expr::Invoke;if(!accept(")")){do{b->args.push_back(expression());}while(accept(","));expect(")");}}
      else {b->kind=Expr::Index;b->args.push_back(expression());expect("]");}
      b->sourceRange=syntaxRange(e->sourceRange.begin);boundExpression(b);e=b;
    }
    while(precedence(peek().text)>=minimum) {
      if(++chain>256)throw Error("E_PARSE_LIMIT","expression chain exceeds 256 operations",peek().span);
      auto op=take(); auto rhs=expression(precedence(op.text)+1);
      auto b=std::make_shared<Expr>(); b->kind=Expr::Binary; b->span=op.span; b->text=op.text; b->args={e,rhs};b->sourceRange={e->sourceRange.begin,rhs->sourceRange.end,true};boundExpression(b);e=b;
    }
    return e;
  }
  std::vector<S> block() {
    expect("{"); std::vector<S> body;
    while(!accept("}")) {
      if(peek().kind==Token::End)throw Error("E_PARSE","unterminated block",peek().span);
      body.push_back(statement());
    }
    return body;
  }
  bool matchAhead()const {
    if(peek().text!="match")return false;int depth=0,braces=0;
    for(size_t n=1;i+n<tokens.size();++n){const auto &text=peek(n).text;if(!depth&&!braces&&(text==";"||text=="="||text=="}"))return false;if(!depth&&text=="{")++braces;else if(!depth&&text=="}"&&braces){if(!--braces)return false;}if(braces==1&&text=="=>")return true;if(text=="("||text=="[")++depth;if(text==")"||text=="]")--depth;if(depth<0)return false;}return false;
  }
  S statement() {
    SyntaxDepth depth(syntaxDepth,peek().span);
    auto s=std::make_shared<Stmt>(); s->span=peek().span;
    if(peek().text=="let" || peek().text=="var") {
      s->kind=take().text=="let" ? Stmt::Let : Stmt::Var; s->name=name().text;
      expect(":"); s->type=type(); expect("="); s->expr=expression(); expect(";");
    } else if(accept("return")) {
      s->kind=Stmt::Return; if(!accept(";")){s->expr=expression();expect(";");}
    } else if(accept("if")) {
      s->kind=Stmt::If; s->expr=expression(); s->body=block();
      if(accept("else")) { if(peek().text=="if")s->alternative={statement()}; else s->alternative=block(); }
    } else if(accept("while")) {
      s->kind=Stmt::While; s->expr=expression(); s->body=block();
    } else if(peek().kind==Token::Id && peek(1).text=="=") {
      s->kind=Stmt::Assign; s->name=take().text; take(); s->expr=expression();expect(";");
    } else {s->kind=Stmt::Expression;s->expr=expression();if(s->expr->kind==Expr::Match&&s->expr->statementMatch){s->kind=Stmt::Match;s->arms=s->expr->arms;}else expect(";");}
    s->sourceRange=syntaxRange(s->span.begin);return s;
  }
public:
  Parser(std::string source,std::string path,unsigned maxTokens=0,std::string kind="unit",bool names=false,bool details=false,bool tasks=false,bool resources=false):inputKind(std::move(kind)),captureNames(names||details),captureDetails(details) {
    p.source=std::move(source);p.path=std::move(path);p.taskPrototype=tasks;
    if(resources)p.sourceLanguage=SourceLanguage::OwnedResources021;
    try{Lexer lex(p.source,p.path);
      do {tokens.push_back(lex.next());if(maxTokens&&tokens.size()>maxTokens)throw Error("E_DEBUG_LIMIT","expression exceeds its token budget",tokens.back().span);}while(tokens.back().kind!=Token::End);
    }catch(Error &error){annotate(error);throw;}
  }
  E expressionOnly()try{auto value=expression();if(peek().kind!=Token::End)throw Error("E_PARSE","unexpected token after expression",peek().span);return value;}catch(Error &error){annotate(error);throw;}
  S statementOnly()try{auto value=statement();if(peek().kind!=Token::End)throw Error("E_PARSE","unexpected token after statement",peek().span);return value;}catch(Error &error){annotate(error);throw;}
  P patternOnly()try{unsigned nodes=0;auto value=pattern(0,nodes);if(peek().kind!=Token::End)throw Error("E_PARSE","unexpected token after pattern",peek().span);return value;}catch(Error &error){annotate(error);throw;}
  Type typeOnly()try{auto value=type();if(peek().kind!=Token::End)throw Error("E_TYPE","unexpected token after type",peek().span);return value;}catch(Error &error){annotate(error);throw;}
  Program run() try {
    expect("module");p.module=qualified();expect(";");
    while(peek().kind!=Token::End) {
      if(accept("endpoint")){
        Endpoint endpoint;endpoint.span=tokens.at(i-1).span;endpoint.name=name().text;
        auto literal=[&](){auto token=take();if(token.kind!=Token::String)throw Error("E_PARSE","endpoint requires quoted method/path",token.span);try{return nexrt::decodeLiteral(token.text);}catch(const nexrt::DataError &err){throw Error(err.code,err.what(),token.span);}};
        expect("(");endpoint.method=literal();expect(",");endpoint.path=literal();
        if(accept(",")){auto token=take();auto [end,error]=std::from_chars(token.text.data(),token.text.data()+token.text.size(),endpoint.successStatus);if(token.kind!=Token::Num||error!=std::errc()||end!=token.text.data()+token.text.size())throw Error("E_PARSE","endpoint status must be an integer literal",token.span);}
        expect(")");expect("=");auto targetSpan=peek().span;endpoint.target=qualified();editorName("function",endpoint.target,head(targetSpan));endpoint.span.end=expect(";").span.end;p.endpoints.push_back(std::move(endpoint));continue;
      }
      if(accept("import")){
        Import dependency;dependency.span=tokens.at(i-1).span;auto token=take();
        if(token.kind!=Token::String)throw Error("E_PARSE","import path must be a quoted string",token.span);
        try{dependency.path=nexrt::decodeLiteral(token.text);}catch(const nexrt::DataError &err){throw Error(err.code,err.what(),token.span);}
        expect("as");auto alias=name();dependency.alias=alias.text;editorName("alias",alias.text,alias.span);dependency.span.end=expect(";").span.end;p.imports.push_back(std::move(dependency));continue;
      }
      auto start=peek().span;bool exported=accept("pub");
      if(supportsExternalResources(p)&&(peek().text=="resource"||((peek().text=="server"||peek().text=="client"||peek().text=="shared")&&peek(1).text=="resource"))){
        auto realm=peek().text=="resource"?"shared":take().text;expect("resource");
        if(realm!="server")throw Error("E_REALM","opaque resource declarations require server realm",start);
        Structure s;s.span=start;s.exported=exported;s.opaqueResource=true;auto identifier=name();s.name=identifier.text;s.nameOrigin=identifier.span;s.typeParameters=templateParameters(s.typeBounds,s.typeArities);s.span.end=expect(";").span.end;
        p.structures.push_back(std::move(s));clearParameters();continue;
      }
      if(accept("trait")){
        Trait value;value.span=start;value.exported=exported;auto traitName=name();value.name=traitName.text;auto selfOrigin=traitName.span;
        if(accept("<")){auto self=expect("Self");selfOrigin=self.span;editorName("parameter_declaration","Self",self.span,self.span);value.selfArity=constructorArity();typeEnd();}
        clearParameters();parameters["Self"]=value.selfArity;if(captureNames)parameterOrigins["Self"]=selfOrigin;expect("{");
        while(!accept("}")){
          if(accept("type")){auto item=name();editorName("member_declaration",value.name+"::"+item.text,item.span);std::set<std::string> bounds;if(accept(":"))bounds=constraintNames();expect(";");if(!value.associated.emplace(item.text,std::move(bounds)).second)throw Error("E_DUPLICATE","duplicate associated type",item.span);continue;}
          Function method;method.span=peek().span;
          if(peek().text=="shared"||peek().text=="server"||peek().text=="client")method.realm=take().text;
          expect("fn");auto methodName=name();method.name=methodName.text;editorName("member_declaration",value.name+"::"+method.name,methodName.span);method.typeParameters=templateParameters(method.typeBounds,method.typeArities,true);expect("(");
          if(!accept(")")){do{auto item=name();expect(":");method.params.push_back({item.text,type(),item.span});}while(accept(","));expect(")");}
          expect("->");method.result=type();method.effects=effects();method.span.end=expect(";").span.end;value.methods.push_back(std::move(method));clearParameters();parameters["Self"]=value.selfArity;if(captureNames)parameterOrigins["Self"]=selfOrigin;
        }
        value.span.end=tokens.at(i-1).span.end;p.traits.push_back(std::move(value));clearParameters();continue;
      }
      if(accept("impl")){
        Implementation value;value.span=start;value.exported=exported;value.name=name().text;
        value.typeParameters=templateParameters(value.typeBounds,value.typeArities);expect(":");auto traitSpan=peek().span;value.trait=qualified();editorName("trait",value.trait,head(traitSpan));expect("for");value.self=type();expect("{");
        while(!accept("}")){
          if(peek().text=="type"&&peek(1).kind==Token::Id&&accept("type")){auto item=name();editorName("member_binding",value.trait+"::"+item.text,item.span);expect("=");auto typeValue=type();expect(";");if(!value.associated.emplace(item.text,std::move(typeValue)).second)throw Error("E_DUPLICATE","duplicate associated type binding",item.span);continue;}
          auto item=name();editorName("member_binding",value.trait+"::"+item.text,item.span);expect("=");ImplementationMethod method;method.span=item.span;auto targetSpan=peek().span;method.target=qualified();editorName("function",method.target,head(targetSpan));if(peek().text=="<")method.typeArguments=typeArguments();expect(";");
          if(!value.methods.emplace(item.text,std::move(method)).second)throw Error("E_DUPLICATE","duplicate implementation method",item.span);
        }
        value.span.end=tokens.at(i-1).span.end;p.implementations.push_back(std::move(value));clearParameters();continue;
      }
      if(peek().text=="enum") {
        Structure s;take();s.span=start;s.exported=exported;s.enumeration=true;s.name=name().text;s.typeParameters=templateParameters(s.typeBounds,s.typeArities);expect("{");
        if(s.name=="result"&&!s.typeParameters.empty())throw Error("E_GENERIC_NAME","generic nominal name conflicts with builtin result<T>",s.span);
        while(!accept("}")){
          auto tag=name();Variant v;v.name=tag.text;v.span=tag.span;v.ordinal=s.variants.size();
          if(accept("(")){if(!accept(")")){do{auto field=name();expect(":");v.fields.push_back({field.text,type(),field.span});}while(accept(","));expect(")");}}
          expect(";");s.variants.push_back(std::move(v));
        }
        s.span.end=tokens.at(i-1).span.end;p.structures.push_back(std::move(s));clearParameters();continue;
      }
      if(peek().text=="struct") {
        Structure s;take();s.span=start;s.exported=exported;s.name=name().text;s.typeParameters=templateParameters(s.typeBounds,s.typeArities);expect("{");
        if(s.name=="result"&&!s.typeParameters.empty())throw Error("E_GENERIC_NAME","generic nominal name conflicts with builtin result<T>",s.span);
        while(!accept("}")){auto field=name();expect(":");auto t=type();expect(";");s.fields.push_back({field.text,t,field.span});}
        s.span.end=tokens.at(i-1).span.end;p.structures.push_back(std::move(s));clearParameters();continue;
      }
      Function f; f.span=start;f.exported=exported;
      if(peek().text=="shared"||peek().text=="server"||peek().text=="client")f.realm=take().text;
      bool external=accept("extern");f.test=accept("test");expect("fn");f.name=name().text;f.typeParameters=templateParameters(f.typeBounds,f.typeArities);expect("(");
      if(!accept(")")) {do {auto n=name();expect(":");f.params.push_back({n.text,type(),n.span});}while(accept(","));expect(")");}
      expect("->"); f.result=type();
      if(accept("!")) {expect("{");if(!accept("}")){do {auto n=name();if(!f.effects.insert(n.text).second)throw Error("E_EFFECT","duplicate effect",n.span);}while(accept(","));expect("}");}}
      if(external){
        expect("=");expect("foreign");expect("(");
        auto literal=[&]{auto token=take();if(token.kind!=Token::String)throw Error("E_PARSE","foreign binding requires a string literal",token.span);try{return nexrt::decodeLiteral(token.text);}catch(const nexrt::DataError &e){throw Error(e.code,e.what(),token.span);}};
        ForeignBinding binding;binding.library=literal();expect(",");binding.symbol=literal();expect(",");binding.manifestSpan=peek().span;binding.manifest=literal();expect(")");expect(";");f.foreign=std::move(binding);
      }else{lambdaCounter=0;f.body=block();}
      f.span.end=tokens.at(i-1).span.end;p.functions.push_back(std::move(f));clearParameters();
    }
    return std::move(p);
  }catch(Error &error){annotate(error);throw;}
};
struct Binding {Type type;bool mutableValue;};
class Checker {
  Program &p; Function *f=nullptr; std::vector<std::map<std::string,Binding>> scopes;
  struct CaptureScope {size_t boundary;std::map<std::string,Binding> bindings;};
  std::vector<CaptureScope*> captures;bool watching=false;Function *watchBoundary=nullptr;
  bool hasLocal(const std::string &name)const{for(auto it=scopes.rbegin();it!=scopes.rend();++it)if(it->contains(name))return true;return false;}
  bool localFunction(const std::string &name)const{for(auto it=scopes.rbegin();it!=scopes.rend();++it)if(it->contains(name))return it->at(name).type.kind==Type::Function;return false;}
  Binding lookup(const std::string &name,Span span) {
    for(size_t index=scopes.size();index>0;--index)if(scopes[index-1].contains(name)){auto value=scopes[index-1].at(name);resourceRealm(value.type,f->realm,span);for(auto capture:captures)if(index-1<capture->boundary){value.mutableValue=false;capture->bindings[name]=value;}return value;}
    throw Error("E_NAME","unknown local '"+name+"'",span);
  }
  void same(Type actual,Type expected,Span span) {
    if(actual!=expected)throw Error("E_TYPE","expected "+typeName(expected)+", found "+typeName(actual),span);
  }
  void define(const std::string &name,Binding b,Span span) {
    if(scopes.back().contains(name))throw Error("E_DUPLICATE","duplicate local '"+name+"'",span);
    scopes.back()[name]=b;
  }
  void validType(Type &t,Span span,bool result=false) {
    t=resolveType(p,t,span);
    if(t==Type::Unit&&!result)throw Error("E_TYPE","unit is only valid as a function result",span);
    if(t.kind==Type::Constructor)throw Error("E_GENERIC_ARITY","type constructor must be fully applied before use as a value",span);
    if(t!=Type::Unit&&argumentKind(p,t,span)!=0)throw Error("E_GENERIC_KIND","value signature requires a fully applied type",span);
    if(f)resourceRealm(t,f->realm,span);
  }
  void resourceRealm(const Type &type,const std::string &realm,Span span){
    if(realm!="server"&&containsExternalResource(p,type))throw Error("E_REALM","external resource values require a server function, including aggregate and capture types",span);
    if(realm!="server"&&containsFile(p,type))throw Error("E_REALM","file values require a server function, including aggregate and capture types",span);
  }
  void unify(Type formal,Type actual,std::map<std::string,Type> &bound,Span span){
    if(formal.kind==Type::Projection){auto resolved=resolveType(p,substituteType(formal,bound),span);if(resolved==actual)return;if(resolved.kind==Type::Projection)throw Error("E_GENERIC_INFER","associated projections do not infer their Self type",span);unify(resolved,actual,bound,span);return;}
    if(formal.kind==Type::Parameter&&!formal.arguments.empty()){
      auto shape=constructorPattern(p,actual);Type head;std::vector<Type> args;
      if(shape.kind==Type::List||shape.kind==Type::Result||shape.kind==Type::Task||shape.kind==Type::Channel){head=Type::constructor(shape.kind==Type::List?"list":shape.kind==Type::Result?"result":shape.kind==Type::Task?"task":"channel",1);args={*shape.element};}
      else if(shape.kind==Type::Record&&!shape.arguments.empty()){head=Type::constructor(shape.name,shape.arguments.size());args=shape.arguments;}
      else if(shape.kind==Type::Parameter&&!shape.arguments.empty()){head=shape;head.arguments.clear();args=shape.arguments;}
      else throw Error("E_GENERIC_INFER","cannot infer an applied constructor from this type",span);
      if(args.size()!=formal.arguments.size())throw Error("E_GENERIC_KIND","constructor application arities differ",span);
      auto base=formal;base.arguments.clear();unify(base,head,bound,span);for(size_t i=0;i<args.size();++i)unify(formal.arguments[i],args[i],bound,span);return;
    }
    if(formal.kind==Type::Parameter){auto found=bound.find(formal.name);if(found==bound.end()){if(actual==Type::Unit)throw Error("E_TYPE","generic argument cannot be unit",span);if(argumentKind(p,actual,span)!=p.parameterKinds.at(formal.name))throw Error("E_GENERIC_KIND","inferred generic argument has the wrong kind",span);bound[formal.name]=actual;}else same(actual,found->second,span);return;}
    if(formal.kind==Type::Record&&!formal.arguments.empty()){
      if(actual.kind!=Type::Record)throw Error("E_TYPE","expected nominal generic type "+typeName(formal),span);
      const auto &instance=p.structure(actual.name);if(instance.templateName!=formal.name||instance.typeArguments.size()!=formal.arguments.size())throw Error("E_TYPE","generic nominal types differ",span);
      for(size_t i=0;i<formal.arguments.size();++i)unify(formal.arguments[i],instance.typeArguments[i],bound,span);return;
    }
    if(formal.kind!=actual.kind)throw Error("E_TYPE","expected "+typeName(formal)+", found "+typeName(actual),span);
    if(formal.kind==Type::Function){if(formal.arguments.size()!=actual.arguments.size()||formal.realm!=actual.realm||formal.effects!=actual.effects)throw Error("E_TYPE","callable signatures differ",span);for(size_t i=0;i<formal.arguments.size();++i)unify(formal.arguments[i],actual.arguments[i],bound,span);unify(*formal.element,*actual.element,bound,span);return;}
    if(formal.element){unify(*formal.element,*actual.element,bound,span);return;}same(actual,formal,span);
  }
  std::vector<Type> infer(const std::vector<std::string> &parameters,const std::vector<Param> &formals,Type result,E call,Type expected,bool partial=false){
    if(formals.size()!=call->args.size())throw Error("E_ARITY","incorrect number of value arguments",call->span);
    std::map<std::string,Type> bound;
    if(!call->typeArguments.empty()){
      if(parameters.size()!=call->typeArguments.size()&&!(partial&&call->typeArguments.size()==1))throw Error("E_GENERIC_ARITY","incorrect number of generic arguments",call->span);
      for(size_t i=0;i<call->typeArguments.size();++i){auto argument=resolveType(p,call->typeArguments[i],call->span);if(argument==Type::Unit)throw Error("E_TYPE","generic argument cannot be unit",call->span);if(argumentKind(p,argument,call->span)!=p.parameterKinds.at(parameters[i]))throw Error("E_GENERIC_KIND","explicit generic argument has the wrong kind",call->span);bound[parameters[i]]=argument;}
    }
    if(expected!=Type::Unknown){
      std::function<bool(const Type&)> projected=[&](const Type &type){if(type.kind==Type::Projection)return true;if(type.element&&projected(*type.element))return true;for(const auto &a:type.arguments)if(projected(a))return true;return false;};
      auto saved=bound;try{unify(result,expected,bound,call->span);}catch(const Error &error){if(!projected(result)||(error.code!="E_TYPE"&&error.code!="E_GENERIC_INFER"))throw;bound=std::move(saved);}
    }
    std::function<bool(const Type&)> missing=[&](const Type &type){if(type.kind==Type::Parameter&&std::find(parameters.begin(),parameters.end(),type.name)!=parameters.end()&&!bound.contains(type.name))return true;if(type.element&&missing(*type.element))return true;for(const auto &a:type.arguments)if(missing(a))return true;return false;};
    std::vector<bool> done(formals.size());size_t remaining=formals.size();
    while(remaining){bool progress=false;for(size_t i=0;i<formals.size();++i)if(!done[i]){
      auto hint=missing(formals[i].type)?Type():resolveType(p,substituteType(formals[i].type,bound),call->span);
      try{auto actual=expr(call->args[i],hint);unify(formals[i].type,actual,bound,call->args[i]->span);done[i]=true;--remaining;progress=true;}
      catch(const Error &error){if(error.code!="E_INFER"&&error.code!="E_GENERIC_INFER")throw;}
    }
      if(!progress)throw Error("E_GENERIC_INFER","cannot infer generic arguments; provide explicit types",call->span);}
    std::vector<Type> types;for(const auto &parameter:parameters){if(!bound.contains(parameter))throw Error("E_GENERIC_INFER","type parameter has no argument or expected-type constraint; provide explicit types",call->span);types.push_back(bound.at(parameter));}
    return types;
  }
  bool matching(E e,Type expected,bool statements){
    if(e->statementMatch!=statements)throw Error("E_MATCH_TYPE","block arms are statements; expression arms produce a value",e->span);
    auto subject=expr(e->args[0]);if(subject==Type::Unit)throw Error("E_MATCH_TYPE","cannot match unit",e->span);
    bool all=true;Type result=expected;
    auto scope=[&](const std::shared_ptr<MatchArm> &arm){scopes.emplace_back();for(const auto &binding:arm->bindings)if(binding.name!="_")define(binding.name,{binding.type,false},binding.span);};
    for(auto arm:e->arms){arm->bindings.clear();checkPattern(p,arm->pattern,subject,arm->bindings);arm->variant=arm->pattern->text;arm->ordinal=arm->pattern->ordinal;scope(arm);
      if(arm->guard)same(expr(e->args[arm->guard],Type::Bool),Type::Bool,arm->span);
      if(statements)all=block(arm->body,false)&&all;
      else {try{auto actual=expr(e->args[arm->value],result);if(result==Type::Unknown)result=actual;else same(actual,result,arm->span);}catch(const Error &error){if(result!=Type::Unknown||(error.code!="E_INFER"&&error.code!="E_GENERIC_INFER"))throw;}}
      scopes.pop_back();
    }
    if(!statements){if(result==Type::Unknown)throw Error("E_INFER","match result requires an expected or inferable arm type",e->span);for(auto arm:e->arms){scope(arm);same(expr(e->args[arm->value],result),result,arm->span);scopes.pop_back();}}
    checkMatchCoverage(p,e);e->type=statements?Type(Type::Unit):result;return all;
  }
  Type signature(const Function &fn){std::vector<Type> args;for(const auto &param:fn.params)args.push_back(param.type);return Type::function(std::move(args),fn.result,fn.realm,fn.effects);}
  void callableRealm(const Type &type,Span span){if(type.realm!="shared"&&type.realm!=f->realm)throw Error("E_REALM","callable realm "+type.realm+" is unavailable from "+f->realm,span);}
  void taskFileCall(const std::set<std::string> &effects,Span span,bool foreignLeaf=false){
    if(supportsTaskFileReads(p)&&f->effects.contains("task")&&
        effects.contains("fs")&&!effects.contains("task"))
      throw Error("E_EFFECT","a filesystem helper called from a task must explicitly declare both task and fs",span);
    if(supportsTaskForeignCalls(p)&&f->effects.contains("task")&&effects.contains("ffi")&&!effects.contains("task")&&!foreignLeaf)
      throw Error("E_EFFECT","a source ffi helper called from a task must explicitly declare both task and ffi",span);
  }
  Type reference(E e,Type expected){
    const Function *target=&p.function(e->text,e->span);
    if(!target->typeParameters.empty()){
      const auto &raw=p.functionTemplates.at(target->name);std::map<std::string,Type> bound;
      if(!e->typeArguments.empty()){if(e->typeArguments.size()!=raw.typeParameters.size()&&!(raw.traitSignature&&e->typeArguments.size()==1))throw Error("E_GENERIC_ARITY","incorrect number of function-reference type arguments",e->span);for(size_t i=0;i<e->typeArguments.size();++i){auto type=resolveType(p,e->typeArguments[i],e->span);if(type==Type::Unit)throw Error("E_TYPE","generic argument cannot be unit",e->span);if(argumentKind(p,type,e->span)!=p.parameterKinds.at(raw.typeParameters[i]))throw Error("E_GENERIC_KIND","reference argument has the wrong constructor kind",e->span);bound[raw.typeParameters[i]]=type;}}
      if(expected.kind==Type::Function)unify(signature(raw),expected,bound,e->span);
      std::vector<Type> arguments;for(const auto &parameter:raw.typeParameters){if(!bound.contains(parameter))throw Error("E_GENERIC_INFER","generic function value requires explicit types or a function-type context",e->span);arguments.push_back(bound.at(parameter));}
      target=&instantiateFunction(p,*target,arguments,e->span);if(raw.traitSignature){e->traitContract=raw.name;e->traitArguments=arguments;e->implementation=containsParameter(arguments[0])?"":selectedImplementation(p,arguments[0],raw.traitOwner,e->span);e->typeArguments=target->typeArguments;}else e->typeArguments=arguments;
    }else if(!e->typeArguments.empty()&&target->templateName.empty())throw Error("E_GENERIC_ARITY","function is not generic",e->span);
    if(target->test)throw Error("E_TEST","test functions cannot be function values",e->span);
    auto type=signature(*target);validType(type,e->span);callableRealm(type,e->span);f->dependencies.insert(target->name);e->text=target->name;e->kind=Expr::FunctionRef;return e->type=type;
  }
  Type lambda(E e){
    if(e->lambda->checked){f->dependencies.insert(e->text);return e->type;}
    if(std::count_if(p.functions.begin(),p.functions.end(),[](const auto &fn){return fn.closure;})>=4096)throw Error("E_FUNCTION_LIMIT","closure instance limit exceeded",e->span);
    auto &fn=*e->lambda;auto outer=f;auto signatureType=signature(fn);validType(signatureType,e->span);resourceRealm(signatureType,fn.realm,e->span);callableRealm(signatureType,e->span);
    fn.result=*signatureType.element;for(size_t i=0;i<fn.params.size();++i)fn.params[i].type=signatureType.arguments[i];
    fn.owner=outer->owner;fn.unit=outer->unit;fn.localName=outer->localName+"::$lambda_"+std::to_string(e->number);fn.name=outer->name+"::"+(watching?"$watch_lambda_":"$lambda_")+std::to_string(e->number);fn.closureOwner=outer->name;fn.closure=true;
    if(fn.name.size()>4096)throw Error("E_FUNCTION_LIMIT","closure target name exceeds 4096 bytes",e->span);
    auto boundary=scopes.size();CaptureScope capture{boundary,{}};scopes.emplace_back();captures.push_back(&capture);f=&fn;fn.dependencies.clear();
    try{
      for(const auto &param:fn.params)define(param.name,{param.type,false},param.span);
      if(!block(fn.body,false)&&fn.result!=Type::Unit)throw Error("E_RETURN","not all closure paths return a value",fn.span);
    }catch(...){captures.pop_back();scopes.resize(boundary);f=outer;throw;}
    captures.pop_back();scopes.resize(boundary);f=outer;fn.captures.clear();e->args.clear();
    for(const auto &[name,value]:capture.bindings){fn.captures.push_back({name,value.type,e->span});auto argument=std::make_shared<Expr>();argument->kind=Expr::Name;argument->span=e->span;argument->text=name;argument->type=value.type;e->args.push_back(std::move(argument));}
    if(fn.captures.size()>1024)throw Error("E_FUNCTION_LIMIT","closure exceeds 1024 captures",e->span);
    if(std::count_if(p.functions.begin(),p.functions.end(),[](const auto &fn){return fn.closure;})>=4096)throw Error("E_FUNCTION_LIMIT","closure instance limit exceeded",e->span);
    fn.checked=true;e->text=fn.name;e->type=signatureType;p.functions.push_back(fn);f->dependencies.insert(fn.name);return e->type;
  }
  Type taskCallback(E callback,const std::vector<Type> &parameters,Type expected){
    Type hint;
    if(callback->kind==Expr::Name&&callback->typeArguments.empty()&&
        !hasLocal(callback->localName.empty()?callback->text:callback->localName)){
      const auto &target=p.function(callback->text,callback->span);
      if(!target.typeParameters.empty()&&target.params.size()==parameters.size()){
        std::map<std::string,Type> bound;
        for(size_t i=0;i<parameters.size();++i)unify(target.params[i].type,parameters[i],bound,callback->span);
        if(expected!=Type::Unknown)unify(target.result,expected,bound,callback->span);
        if(std::all_of(target.typeParameters.begin(),target.typeParameters.end(),[&](const auto &name){return bound.contains(name);}))
          hint=substituteType(signature(target),bound);
      }
    }
    auto type=expr(callback,hint);
    if(type.kind!=Type::Function||type.arguments.size()!=parameters.size())
      throw Error("E_TASK_TYPE","task callback has an incorrect function signature",callback->span);
    for(size_t i=0;i<parameters.size();++i)same(type.arguments[i],parameters[i],callback->span);
    callableRealm(type,callback->span);
    const bool fileCallback=supportsTaskFileReads(p)&&type.realm=="server"&&
      type.effects==std::set<std::string>{"fs","task"};
    const bool foreignCallback=supportsTaskForeignCalls(p)&&type.realm=="server"&&type.effects.contains("task")&&type.effects.contains("ffi")&&
      std::all_of(type.effects.begin(),type.effects.end(),[](const auto &effect){return effect=="task"||effect=="ffi"||effect=="fs";});
    if(foreignCallback){
      if(f->realm!="server"||!std::includes(f->effects.begin(),f->effects.end(),type.effects.begin(),type.effects.end()))
        throw Error("E_EFFECT","a task/ffi callback requires the server caller's complete declared effects",callback->span);
    }else if(fileCallback){
      if(f->realm!="server"||!f->effects.contains("fs")||!f->effects.contains("task"))
        throw Error("E_EFFECT","a task/fs callback requires a server caller declaring task and fs",callback->span);
    }else for(const auto &effect:type.effects)if(effect!="task")
      throw Error("E_EFFECT",supportsTaskFileReads(p)?
        "task callbacks must be pure, task-only, or server task/fs with caller authorization":
        "task callbacks may declare only the task effect",callback->span);
    auto unsupportedResource=[&](const Type &value){return supportsTaskForeignCalls(p)?containsFile(p,value):containsNonTaskResource(p,value);};
    if(unsupportedResource(type))throw Error("E_TASK_TYPE","task callback signatures cannot carry file resources",callback->span);
    if(callback->kind==Expr::Lambda||callback->kind==Expr::FunctionRef){
      const auto &target=p.function(callback->text,callback->span);
      for(const auto &capture:target.captures)if(unsupportedResource(capture.type))
        throw Error("E_TASK_TYPE","task callbacks cannot capture file resources",callback->span);
    }
    return *type.element;
  }
  Type taskCall(E e,Type expected){
    if(!f->effects.contains("task"))throw Error("E_EFFECT",e->text+" requires declared effect task",e->span);
    auto arity=[&](size_t count){if(e->args.size()!=count)throw Error("E_ARITY",e->text+" expects "+std::to_string(count)+" arguments",e->span);};
    if(e->text=="with_tasks"){
      arity(2);same(expr(e->args[0],Type::I64),Type::I64,e->args[0]->span);
      return taskCallback(e->args[1],{Type::TaskScope},expected);
    }
    if(e->text=="task_spawn"){
      arity(2);same(expr(e->args[0],Type::TaskScope),Type::TaskScope,e->args[0]->span);
      return Type::task(taskCallback(e->args[1],{},expected.kind==Type::Task?*expected.element:Type()));
    }
    if(e->text=="current_task_scope"){arity(0);return Type::TaskScope;}
    if(e->text=="task_yield"){arity(0);return Type::Unit;}
    if(e->text=="channel_new"){
      arity(2);same(expr(e->args[0],Type::TaskScope),Type::TaskScope,e->args[0]->span);
      same(expr(e->args[1],Type::I64),Type::I64,e->args[1]->span);
      if(e->typeArguments.size()>1)throw Error("E_GENERIC_ARITY","channel_new accepts one payload type",e->span);
      auto item=e->typeArguments.empty()?(expected.kind==Type::Channel?*expected.element:Type()):e->typeArguments[0];
      if(item==Type::Unknown)throw Error("E_INFER","channel_new needs a payload type or channel<T> context",e->span);
      validType(item,e->span);
      if(supportsTaskForeignCalls(p)?containsFile(p,item):containsNonTaskResource(p,item))throw Error("E_TASK_TYPE","channel payloads cannot carry file resources",e->span);
      return Type::channel(std::move(item));
    }
    arity(e->text=="task_send"?2:1);
    auto value=expr(e->args[0]);
    if(e->text=="task_wait"||e->text=="task_cancel"){
      if(value.kind!=Type::Task)throw Error("E_TASK_TYPE",e->text+" requires task<T>",e->args[0]->span);
      return e->text=="task_cancel"?Type(Type::Bool):*value.element;
    }
    if(value.kind!=Type::Channel)throw Error("E_TASK_TYPE",e->text+" requires channel<T>",e->args[0]->span);
    if(e->text=="task_send"){
      same(expr(e->args[1],*value.element),*value.element,e->args[1]->span);return Type::Bool;
    }
    if(e->text=="task_recv")return Type::result(*value.element);
    return Type::Bool;
  }
  Type expr(E e,Type expected={}) {
    switch(e->kind) {
    case Expr::FunctionRef:reference(e,expected);break;
    case Expr::Lambda:lambda(e);break;
    case Expr::Invoke:{
      auto type=expr(e->args[0]);if(type.kind!=Type::Function)throw Error("E_TYPE","called expression is not a function",e->span);
      if(e->args.size()!=type.arguments.size()+1)throw Error("E_ARITY","incorrect number of callable arguments",e->span);
      for(size_t i=0;i<type.arguments.size();++i)same(expr(e->args[i+1],type.arguments[i]),type.arguments[i],e->args[i+1]->span);
      callableRealm(type,e->span);for(const auto &effect:type.effects)if(!f->effects.contains(effect))throw Error("E_EFFECT","indirect call requires declared effect "+effect,e->span);taskFileCall(type.effects,e->span);e->type=*type.element;break;
    }
    case Expr::Match:matching(e,expected,false);break;
    case Expr::Integer:e->type=(expected.kind==Type::Parameter||expected.kind==Type::Projection)&&satisfiesConstraint(p,expected,"integer")?expected:Type(Type::I64);break;
    case Expr::Floating:e->type=Type::F64;break;
    case Expr::Boolean:e->type=Type::Bool;break;
    case Expr::String:e->type=Type::Str;break;
    case Expr::List: {
      Type element=expected.kind==Type::List?*expected.element:Type();
      for(auto a:e->args){auto actual=expr(a,element);if(element==Type::Unknown)element=actual;else same(actual,element,a->span);}
      if(element==Type::Unknown)throw Error("E_INFER","empty list requires a list element type from context",e->span);
      validType(element,e->span);e->type=Type::list(element);break;
    }
    case Expr::Field: {
      auto base=expr(e->args[0]);if(base.kind!=Type::Record)throw Error("E_TYPE","field selection requires a structure",e->span);
      const auto &s=p.structure(base.name);bool found=false;
      for(size_t i=0;i<s.fields.size();++i)if(s.fields[i].name==e->text){e->number=int64_t(i);e->type=s.fields[i].type;found=true;break;}
      if(!found)throw Error("E_FIELD","unknown field '"+e->text+"' on "+base.name,e->span);break;
    }
    case Expr::Index: {
      auto base=expr(e->args[0]);same(expr(e->args[1],Type::I64),Type::I64,e->span);
      if(base.kind!=Type::List&&base!=Type::Str&&base!=Type::Bytes)throw Error("E_TYPE","indexing requires a list, string or bytes",e->span);
      e->type=base==Type::Str?Type(Type::Str):base==Type::Bytes?Type(Type::I64):*base.element;break;
    }
    case Expr::Name:{auto local=e->localName.empty()?e->text:e->localName;if(hasLocal(local)){e->text=local;e->type=lookup(local,e->span).type;}else reference(e,expected);break;}
    case Expr::Propagate: {
      if(watching&&f==watchBoundary)throw Error("E_DEBUG_RETURN","result propagation needs an executing function; use a pure helper or inspect the result",e->span);
      if(f->result.kind!=Type::Result)throw Error("E_RESULT_RETURN","postfix ? requires the current function to return result<T>",e->span);
      auto operand=expr(e->args[0],expected==Type::Unknown?Type():Type::result(expected));
      if(operand.kind!=Type::Result)throw Error("E_TYPE","postfix ? requires a result<T> operand",e->span);
      e->type=*operand.element;break;
    }
    case Expr::Unary: {
      auto operand=expr(e->args[0],e->text=="!"?Type(Type::Bool):satisfiesConstraint(p,expected,"number")?expected:Type());
      if(e->text=="!")same(operand,Type::Bool,e->span);else if(!satisfiesConstraint(p,operand,"number"))throw Error("E_TYPE","unary - requires number constraint, i64 or f64",e->span);
      e->type=operand;break;
    }
    case Expr::Binary: {
      const auto &op=e->text;
      bool equality=op=="=="||op=="!=";Type hint;
      if(equality)hint=Type::Unknown;else if(op=="&&"||op=="||")hint=Type::Bool;
      else if(op=="+")hint=satisfiesConstraint(p,expected,"add")?expected:Type();
      else if(satisfiesConstraint(p,expected,"number")&&op!="<"&&op!="<="&&op!=">"&&op!=">=")hint=expected;
      Type a,b;bool rightTyped=false;
      try{a=expr(e->args[0],hint);}catch(const Error &error){if(op=="&&"||op=="||"||(error.code!="E_INFER"&&error.code!="E_GENERIC_INFER"))throw;b=expr(e->args[1]);rightTyped=true;a=expr(e->args[0],b);}
      if(!rightTyped)b=expr(e->args[1],a);
      if(a==Type::I64&&(b.kind==Type::Parameter||b.kind==Type::Projection)&&satisfiesConstraint(p,b,"integer"))a=expr(e->args[0],b);
      same(b,a,e->span);
      if(op=="&&"||op=="||"){same(a,Type::Bool,e->span);e->type=Type::Bool;}
      else if(op=="=="||op=="!="){if(a==Type::Unit)throw Error("E_TYPE","cannot compare unit",e->span);e->type=Type::Bool;}
      else {bool ordering=op=="<"||op=="<="||op==">"||op==">=";auto bound=ordering?"ordered":op=="+"?"add":"number";
        if(!satisfiesConstraint(p,a,bound))throw Error("E_TYPE","operator '"+op+"' requires '"+bound+"' for "+typeName(a),e->span);e->type=ordering?Type(Type::Bool):a;}
      break;
    }
    case Expr::Call: {
      auto local=e->localName.empty()?e->text:e->localName;
      if(localFunction(local)){
        if(!e->typeArguments.empty())throw Error("E_GENERIC_ARITY","function values do not accept type arguments at invocation",e->span);
        auto callee=std::make_shared<Expr>();callee->kind=Expr::Name;callee->text=local;callee->span=e->span;e->args.insert(e->args.begin(),std::move(callee));e->kind=Expr::Invoke;e->text.clear();return expr(e,expected);
      }
      if(!e->typeArguments.empty()&&builtinNames(p.taskPrototype,supportsExternalResources(p)).contains(e->text)&&!(p.taskPrototype&&e->text=="channel_new"))throw Error("E_GENERIC_ARITY","this builtin does not accept explicit type arguments",e->span);
      auto arity=[&](size_t count){if(e->args.size()!=count)throw Error("E_ARITY",e->text+" expects "+std::to_string(count)+" arguments",e->span);};
      if(p.taskPrototype&&taskBuiltins().contains(e->text)){e->type=taskCall(e,expected);break;}
      if(supportsExternalResources(p)&&externalResourceBuiltins().contains(e->text)){
        arity(1);auto type=expr(e->args[0]);
        if(!isExternalResource(p,type))throw Error("E_RESOURCE_TYPE",e->text+" requires an opaque resource owner",e->args[0]->span);
        if(f->realm!="server")throw Error("E_REALM",e->text+" requires a server function",e->span);
        if(!f->effects.contains("ffi"))throw Error("E_EFFECT",e->text+" requires declared effect ffi",e->span);
        e->type=Type::Bool;break;
      }
      if(e->text=="parallel_map"){
        arity(3);Type items,callback;bool callbackTyped=false;
        auto checkCallback=[&](Type value){
          if(value.kind!=Type::Function||value.arguments.size()!=1||*value.element==Type::Unit)
            throw Error("E_PARALLEL_TYPE","parallel_map needs a one-argument value-returning callback",e->args[1]->span);
          callableRealm(value,e->args[1]->span);
          if(!value.effects.empty())throw Error("E_EFFECT","parallel_map callback must have no declared effects",e->args[1]->span);
          if(containsNonTaskResource(p,value)||containsTaskAuthority(p,value))throw Error("E_PARALLEL_TYPE","parallel_map callback signature cannot contain file or task resources",e->args[1]->span);
        };
        try{items=expr(e->args[0]);}catch(const Error &error){
          if(error.code!="E_INFER"&&error.code!="E_GENERIC_INFER")throw;
          callback=expr(e->args[1]);callbackTyped=true;checkCallback(callback);
          items=expr(e->args[0],Type::list(callback.arguments[0]));
        }
        if(items.kind!=Type::List)throw Error("E_TYPE","parallel_map input must be a list",e->args[0]->span);
        if(containsNonTaskResource(p,items)||containsTaskAuthority(p,items))throw Error("E_PARALLEL_TYPE","parallel_map input cannot contain file or task resources",e->args[0]->span);
        if(!callbackTyped){
          Type hint;
          if(e->args[1]->kind==Expr::Name&&!hasLocal(e->args[1]->localName.empty()?e->args[1]->text:e->args[1]->localName)&&e->args[1]->typeArguments.empty()){
            const auto &target=p.function(e->args[1]->text,e->args[1]->span);
            if(!target.typeParameters.empty()&&target.params.size()==1){
              std::map<std::string,Type> bound;unify(target.params[0].type,*items.element,bound,e->args[1]->span);
              if(expected.kind==Type::List)unify(target.result,*expected.element,bound,e->args[1]->span);
              if(std::all_of(target.typeParameters.begin(),target.typeParameters.end(),[&](const auto&name){return bound.contains(name);}))hint=substituteType(signature(target),bound);
            }
          }
          callback=expr(e->args[1],hint);checkCallback(callback);
        }
        if(p.taskPrototype&&(e->args[1]->kind==Expr::Lambda||e->args[1]->kind==Expr::FunctionRef)){
          const auto &target=p.function(e->args[1]->text,e->args[1]->span);
          for(const auto &capture:target.captures)if(containsTaskAuthority(p,capture.type)||containsExternalResource(p,capture.type))
            throw Error("E_PARALLEL_TYPE","parallel_map callbacks cannot capture task, channel or external resource authority",e->args[1]->span);
        }
        same(*items.element,callback.arguments[0],e->args[0]->span);
        same(expr(e->args[2],Type::I64),Type::I64,e->args[2]->span);
        e->type=Type::list(*callback.element);break;
      }
      if(e->text=="as_f64"||e->text=="as_i64"){
        arity(1);auto input=e->text=="as_f64"?Type(Type::I64):Type(Type::F64);
        same(expr(e->args[0],input),input,e->span);e->type=e->text=="as_f64"?Type(Type::F64):Type::result(Type::I64);break;
      }
      if(e->text=="bytes"||e->text=="utf8_bytes"||e->text=="decode_utf8"||e->text=="encode_base64"||e->text=="decode_base64"){
        arity(1);auto input=e->text=="bytes"?Type::list(Type::I64):e->text=="decode_utf8"||e->text=="encode_base64"?Type(Type::Bytes):Type(Type::Str);
        same(expr(e->args[0],input),input,e->span);
        e->type=e->text=="bytes"||e->text=="decode_base64"?Type::result(Type::Bytes):e->text=="decode_utf8"?Type::result(Type::Str):e->text=="utf8_bytes"?Type(Type::Bytes):Type(Type::Str);break;
      }
      if(streamFileBuiltins().contains(e->text)){
        bool open=e->text.starts_with("file_open_");
        bool pair=e->text=="file_read"||e->text=="file_write"||e->text=="file_seek";
        arity(pair?2:1);
        auto first=open?Type(Type::Str):Type(Type::File);same(expr(e->args[0],first),first,e->args[0]->span);
        if(pair){auto second=e->text=="file_write"?Type(Type::Bytes):Type(Type::I64);same(expr(e->args[1],second),second,e->args[1]->span);}
        if(f->realm!="server")throw Error("E_REALM",e->text+" requires a server function",e->span);
        if(!f->effects.contains("fs"))throw Error("E_EFFECT",e->text+" requires declared effect fs",e->span);
        e->type=open?Type::result(Type::File):e->text=="file_read"?Type::result(Type::Bytes):e->text=="file_close"||e->text=="file_is_open"?Type(Type::Bool):e->text=="file_flush"?Type::result(Type::Bool):Type::result(Type::I64);break;
      }
      if(e->text=="read_env"||e->text=="store_get"||e->text=="store_put"||e->text=="store_remove"||e->text=="store_keys"||e->text=="file_read_text"||e->text=="file_write_text"||e->text=="file_read_bytes"||e->text=="file_write_bytes"){
        arity(e->text=="store_put"||e->text=="file_write_text"||e->text=="file_write_bytes"?2:1);
        for(size_t i=0;i<e->args.size();++i){auto type=i==1&&e->text=="file_write_bytes"?Type(Type::Bytes):Type(Type::Str);same(expr(e->args[i],type),type,e->args[i]->span);}
        if(f->realm!="server")throw Error("E_REALM",e->text+" requires a server function",e->span);
        std::string effect=e->text=="read_env"?"io":e->text.starts_with("file_")?"fs":"db";if(!f->effects.contains(effect))throw Error("E_EFFECT",e->text+" requires declared effect "+effect,e->span);
        e->type=Type::result(e->text=="store_keys"?Type::list(Type::Str):e->text=="store_put"||e->text=="store_remove"||e->text=="file_write_text"||e->text=="file_write_bytes"?Type(Type::Bool):e->text=="file_read_bytes"?Type(Type::Bytes):Type(Type::Str));break;
      }
      if(e->text=="ok"){
        arity(1);auto item=expr(e->args[0],expected.kind==Type::Result?*expected.element:Type());validType(item,e->span);e->type=Type::result(item);break;
      }
      if(e->text=="err"){
        arity(2);for(auto a:e->args)same(expr(a,Type::Str),Type::Str,a->span);
        auto item=e->annotation!=Type::Unknown?e->annotation:expected.kind==Type::Result?*expected.element:Type();
        if(item==Type::Unknown)throw Error("E_INFER","err requires result<T> context or err<T>(code, message)",e->span);
        validType(item,e->span);e->type=Type::result(item);break;
      }
      if(e->text=="is_ok"||e->text=="unwrap"||e->text=="error_code"||e->text=="error_message"){
        arity(1);auto hint=e->text=="unwrap"&&expected!=Type::Unknown?Type::result(expected):Type();auto item=expr(e->args[0],hint);if(item.kind!=Type::Result)throw Error("E_TYPE",e->text+" requires result<T>",e->span);
        e->type=e->text=="is_ok"?Type(Type::Bool):e->text=="unwrap"?*item.element:Type(Type::Str);break;
      }
      if(e->text=="encode_json"){
        arity(1);auto type=expr(e->args[0]);validType(type,e->span);if(!satisfiesConstraint(p,type,"wire"))throw Error("E_GENERIC_BOUND","encode_json requires a wire type or a wire generic constraint",e->span);e->type=Type::Str;break;
      }
      if(e->text=="decode_json"){
        arity(1);same(expr(e->args[0],Type::Str),Type::Str,e->span);
        if(e->annotation==Type::Unknown)throw Error("E_INFER","decode_json requires an explicit type: decode_json<T>(text)",e->span);
        validType(e->annotation,e->span);if(!satisfiesConstraint(p,e->annotation,"wire"))throw Error("E_GENERIC_BOUND","decode_json requires a wire type or a wire generic constraint",e->span);e->type=Type::result(e->annotation);break;
      }
      if(const Structure *owner=nullptr;auto variant=p.variant(e->text,&owner)){
        if(!owner->typeParameters.empty()){
          const auto &raw=p.structureTemplates.at(owner->name);const Variant *source=nullptr;for(const auto &v:raw.variants)if(v.name==variant->name)source=&v;
          auto result=Type::record(raw.name);for(const auto &parameter:raw.typeParameters){Type t(Type::Parameter);t.name=parameter;result.arguments.push_back(t);}
          auto arguments=infer(raw.typeParameters,source->fields,result,e,expected);auto instance=Type::record(raw.name);instance.arguments=arguments;instance=resolveType(p,instance,e->span);
          e->text=instance.name+"::"+source->name;e->typeArguments=arguments;variant=p.variant(e->text,&owner);
        }else if(!e->typeArguments.empty()&&owner->templateName.empty())throw Error("E_GENERIC_ARITY","enum is not generic",e->span);
        arity(variant->fields.size());for(size_t i=0;i<e->args.size();++i)same(expr(e->args[i],variant->fields[i].type),variant->fields[i].type,e->args[i]->span);
        e->number=variant->ordinal;e->type=Type::record(owner->name);break;
      }
      if(p.hasStructure(e->text)) {
        const auto &declaration=p.structure(e->text);
        if(declaration.opaqueResource)throw Error("E_RESOURCE_CONSTRUCTOR","opaque resources have no source constructor; use a granted external factory",e->span);
        if(!declaration.typeParameters.empty()){
          const auto &raw=p.structureTemplates.at(declaration.name);auto result=Type::record(raw.name);for(const auto &parameter:raw.typeParameters){Type t(Type::Parameter);t.name=parameter;result.arguments.push_back(t);}
          auto arguments=infer(raw.typeParameters,raw.fields,result,e,expected);auto instance=Type::record(raw.name);instance.arguments=arguments;instance=resolveType(p,instance,e->span);e->text=instance.name;e->typeArguments=arguments;
        }else if(!e->typeArguments.empty()&&declaration.templateName.empty())throw Error("E_GENERIC_ARITY","structure is not generic",e->span);
        const auto &s=p.structure(e->text);if(s.enumeration)throw Error("E_CONSTRUCTOR","construct an enum through its named variant",e->span);arity(s.fields.size());
        for(size_t i=0;i<e->args.size();++i)same(expr(e->args[i],s.fields[i].type),s.fields[i].type,e->args[i]->span);
        e->type=Type::record(s.name);break;
      }
      if(e->text=="len"||e->text=="str") {
        arity(1);auto t=expr(e->args[0]);
        if(e->text=="len"&&t!=Type::Str&&t!=Type::Bytes&&t.kind!=Type::List)throw Error("E_TYPE","len requires str, bytes or list",e->span);
        if(t==Type::Unit)throw Error("E_TYPE","cannot format unit",e->span);
        e->type=e->text=="len"?Type::I64:Type::Str;break;
      }
      if(e->text=="push"||e->text=="set") {
        arity(e->text=="push"?2:3);auto item=e->args.back();
        Type list,itemType;bool listTyped=false;
        try{list=expr(e->args[0],expected.kind==Type::List||expected==Type::Bytes?expected:Type());listTyped=true;}catch(const Error &error){if(error.code!="E_INFER"&&error.code!="E_GENERIC_INFER")throw;}
        if(listTyped&&list==Type::Bytes){same(expr(item,Type::I64),Type::I64,e->span);if(e->text=="set")same(expr(e->args[1],Type::I64),Type::I64,e->span);e->type=list;break;}
        if(listTyped&&list.kind!=Type::List)throw Error("E_TYPE",e->text+" requires a list",e->span);
        itemType=expr(item,listTyped?*list.element:expected.kind==Type::List?*expected.element:Type());
        if(!listTyped)list=expr(e->args[0],Type::list(itemType));
        if(list.kind!=Type::List)throw Error("E_TYPE",e->text+" requires a list",e->span);
        same(itemType,*list.element,e->span);if(e->text=="set")same(expr(e->args[1],Type::I64),Type::I64,e->span);e->type=list;break;
      }
      if(e->text=="slice"||e->text=="contains") {
        arity(e->text=="slice"?3:2);auto base=expr(e->args[0],e->text=="slice"&&expected==Type::Bytes?Type(Type::Bytes):Type(Type::Str));
        if(base!=Type::Str&&(e->text!="slice"||base!=Type::Bytes))throw Error("E_TYPE",e->text+" requires "+(e->text=="slice"?"str or bytes":"str"),e->span);
        for(size_t i=1;i<e->args.size();++i)same(expr(e->args[i],e->text=="slice"?Type::I64:Type::Str),e->text=="slice"?Type::I64:Type::Str,e->span);
        e->type=e->text=="slice"?base:Type(Type::Bool);break;
      }
      if(e->text=="print"||e->text=="assert") {
        if(e->args.size()!=1)throw Error("E_ARITY",e->text+" expects one argument",e->span);
        auto t=expr(e->args[0],e->text=="assert"?Type(Type::Bool):Type());
        if(e->text=="assert")same(t,Type::Bool,e->span);
        else {if(t==Type::Unit)throw Error("E_TYPE","cannot print unit",e->span);
          if(!f->effects.contains("io"))throw Error("E_EFFECT","print requires declared effect io",e->span);}
        e->type=Type::Unit;break;
      }
      const Function *target=&p.function(e->text,e->span);
      if(!target->typeParameters.empty()){
        const auto &raw=p.functionTemplates.at(target->name);auto arguments=infer(raw.typeParameters,raw.params,raw.result,e,expected,raw.traitSignature);target=&instantiateFunction(p,*target,arguments,e->span);e->text=target->name;if(raw.traitSignature){e->traitContract=raw.name;e->traitArguments=arguments;e->implementation=containsParameter(arguments[0])?"":selectedImplementation(p,arguments[0],raw.traitOwner,e->span);e->typeArguments=target->typeArguments;}else e->typeArguments=arguments;
      }else if(!e->typeArguments.empty()&&target->templateName.empty())throw Error("E_GENERIC_ARITY","function is not generic",e->span);
      const auto &callee=*target;
      if(callee.test)throw Error("E_TEST","test functions cannot be called",e->span);
      if(callee.params.size()!=e->args.size())throw Error("E_ARITY","incorrect number of arguments to '"+e->text+"'",e->span);
      for(size_t j=0;j<e->args.size();++j)same(expr(e->args[j],callee.params[j].type),callee.params[j].type,e->args[j]->span);
      for(const auto &effect:callee.effects)if(!f->effects.contains(effect))throw Error("E_EFFECT","call requires declared effect "+effect,e->span);
      taskFileCall(callee.effects,e->span,callee.foreign.has_value());
      if(supportsTaskForeignCalls(p)&&f->effects.contains("task")&&callee.foreign&&
          (containsFile(p,callee.result)||std::any_of(callee.params.begin(),callee.params.end(),[&](const auto &parameter){return containsFile(p,parameter.type);})))
        throw Error("E_TASK_TYPE","task foreign calls cannot transport file authority",e->span);
      if(callee.realm!="shared" && callee.realm!=f->realm)throw Error("E_REALM","direct call from "+f->realm+" to "+callee.realm+" is forbidden",e->span);
      f->dependencies.insert(callee.name);e->type=callee.result;break;
    }
    }
    resourceRealm(e->type,f->realm,e->span);return e->type;
  }
  bool block(const std::vector<S> &body,bool newScope=true) {
    if(newScope)scopes.emplace_back(); bool returns=false;
    for(const auto &s:body) {
      if(returns)throw Error("E_UNREACHABLE","statement after unconditional return",s->span);
      switch(s->kind) {
      case Stmt::Let:case Stmt::Var:
        validType(s->type,s->span);
        same(expr(s->expr,s->type),s->type,s->span);define(s->name,{s->type,s->kind==Stmt::Var},s->span);break;
      case Stmt::Assign: {
        auto b=lookup(s->name,s->span);if(!b.mutableValue)throw Error("E_MUTABILITY","cannot assign immutable '"+s->name+"'",s->span);
        same(expr(s->expr,b.type),b.type,s->span);s->type=b.type;break;
      }
      case Stmt::Expression:expr(s->expr);break;
      case Stmt::Return:same(s->expr?expr(s->expr,f->result):Type::Unit,f->result,s->span);returns=true;break;
      case Stmt::If: {
        same(expr(s->expr,Type::Bool),Type::Bool,s->span);bool a=block(s->body),b=block(s->alternative);returns=a&&b;break;
      }
      case Stmt::Match:returns=matching(s->expr,{},true);s->type=s->expr->args[0]->type;break;
      case Stmt::While:same(expr(s->expr,Type::Bool),Type::Bool,s->span);block(s->body);break;
      }
    }
    if(newScope)scopes.pop_back();return returns;
  }
  void functionBody(Function &fn){
    if(fn.checked)return;auto previous=f;auto previousScopes=std::move(scopes);f=&fn;f->dependencies.clear();scopes.clear();scopes.emplace_back();
    try{
      for(auto &parameter:fn.params){validType(parameter.type,parameter.span);define(parameter.name,{parameter.type,false},parameter.span);}
      validType(fn.result,fn.span,true);
      if(fn.traitSignature){}
      else if(fn.foreign)(void)foreignSignature(p,fn);
      else if(!block(fn.body,false)&&fn.result!=Type::Unit)throw Error("E_RETURN","not all paths return a value in '"+fn.name+"'",fn.span);
      fn.checked=true;
    }catch(...){f=previous;scopes=std::move(previousScopes);throw;}
    f=previous;scopes=std::move(previousScopes);
  }
public:
  explicit Checker(Program &p):p(p){}
  Type watch(const std::string &function,E expression,const std::map<std::string,Type> &locals){
    auto selected=function;
    prepareGenerics(p);
    auto context=p.function(selected);context.effects.clear();context.dependencies.clear();f=&context;scopes.emplace_back();watching=true;watchBoundary=&context;
    for(const auto &[name,value]:locals){auto type=value;validType(type,expression->span);define(name,{type,false},expression->span);}
    auto result=expr(expression);for(size_t i=0;i<p.functions.size();++i)functionBody(p.functions[i]);return result;
  }
  void run() {
    prepareTraits(p);prepareGenerics(p);
    std::set<std::string> names;
    const auto &builtins=builtinNames(p.taskPrototype,supportsExternalResources(p));
    for(size_t index=0;index<p.structures.size();++index){auto &s=p.structures[index];
      if(s.opaqueResource&&(!supportsExternalResources(p)||s.enumeration||!s.fields.empty()||!s.variants.empty()))throw Error("E_RESOURCE_DECLARATION","invalid opaque resource declaration or source version",s.span);
      if(builtins.contains(s.localName.empty()?s.name:s.localName)||!names.insert(s.name).second)throw Error("E_DUPLICATE","duplicate or reserved structure '"+s.name+"'",s.span);
      auto fields=[&](auto &members){std::set<std::string> seen;for(auto &field:members){if(!seen.insert(field.name).second)throw Error("E_DUPLICATE","duplicate field '"+field.name+"'",field.span);validType(field.type,field.span);}};
      fields(s.fields);if(s.enumeration&&s.variants.empty())throw Error("E_ENUM","an enum requires at least one variant",s.span);
      std::set<std::string> tags;for(auto &variant:s.variants){if(!tags.insert(variant.name).second||!names.insert(s.name+"::"+variant.name).second)throw Error("E_DUPLICATE","duplicate enum variant",variant.span);fields(variant.fields);}
    }
    for(auto &fn:p.functions) {
      if(builtins.contains(fn.localName.empty()?fn.name:fn.localName)||!names.insert(fn.name).second)throw Error("E_DUPLICATE","duplicate or reserved function '"+fn.name+"'",fn.span);
      if(fn.foreign){
        if(fn.realm!="server")throw Error("E_REALM","external functions require server realm",fn.span);
        if(!fn.effects.contains("ffi"))throw Error("E_EFFECT","external functions require declared effect ffi",fn.span);
        if(fn.test||!fn.typeParameters.empty()||fn.closure)throw Error("E_FFI_DECLARATION","external declarations must be concrete named non-test functions",fn.span);
        auto identifier=[](const std::string &v){auto letter=[](char c){return(c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='_';};return !v.empty()&&v.size()<=128&&letter(v.front())&&std::all_of(v.begin(),v.end(),[&](char c){return letter(c)||(c>='0'&&c<='9');});};
        const auto &binding=*fn.foreign;if(!identifier(binding.library)||!identifier(binding.symbol)||binding.manifest.size()!=64||binding.manifest.find_first_not_of("0123456789abcdef")!=std::string::npos)throw Error("E_FFI_BINDING","external binding requires logical ASCII library/export names and a lowercase SHA-256 manifest pin",fn.span);
      }
      if(fn.foreign&&(fn.effects.contains("task")||containsTaskAuthority(p,fn.result)||std::any_of(fn.params.begin(),fn.params.end(),[&](const auto &param){return containsTaskAuthority(p,param.type);})))throw Error("E_TASK_TYPE","foreign declarations cannot carry task authority or suspend",fn.span);
      validType(fn.result,fn.span,true);
      for(auto &parameter:fn.params)validType(parameter.type,parameter.span);
      for(const auto &effect:fn.effects)if(effect!="io"&&effect!="db"&&effect!="fs"&&effect!="ffi"&&!(p.taskPrototype&&effect=="task"))throw Error("E_EFFECT","unsupported effect '"+effect+"'",fn.span);
      if(fn.effects.contains("ffi")&&fn.realm!="server")throw Error("E_REALM","ffi effect requires a server function",fn.span);
      if(fn.effects.contains("db")&&fn.realm!="server")throw Error("E_REALM","db effect requires a server function",fn.span);
      if(fn.effects.contains("fs")&&fn.realm!="server")throw Error("E_REALM","fs effect requires a server function",fn.span);
      if(fn.test && (!fn.params.empty()||fn.result!=Type::Unit||!fn.typeParameters.empty()))throw Error("E_TEST","test must take no generic/value parameters and return unit",fn.span);
    }
    checkImplementations(p);
    for(size_t i=0;i<p.functions.size();++i)functionBody(p.functions[i]);
    std::set<std::string> publicSeen;
    std::function<void(const Type&,Span)> publicType=[&](const Type &t,Span span){
      if(t.element)publicType(*t.element,span);for(const auto &argument:t.arguments)publicType(argument,span);
      if(t.kind==Type::Projection&&!traitDefinition(p,t.name.substr(0,t.name.rfind("::")),span).exported)throw Error("E_VISIBILITY","public signature exposes a private trait",span);
      if(t.kind==Type::Constructor&&p.hasStructure(t.name)&&!p.structure(t.name).exported)throw Error("E_VISIBILITY","public signature exposes a private constructor",span);
      if(t.kind==Type::Record){const auto &s=p.structure(t.name);if(!s.exported)throw Error("E_VISIBILITY","public API exposes private type '"+t.name+"'",span);if(publicSeen.insert(s.name).second){for(const auto &argument:s.typeArguments)publicType(argument,span);for(auto field:s.members())publicType(field->type,field->span);}}
    };
    auto publicBounds=[&](const TypeBounds &bounds,Span span){for(const auto &values:bounds)for(const auto &bound:values)if(std::any_of(p.traits.begin(),p.traits.end(),[&](const auto &trait){return trait.name==bound&&!trait.exported;}))throw Error("E_VISIBILITY","public declaration exposes private trait bound",span);};
    for(const auto &s:p.structures)if(s.exported&&s.templateName.empty())publicBounds(s.typeBounds,s.span);
    for(const auto &fn:p.functions)if(fn.exported&&fn.templateName.empty())publicBounds(fn.typeBounds,fn.span);
    for(const auto &trait:p.traits)if(trait.exported){for(const auto &[name,bounds]:trait.associated)publicBounds(TypeBounds{bounds},trait.span);for(const auto &method:trait.methods){publicType(method.result,method.span);for(const auto &param:method.params)publicType(param.type,param.span);publicBounds(method.typeBounds,method.span);}}
    for(const auto &value:p.implementations){const auto &trait=traitDefinition(p,value.trait);bool exposed=trait.exported;if((value.self.kind==Type::Record||value.self.kind==Type::Constructor)&&p.hasStructure(value.self.name))exposed=exposed&&p.structure(value.self.name).exported;if(exposed)for(const auto &[name,type]:value.associated)publicType(resolveType(p,type,value.span),value.span);}
    for(const auto &s:p.structures)if(s.exported&&s.templateName.empty())for(auto field:s.members())publicType(field->type,field->span);
    for(const auto &fn:p.functions)if(fn.exported&&fn.templateName.empty()){publicType(fn.result,fn.span);for(const auto &param:fn.params)publicType(param.type,param.span);}
    std::set<std::string> operations,routes;
    auto apiWire=[&](const Type &type,Span span){
      auto schema=wireSchema(p,type);auto object=schema.getAsObject();auto records=object->getObject("records");size_t nodes=0;
      auto enums=object->getObject("enums");if(json(schema,false).size()>262144||records->size()+enums->size()>1024)throw Error("E_API_LIMIT","endpoint wire schema exceeds size/record limits",span);
      std::function<void(const llvm::json::Value&,unsigned)> descriptor=[&](const auto &value,unsigned depth){if(++nodes>10000||depth>64)throw Error("E_API_LIMIT","endpoint wire schema exceeds descriptor limits",span);if(auto object=value.getAsObject()){if(auto item=object->get("list"))descriptor(*item,depth+1);if(auto item=object->get("result"))descriptor(*item,depth+1);}};
      for(const auto &[name,fields]:*records){auto array=fields.getAsArray();if(array->size()>1024)throw Error("E_API_LIMIT","endpoint record exceeds field limit",span);for(const auto &field:*array)descriptor(*field.getAsObject()->get("type"),0);}
      for(const auto &[name,cases]:*enums){auto variants=cases.getAsArray();if(variants->size()>1024)throw Error("E_API_LIMIT","endpoint enum exceeds variant limit",span);for(const auto &variant:*variants){auto fields=variant.getAsObject()->getArray("fields");if(fields->size()>1024)throw Error("E_API_LIMIT","endpoint enum payload exceeds field limit",span);for(const auto &field:*fields)descriptor(*field.getAsObject()->get("type"),0);}}
      descriptor(*object->get("root"),0);
    };
    for(const auto &endpoint:p.endpoints){
      auto local=endpoint.localName.empty()?endpoint.name:endpoint.localName;
      if(!operations.insert(local).second||!names.insert(endpoint.name).second)throw Error("E_API_NAME","endpoint operation names must be unique across the API and distinct from local definitions",endpoint.span);
      if(endpoint.method!="GET"&&endpoint.method!="POST"&&endpoint.method!="PUT"&&endpoint.method!="PATCH"&&endpoint.method!="DELETE")throw Error("E_API_METHOD","endpoint method must be GET, POST, PUT, PATCH or DELETE",endpoint.span);
      auto path=endpoint.path;
      if(!path.starts_with("/api/")||path.size()<=5||path.size()>256||path.find("//")!=std::string::npos||path.find("/../")!=std::string::npos||path.ends_with("/..")||path.find("/./")!=std::string::npos||path.ends_with("/.")||!std::all_of(path.begin(),path.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='/'||c=='_'||c=='-'||c=='.';}))throw Error("E_API_PATH","endpoint requires a normalized literal /api/ path of at most 256 ASCII bytes",endpoint.span);
      if(!routes.insert(endpoint.method+" "+path).second)throw Error("E_API_ROUTE","duplicate endpoint method/path",endpoint.span);
      if(endpoint.successStatus<200||endpoint.successStatus>=300||endpoint.successStatus==204||endpoint.successStatus==205)throw Error("E_API_STATUS","endpoint success status must permit a JSON body (2xx except 204/205)",endpoint.span);
      const auto &handler=p.function(endpoint.target,endpoint.span);
      if(handler.realm!="server"||handler.test||!handler.typeParameters.empty()||handler.params.empty()||handler.params.size()>2||handler.params[0].type!=Type::record("std::api::Context")||handler.result.kind!=Type::Result)throw Error("E_API_SIGNATURE","endpoint handler must be a concrete server fn(Context[, Input]) -> result<Output>",endpoint.span);
      if(endpoint.method=="GET"&&handler.params.size()!=1)throw Error("E_API_SIGNATURE","GET endpoints have context only; query/body input is not implicit",endpoint.span);
      const auto &context=p.structure("std::api::Context");
      if(context.fields.size()!=2||context.fields[0].name!="user"||context.fields[0].type!=Type::Str||context.fields[1].name!="request_id"||context.fields[1].type!=Type::Str)throw Error("E_API_SIGNATURE","incompatible std::api::Context",endpoint.span);
      publicType(handler.result,endpoint.span);
      if(handler.params.size()==2){publicType(handler.params[1].type,endpoint.span);apiWire(handler.params[1].type,endpoint.span);}
      apiWire(handler.result,endpoint.span);
    }
  }
};
llvm::json::Array blockJSON(const std::vector<S> &body);
llvm::json::Value exprJSON(E e) {
  if(!e)return nullptr;
  llvm::json::Array args;for(auto a:e->args)args.push_back(exprJSON(a));
  llvm::json::Object result{{"kind",int64_t(e->kind)},{"operator",e->text},{"value",e->number},{"type",typeName(e->type)},{"args",std::move(args)}};
  if(!e->traitContract.empty()){result["trait_contract"]=e->traitContract;result["implementation"]=e->implementation;llvm::json::Array types;for(const auto &type:e->traitArguments)types.push_back(typeName(type));result["trait_arguments"]=std::move(types);}
  if(e->kind==Expr::Lambda)result["lambda"]=canonical(*e->lambda);
  if(e->kind==Expr::Match){llvm::json::Array arms;for(auto arm:e->arms)arms.push_back(llvm::json::Object{{"pattern",canonicalPattern(arm->pattern)},{"guard",int64_t(arm->guard)},{"value",int64_t(arm->value)},{"body",blockJSON(arm->body)}});result["arms"]=std::move(arms);result["statement"]=e->statementMatch;}return result;
}
llvm::json::Array blockJSON(const std::vector<S> &body) {
  llvm::json::Array out;
  for(auto s:body){llvm::json::Object item{{"kind",int64_t(s->kind)},{"name",s->name},{"type",typeName(s->type)},{"expression",exprJSON(s->expr)},{"body",blockJSON(s->body)},{"else",blockJSON(s->alternative)}};
    out.push_back(std::move(item));}
  return out;
}
}
namespace {
void sourceUTF8(const std::string &source,const std::string &path,const std::string &kind){
  try{nexrt::unicodeOffsets(source,false);}catch(const nexrt::DataError &error){
    Span span;span.begin=span.end=error.offset;span.file=path;
    for(size_t i=0;i<error.offset;++i){if(source[i]=='\n'){++span.line;span.column=1;}else ++span.column;}
    Error diagnostic(error.code,error.what(),span);attachFrontendDiagnostic(diagnostic,{{path,source}},path,kind,"parse",true);throw diagnostic;
  }
}
}
Program parseVersioned(std::string source,std::string path,SourceLanguage language,bool editorNames,bool editorDetails){
  switch(language){
  case SourceLanguage::Language018:return parseLegacy018(std::move(source),std::move(path),editorNames,editorDetails);
  case SourceLanguage::Tasks019:case SourceLanguage::TaskFiles020:case SourceLanguage::OwnedResources021:case SourceLanguage::TaskForeign022:case SourceLanguage::TaskWrites023:break;
  default:throw Error("E_LANGUAGE_VERSION","unknown source language selected for parsing");
  }
  sourceUTF8(source,path,"unit");
  auto p=Parser(std::move(source),std::move(path),0,"unit",editorNames,editorDetails,true,language==SourceLanguage::OwnedResources021||language==SourceLanguage::TaskForeign022||language==SourceLanguage::TaskWrites023).run();
  p.sourceLanguage=language;return p;
}
Program parse(std::string source,std::string path,bool editorNames,bool editorDetails){return parseVersioned(std::move(source),std::move(path),currentSourceLanguage,editorNames,editorDetails);}
Program parseLegacy018(std::string source,std::string path,bool names,bool details){sourceUTF8(source,path,"unit");return Parser(std::move(source),std::move(path),0,"unit",names,details,false).run();}
Program parseTaskPrototype(std::string source,std::string path,bool names,bool details){sourceUTF8(source,path,"unit");return Parser(std::move(source),std::move(path),0,"unit",names,details,true).run();}
std::vector<SourceToken> sourceTokens(const std::string &source,const std::string &file){
  sourceUTF8(source,file,"unit");Lexer lexer(source,file);std::vector<SourceToken> result;
  for(;;){auto token=lexer.next();if(token.kind==Token::End)break;
    if(result.size()>=1000000)throw Error("E_ANALYSIS_LIMIT","editor source exceeds one million tokens");
    result.push_back({std::move(token.text),std::move(token.span),token.kind==Token::Id});}
  return result;
}
void check(Program &p){
  try{Checker(p).run();if(isPublicTaskLanguage(p)&&std::any_of(p.functions.begin(),p.functions.end(),[](const auto &fn){return fn.effects.contains("task");}))(void)analyzeTaskLifetimes(p);}catch(Error &error){
    std::map<std::string,std::string> sources;
    for(const auto &[key,unit]:p.units)sources[key]=unit.source;
    if(sources.empty())sources[p.path]=p.source;
    attachFrontendDiagnostic(error,sources,p.units.empty()?p.path:p.entryUnit,p.units.empty()?"unit":"project","check",true);throw;
  }
}
Type checkExpression(Program &p,const std::string &function,E expression,const std::map<std::string,Type> &locals){return Checker(p).watch(function,expression,locals);}
Type parseType(std::string source){sourceUTF8(source,"<debug-type>","type");return Parser(std::move(source),"<debug-type>",0,"type",false,false,true).typeOnly();}
E parseExpression(std::string source,std::string path,unsigned maxTokens){sourceUTF8(source,path,"expression");return Parser(std::move(source),std::move(path),maxTokens,"expression",false,false,true).expressionOnly();}
S parseStatement(std::string source,std::string path,unsigned maxTokens){sourceUTF8(source,path,"statement");return Parser(std::move(source),std::move(path),maxTokens,"statement",false,false,true).statementOnly();}
P parsePattern(std::string source,std::string path,unsigned maxTokens){sourceUTF8(source,path,"pattern");return Parser(std::move(source),std::move(path),maxTokens,"pattern",false,false,true).patternOnly();}
llvm::json::Array canonicalKinds(const std::vector<std::string> &names,const std::vector<unsigned> &kinds){llvm::json::Array result;for(size_t i=0;i<names.size();++i)result.push_back(int64_t(i<kinds.size()?kinds[i]:0));return result;}
llvm::json::Value canonical(const Function &f) {
  llvm::json::Array params,effects;
  for(const auto &p:f.params)params.push_back(llvm::json::Object{{"name",p.name},{"type",typeName(p.type)}});
  for(const auto &e:f.effects)effects.push_back(e);
  llvm::json::Array generic,arguments;for(const auto &parameter:f.typeParameters)generic.push_back(parameter);for(const auto &argument:f.typeArguments)arguments.push_back(typeName(argument));
  llvm::json::Object result{{"format","nex.function/13"},{"name",f.name},{"owner",f.owner},{"public",f.exported},{"realm",f.realm},{"parameters",std::move(params)},{"result",typeName(f.result)},{"effects",std::move(effects)},{"test",f.test},{"type_parameters",std::move(generic)},{"type_bounds",canonicalBounds(f.typeParameters,f.typeBounds)},{"template",f.templateName},{"type_arguments",std::move(arguments)},{"body",blockJSON(f.body)}};
  result["type_parameter_kinds"]=canonicalKinds(f.typeParameters,f.typeArities);if(f.traitSignature)result["trait_owner"]=f.traitOwner;
  if(f.foreign)result["foreign"]=llvm::json::Object{{"library",f.foreign->library},{"export",f.foreign->symbol},{"manifest_sha256",f.foreign->manifest}};
  if(f.closure){llvm::json::Array captures;for(const auto &capture:f.captures)captures.push_back(llvm::json::Object{{"name",capture.name},{"type",typeName(capture.type)}});result["closure_owner"]=f.closureOwner;result["captures"]=std::move(captures);}return result;
}
llvm::json::Value canonical(const Structure &s) {
  llvm::json::Array generic,arguments;for(const auto &parameter:s.typeParameters)generic.push_back(parameter);for(const auto &argument:s.typeArguments)arguments.push_back(typeName(argument));
  llvm::json::Object result{{"format",s.opaqueResource?"nex.resource/1":s.enumeration?"nex.enum/4":"nex.structure/5"},{"name",s.name},{"owner",s.owner},{"public",s.exported},{"type_parameters",std::move(generic)},{"type_bounds",canonicalBounds(s.typeParameters,s.typeBounds)},{"template",s.templateName},{"type_arguments",std::move(arguments)}};
  result["type_parameter_kinds"]=canonicalKinds(s.typeParameters,s.typeArities);
  if(s.enumeration){llvm::json::Array variants;for(const auto &variant:s.variants){llvm::json::Array fields;for(const auto &field:variant.fields)fields.push_back(llvm::json::Object{{"name",field.name},{"type",typeName(field.type)}});variants.push_back(llvm::json::Object{{"name",variant.name},{"fields",std::move(fields)}});}result["variants"]=std::move(variants);}
  else{llvm::json::Array fields;for(const auto &f:s.fields)fields.push_back(llvm::json::Object{{"name",f.name},{"type",typeName(f.type)}});result["fields"]=std::move(fields);}return result;
}
llvm::json::Value canonical(const Endpoint &endpoint){
  return llvm::json::Object{{"format","nex.endpoint/1"},{"name",endpoint.name},{"method",endpoint.method},{"path",endpoint.path},{"success_status",endpoint.successStatus},{"handler",endpoint.target}};
}
llvm::json::Value canonical(const Trait &value){
  llvm::json::Object items,methods;for(const auto &[name,bounds]:value.associated){llvm::json::Array values;for(const auto &bound:bounds)values.push_back(bound);items[name]=std::move(values);}for(const auto &method:value.methods)methods[method.name]=canonical(method);
  return llvm::json::Object{{"format","nex.trait/1"},{"name",value.name},{"owner",value.owner},{"public",value.exported},{"self_kind",int64_t(value.selfArity)},{"associated_types",std::move(items)},{"methods",std::move(methods)}};
}
llvm::json::Value canonical(const Implementation &value){
  llvm::json::Object aliases,methods;for(const auto &[name,type]:value.associated)aliases[name]=typeName(type);for(const auto &[name,method]:value.methods){llvm::json::Array types;for(const auto &type:method.typeArguments)types.push_back(typeName(type));methods[name]=llvm::json::Object{{"target",method.target},{"type_arguments",std::move(types)}};}
  llvm::json::Array parameters;for(const auto &name:value.typeParameters)parameters.push_back(name);
  return llvm::json::Object{{"format","nex.implementation/1"},{"name",value.name},{"owner",value.owner},{"public",value.exported},{"trait",value.trait},{"self",typeName(value.self)},{"type_parameters",std::move(parameters)},{"type_parameter_kinds",canonicalKinds(value.typeParameters,value.typeArities)},{"type_bounds",canonicalBounds(value.typeParameters,value.typeBounds)},{"associated_types",std::move(aliases)},{"methods",std::move(methods)}};
}
std::string revision(const Program &p) {
  rejectUnarchivedTasks(p,"revision storage");
  std::map<std::string,std::string> ordered;
  for(const auto &f:p.functions)if(f.templateName.empty()&&!f.closure&&!f.traitSignature)ordered[f.name]=json(canonical(f),false);
  llvm::json::Object functions;for(const auto &[name,text]:ordered)functions[name]=text;
  llvm::json::Object structures;for(const auto &s:p.structures)if(s.templateName.empty())structures[s.name]=canonical(s);
  llvm::json::Object modules;
  for(const auto &[key,unit]:p.units){std::set<std::string> targets;for(const auto &import:unit.imports)targets.insert(p.units.at(import.target).module);llvm::json::Array deps;for(const auto &target:targets)deps.push_back(target);modules[unit.module]=std::move(deps);}
  llvm::json::Object endpoints;for(const auto &endpoint:p.endpoints)endpoints[endpoint.name]=canonical(endpoint);
  llvm::json::Object traits,implementations;for(const auto &value:p.traits)traits[value.name]=canonical(value);for(const auto &value:p.implementations)implementations[value.name]=canonical(value);
  return hash(json(llvm::json::Object{{"format","nex.program/14"},{"language",programLanguage(p)},{"module",p.module},{"functions",std::move(functions)},{"structures",std::move(structures)},{"modules",std::move(modules)},{"endpoints",std::move(endpoints)},{"traits",std::move(traits)},{"implementations",std::move(implementations)}},false));
}
llvm::json::Value describe() {
  return llvm::json::Object{
    {"schema","nex.language/1"},{"version",languageVersion},
    {"task_foreign_prototype",llvm::json::Object{{"status","public022_source_ffi_owned_transfers"},{"source_support",true},{"public_enabled",true},{"private_source_language",languageVersion},{"public_source_language",languageVersion},{"guide","docs/task-foreign-prototype.md"},{"native",true},{"independent_reference",true},{"copied_typed_data",true},{"external_resource_transport",true},{"public022_migration_complete",true},{"installed_SDK_accepted",false},{"module_value_quotas_separate",true},{"private_task_local_resources",true},{"owned_completion_channel",true},{"generic_completion_contains_owners",false},{"private_cross_task_resource_transport",true},{"atomic_owner_transfer",true},{"resource_authority_on_demand",true},{"maximum_task_snapshot_owners",int64_t(4096)},{"maximum_ffi_snapshot_owners",int64_t(64)},{"explicit_history_migration",true},{"guide_kind","task-foreign-source"},{"fixed_provider_FFI_exports",false}}},
    {"task_value_retirement",llvm::json::Object{{"status","private_native_scheduler"},{"source_syntax",false},{"source_resource_transport",true},{"stable_host_abi",false},{"guide","docs/task-value-retirement.md"},{"destruction","outside scheduler mutex"},{"cleanup_admission","intrusive queues and three retained root slots per admitted job; no allocation during retirement"},{"completion","task, logical scope and group publication wait their retired value roots"},{"channel_slot_reuse","after actual retired values and buffer storage destruction"},{"aliases","independently retained passive aliases and successful root results keep existing ownership"},{"retained_roots_per_job",int64_t(3)},{"suspending_api_cleanup","Suspending calls transfer their tagged roots to a Job-owned fence before unlock; source workers remain available"},{"api_cleanup","API guards retire only their own tagged roots; stack-owned fences survive batches taken by other workers"},{"scope_closure","deduplicated preallocated completion queue;256 nested scopes without recursive native closure"},{"source_task_FFI_bridge",true},{"actual_GPU_NPU_resources",false}}},
    {"resource_regions",llvm::json::Object{{"status","private_trusted_host_native_and_reference_schedulers"},{"dependency_graph",llvm::json::Object{{"status","development_typed_C_and_Cpp_host_API"},{"introduced_toolchain","0.131.0"},{"source_parent_creation",false},{"source_FFI_parent_construction",true},{"C_table_parent_creation",true},{"C_table_prefix","NEX_FFI_V1_RESOURCE_PARENTS_SIZE"},{"physical_parent_leases",true},{"original_parent_grants_rechecked",true},{"atomic_logical_dependency_promotion",true},{"metadata_retains_no_payload",true},{"maximum_direct_parents",int64_t(16)},{"maximum_objects_including_child",int64_t(4096)},{"maximum_dependency_depth",int64_t(256)},{"guide","docs/resource-regions.md"}}},{"source_support",false},{"source_task_bridge",true},{"frame_value_transport",true},{"native_scheduler",true},{"reference_scheduler",true},{"actual_GPU_NPU_resources",false},{"stable_host_abi",false},{"guide","docs/resource-regions.md"},{"header","runtime/nex_resource_region.h"},{"native_group_enable","TaskGroup::enableResourceRegions(optional genuine request parent) before spawning"},{"native_current_authority","task root or owned inner scope on workers; group root on coordinator"},{"physical_access","explicit coordinator-captured grant/request; no per-resume TLS lookup"},{"ancestry","same scheduler ancestry or genuine request ancestor; sibling groups and foreign requests rejected"},{"promotion","explicit trusted ancestor transfer, reserving destination ownership before cross-graph return; aliases retain physical identity"},{"close","logical revocation under scheduler lock where applicable; destructor request outside locks; native and independent reference task/scope publication after complete physical fence"},{"root_retirement","group finish closes remaining group-owned resources; explicitly returned request owners survive until request retirement"},{"maximum",llvm::json::Object{{"scope_nodes_including_root",int64_t(1025)},{"scope_depth",int64_t(256)},{"owners",int64_t(4096)},{"physical_joined_domains",int64_t(8)},{"task_nodes",int64_t(65536)},{"task_depth",int64_t(256)},{"request_group_links",int64_t(1024)},{"reference_task_nodes",int64_t(4096)}}},{"pending",llvm::json::Array{"actual device bindings and matching compiler/SDK/platform delivery"}},{"reference_enable","TaskReferenceExternalHost::resourceRegions and optional genuine resourceRequestParent before evaluation"},{"reference_current_authority","task root or owned inner scope via coordinator-only prepareInRegion/admitInRegion"},{"reference_cleanup","task/scope publication after complete physical settlement; root and unexpected unwind drain operations, frames and resources"},{"native_task_regions",true},{"native_request_parent",true},{"reference_task_regions",true},{"reference_request_parent",true},{"source_language",languageVersion}}},
    {"resource_executor",llvm::json::Object{{"status","private_trusted_host"},{"source_support",false},{"source_task_bridge",true},{"C_resource_executor_binding",false},{"actual_GPU_NPU_resources",false},{"stable_host_abi",false},{"guide","docs/resource-executor.md"},{"header","runtime/nex_resource_executor.h"},{"construction_and_cleanup","one owning thread"},{"cleanup_admission","pre-reserved bounded slot before factory; finalizer cannot be rejected after close"},{"quota_release","after destructor and code-pin release; admitted borrows retain complete physical owner"},{"operation_completion","run returns only after actual fence/IPC settlement; operation destructor precedes completion publication"},{"cancellation","queued work does not start; running work retains leases and reservations until physical settlement"},{"close","reject new admission; retain all previously reserved finalizers"},{"drain","current queue/running work only; idle owners remain live"},{"finish","close admission, wait all reserved resources/operations, join worker"},{"declared_capacity_only",true},{"maximum",llvm::json::Object{{"resources",int64_t(4096)},{"operations",int64_t(64)},{"reserved_bytes",int64_t(8388608)}}},{"pending",llvm::json::Array{"actual model/device session and buffer bindings","vendor-specific fences and failure settlement","matching full compiler, installed SDK and platform delivery"}}}},
    {"source_resources",llvm::json::Object{{"source_support",true},{"public_enabled",true},{"language",languageVersion},{"syntax","[pub] server resource Name<T...>;"},{"operations",llvm::json::Array{"resource_close(Resource) -> bool","resource_is_open(Resource) -> bool"}},{"server_only",true},{"effect","ffi"},{"opaque_declarations",true},{"generic_resources",true},{"source_constructor",false},{"reference",true},{"native",true},{"typescript",false},{"wire",false},{"source_task_bridge",true},{"async_completion",true},{"migration","explicit origin recheck; retained old rows/schema/IDs; reviewed graph repairs for builtin conflicts"},{"guide","docs/source-resources.md"},{"acceptance_pending",llvm::json::Array{"matching full compiler regression","installed SDK and supported native platforms"}},{"debugger",llvm::json::Object{{"LLDB_opaque_alias_view",true},{"DAP_opaque_alias_view",true},{"archived_source",true},{"ordinary_pure_watches",true},{"resource_watch_proxy_authority",false},{"runtime_arguments","DAP launch.args; raw LLDB CLI run-args exactly once"}}}}},
    {"scoped_discovery",llvm::json::Object{{"schema","nex.discovery/1"},{"schema_file","llm/discovery.schema.json"},
      {"index_command","nex describe --kind index --json"},{"field_command","nex describe --field PATH --json"},
      {"full_command","nex describe --json"},{"guide","docs/discovery.md"},{"bootstrap_prompt","llm/BOOTSTRAP.md"},
      {"field_bytes",256},{"path_components",8},{"graph_store_opened",false},{"source_read",false}}},
    {"model",llvm::json::Object{{"status","development_checked_model_library"},{"source_support",true},{"contract_version",int64_t(1)},{"language",languageVersion},{"language_migration_required",false},{"guide","docs/models.md"},{"import","std/model.nex"},{"tensor_dtypes",llvm::json::Array{"f32","u8","i8","i32"}},{"immutable_row_major_bytes",true},{"f32_encoding","finite IEEE754 binary32 little-endian bytes"},{"implicit_f64_narrowing",false},{"maximum_rank",int64_t(4)},{"maximum_elements_per_port",int64_t(262144)},{"maximum_ports_per_direction",int64_t(16)},{"maximum_combined_io_bytes",int64_t(786432)},{"precision_policies",llvm::json::Array{"match-cpu","vendor"}},{"exact_integer_f32_helper_range",llvm::json::Array{int64_t(-16777216),int64_t(16777216)}},{"tensor_native",true},{"tensor_reference",true},{"tensor_typescript",true},{"provider_context",true},{"provider_realm","server"},{"provider_effects",llvm::json::Array{"ffi"}},{"context_wire",false},{"context_host_grant",false},{"explicit_cpu_fallback",true},{"builtin_cpu_inference",false},{"builtin_gpu_inference",false},{"builtin_npu_inference",false},{"owned_model_handles",false},{"source_task_bridge",false},{"provider_preparation",llvm::json::Object{{"tool","tools/models/prepare.py"},{"status","experimental_pinned_ONNX_child"},{"native_targets",llvm::json::Array{"linux-arm64"}},{"runtime_C_API",int64_t(20)},{"maximum_model_bytes",int64_t(33554432)},{"device_initialized_during_preparation",false},{"candidate_NPU_provider","ZhouyiExecutionProvider"},{"runtime_digest_is_immutable_pin",false},{"driver_and_operator_dependencies_bundled",false}}},{"pending",llvm::json::Array{"matching full regression and installed SDK acceptance","matching compiler/provider platform delivery","other model formats and dynamic/scalar shapes","owned model/device resources and persistent/async worker lifetime"}}}},
    {"device",llvm::json::Object{{"status","development_owned_device_library"},{"guide","docs/device.md"},{"import","std/device.nex"},{"contract_version",int64_t(1)},{"source_support",true},{"language",languageVersion},{"language_migration_required",false},{"provider_realm","server"},{"provider_effects",llvm::json::Array{"task","ffi"}},{"opaque_session",true},{"opaque_buffer",true},{"immutable_tensor_metadata",true},{"hidden_physical_parent_retention",true},{"source_task_bridge",true},{"context_wire",false},{"explicit_cpu_fallback",true},{"builtin_gpu",false},{"builtin_npu",false},{"experimental_opencl_provider",true},{"provider_preparation","tools/owned-opencl/prepare.py"},{"provider_delivery","experimental_operator_preparation"},{"opencl_success_reply_validation","serialized_decode_and_physical_drain_on_fault"},{"opencl_unique_allocation_ids",true},{"fault_verification","tools/owned-opencl/faults.py"},{"log_verification","tools/owned-opencl/logs.py"},{"opencl_diagnostics",llvm::json::Object{{"transport","drained_pipe"},{"capture","bounded_first_and_last"},{"maximum_saved_bytes",int64_t(65536)},{"process_file_size_limit",false}}},{"opencl_operations",llvm::json::Array{"add_u8","affine_u8"}},{"maximum_rank",int64_t(4)},{"maximum_elements",int64_t(262144)},{"maximum_tensor_bytes",int64_t(1048576)},{"opencl_maximum_upload_bytes",int64_t(1044480)},{"pending",llvm::json::Array{"matching full regression, installed SDK and platform acceptance","owned NPU/model adapters","device-loss recovery/reset","float tensors, additional operations and general kernels","concurrent queues and explicit fence values"}}}},
    {"compute",llvm::json::Object{{"status","development_checked_library_contract"},{"guide","docs/compute.md"},{"import","std/compute.nex"},{"contract_version",int64_t(1)},{"source_support",true},{"language",languageVersion},{"language_migration_required",false},{"tensor_dtypes",llvm::json::Array{"u8","i8","i32"}},{"operations",llvm::json::Array{"add_u8","affine_u8","matmul_i8_i32"}},{"immutable_row_major_bytes",true},{"maximum_rank",int64_t(4)},{"maximum_elements",int64_t(262144)},{"maximum_bytes",int64_t(1048576)},{"cpu_maximum_multiply_accumulates",int64_t(1048576)},{"cpu_backend","checked NEX source"},{"cpu_reference",true},{"cpu_native",true},{"cpu_typescript",true},{"provider_context",true},{"provider_realm","server"},{"provider_effects",llvm::json::Array{"ffi"}},{"context_wire",false},{"explicit_cpu_fallback",true},{"builtin_gpu",false},{"builtin_npu",false},{"source_task_bridge",false},{"owned_device_buffers",false},{"pending",llvm::json::Array{"matching full regression and installed SDK acceptance","real common-API OpenCL/RKNN/Zhouyi providers and device tests","float tensors and additional operations","general kernels/models","owned resources and persistent/async worker lifetime"}}}},
    {"source_concurrency",llvm::json::Object{{"status","development_ordered_cpu_mapping"},{"guide","docs/concurrency-design.md"},{"language",languageVersion},{"operation","parallel_map"},{"source_operations",true},{"internal_runtime_prototype",true},{"emitted_runtime_enabled",true},{"runtime_inclusion","reachable program or linked provider requirement"},{"stable_host_abi",false},{"development_compile_definition","NEX_STRUCTURED_WORKERS"},{"callback_effects",llvm::json::Array{}},{"callback_realm","shared or current caller realm"},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"native_execution","bounded joined CPU threads"},{"reference_execution","sequential semantic oracle"},{"typescript_execution","sequential synchronous evaluation"},{"browser_workers",false},{"maximum_workers",int64_t(16)},{"maximum_items",int64_t(65536)},{"maximum_value_graph_nodes",int64_t(262144)},{"callback_call_depth",int64_t(256)},{"standalone_group_steps",int64_t(1000000)},{"standalone_group_timeout_ms",int64_t(5000)},{"hosted_budget","inherit existing request control"},{"capture_guard","reject hidden file graphs before callbacks start"},{"source_async_await",false},{"pending",llvm::json::Array{"full_current_regression","installed_sdk","platform_editor_debug_profile_validation","integration of parallel_map/source tasks with the separate typed browser-worker adapter","task IO beyond whole-file reads/writes and task host adapters","other_cpu_targets","gpu","npu"}}}},
    {"task_file_writes_prototype",llvm::json::Object{{"status","development_public_whole_file_writes"},{"guide","docs/task-file-writes-prototype.md"},{"language",languageVersion},{"public_language",languageVersion},{"source_support",true},{"private_source_support",true},{"private_history_migration_verified",true},{"migration_guide","docs/task-write-migration.md"},{"private_static_shared_providers",true},{"static_shared_providers",true},{"provider_mask",int64_t(799)},{"provider_schemas",llvm::json::Array{"nex.native-task-provider/5","nex.native-task-provider/6","nex.native-task-provider/7"}},{"private_provider_mask",int64_t(799)},{"private_provider_schemas",llvm::json::Array{"nex.native-task-provider/5","nex.native-task-provider/6","nex.native-task-provider/7"}},{"provider_guide","docs/task-write-providers.md"},{"provider_schema_file","llm/native-write-task-provider.schema.json"},{"write_requirement_metadata",true},{"public_enabled",true},{"native",true},{"reference",true},{"typescript_server_files",false},{"execution_ABI",int64_t(4)},{"retained_provider_ABI",int64_t(3)},{"retained_provider_mask",int64_t(31)},{"descriptor_bytes",int64_t(88)},{"operations",llvm::json::Array{"file_write_text(str,str) -> result<bool>","file_write_bytes(str,bytes) -> result<bool>"}},{"function_effects",llvm::json::Array{"task","fs"}},{"realm","server"},{"explicit_write_grant",true},{"snapshot_inputs",true},{"physical_drain",true},{"postcommit_rollback",false},{"public_migration_complete",false},{"pending",llvm::json::Array{"matching genuine022 public migration and retained capture/replay/package acceptance","matching CLI/editor/debug/profile/SDK/platform delivery","streams, networking, DB and task HTTP handlers"}}}},
    {"task_file_writes",llvm::json::Object{{"status","development_public_whole_file_writes"},{"guide","docs/task-file-writes-prototype.md"},{"language",languageVersion},{"public_language",languageVersion},{"source_support",true},{"private_source_support",true},{"private_history_migration_verified",true},{"migration_guide","docs/task-write-migration.md"},{"private_static_shared_providers",true},{"static_shared_providers",true},{"provider_mask",int64_t(799)},{"provider_schemas",llvm::json::Array{"nex.native-task-provider/5","nex.native-task-provider/6","nex.native-task-provider/7"}},{"private_provider_mask",int64_t(799)},{"private_provider_schemas",llvm::json::Array{"nex.native-task-provider/5","nex.native-task-provider/6","nex.native-task-provider/7"}},{"provider_guide","docs/task-write-providers.md"},{"provider_schema_file","llm/native-write-task-provider.schema.json"},{"write_requirement_metadata",true},{"public_enabled",true},{"native",true},{"reference",true},{"typescript_server_files",false},{"execution_ABI",int64_t(4)},{"retained_provider_ABI",int64_t(3)},{"retained_provider_mask",int64_t(31)},{"descriptor_bytes",int64_t(88)},{"operations",llvm::json::Array{"file_write_text(str,str) -> result<bool>","file_write_bytes(str,bytes) -> result<bool>"}},{"function_effects",llvm::json::Array{"task","fs"}},{"realm","server"},{"explicit_write_grant",true},{"snapshot_inputs",true},{"physical_drain",true},{"postcommit_rollback",false},{"public_migration_complete",false},{"pending",llvm::json::Array{"matching genuine022 public migration and retained capture/replay/package acceptance","matching CLI/editor/debug/profile/SDK/platform delivery","streams, networking, DB and task HTTP handlers"}}}},
    {"task_file_writes_host",llvm::json::Object{{"status","private_trusted_host_whole_file_writes"},{"guide","docs/task-file-writes-host.md"},{"header","runtime/nex_task_file_write.h"},{"source_support",true},{"reference_source_support",true},{"language",languageVersion},{"stable_host_abi",false},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"authority","explicit coordinator-captured revocable FileWriteGrant; read-only capability cannot be upgraded"},{"input_snapshot","exact visible bytes; no source Values or mutable backing storage on worker"},{"maximum_file_bytes",int64_t(1048576)},{"maximum_path_bytes",int64_t(4096)},{"reservation","owned input bytes plus retained path bytes"},{"atomic_replacement",true},{"commit","temporary write, fsync, final control/authority check, rename"},{"crash_durable_directory",false},{"postcommit_cancellation","result may be suppressed after complete publication; no rollback"},{"physical_drain",true},{"pending",llvm::json::Array{"matching full regression, installed SDK and platform acceptance","streams, networking, DB and task HTTP handlers"}}}},
    {"task_file_reads",llvm::json::Object{{"status","development_public_whole_file_reads"},{"guide","docs/task-file-reads.md"},{"language",languageVersion},{"source_support",true},{"operations",llvm::json::Array{"file_read_text(str) -> result<str>","file_read_bytes(str) -> result<bytes>"}},{"function_effects",llvm::json::Array{"task","fs"}},{"realm","server"},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"reference",true},{"typescript",false},{"windows",false},{"wasm",false},{"http_task_handlers",false},{"binary_providers",true},{"writes",true},{"streams",false},{"task_debug_profile",false},{"authority","root coordinator captures explicit revocable FileReadGrant; task/fs does not choose an OS root"},{"fs_only_helpers_in_task","E_EFFECT; explicitly declare task and fs"},{"ordinary_errors","typed result at attempted read, including absent capability and invalid UTF-8"},{"fatal_errors","traps, cancellation, revoked authority and execution limits abort/drain; first fatal retained"},{"physical_drain",true},{"source_admission","owning scheduler after physical settlement and authority/control checks"},{"io_workers",int64_t(2)},{"maximum_pending",int64_t(64)},{"reserved_transport_bytes",int64_t(8388608)},{"maximum_file_bytes",int64_t(1048576)},{"maximum_path_bytes",int64_t(4096)},{"maximum_whole_file_reservations",int64_t(7)},{"total_process_ram_bound",false},{"migration","explicit019-to020 checked recheck; original rows/IDs/schema retained"},{"acceptance_pending",llvm::json::Array{"matching delivery regression and installed SDK acceptance","supported native platform acceptance"}},{"task_profile",true},{"task_debug",true},{"provider_linkage",llvm::json::Array{"static","shared-fixed"}},{"provider_source_required",true}}},
    {"task_providers",llvm::json::Object{{"status","development_static_native_tasks"},{"public_enabled",true},{"provider_file_writes",true},{"language",languageVersion},{"guide","docs/task-providers.md"},{"record_schema","nex.native-task-provider/5"},{"record_schema_file","llm/native-write-task-provider.schema.json"},{"plan_schema","nex.project-static-task-linkage/2"},{"plan_schema_file","llm/project-write-task-linkage.schema.json"},{"execution_task_abi",int64_t(4)},{"descriptor_bytes",int64_t(88)},{"abi_offset",int64_t(40)},{"source_required",true},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"static_linkage",true},{"supported_actions",llvm::json::Array{"build","run","test","build-test","package"}},{"checked_task_io",true},{"provider_file_reads",true},{"reviewed_capture_replay",true},{"runtime_ownership","one root application executor, request control and file grant; code-only provider archives"},{"authority_transport",false},{"callable_transport",false},{"imported_function_values",false},{"dynamic_linkage",false},{"profiling",false},{"logical_debugging",false},{"http_task_handlers",false},{"foreign",false},{"binary_only",false},{"unload",false},{"acceptance_pending",llvm::json::Array{"matching delivery regression and installed SDK acceptance","supported native platform acceptance"}}}},
    {"task_shared_providers",llvm::json::Object{{"status","development_checked_fixed_native_task_images"},{"public_enabled",true},{"provider_file_writes",true},{"language",languageVersion},{"guide","docs/task-shared-providers.md"},{"record_schema","nex.native-task-provider/5"},{"record_schema_file","llm/native-write-task-provider.schema.json"},{"plan_schema","nex.project-task-linkage/5"},{"plan_schema_file","llm/project-write-task-linkage.schema.json"},{"completion_schema","nex.native-completion/5"},{"retained_build_schema","nex.retained-native-task-build/2"},{"execution_task_abi",int64_t(4)},{"descriptor_bytes",int64_t(88)},{"abi_offset",int64_t(40)},{"source_required",true},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"linkage","fixed OS startup load closure"},{"mixed_static_shared",true},{"ownership","checked definitions owned once per application load closure; independent roots have independent ledgers"},{"runtime_ownership","one common runtime and one root executor, request control, file grant and limits"},{"application_entry","declared task entry in final executable; no application code DSO"},{"checked_task_io",true},{"provider_file_reads",true},{"reviewed_capture_replay",true},{"supported_actions",llvm::json::Array{"build","run","test","build-test","package"}},{"authority_transport",false},{"callable_transport",false},{"imported_function_values",false},{"profiling",false},{"logical_debugging",false},{"http_task_handlers",false},{"foreign",false},{"binary_only",false},{"runtime_load_unload",false},{"acceptance_pending",llvm::json::Array{"matching delivery regression and installed SDK acceptance","supported native platform acceptance"}}}},
    {"task_provider_debugging",llvm::json::Object{{"status","development_checked_native_task_provider_debugging"},{"public_enabled",true},{"provider_file_writes",true},{"source_support",true},{"language",languageVersion},{"guide","docs/task-provider-debugging.md"},{"source_required",true},{"configuration","debug"},{"execution_task_abi",int64_t(4)},{"descriptor_bytes",int64_t(88)},{"registry_abi",int64_t(1)},{"registry_bytes",int64_t(32)},{"catalog_abi",int64_t(2)},{"catalog_bytes",int64_t(200)},{"maximum_total_registries_including_root",int64_t(128)},{"record_schema_file","llm/native-write-task-provider.schema.json"},{"plan_schema","nex.project-task-linkage/7"},{"plan_schema_file","llm/project-write-task-linkage.schema.json"},{"record_schema","nex.native-task-provider/7"},{"catalog_schema","nex.task-debug-catalog/1"},{"source_union_schema","nex.task-debug-source-union/1"},{"completion_schema","nex.native-completion/7"},{"manifest_schema","nex.debug/3"},{"view_schema","nex.task-debug-view/2"},{"frame_schema","nex.debug-frame/4"},{"supported_actions",llvm::json::Array{"plan","build","debug","package"}},{"ordinary_pure_helper_logical_frames",false},{"combined_debug_profile",false},{"runtime_load_unload",false},{"authority_transport",false},{"callable_transport",false},{"foreign",false},{"binary_only",false},{"http_task_handlers",false},{"reference",false},{"typescript",false},{"windows",false},{"wasm",false},{"language_migration_required",false},{"acceptance_pending",llvm::json::Array{"matching delivery regression and installed SDK acceptance","supported native platform acceptance"}},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"linkage_modes",llvm::json::Array{"static","shared-fixed"}}}},
    {"task_provider_profiling",llvm::json::Object{{"status","development_checked_native_task_provider_profiles"},{"public_enabled",true},{"provider_file_writes",true},{"source_support",true},{"language",languageVersion},{"guide","docs/task-provider-profiling.md"},{"configuration","profile"},{"source_required",true},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"static_linkage",true},{"fixed_shared_linkage",true},{"execution_task_abi",int64_t(4)},{"descriptor_bytes",int64_t(88)},{"registry_abi",int64_t(1)},{"registry_bytes",int64_t(32)},{"record_schema_file","llm/native-write-task-provider.schema.json"},{"record_schema","nex.native-task-provider/6"},{"catalog_schema","nex.task-profile-catalog/1"},{"completion_schema","nex.native-completion/6"},{"plan_schema_file","llm/project-write-task-linkage.schema.json"},{"plan_schema","nex.project-task-linkage/6"},{"retained_build_schema","nex.retained-native-task-build/3"},{"runtime_schema","nex.profile-runtime/3"},{"report_schema","nex.profile/3"},{"session_schema","nex.profile-session/3"},{"build_schema","nex.profile-build/2"},{"supported_actions",llvm::json::Array{"build","run","profile","package"}},{"collector_ownership","one collector and one checked registry batch per running application physical load closure"},{"source_attribution","checked component source catalogs, including unused concrete provider definitions"},{"source_calls","one logical activation across suspension and image boundaries"},{"root_limits_and_grants","preserved root execution policy; catalogs do not grant authority"},{"reviewed_capture_replay",true},{"logical_debugging",false},{"combined_debug_profile",false},{"runtime_load_unload",false},{"authority_transport",false},{"callable_transport",false},{"foreign",false},{"binary_only",false},{"http_task_handlers",false},{"tracy",false},{"reference",false},{"typescript",false},{"windows",false},{"wasm",false},{"acceptance_pending",llvm::json::Array{"matching delivery regression and installed SDK acceptance","supported native platform acceptance"}},{"profile_configuration_test_builds",true},{"measured_test_sessions",false}}},
    {"task_profiling",llvm::json::Object{{"status","development_native_source_tasks"},{"source_support",true},{"guide","docs/profiling.md"},{"cli_language",languageVersion},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"execution_task_abi",int64_t(4)},{"runtime_schema","nex.profile-runtime/2"},{"report_schema","nex.profile/2"},{"session_schema","nex.profile-session/2"},{"source_only_project",true},{"reviewed_capture_replay",true},{"task_file_reads",true},{"source_calls","one logical activation; not one scheduler resume"},{"clocks",llvm::json::Array{"thread CPU in active source segments","active monotonic elapsed","logical lifetime wall"}},{"scheduler_metrics",llvm::json::Array{"ready","future","send","receive","scope","external","drain","executor CPU/elapsed"}},{"completeness",llvm::json::Array{"aggregates","timeline","memory","cpu","elapsed","lifetime"}},{"event_only_truncation_preserves_aggregates",true},{"memory_scope","managed shallow handles and Data objects; not total heap/RAM"},{"limits",llvm::json::Object{{"events",int64_t(1000000)},{"sites",int64_t(16384)},{"tasks",int64_t(4096)},{"active_invocations",int64_t(65536)},{"guards_per_thread",int64_t(4096)},{"live_allocations",int64_t(1000000)},{"report_bytes",int64_t(67108864)}}},{"tracy",false},{"async_debugger",false},{"reference",false},{"typescript",false},{"http_task_handlers",false},{"binary_providers",false},{"windows",false},{"wasm",false},{"acceptance_pending",llvm::json::Array{"matching delivery regression and installed SDK acceptance","supported native platform acceptance"}}}},
    {"task_debugging",llvm::json::Object{{"status","development_native_source_tasks"},{"source_support",true},{"guide","docs/task-debugging.md"},{"language",languageVersion},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"execution_task_abi",int64_t(4)},{"catalog_abi",int64_t(1)},{"manifest_schema","nex.debug/2"},{"view_schema","nex.task-debug-view/1"},{"frame_schema","nex.debug-frame/3"},{"process_model","LLDB all-stop; read-only borrowed safe-point/accepted-park inspection"},{"public_launch",true},{"nex_dap",true},{"raw_dap",false},{"source_only_project",true},{"logical_step",true},{"inferior_function_evaluation",false},{"source_value_retention",false},{"deadline_advances_while_stopped",true},{"limits",llvm::json::Object{{"tasks",int64_t(4096)},{"live_frames",int64_t(65536)},{"stack_depth",int64_t(256)},{"locals",int64_t(256)},{"codes",int64_t(16384)},{"points",int64_t(262144)},{"bindings",int64_t(65536)},{"visible_indices",int64_t(1048576)},{"metadata_text_bytes",int64_t(16777216)},{"metadata_bytes",int64_t(67108864)},{"host_manifest_bytes",int64_t(8388608)}}},{"pending",llvm::json::Array{"matching delivery regression and installed SDK acceptance","supported native platform acceptance","native helper logical-stack merge","target name before first activation","HTTP task handlers","browser/TypeScript/reference and other platforms","combined task debug/profile"}},{"schema_files",llvm::json::Object{{"view","llm/task-debug-view.schema.json"},{"frame","llm/task-debug-frame.schema.json"},{"expression","llm/task-debug-expression.schema.json"}}},{"source_cli","nex debug FILE --kind nex-dap --json"},{"project_cli","nex project --kind debug --component NAME --adapter nex-dap --json"},{"combined_debug_profile",false},{"queued_target_name",false},{"lldb_commands",llvm::json::Array{"nex-tasks","nex-task-select TASK_ID","nex-task-stack [TASK_ID]","nex-task-values [TASK_ID [FRAME_INDEX]]","nex-task-break function QUALIFIED_NAME","nex-task-break line FILE LINE","nex-task-next [TASK_ID]","nex-task-in [TASK_ID]","nex-task-out [TASK_ID]"}},{"dap_requests",llvm::json::Array{"threads","stackTrace","scopes","variables","evaluate","next","stepIn","stepOut","continue"}},{"provider_debugging_contract","task_provider_debugging; separate catalog ABI2/debug3, not source-only ABI1"}}},
    {"task_profile_collector",llvm::json::Object{{"status","development_integrated_native_tasks"},{"guide","docs/profiling.md"},{"header","runtime/nex_task_profile.h"},{"probe","nex_task_profile_collector_probe"},{"source_support",true},{"runtime_integration",true},{"public_profile_enabled",true},{"execution_task_abi_changed",true},{"measurement_scope","native compiled source tasks; public CLI language020; see task_profiling scope"}}},
    {"task_external_completion",llvm::json::Object{{"status","experimental_private_trusted_host_kernel"},{"guide","docs/task-external.md"},{"source_support",false},{"public_source_async_io",true},{"source_syntax_changed",false},{"canonical_formats_changed",false},{"stable_host_abi",false},{"transport","owned bounded host bytes/results; no source Value, Handle or frame transported to I/O workers"},{"tickets","driver and logical owner; slot generation; single acceptance"},{"cancellation","request cancellation; retain physical lease and quota until operation settlement; drain before owner completion"},{"admission","owning scheduler only; validate concrete host schema and authority before source publication"},{"memory_bound","declared retained transport payload; not total host/process memory"},{"maximum",llvm::json::Object{{"pending",int64_t(64)},{"reserved_bytes",int64_t(8388608)},{"result_payload_bytes",int64_t(1048576)},{"io_workers_native_reference",int64_t(2)}}},{"native",llvm::json::Object{{"header","runtime/nex_task_external.h"},{"group_header","runtime/nex_tasks.h"},{"entry_points",llvm::json::Array{"TaskExternalPool","TaskGroup::submitExternal","TaskGroup::awaitExternal"}},{"io_execution","separate bounded joined host worker pool"}}},{"reference",llvm::json::Object{{"header","include/nex/task_reference_external.h"},{"entry_point","evaluateTaskReference"},{"host","TaskReferenceExternalHost"},{"coordinator","independent serial checked AST scheduler"},{"hook","private checked task_yield interception; source response remains unit"},{"source_io_lowering",true}}},{"typescript",llvm::json::Object{{"runtime","web/nex-task-runtime.ts"},{"host_api",llvm::json::Array{"hostPending","hostAwait"}},{"executor_workers",int64_t(1)},{"settlement","trusted HostOperation.settled Promise means physical quiescence"},{"admission","trusted schema decoder; checked capability-free copied immutable NEX graph"}}},{"file_read_lease",llvm::json::Object{{"header","runtime/nex_files.h"},{"capture","captureFileReadLease"},{"adapter_header","runtime/nex_task_file_read.h"},{"adapter","PreparedTaskFileRead"},{"grant","coordinator-captured revocation-aware lexical/request lease; no worker TLS discovery"},{"source_lowering",true},{"windows",false},{"grant_type","FileReadGrant"},{"capture_grant","captureFileReadGrant"},{"grant_per_path_ambient_lookup",false},{"unavailable_grant_deferred",true},{"retained_path_storage","exact owned bytes up to4096"}}},{"pending",llvm::json::Array{"streaming file IO","source db/network task lowering","browser filesystem and task network/UI/worker adapters","combined task debug/profile, Tracy and binary-provider ABI","full current regression, installed SDK and platform acceptance"}},{"public_source_guide","docs/task-file-reads.md"},{"public_source_subset",llvm::json::Array{"file_read_text","file_read_bytes","file_write_text","file_write_bytes"}}}},
    {"task_execution_limits",llvm::json::Object{{"status","development_explicit_task_limits"},{"source_syntax_changed",false},{"guide","docs/task-limits.md"},{"native_header","runtime/nex_task_limits.h"},{"defaults",llvm::json::Object{{"steps",int64_t(1000000)},{"timeout_ms",int64_t(5000)},{"workers",int64_t(16)}}},{"maximum",llvm::json::Object{{"steps",int64_t(9007199254740991)},{"timeout_ms",int64_t(3600000)},{"workers",int64_t(16)}}},{"cli_options",llvm::json::Array{"--task-steps","--task-timeout-ms","--task-workers"}},{"launcher_options",llvm::json::Array{"--nex-task-steps","--nex-task-timeout-ms","--nex-task-workers"}},{"launcher_can_only_lower",true},{"ambient_environment",false},{"project_field","configurations.NAME.task_limits"},{"acceptance_field","checks[].task_limits (nonproject build/run/test/profile)"},{"reference_executor_workers",int64_t(1)},{"typescript_executor_workers",int64_t(1)},{"identical_step_thresholds",false},{"deadline","one cooperative monotonic root deadline; children cannot renew it"},{"process_supervision","separate outer timeout; forced termination does not prove joined cleanup"}}},
    {"structured_tasks_runtime",llvm::json::Object{{"status","development_source_task_file_reads020"},{"source_support",true},{"guide","docs/tasks-runtime-design.md"},{"header","runtime/nex_tasks.h"},{"probe","nex_task_scheduler_probe"},{"development_definitions",llvm::json::Array{"NEX_STRUCTURED_WORKERS","NEX_ASYNC_TASKS"}},{"ordinary_applications_enabled",true},{"scheduler","bounded ready ring; parked coroutine waits do not block OS workers"},{"maximum_workers",int64_t(16)},{"default_task_slots",int64_t(4096)},{"maximum_task_slots",int64_t(65536)},{"maximum_channels",int64_t(1024)},{"maximum_total_channel_slots",int64_t(65536)},{"channel_rendezvous",true},{"nested_task_depth",int64_t(256)},{"request_control","shared atomic budget/deadline/cancellation; coordinator-only host callback"},{"task_input_output","owned immutable Value snapshots; scoped task authority checked by owner ancestry; no raw Handle across suspension"},{"pending",llvm::json::Array{"complete static region/lifetime inference","streams/db/network","non-native task debugging/profiling","runtime provider load/unload","full current installed SDK and platform delivery","NEX UI adapter task integration","task limit SDK/platform acceptance"}},{"private_native_steps",llvm::json::Object{{"entry_point","emitTaskNativeStep"},{"probe","nex_task_native_emit_probe"},{"scheduler_request","task_yield"},{"frame_values","owned snapshots; resume-local Handle leases"},{"public_build_enabled",true},{"task_calls",true},{"task_scope_channels",true},{"debug_profile",false},{"task_closure_descriptors",true},{"combined_call_depth",int64_t(256)},{"logical_scope_worker_caps",true},{"authority_graph_validation",true},{"region_type_system_complete",false},{"scheduler_requests",llvm::json::Array{"task_yield","with_tasks","task_spawn","task_wait","channel_new","task_send","task_recv","task_close","task_cancel","current_task_scope","file_read_text","file_read_bytes","file_write_text","file_write_bytes","checked direct extern call"}},{"root_task_depth",int64_t(1)},{"profile",true},{"debug",true}}},{"private_ast_steps",llvm::json::Object{{"entry_point","TaskAstMachine"},{"probe","nex_task_ast_probe"},{"control","checked AST actions; no TaskIR lowering or execution"},{"owned_values",true},{"maximum_call_depth",int64_t(256)},{"transport","TaskTransition"},{"scheduler_integrated",true},{"public_build_enabled",false},{"host_effects","pure/io atoms, server task/fs reads/writes and task/ffi typed calls; db and file authority transport rejected"},{"maximum_pending_actions",int64_t(262144)}}},{"private_ast_scheduler",llvm::json::Object{{"entry_point","evaluateTaskReference"},{"probe","nex_task_reference_probe"},{"control","independent checked AST scheduler; no TaskIR or native TaskGroup dispatch"},{"scheduler_integrated",true},{"cooperative",true},{"physical_cpu_overlap",false},{"scope_future_channel_requests",int64_t(10)},{"owned_capability_family","reference; immutable family and weak scheduler identity"},{"scope_graph_validation",true},{"maximum_tasks",int64_t(4096)},{"maximum_scopes",int64_t(1024)},{"maximum_channels",int64_t(1024)},{"maximum_channel_slots",int64_t(65536)},{"maximum_pending_actions_per_task",int64_t(262144)},{"public_build_enabled",true},{"host_effects","pure/io atoms, server task/fs reads/writes and task/ffi typed calls; db and file authority transport rejected"},{"stalled_channels","E_TASK_DEADLOCK"},{"root_task_depth",int64_t(1)}}},{"private_typescript_tasks",llvm::json::Object{{"entry_point","emitTaskTypeScript"},{"probe","nex_task_typescript_emit_probe"},{"runtime","web/nex-task-runtime.ts"},{"execution","checked source generators and independent cooperative queue"},{"source_requests",int64_t(10)},{"internal_checkpoint_request","$poll"},{"checkpoint_interval",int64_t(64)},{"pure_helpers_resumable",true},{"maximum_call_depth",int64_t(256)},{"root_task_depth",int64_t(1)},{"maximum_task_nesting",int64_t(256)},{"maximum_tasks",int64_t(4096)},{"maximum_scopes",int64_t(1024)},{"maximum_channels",int64_t(1024)},{"maximum_channel_slots",int64_t(65536)},{"owned_values","immutable snapshots; private weak owner brands; canonical opaque identities"},{"scope_graph_validation",true},{"event_loop","MessageChannel turns; statement/loop compiler checkpoints"},{"result_propagation","current generated source function boundary"},{"source_map","nex.typescript-map/1 for public019..023; nex.private-typescript-task-map/1 for private018"},{"public_build_enabled",true},{"nex_ui_adapter_tasks",false},{"host_effects","shared/client pure and io atoms; server/file/foreign rejected"},{"debug_profile",false},{"physical_cpu_overlap",false}}},{"private_lifetime_analysis",llvm::json::Object{{"entry_point","analyzeTaskLifetimes"},{"probe","nex_task_lifetime_probe"},{"guide","docs/task-lifetimes.md"},{"report_schema","nex.private-task-lifetime/1"},{"known_owner_diagnostics",true},{"ancestor_borrowing",true},{"interprocedural_captures",true},{"aggregate_projections",true},{"fully_static",false},{"mandatory_runtime_guards",true},{"default_analysis_steps",int64_t(262144)},{"maximum_analysis_steps",int64_t(1048576)},{"maximum_active_functions",int64_t(128)},{"maximum_join_depth",int64_t(32)},{"abstract_loop_iterations",int64_t(2)},{"budget_exhaustion","deferred runtime obligation"},{"ordinary_check_invokes_pass",true},{"public_source_tasks",true}}},{"language",languageVersion},{"types",llvm::json::Array{"task_scope","task<T>","channel<T>"}},{"effect","task"},{"callback_effects",llvm::json::Array{"pure","task","server task/fs with caller task/fs","server task/ffi with optional fs and complete caller effects"}},{"native_platforms",llvm::json::Array{"macOS 64-bit","Linux 64-bit"}},{"native_application","compiled continuations in standalone or checked fixed-load images; one bounded joined TaskGroup"},{"source_only_project",true},{"migration_guide","docs/task-migration.md"},{"standalone_group_steps",int64_t(1000000)},{"standalone_group_timeout_ms",int64_t(5000)},{"runtime_inclusion","reachable task effect"}}},
    {"browser_workers",llvm::json::Object{{"status","development_browser_task_jobs"},{"structured_tasks",true},{"compute_effects","empty or exactly task"},{"task_execution","one independent cooperative scheduler per dedicated Worker"},{"task_limits",llvm::json::Object{{"steps",1000000},{"timeout_ms",5000},{"workers",16}}},{"task_authority_transport",false},{"task_io",false},{"main_thread_tasks",false},{"source_support",true},{"guide","docs/browser-workers.md"},{"library","std/worker.nex"},{"compute_entry","worker_compute"},{"commands_entry","worker_commands"},{"execution","dedicated module Worker per running job"},{"maximum_running",2},{"maximum_pending",32},{"maximum_batch",64},{"maximum_timeout_ms",60000},{"wire_bytes",1048576},{"input_output","checked wire values; no functions or files"},{"deadline","queue and worker startup included; host timer termination"},{"delivery","at most once per accepted job; no delivery after close"},{"source_async_await",false},{"parallel_map_workers",false},{"pending",llvm::json::Array{"production_browser_validation","full_current_regression","installed_sdk","platform_editor_validation","task IO beyond whole-file reads/writes and task host adapters"}}}},
    {"wasm_features",llvm::json::Object{{"source_support",true},{"status","experimental_scalar_compute_validation_pending"},
      {"command","nex build FILE --target wasm --entry NAME --profile debug|release --json"},{"guide","docs/wasm.md"},
      {"target","wasm32-unknown-unknown"},{"abi",1},{"types",llvm::json::Array{"i64","bool","unit"}},
      {"realms",llvm::json::Array{"shared","client"}},{"effects",llvm::json::Array{}},
      {"javascript_i64","BigInt"},{"host_imports",false},{"wrapper","(await createNexWasm(bytes)).call(argumentArray, {budget})"},
      {"limits",llvm::json::Object{{"functions",128},{"operations",8192},{"function_operations",512},{"parameters",32},{"call_depth",64},{"maximum_budget",10000000},{"memory_bytes",16777216},{"module_bytes",8388608}}},
      {"pending",llvm::json::Array{"full_current_regression","native_reference_typescript_wasm_matrix","actual_browsers","installed_and_portable_sdk","comparable_performance","general_wasm_applications","wasi","f64","heap_values"}}}},
    {"result_propagation",llvm::json::Object{{"operator","?"},{"guide","docs/error-propagation.md"},
      {"operand","result<T>"},{"enclosing_return","result<U>"},{"success","payload"},{"failure","return unchanged code/message from current function"},
      {"evaluations",1},{"nested_expressions",true},{"lambda_boundary","nearest function"},{"native_owned_function_cleanup",true},
      {"native_owner_depth",4096},{"watch_top_level",false},{"pure_watch_helpers",true},{"scalar_verification",false},
      {"checked_traps_caught",false},{"source_try_catch_throw",false},{"explicit_016_migration",true},
      {"integration_pending",llvm::json::Array{"complete_source_and_sdk_regression","platform_execution","installed_editor","migration_and_preservation_gates"}}}},
    {"types",llvm::json::Array{"i64","f64","bool","unit","str","bytes","file","list<T>","result<T>","nominal structures","nominal enums","user generic types","function values","task_scope","task<T>","channel<T>"}},
    {"effects",llvm::json::Array{"io","db","fs","ffi","task"}},
    {"file_features",llvm::json::Array{"strict_utf8_text","explicit_directory_capability","read_only_default","atomic_text_replacement","immutable_binary_files","atomic_binary_replacement","bounded_bytes_and_paths","host_owned_descriptors","cooperative_operation_polling","no_implicit_http_capability"}},
    {"file_limits",llvm::json::Object{{"text_bytes",1048576},{"binary_bytes",1048576},{"path_bytes",4096},{"path_components",128}}},
    {"file_platforms",llvm::json::Array{"macos","linux"}},
    {"file_environment",llvm::json::Object{{"root","NEX_FILES_ROOT"},{"write","NEX_FILES_WRITE=1"},{"http_inherits_environment",false}}},
    {"file_guide","docs/files.md"},
    {"resource_guide","docs/resources.md"},
    {"foreign_boundary",llvm::json::Object{
      {"source_support",true},{"status","experimental_source_ffi"},{"abi_version",1},
      {"header","runtime/nex_ffi.h"},{"host_header","runtime/nex_ffi_host.h"},{"guide","docs/ffi-design.md"},
      {"signature_schema","nex.foreign-signature/1"},{"signature_command","nex ffi FILE --symbol NAME --json"},
      {"owned_external_host",llvm::json::Object{{"source_support",true},{"status","development_typed_C_loader_resources"},{"guide","docs/external-resources-design.md"},{"header","runtime/nex_ffi_resources.h"},{"value_kind",15},{"C_resource_construction",true},{"C_parent_construction",true},{"result_reachable_construction_only",true},{"actual_module_callback_ownership",true},{"per_image_borrow_origin",true},{"call_thread_borrow_lifetime",true},{"lexical_and_request_revocation",true},{"physical_capacity_retained",true},{"source_resource_types",true},{"source_task_bridge",true},{"device_executor",false},{"actual_GPU_NPU_resources",false}}},
      {"invocation_context",llvm::json::Object{{"source_support",true},{"host_schema","nex.foreign-host/1"},{"binding_schema","nex.foreign-binding/1"},{"header","runtime/nex_foreign.h"},{"native_header","runtime/nex_foreign_abi.h"},{"features",llvm::json::Array{"explicit_regular_file_catalogue","relative_operator_paths","no_ambient_grants","lexical_thread_contexts","snapshotted_call_storage","bounded_binding_cache","request_rebinding","native_managed_value_bridge","sticky_native_source_traps","terminal_module_cleanup"}},{"limits",llvm::json::Object{{"configuration_bytes",1048576},{"binding_bytes",1048576},{"cached_bindings",4096},{"cached_binding_utf8_bytes",67108864},{"scope_depth",64},{"arguments",4096}}}}},
      {"module_loading",llvm::json::Object{{"source_support",true},{"executable_members",true},{"executable_members_field","executables"},{"schema","nex.foreign-bundle/1"},{"abi_version",1},{"header","runtime/nex_ffi_module.h"},{"host_header","runtime/nex_ffi_loader.h"},{"platforms",llvm::json::Array{"macos-arm64","macos-x86_64","linux-arm64","linux-x86_64"}},{"features",llvm::json::Array{"explicit_host_export_grants","manifest_and_signature_pins","preload_member_hashes","private_snapshot","typed_calls","resource_scope_revocation","physical_image_leases","cooperative_cancellation","content_addressed_image_cache"}},{"limits",llvm::json::Object{{"manifest_bytes",1048576},{"files",128},{"member_bytes",67108864},{"bundle_bytes",268435456},{"exports",1024},{"host_grants",128}}}}},
      {"features",llvm::json::Array{"source_external_declarations","server_ffi_effect","pinned_source_bindings","interpreter_native_calls","browser_server_exclusion","call_scoped_tokens","copied_utf8_and_bytes","immutable_aggregate_inspection","owned_value_forwarding","sticky_host_traps","cooperative_polling","thread_checked_contexts","typed_input_validation","typed_return_validation","nominal_builders","borrowed_callable_authority","unit_results","legacy_c_table_prefix"}},
      {"default_limits",llvm::json::Object{{"references",4096},{"copied_bytes",1048576},{"operations",65536}}},
      {"pending",llvm::json::Array{"current_platform_validation","callbacks_into_nex","stable_abi_validation"}}}},
    {"resource_features",llvm::json::Array{"server_file_type","identity_aliases","owned_aggregate_and_capture_values","explicit_close","scope_revocation","bounded_streaming_io","opaque_pure_debug_identity","no_wire_or_browser_authority"}},
    {"host_resource_runtime",llvm::json::Object{
      {"source_support",true},{"status","development_source_files"},{"design","docs/resources-design.md"},
      {"features",llvm::json::Array{"typed_alias_owners","physical_operation_leases","ancestor_revocation","physical_quotas","streaming_regular_files","managed_file_values","profiled_owned_payloads","nested_json_resource_rejection","native_streaming_boundary","joined_request_capabilities"}},
      {"limits",llvm::json::Object{{"default_domain_resources",64},{"maximum_domain_resources",4096},{"domain_depth",8},{"file_call_bytes",1048576}}},
      {"pending",llvm::json::Array{"general_resource_types","stable_ffi_abi","async_tasks","full_platform_sdk_validation"}}}},
    {"realms",llvm::json::Array{"shared","client","server"}},
    {"features",llvm::json::Array{"functions","recursion","let","var","assignment","if","while","short_circuit","checked_i64","tests","unicode_strings","immutable_lists","structures","algebraic_enums","exhaustive_match","automatic_reference_counting","modules","imports","public_exports","source_bundles","dependency_locks","typescript_backend","web_ui","web_state_update_view","web_request_commands","web_request_cancellation","client_reachability","recoverable_results","typed_json","native_libraries","request_scopes","sqlite_storage","native_http","native_https","principal_storage","cooperative_request_cancellation"}},
    {"builtins",llvm::json::Array{"with_tasks(i64, fn(task_scope)->T !{task}) -> T !{task} [callback pure, task, or authorized server task/fs]","task_spawn(task_scope, fn()->T !{task}) -> task<T> !{task} [callback pure, task, or authorized server task/fs]","task_wait(task<T>) -> T !{task}","task_yield() -> unit !{task}","current_task_scope() -> task_scope !{task}","channel_new<T>(task_scope, i64) -> channel<T> !{task}","task_send(channel<T>, T) -> bool !{task}","task_recv(channel<T>) -> result<T> !{task}","task_close(channel<T>) -> bool !{task}","task_cancel(task<T>) -> bool !{task}","parallel_map(list<T>, fn(T)->U, i64) -> list<U> [available-realm pure callback]","as_f64(i64) -> f64","as_i64(f64) -> result<i64>","print(T) -> unit !{io}","assert(bool) -> unit","len(str|bytes|list<T>) -> i64","str(T) -> str","push(list<T>, T) -> list<T>","push(bytes, i64) -> bytes","set(list<T>, i64, T) -> list<T>","set(bytes, i64, i64) -> bytes","slice(str, i64, i64) -> str","slice(bytes, i64, i64) -> bytes","contains(str, str) -> bool","ok(T) -> result<T>","err<T>(str, str) -> result<T>","is_ok(result<T>) -> bool","unwrap(result<T>) -> T","error_code(result<T>) -> str","error_message(result<T>) -> str","encode_json(T) -> str","decode_json<T>(str) -> result<T>","read_env(str) -> result<str> !{io} [server]","store_get(str) -> result<str> !{db} [server]","store_put(str, str) -> result<bool> !{db} [server]","store_remove(str) -> result<bool> !{db} [server]","store_keys(str) -> result<list<str>> !{db} [server]","file_read_text(str) -> result<str> !{fs} [server]","file_write_text(str, str) -> result<bool> !{fs} [server]","bytes(list<i64>) -> result<bytes>","utf8_bytes(str) -> bytes","decode_utf8(bytes) -> result<str>","encode_base64(bytes) -> str","decode_base64(str) -> result<bytes>","file_read_bytes(str) -> result<bytes> !{fs} [server]","file_write_bytes(str, bytes) -> result<bool> !{fs} [server]","file_open_read(str) -> result<file> !{fs} [server]","file_open_write(str) -> result<file> !{fs} [server]","file_open_append(str) -> result<file> !{fs} [server]","file_read(file, i64) -> result<bytes> !{fs} [server]","file_write(file, bytes) -> result<i64> !{fs} [server]","file_seek(file, i64) -> result<i64> !{fs} [server]","file_size(file) -> result<i64> !{fs} [server]","file_flush(file) -> result<bool> !{fs} [server]","file_close(file) -> bool !{fs} [server]","file_is_open(file) -> bool !{fs} [server]"}},
    {"binary_features",llvm::json::Array{"immutable_contiguous_octets","retained_slice_owners","copied_mutable_host_boundaries","checked_byte_updates","strict_utf8_codecs","canonical_padded_base64","typed_json_base64","binary_files","generic_add_and_wire","bounded_binary_watches"}},
    {"binary_limits",llvm::json::Object{{"octet_min",0},{"octet_max",255},{"standalone_json_raw_bytes",786429},{"partial_watch_slice_octets",255}}},
    {"binary_guide","docs/bytes.md"},
    {"binary_integration_pending",llvm::json::Array{"full_source_regression_and_migration_validation","full_platform_and_installed_sdk_validation"}},
    {"numeric_features",llvm::json::Array{"finite_binary64","decimal_exponent_literals","checked_f64","explicit_numeric_conversions","numeric_wire_numbers","generic_number_bound"}},
    {"numeric_limits",llvm::json::Object{{"literal_bytes",4096}}},
    {"numeric_integration_pending",llvm::json::Array{"full_platform_and_installed_sdk_validation"}},
    {"match_guide","docs/matching.md"},
    {"match_features",llvm::json::Array{"typed_nested_patterns","match_expressions","ordered_guards","result_patterns","record_patterns","exact_list_patterns","literal_patterns","wildcards","checked_coverage","checked_unreachable_arms","lazy_watch_patterns"}},
    {"match_limits",llvm::json::Object{{"arms",4096},{"pattern_nodes",10000},{"pattern_depth",64},{"pattern_payload",1024},{"coverage_states",100000},{"coverage_depth",128}}},
    {"generic_features",llvm::json::Array{"parametric_body_checking","generic_functions","generic_structures","generic_enums","expected_type_inference","argument_type_inference","checked_monomorphization","derived_instance_context","source_template_patches","builtin_type_constraints","constraint_implication","constrained_numeric_literals","user_traits","coherent_implementations","associated_types","constructor_parameters","generic_trait_methods","static_trait_dispatch"}},
    {"generic_constraints",llvm::json::Object{{"add",llvm::json::Array{"i64","f64","str","bytes","list<T>"}},{"ordered",llvm::json::Array{"i64","f64"}},{"integer",llvm::json::Array{"i64"}},{"number",llvm::json::Array{"i64","f64"}},{"wire","recursive scalar/list/result/nominal payloads without function values or file types, including phantom file arguments"},{"implications",llvm::json::Object{{"integer",llvm::json::Array{"number","add","ordered","wire"}},{"number",llvm::json::Array{"add","ordered","wire"}},{"ordered",llvm::json::Array{"wire"}}}}}},
    {"function_value_features",llvm::json::Array{"typed_named_references","generic_reference_inference","higher_order_calls","snapshot_closures","transitive_captures","identity_equality","native_indirect_calls","typescript_closures","owned_capture_cleanup","lazy_callable_watches"}},
    {"function_value_limits",llvm::json::Object{{"parameters",1024},{"captures",1024},{"closure_nesting",64},{"closure_instances",4096},{"signature_bytes",4096},{"target_name_bytes",4096}}},
    {"function_value_guide","docs/functions.md"},
    {"generic_limits",llvm::json::Object{{"parameters",64},{"instances_per_kind",4096},{"type_expansion_depth",64},{"source_type_depth",128},{"instance_name_bytes",4096}}},
    {"api_features",llvm::json::Array{"endpoint_declarations","api_generation","openapi_3_1","typed_request_validation","generated_client_helpers","generated_server_dispatch","associated_model_projection","constructor_model_parameters","client_trait_library_projection","filtered_server_trait_members"}},
    {"editor_features",llvm::json::Array{"installed_vscode_extension_sources","fresh_compiler_debug_session","byte_checked_original_source_mapping","frozen_source_fallback","workspace_trust_gate","vscode_stdio_language_client","unsaved_source_diagnostics","checked_hover_definition_symbols","versioned_document_updates","checked_symbol_references","project_architecture_debug_launch","pinned_project_launch_plans","dirty_project_buffer_gate"}},
    {"editor_extension_manifest","editor/vscode/package.json"},
    {"editor_project_debug",llvm::json::Object{{"command","nex.debugProject"},{"extension_version","0.7.0"},{"minimum_server_toolchain","0.85.0"},{"kinds",llvm::json::Array{"executable","server"}},{"foreign_launch_field","foreign"},{"launch_field","project"},{"fields",llvm::json::Array{"manifest","component","configuration"}},{"native_executable_only",false},{"plan_checks","before and after native debug preparation"},{"declared_binary_dependencies",true},{"unsaved_compiled_sources_rejected",true},{"guide","docs/editor.md"}}},
    {"editor_analysis",llvm::json::Object{{"command","nex analyze FILE [--overlay FILE] --json"},{"schema","nex.analysis/1"},{"guide","docs/lsp.md"},{"overlay_schema","llm/editor-overlay.schema.json"},{"analysis_schema","llm/editor-analysis.schema.json"},{"references_command","nex analyze FILE --references [--overlay FILE] --json"},{"references_schema","llm/editor-references.schema.json"},{"references_format","nex.analysis/2"},{"identifiers_command","nex analyze FILE --details [--overlay FILE] --json"},{"identifiers_schema","llm/editor-identifiers.schema.json"},{"identifiers_format","nex.analysis/3"},{"identifiers_limits",llvm::json::Object{{"entries",200000},{"identifier_json_bytes",8388608},{"detail_utf8_bytes",16384}}},{"references_coverage",llvm::json::Array{"function_calls_and_values","lexical_declarations_reads_writes","nominal_constructor_calls_patterns","struct_fields","type_annotations_and_arguments","lexical_type_parameters","trait_contracts_and_implementation_bindings","enum_variant_declarations","import_aliases"}},{"references_limits",llvm::json::Object{{"locations",10000},{"result_bytes",8388608}}},{"references_pending",llvm::json::Array{"closed_unreachable_files","cross_workspace_buffers"}},{"graph_writes",false},{"source_writes",false},{"execution",false}}},
    {"language_server",llvm::json::Object{{"command","nex lsp"},{"protocol","LSP 3.17"},{"transport","stdio"},{"position_encoding","utf-16"},{"sync","full"},{"adapter","editor/lsp/server.py"},{"editor_client","editor/vscode/language.js"},{"vscode_extension_version","0.6.0"},{"methods",llvm::json::Array{"diagnostics","hover","definition","documentSymbol","references"}},{"status","development_validation_pending"}}},
    {"editor_integration_pending",llvm::json::Array{"current_compiler_sdk_acceptance","wider_ide_platform_matrix","lsp_wider_editor_matrix","lsp_completion_references_rename","studio","marketplace_publication"}},
    {"debug_features",llvm::json::Array{"dwarf_parameters","dwarf_locals","lexical_scopes","bounded_value_previews","read_only_frame_json","lldb_dap_launch","checked_pure_expressions","exact_typed_frame_capture","isolated_expression_interpreter","nex_dap_watches","paged_computed_values","demand_driven_aggregate_reads","paged_native_indexed_roots","bounded_backend_variables_requests","constant_time_indexed_child_lookup","frame_module_identity_guard","core_recorded_mapping_image_guard"}},
    {"native_debug_session",llvm::json::Object{{"schema","nex.debug-session/1"},{"schema_file","llm/debug-session.schema.json"},{"guide","docs/server-debugging.md"},{"application_kinds",llvm::json::Array{"executable","http_server"}},{"host_only",true},{"request_deadlines_preserved",true},{"argument_limits",llvm::json::Object{{"arguments",128},{"member_bytes",4096},{"total_bytes",65536}}}}},
    {"native_debug_image_binding",llvm::json::Object{{"selected_frame","executable_or_captured_owned_native_image"},{"function_names_are_not_image_identity",true},{"owned_image_hash","sha256"},{"owned_image_uuid",true},{"requires_matching_manifest",true},{"linux_core_requires_recorded_mapping",true},{"ambiguous_same_path_image_rejected",true},{"content_addressed_build_directory",true},{"recorded_mapping_sources",llvm::json::Array{"minidump_memory_region","elf_nt_file"}}}},
    {"native_core",llvm::json::Object{{"schema","nex.core-report/1"},{"guide","docs/core-debugging.md"},{"reader","debug/core_report.py"},{"formats",llvm::json::Array{"elf64","macho64","minidump64"}},{"readonly",true},{"requires_retained_build",true},{"requires_matching_compiler",true},{"portable_capsule",true},{"owned_images",true},{"capsule",llvm::json::Object{{"schema","nex.core-capsule/1"},{"schema_document","llm/core-capsule.schema.json"},{"helper","tools/core_capsule.py"},{"matching_host_only",true},{"original_paths_required",false},{"source_foreign_declarations",false},{"non_system_dependencies",false},{"captured_first_party_images",true},{"file_limit",int64_t(4096)},{"total_bytes_limit",int64_t(35433480192)},{"copy_timeout_seconds",int64_t(900)}}},{"operation_precision","explicit_source_candidates"},{"limits",llvm::json::Object{{"core_bytes",int64_t(32)*1024*1024*1024},{"threads",64},{"frames",64},{"timeout_seconds_default",60},{"timeout_seconds_maximum",300}}}}},
    {"native_debug_pages",llvm::json::Object{{"root_types",llvm::json::Array{"list<T>","bytes"}},{"page_items",1000},{"maximum_index",2147483647},{"maximum_indexed_children",2147483647},{"page_schema","llm/dap-native-page.schema.json"},{"metadata_field","body.nex.native_page"},{"requires_matching_nex_dap_bridge",true},{"native_preview_not_exact_wire_value",true}}},
    {"debug_guide","docs/debugging.md"},
    {"graph_features",llvm::json::Array{"persistent_operation_ids","typed_operation_tree","lexical_binding_edges","paged_operation_context","deterministic_operation_sites","history_preserving_operation_index","persistent_module_ids","persistent_type_ids","paged_declaration_context","transitive_dependency_context","snapshot_scoped_identity_reconciliation","atomic_identity_pages","history_preserving_declaration_backfill"}},
    {"diagnostic_features",llvm::json::Array{"native_operation_sites","native_application_identity","manifest_checked_trap_mapping","archived_native_log_mapping","bounded_native_trap_records","request_operator_diagnostics"}},
    {"native_diagnostic_guide","docs/native-diagnostics.md"},{"native_diagnostic_schema","llm/native-diagnostics.schema.json"},
    {"native_application_lifetime",llvm::json::Object{{"normal_and_checked_failure_cleanup",true},{"checked_failure_exit",70},{"request_capabilities_added",false},{"request_budgets_added",false},{"embedding_request_scope","explicit"},{"forced_termination_cleanup",false},{"guide","docs/incremental.md"}}},
    {"native_diagnostic_limits",llvm::json::Object{{"record_bytes",65536},{"records",32},{"source_descriptor_bytes",16384},{"message_input_bytes",4096},{"code_input_bytes",128},{"log_bytes",4194304},{"manifest_bytes",67108864},{"json_depth",64}}},
    {"operation_guide","docs/operations.md"},{"operation_schema","llm/operations.schema.json"},{"operation_identity_policy","nex.operation-identity/1"},{"graph_database_schema",4},
    {"history_features",llvm::json::Array{"atomic_head_transition_journal","exact_archived_source_hashes","declared_change_labels","paged_changes","optimistic_archived_restore","history_preserving_schema4"}},
    {"history_limits",llvm::json::Object{{"page_records",1000},{"maximum_offset",10000000},{"note_bytes",1024},{"actor_bytes",128},{"record_bytes",16384}}},
    {"history_guide","docs/history.md"},{"history_schema","llm/history.schema.json"},
    {"snapshot_features",llvm::json::Array{"consistent_sqlite_backup","committed_wal_capture","preserved_graph_rows_and_ids","no_source_schema_migration","new_directory_recovery","source_deleted_replay","sha256_database_manifest","cooperative_deadline"}},
    {"snapshot_limits",llvm::json::Object{{"manifest_bytes",65536},{"json_depth",16},{"tables",64},{"timeout_seconds_default",60},{"timeout_seconds_minimum",1},{"timeout_seconds_maximum",3600}}},
    {"snapshot_external_artifacts_included",false},{"snapshot_guide","docs/snapshots.md"},{"snapshot_schema","llm/graph-snapshot.schema.json"},
    {"project_features",llvm::json::Array{"declared_source_language_guard","root_version_preflight_before_store","reachable_library_language_guard","declared_project_schema_guard","legacy_omitted_metadata","archived_manifest_independence"}},
    {"project_manifest_schema","llm/project.schema.json"},{"compatibility_guide","docs/compatibility.md"},
    {"project_build",llvm::json::Object{{"foreign_projection_schema","llm/project-foreign-projection.schema.json"},{"foreign_package_option","--foreign HOST.json"},{"manifest_schema","nex.project-build/1"},{"manifest_file","nex.build.json"},{"schema_file","llm/project-build.schema.json"},{"guide","docs/project-build.md"},{"plan_command","nex project --kind plan --json"},{"build_command","nex project --kind build --json"},{"package_command","nex project --kind package --directory NEW_DIRECTORY --json"},{"test_build_command","nex project --kind build-test --component NAME --symbol TEST --json"},{"project_task_guide","docs/project-tasks.md"},{ "task_workload_guide","docs/task-workloads.md"},{"task_workload_state_schema","llm/task-workload-state.schema.json"},{"project_capture_schema","llm/project-capture.schema.json"},{"run_command","nex project --kind run --component NAME --json"},{"test_command","nex project --kind test --json"},{"debug_command","nex project --kind debug --component NAME --adapter nex-dap --json"},{"profile_command","nex project --kind profile --component NAME --configuration PROFILE_CONFIG --json"},{"server_workload",llvm::json::Object{{"schema","nex.server-workload/1"},{"schema_file","llm/server-workload.schema.json"},{"result_schema","llm/server-workload-result.schema.json"},{"guide","docs/server-workload.md"},{"runner","tools/server_workload.py"},{"profile_command","nex project --kind profile --component NAME --configuration PROFILE_CONFIG --workload FILE --json"},{"definition_bytes",1048576},{"maximum_requests",4096},{"maximum_concurrency",64},{"loopback_only",true},{"task_capture_replay",true}}},{"action_schema_file","llm/project-action.schema.json"},{"package_schema","nex.project-package/1"},{"package_schema_file","llm/project-package.schema.json"},{"artifact_kinds",llvm::json::Array{"source","executable","static_library","shared_library","server","web"}},{"dependency_linkage",llvm::json::Array{"source","static","dynamic"}},{"features",llvm::json::Array{"disjoint_component_roots","checked_direct_import_edges","acyclic_component_dependencies","named_build_configurations","readonly_checked_plan","captured_source_closures","native_and_web_artifacts","checked_static_archive_consumption","multiple_concrete_library_exports","single_application_runtime","macos_linux_shared_images","captured_owned_image_closure","shared_image_lldb_frames","shared_image_core_capsules","project_application_packages","project_foreign_pin_projection","per_application_foreign_grants","project_foreign_package_tasks","project_web_distribution_packages","project_binary_execution","project_owned_tests","project_test_build_only","project_architecture_tasks","project_architecture_replay","project_native_debug_descriptors","project_server_debug_descriptors","editor_http_server_launches","project_native_profiles","project_server_workload_profiles","captured_project_diagnostics","explicit_consumer_template_instantiations","no_graph_head_synchronization"}},{"limits",llvm::json::Object{{"manifest_bytes",262144},{"components",128},{"configurations",32},{"selected_source_bytes",67108864},{"plan_bytes",8388608},{"tests",256},{"test_response_bytes",32768}}},{"pending",llvm::json::Array{"windows_dll_output","packaged_debug_provenance","server_workload_debug","project_task_editor_commands","fully_static_executables","resolved_artifact_dependency_report","source_concurrency","gpu_npu_adapters"}}}},
    {"string_debug_features",llvm::json::Array{"unicode_scalar_shape","bounded_text_range_captures","whole_string_compatibility","binding_and_callable_alias_range_consistency","readonly_utf8_streaming_provider","per_stop_checkpoint_cache"}},
    {"string_debug_limits",llvm::json::Object{{"range_scalars",4096},{"range_bytes",16384},{"provider_chunk_bytes",65536},{"provider_scan_bytes",32*1048576},{"observed_text_scalars",100000}}},
    {"string_debug_capture_kind","text_range"},{"string_debug_guide","docs/string-debug.md"},{"string_debug_schema","llm/text-range.schema.json"},
    {"graph_query_features",llvm::json::Array{"literal_symbol_search","literal_source_search","bounded_declaration_preview","archived_input_selection","paged_dependency_radius","reverse_static_references","explicit_depth_boundary","independent_node_edge_pages","revision_source_namespace_query_identity"}},
    {"graph_query_entities",llvm::json::Array{"module","type","function","endpoint"}},
    {"graph_query_limits",llvm::json::Object{{"query_bytes",1024},{"symbol_bytes",8192},{"label_bytes",8192},{"id_bytes",128},{"preview_bytes",2048},{"page_rows",1000},{"offset",10000000},{"depth",8},{"collection_budget_bytes",65536},{"response_bytes",262144}}},
    {"graph_query_guide","docs/queries.md"},{"graph_query_schema","llm/graph-query.schema.json"},
    {"frontend_diagnostic_features",llvm::json::Array{"captured_source_inputs","parser_binder_checker_context","explicit_partial_source_closure","bounded_utf8_or_base64_preview","content_diagnostic_identity","uncommitted_candidate_context","watch_frame_bound_context","preserved_runtime_operation_metadata"}},
    {"frontend_diagnostic_limits",llvm::json::Object{{"preview_bytes",4096},{"label_bytes",1024}}},
    {"frontend_diagnostic_guide","docs/frontend-diagnostics.md"},{"frontend_diagnostic_schema","llm/frontend-diagnostics.schema.json"},
    {"graph_identity_policy","nex.graph-identity/1"},{"graph_identity_schema",1},{"graph_guide","docs/graph.md"},{"graph_schema","llm/graph-identity.schema.json"},
    {"patch_entities",llvm::json::Array{"function","endpoint","type","operation","trait","impl"}},
    {"patch_features",llvm::json::Array{"expected_head","whole_bundle_recheck","atomic_multi_module","explicit_definition_kind","source_type_templates","source_trait_implementations","persistent_declaration_ids","local_operation_replacements","exact_source_guard","single_syntax_fragment","overlap_rejection","isolated_comment_boundaries"}},
    {"operation_source_kinds",llvm::json::Array{"expression","statement","pattern"}},
    {"patch_limits",llvm::json::Object{{"file_bytes",4194304},{"json_depth",64},{"replacements",1000},{"fragment_tokens",100000},{"source_preview_bytes",4096}}},
    {"parser_limits",llvm::json::Object{{"syntax_recursion",256},{"expression_chain",256},{"expression_tree_depth",256}}},
    {"graph_identity_limits",llvm::json::Object{{"declaration_nodes",100000},{"dependency_edges",2000000},{"page_nodes",1000},{"manifest_bytes",4194304},{"context_source_bytes",4096},{"context_definition_bytes",8192},{"context_references",100},{"symbol_bytes",8192},{"operation_path_bytes",8192},{"id_bytes",128}}},
    {"expression_guide","docs/expressions.md"},{"debug_frame_schema","llm/debug-frame.schema.json"},
    {"partial_debug_frame_schema","llm/debug-frame-v2.schema.json"},{"debug_frame_protocols",llvm::json::Array{"nex.debug-frame/1","nex.debug-frame/2"}},
    {"debug_wire_schema","llm/debug-wire.schema.json"},{"debug_value_protocol","nex.debug-wire/1"},{"debug_runtime_view","nex.runtime-view/3"},{"debug_expression_protocol","nex.debug-expression/3"},
    {"native_tool_arguments",llvm::json::Object{{"guide","docs/incremental.md"},{"response_file_dialect","GNU"},{"encoding","UTF-8"},{"application_argv_unchanged",true},{"private_directory_mode","0700"},{"private_file_mode","0600"},{"successful_files_removed",true},{"failed_files_retained_in_diagnostic",true},{"hosts",llvm::json::Array{"macos","linux"}},{"windows_host_validation","pending"}}},
    {"build_features",llvm::json::Array{"gnu_native_tool_response_files","native_checked_i64_ssa","cold_integer_failure_calls","cold_native_assertions","native_module_compilation","native_function_compilation","function_source_invalidation","frozen_debug_source_maps","interface_type_invalidation","verified_native_object_cache","compilation_dependency_index","explicit_native_toolchains","target_abi_probe","architecture_isolated_caches","macos_cross_compilation","linux_native","explicit_linker_selection","streamed_artifact_copy","relative_host_sdk","explicit_archive_debug_tools","ios_explicit_sdk_archives","windows_explicit_gnu_ucrt_core"}},
    {"windows_core_target",llvm::json::Object{{"architectures",llvm::json::Array{"x86_64","aarch64"}},{"environment","gnu"},
      {"runtime","ucrt-static"},{"artifacts",llvm::json::Array{"executable","static_library"}},{"profiles",llvm::json::Array{"debug","release"}},
      {"explicit_toolchain",true},{"explicit_component_notices",true},{"host_execution",false},{"application_packaging",false},
      {"database",true},{"explicit_target_sqlite",true},{"files",false},{"environment_access",true},
      {"environment_encoding","strict_utf8_utf16"},{"source_foreign_loading",false},{"profiling",false},{"guide","docs/windows.md"}}},
    {"ios_archive_target",llvm::json::Object{{"host","macos"},{"artifact","static_library"},{"device_architectures",llvm::json::Array{"arm64"}},
      {"simulator_architectures",llvm::json::Array{"arm64","x86_64"}},{"profiles",llvm::json::Array{"debug","release"}},
      {"explicit_toolchain",true},{"explicit_sysroot",true},{"versioned_target",true},{"host_execution",false},
      {"application_packaging",false},{"source_foreign_loading",false},{"guide","docs/ios.md"}}},
    {"mobile_project_generation",llvm::json::Object{{"tool","tools/mobile_project.py"},{"guide","docs/mobile.md"},
      {"platforms",llvm::json::Array{"ios","android"}},{"ui","webview"},{"source_backend","typescript-react"},
      {"capacitor_version","8.5.3"},{"artifact","native_project"},{"ios_dependencies","checksum_pinned_local_xcframework"},
      {"api_origin_option","--api-origin"},{"api_transport","bounded_https_fetch_cors"},{"api_credentials","runtime_bearer"},
      {"offline_cache",true},{"automatic_signing",false},{"automatic_installation",false},{"native_archive_target",false}}},
    {"server_cors",llvm::json::Object{{"option","--cors-origin"},{"maximum_origins",16},{"wildcards",false},{"cookies",false},{"preflight_authentication",false},{"api_authentication","bearer"},{"guide","docs/mobile-api.md"}}},
    {"host_sdk_schema","llm/sdk-host.schema.json"},{"sdk_bundle_tool","tools/sdk_bundle.py"},{"sdk_bundle_platforms",llvm::json::Array{"macos","linux"}},
    {"application_package_command","nex package [file] --directory NEW [--target server] [--foreign HOST.json] [--notices FILE] [--dpkg-notices] --json"},
    {"application_package_platforms",llvm::json::Array{"macos","linux"}},
    {"application_package_schema","llm/application-package.schema.json"},
    {"application_package_guide","docs/packaging.md"},
    {"application_package_foreign",llvm::json::Object{{"source_support",true},{"project_support",true},
      {"projection_schema","llm/foreign-projection.schema.json"},
      {"preparation_schema","llm/foreign-package.schema.json"},
      {"features",llvm::json::Array{"explicit_operator_grant","reachable_library_exports","recursive_native_dependencies","complete_component_notices","relocated_manifest_pins","checked_source_projection","preserved_graph_history","preserved_module_image_identity","executable_relative_catalogue","captured_file_integrity"}},
      {"catalogue_capture_limits",llvm::json::Object{{"bytes",134217728},{"files",8190},{"notice_member_bytes",67108864}}},
      {"limits",llvm::json::Array{"matching_host_target","native_loader_dependencies_only","trusted_native_code","current_platform_validation_pending"}}}},
    {"application_package_limits",llvm::json::Array{"host_platform_assembly","external_platform_runtime","execution_verified_separately","no_web_assets_or_runtime_secrets","no_gui_installer_or_notarization"}},
    {"native_toolchain_schema","llm/toolchain.schema.json"},{"native_target_policy","64-bit host ABI; macOS arm64/x86_64 cross-builds on macOS; run/test/debug/profile require host architecture; target libraries must be supplied for cross-storage/server builds"},
    {"build_guide","docs/incremental.md"},{"linux_guide","docs/linux.md"},{"toolchain_fingerprint","nex.toolchain-snapshot/2"},
    {"profile_features",llvm::json::Array{"native_function_instrumentation","graph_attributed_wall_time","bounded_trace_events","managed_shallow_allocations","tracy_cpu_zones","tracy_named_memory_pools"}},
    {"profile_guide","docs/profiling.md"},
    {"verification_features",llvm::json::Array{"snapshot_bound_contracts","z3_checked_scalar_proofs","inductive_while_invariants","loop_termination_rankings","inlined_pure_calls","counterexample_models","replayable_smt_queries","explicit_unproven_status"}},
    {"verification_guide","docs/verification.md"},
    {"task_features",llvm::json::Array{"task_contracts","pinned_acceptance_intent","requirement_graph_linkage","multi_program_snapshots","acceptance_checks","checkpointed_receipts","task_input_replay","isolated_replay_graph","readonly_receipt_replay","process_group_cleanup","pinned_native_toolchains","foreign_build_acceptance","trusted_toolchain_replay","reviewed_foreign_catalogues","captured_foreign_inventory","trusted_foreign_replay","owned_foreign_temporary_files","project_architecture_tasks","project_architecture_replay","project_configurations","direct_project_native_supervision","project_task_packages","project_foreign_package_tasks","pinned_package_notices","project_task_server_workloads","captured_workload_inputs","synthetic_workload_runtime_state","hardware_bound_request_budgets"}},
    {"task_guide","docs/tasks.md"},{"task_schema","llm/task.schema.json"},
    {"task_catalogue_command","nex foreign HOST.json --json"},{"task_foreign_field","foreign_hash"},
    {"trait_features",llvm::json::Array{"parametric_contracts","named_implementations","associated_value_types","constructor_kinds","generic_methods","ordinary_function_bindings","static_dispatch","method_references","overlap_rejection","orphan_ownership","finite_witnesses","source_declaration_patches","history_preserving_015_migration"}},
    {"trait_limits",llvm::json::Object{{"declarations",4096},{"implementations",4096},{"members_per_trait",1024},{"self_plus_method_parameters",64},{"constructor_arity",64},{"obligation_depth",64},{"obligation_steps",4096}}},
    {"trait_integration_pending",llvm::json::Array{"full_current_regression","installed_sdk","linux_matrix","extended_generic_watch_context","trait_projection_full_matrix","release_sanitizers"}},
    {"not_yet_supported",llvm::json::Array{"async","general_wasm_applications","gpu","effect_handlers","mutable_collections","cyclic_module_imports","remote_package_registry"}},
    {"specification","docs/language.md"},{"grammar","docs/grammar.ebnf"},{"llm_prompt","llm/SYSTEM_PROMPT.md"},{"web_guide","docs/web.md"},{"server_guide","docs/server.md"},{"api_guide","docs/api.md"},
    {"discovery_commands",llvm::json::Array{"nex guide --kind prompt --json","nex guide --kind language --json","nex guide --kind grammar --json","nex guide --kind protocol --json","nex guide --kind web --json","nex guide --kind server --json","nex guide --kind api --json","nex api FILE --json"}}};
}
}
