#include "nex/language.h"
#include "llvm/Support/BLAKE3.h"
#include "llvm/ADT/APFloat.h"
#include "llvm/Support/FormatVariadic.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"
#include <algorithm>
#include <charconv>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <limits>
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
    case Type::Function:{std::string result=t.realm=="shared"?"fn(":t.realm+" fn(";for(size_t i=0;i<t.arguments.size();++i){if(i)result+=",";result+=typeName(t.arguments[i]);}result+=")->"+(t.element->kind==Type::Function?"("+typeName(*t.element)+")":typeName(*t.element));if(!t.effects.empty()){result+="!{";for(const auto &effect:t.effects){if(result.back()!='{')result+=",";result+=effect;}result+="}";}return result;}
    case Type::Record:return t.arguments.empty()?t.name:genericName(t.name,t.arguments);
    case Type::Parameter:return "$"+t.name;default: return "unknown"; }
}
const std::set<std::string> &builtinNames(){
  static const std::set<std::string> names=[] {
    std::set<std::string> result={"as_f64","as_i64","print","assert","len","str","push","set","slice","contains","ok","err","is_ok","unwrap","error_code","error_message","encode_json","decode_json","read_env","store_get","store_put","store_remove","store_keys","file_read_text","file_write_text","bytes","utf8_bytes","decode_utf8","encode_base64","decode_base64","file_read_bytes","file_write_bytes","file"};
    result.insert(streamFileBuiltins().begin(),streamFileBuiltins().end());return result;
  }();
  return names;
}
const std::set<std::string> &streamFileBuiltins(){
  static const std::set<std::string> names={"file_open_read","file_open_write","file_open_append","file_read","file_write","file_seek","file_size","file_flush","file_close","file_is_open"};return names;
}
std::string readFile(const std::string &path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw Error("E_FILE", "cannot read " + path);
  return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
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
      else if (std::string("(){}[]:;.,+-*/%<>=!").find(c) != std::string::npos) advance();
      else throw Error("E_LEX", "unexpected character", s);
    }
    s.end = i; return {source.substr(s.begin, i-s.begin), s, kind};
  }
};
class Parser {
  Program p; std::vector<Token> tokens; size_t i = 0; unsigned typeDepth=0,lambdaCounter=0,lambdaDepth=0;std::set<std::string> parameters;
  const Token &peek(size_t n=0) const { return tokens.at(std::min(i+n,tokens.size()-1)); }
  Token take() { return tokens.at(i++); }
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
  std::vector<std::string> templateParameters(TypeBounds &bounds){
    parameters.clear();bounds.clear();std::vector<std::string> result;if(!accept("<"))return result;
    do{auto parameter=name();if(parameter.text=="bytes"||parameter.text=="file"||!parameters.insert(parameter.text).second)throw Error("E_DUPLICATE","duplicate or reserved generic parameter",parameter.span);if(result.size()>=64)throw Error("E_GENERIC_LIMIT","generic declarations support at most 64 parameters",parameter.span);result.push_back(parameter.text);bounds.emplace_back();
      if(accept(":"))do{auto bound=name();if(bound.text!="add"&&bound.text!="ordered"&&bound.text!="integer"&&bound.text!="number"&&bound.text!="wire")throw Error("E_GENERIC_BOUND","unknown generic constraint '"+bound.text+"'",bound.span);if(!bounds.back().insert(bound.text).second)throw Error("E_GENERIC_BOUND","duplicate generic constraint '"+bound.text+"'",bound.span);}while(accept("+"));
    }while(accept(","));typeEnd();return result;
  }
  std::vector<Type> typeArguments(){std::vector<Type> result;expect("<");do{if(result.size()>=64)throw Error("E_GENERIC_LIMIT","generic calls support at most 64 arguments",peek().span);result.push_back(type());}while(accept(","));typeEnd();return result;}
  std::set<std::string> effects(){std::set<std::string> result;if(accept("!")){expect("{");if(!accept("}")){do{auto effect=name();if(!result.insert(effect.text).second)throw Error("E_EFFECT","duplicate effect",effect.span);}while(accept(","));expect("}");}}return result;}
  Type type() {
    if(typeDepth>=128)throw Error("E_GENERIC_LIMIT","source type nesting exceeds limit",peek().span);
    struct Depth {unsigned &value;Depth(unsigned &v):value(v){++value;}~Depth(){--value;}} guard(typeDepth);
    auto t = take();
    if(t.text=="("){auto result=type();expect(")");return result;}
    if(t.text=="fn"||t.text=="shared"||t.text=="client"||t.text=="server"){
      auto realm=t.text=="fn"?"shared":t.text;if(t.text!="fn")expect("fn");std::vector<Type> args;expect("(");if(!accept(")")){do{if(args.size()>=1024)throw Error("E_FUNCTION_LIMIT","function type exceeds 1024 parameters",peek().span);args.push_back(type());}while(accept(","));expect(")");}expect("->");auto result=type();return Type::function(std::move(args),std::move(result),realm,effects());
    }
    if (t.text=="i64") return Type::I64; if (t.text=="bool") return Type::Bool; if(t.text=="unit")return Type::Unit;if(t.text=="str")return Type::Str;
    if(t.text=="f64")return Type::F64;
    if(t.text=="bytes"&&peek().text!="::")return Type::Bytes;
    if(t.text=="file"&&peek().text!="::")return Type::File;
    if(t.text=="list"||(t.text=="result"&&peek().text=="<")) {
      expect("<");auto item=type();
      typeEnd();
      return t.text=="list"?Type::list(std::move(item)):Type::result(std::move(item));
    }
    if(t.kind==Token::Id){auto text=t.text;while(accept("::"))text+="::"+name().text;auto value=Type::record(text);if(parameters.contains(text)){value.kind=Type::Parameter;return value;}if(peek().text=="<")value.arguments=typeArguments();return value;}
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
      if(token.text=="true"||token.text=="false"){value->kind=Pattern::Boolean;value->number=token.text=="true";return value;}
      bool list=token.text=="[";if(!list){--i;token=name();value->text=token.text;while(accept("::"))value->text+="::"+name().text;}
      if(list||accept("(")){value->kind=list?Pattern::List:Pattern::Constructor;auto end=list?"]":")";if(!accept(end)){do{if(value->args.size()>=1024)throw Error("E_MATCH_LIMIT","pattern payload exceeds 1024 entries",peek().span);value->args.push_back(pattern(depth+1,nodes));}while(accept(","));expect(end);}}
      else{if(value->text.find("::")!=std::string::npos)throw Error("E_PARSE","constructor pattern requires parentheses",token.span);value->kind=value->text=="_"?Pattern::Wildcard:Pattern::Binding;}
    }else if(token.kind==Token::String){value->kind=Pattern::String;try{value->text=nexrt::decodeLiteral(token.text);}catch(const nexrt::DataError &err){throw Error(err.code,err.what(),token.span);}}
    else if(token.kind==Token::Num||token.text=="-"){
      auto text=token.text;if(token.text=="-"){auto number=take();if(number.kind!=Token::Num)throw Error("E_PARSE","negative pattern requires an integer literal",number.span);text+=number.text;}
      value->kind=Pattern::Integer;auto result=std::from_chars(text.data(),text.data()+text.size(),value->number);if(result.ec!=std::errc())throw Error("E_RANGE","integer pattern is outside i64",token.span);
    }else throw Error("E_PARSE","expected a pattern",token.span);return value;
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
      }
      if(accept("(")) {
        e->kind=Expr::Call;
        if(!accept(")")) { do {e->args.push_back(expression());}while(accept(",")); expect(")"); }
      }
    } else throw Error("E_PARSE","expected expression, found '"+token.text+"'",token.span);
    while(peek().text=="."||peek().text=="["||peek().text=="(") {
      auto op=take();auto b=std::make_shared<Expr>();b->span=op.span;b->args={e};
      if(op.text=="."){b->kind=Expr::Field;b->text=name().text;}
      else if(op.text=="("){b->kind=Expr::Invoke;if(!accept(")")){do{b->args.push_back(expression());}while(accept(","));expect(")");}}
      else {b->kind=Expr::Index;b->args.push_back(expression());expect("]");}
      e=b;
    }
    while(precedence(peek().text)>=minimum) {
      auto op=take(); auto rhs=expression(precedence(op.text)+1);
      auto b=std::make_shared<Expr>(); b->kind=Expr::Binary; b->span=op.span; b->text=op.text; b->args={e,rhs}; e=b;
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
    return s;
  }
public:
  Parser(std::string source,std::string path,unsigned maxTokens=0) {
    p.source=std::move(source);p.path=std::move(path);Lexer lex(p.source,p.path);
    do {tokens.push_back(lex.next());if(maxTokens&&tokens.size()>maxTokens)throw Error("E_DEBUG_LIMIT","expression exceeds its token budget",tokens.back().span);}while(tokens.back().kind!=Token::End);
  }
  E expressionOnly(){auto value=expression();if(peek().kind!=Token::End)throw Error("E_PARSE","unexpected token after expression",peek().span);return value;}
  Type typeOnly(){auto value=type();if(peek().kind!=Token::End)throw Error("E_TYPE","unexpected token after type",peek().span);return value;}
  Program run() {
    expect("module");p.module=qualified();expect(";");
    while(peek().kind!=Token::End) {
      if(accept("endpoint")){
        Endpoint endpoint;endpoint.span=tokens.at(i-1).span;endpoint.name=name().text;
        auto literal=[&](){auto token=take();if(token.kind!=Token::String)throw Error("E_PARSE","endpoint requires quoted method/path",token.span);try{return nexrt::decodeLiteral(token.text);}catch(const nexrt::DataError &err){throw Error(err.code,err.what(),token.span);}};
        expect("(");endpoint.method=literal();expect(",");endpoint.path=literal();
        if(accept(",")){auto token=take();auto [end,error]=std::from_chars(token.text.data(),token.text.data()+token.text.size(),endpoint.successStatus);if(token.kind!=Token::Num||error!=std::errc()||end!=token.text.data()+token.text.size())throw Error("E_PARSE","endpoint status must be an integer literal",token.span);}
        expect(")");expect("=");endpoint.target=qualified();endpoint.span.end=expect(";").span.end;p.endpoints.push_back(std::move(endpoint));continue;
      }
      if(accept("import")){
        Import dependency;dependency.span=tokens.at(i-1).span;auto token=take();
        if(token.kind!=Token::String)throw Error("E_PARSE","import path must be a quoted string",token.span);
        try{dependency.path=nexrt::decodeLiteral(token.text);}catch(const nexrt::DataError &err){throw Error(err.code,err.what(),token.span);}
        expect("as");dependency.alias=name().text;dependency.span.end=expect(";").span.end;p.imports.push_back(std::move(dependency));continue;
      }
      auto start=peek().span;bool exported=accept("pub");
      if(peek().text=="enum") {
        Structure s;take();s.span=start;s.exported=exported;s.enumeration=true;s.name=name().text;s.typeParameters=templateParameters(s.typeBounds);expect("{");
        if(s.name=="result"&&!s.typeParameters.empty())throw Error("E_GENERIC_NAME","generic nominal name conflicts with builtin result<T>",s.span);
        while(!accept("}")){
          auto tag=name();Variant v;v.name=tag.text;v.span=tag.span;v.ordinal=s.variants.size();
          if(accept("(")){if(!accept(")")){do{auto field=name();expect(":");v.fields.push_back({field.text,type(),field.span});}while(accept(","));expect(")");}}
          expect(";");s.variants.push_back(std::move(v));
        }
        s.span.end=tokens.at(i-1).span.end;p.structures.push_back(std::move(s));parameters.clear();continue;
      }
      if(peek().text=="struct") {
        Structure s;take();s.span=start;s.exported=exported;s.name=name().text;s.typeParameters=templateParameters(s.typeBounds);expect("{");
        if(s.name=="result"&&!s.typeParameters.empty())throw Error("E_GENERIC_NAME","generic nominal name conflicts with builtin result<T>",s.span);
        while(!accept("}")){auto field=name();expect(":");auto t=type();expect(";");s.fields.push_back({field.text,t,field.span});}
        s.span.end=tokens.at(i-1).span.end;p.structures.push_back(std::move(s));parameters.clear();continue;
      }
      Function f; f.span=start;f.exported=exported;
      if(peek().text=="shared"||peek().text=="server"||peek().text=="client")f.realm=take().text;
      bool external=accept("extern");f.test=accept("test");expect("fn");f.name=name().text;f.typeParameters=templateParameters(f.typeBounds);expect("(");
      if(!accept(")")) {do {auto n=name();expect(":");f.params.push_back({n.text,type(),n.span});}while(accept(","));expect(")");}
      expect("->"); f.result=type();
      if(accept("!")) {expect("{");if(!accept("}")){do {auto n=name();if(!f.effects.insert(n.text).second)throw Error("E_EFFECT","duplicate effect",n.span);}while(accept(","));expect("}");}}
      if(external){
        expect("=");expect("foreign");expect("(");
        auto literal=[&]{auto token=take();if(token.kind!=Token::String)throw Error("E_PARSE","foreign binding requires a string literal",token.span);try{return nexrt::decodeLiteral(token.text);}catch(const nexrt::DataError &e){throw Error(e.code,e.what(),token.span);}};
        ForeignBinding binding;binding.library=literal();expect(",");binding.symbol=literal();expect(",");binding.manifest=literal();expect(")");expect(";");f.foreign=std::move(binding);
      }else{lambdaCounter=0;f.body=block();}
      f.span.end=tokens.at(i-1).span.end;p.functions.push_back(std::move(f));parameters.clear();
    }
    return std::move(p);
  }
};
struct Binding {Type type;bool mutableValue;};
class Checker {
  Program &p; Function *f=nullptr; std::vector<std::map<std::string,Binding>> scopes;
  struct CaptureScope {size_t boundary;std::map<std::string,Binding> bindings;};
  std::vector<CaptureScope*> captures;bool watching=false;
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
    if(f)resourceRealm(t,f->realm,span);
  }
  void resourceRealm(const Type &type,const std::string &realm,Span span){
    if(realm!="server"&&containsFile(p,type))throw Error("E_REALM","file values require a server function, including aggregate and capture types",span);
  }
  void unify(Type formal,Type actual,std::map<std::string,Type> &bound,Span span){
    if(formal.kind==Type::Parameter){auto found=bound.find(formal.name);if(found==bound.end()){if(actual==Type::Unit)throw Error("E_TYPE","generic argument cannot be unit",span);bound[formal.name]=actual;}else same(actual,found->second,span);return;}
    if(formal.kind==Type::Record&&!formal.arguments.empty()){
      if(actual.kind!=Type::Record)throw Error("E_TYPE","expected nominal generic type "+typeName(formal),span);
      const auto &instance=p.structure(actual.name);if(instance.templateName!=formal.name||instance.typeArguments.size()!=formal.arguments.size())throw Error("E_TYPE","generic nominal types differ",span);
      for(size_t i=0;i<formal.arguments.size();++i)unify(formal.arguments[i],instance.typeArguments[i],bound,span);return;
    }
    if(formal.kind!=actual.kind)throw Error("E_TYPE","expected "+typeName(formal)+", found "+typeName(actual),span);
    if(formal.kind==Type::Function){if(formal.arguments.size()!=actual.arguments.size()||formal.realm!=actual.realm||formal.effects!=actual.effects)throw Error("E_TYPE","callable signatures differ",span);for(size_t i=0;i<formal.arguments.size();++i)unify(formal.arguments[i],actual.arguments[i],bound,span);unify(*formal.element,*actual.element,bound,span);return;}
    if(formal.element){unify(*formal.element,*actual.element,bound,span);return;}same(actual,formal,span);
  }
  std::vector<Type> infer(const std::vector<std::string> &parameters,const std::vector<Param> &formals,Type result,E call,Type expected){
    if(formals.size()!=call->args.size())throw Error("E_ARITY","incorrect number of value arguments",call->span);
    std::map<std::string,Type> bound;
    if(!call->typeArguments.empty()){
      if(parameters.size()!=call->typeArguments.size())throw Error("E_GENERIC_ARITY","incorrect number of generic arguments",call->span);
      for(size_t i=0;i<parameters.size();++i){auto argument=call->typeArguments[i];validType(argument,call->span);bound[parameters[i]]=argument;}
    }
    if(expected!=Type::Unknown)unify(result,expected,bound,call->span);
    std::function<bool(const Type&)> missing=[&](const Type &type){if(type.kind==Type::Parameter)return std::find(parameters.begin(),parameters.end(),type.name)!=parameters.end()&&!bound.contains(type.name);if(type.element&&missing(*type.element))return true;for(const auto &a:type.arguments)if(missing(a))return true;return false;};
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
  Type reference(E e,Type expected){
    const Function *target=&p.function(e->text,e->span);
    if(!target->typeParameters.empty()){
      const auto &raw=p.functionTemplates.at(target->name);std::map<std::string,Type> bound;
      if(!e->typeArguments.empty()){if(e->typeArguments.size()!=raw.typeParameters.size())throw Error("E_GENERIC_ARITY","incorrect number of function-reference type arguments",e->span);for(size_t i=0;i<raw.typeParameters.size();++i){auto type=e->typeArguments[i];validType(type,e->span);bound[raw.typeParameters[i]]=type;}}
      if(expected.kind==Type::Function)unify(signature(raw),expected,bound,e->span);
      std::vector<Type> arguments;for(const auto &parameter:raw.typeParameters){if(!bound.contains(parameter))throw Error("E_GENERIC_INFER","generic function value requires explicit types or a function-type context",e->span);arguments.push_back(bound.at(parameter));}
      target=&instantiateFunction(p,*target,arguments,e->span);e->typeArguments=arguments;
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
  Type expr(E e,Type expected={}) {
    switch(e->kind) {
    case Expr::FunctionRef:reference(e,expected);break;
    case Expr::Lambda:lambda(e);break;
    case Expr::Invoke:{
      auto type=expr(e->args[0]);if(type.kind!=Type::Function)throw Error("E_TYPE","called expression is not a function",e->span);
      if(e->args.size()!=type.arguments.size()+1)throw Error("E_ARITY","incorrect number of callable arguments",e->span);
      for(size_t i=0;i<type.arguments.size();++i)same(expr(e->args[i+1],type.arguments[i]),type.arguments[i],e->args[i+1]->span);
      callableRealm(type,e->span);for(const auto &effect:type.effects)if(!f->effects.contains(effect))throw Error("E_EFFECT","indirect call requires declared effect "+effect,e->span);e->type=*type.element;break;
    }
    case Expr::Match:matching(e,expected,false);break;
    case Expr::Integer:e->type=expected.kind==Type::Parameter&&satisfiesConstraint(p,expected,"integer")?expected:Type(Type::I64);break;
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
      if(a==Type::I64&&b.kind==Type::Parameter&&satisfiesConstraint(p,b,"integer"))a=expr(e->args[0],b);
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
      if(!e->typeArguments.empty()&&builtinNames().contains(e->text))throw Error("E_GENERIC_ARITY","this builtin does not accept explicit type arguments",e->span);
      auto arity=[&](size_t count){if(e->args.size()!=count)throw Error("E_ARITY",e->text+" expects "+std::to_string(count)+" arguments",e->span);};
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
        const auto &raw=p.functionTemplates.at(target->name);auto arguments=infer(raw.typeParameters,raw.params,raw.result,e,expected);target=&instantiateFunction(p,*target,arguments,e->span);e->text=target->name;e->typeArguments=arguments;
      }else if(!e->typeArguments.empty()&&target->templateName.empty())throw Error("E_GENERIC_ARITY","function is not generic",e->span);
      const auto &callee=*target;
      if(callee.test)throw Error("E_TEST","test functions cannot be called",e->span);
      if(callee.params.size()!=e->args.size())throw Error("E_ARITY","incorrect number of arguments to '"+e->text+"'",e->span);
      for(size_t j=0;j<e->args.size();++j)same(expr(e->args[j],callee.params[j].type),callee.params[j].type,e->args[j]->span);
      for(const auto &effect:callee.effects)if(!f->effects.contains(effect))throw Error("E_EFFECT","call requires declared effect "+effect,e->span);
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
      if(fn.foreign)(void)foreignSignature(p,fn);
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
    auto context=p.function(selected);context.effects.clear();context.dependencies.clear();f=&context;scopes.emplace_back();watching=true;
    for(const auto &[name,value]:locals){auto type=value;validType(type,expression->span);define(name,{type,false},expression->span);}
    auto result=expr(expression);for(size_t i=0;i<p.functions.size();++i)functionBody(p.functions[i]);return result;
  }
  void run() {
    prepareGenerics(p);
    std::set<std::string> names;
    const auto &builtins=builtinNames();
    for(size_t index=0;index<p.structures.size();++index){auto &s=p.structures[index];
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
      validType(fn.result,fn.span,true);
      for(auto &parameter:fn.params)validType(parameter.type,parameter.span);
      for(const auto &effect:fn.effects)if(effect!="io"&&effect!="db"&&effect!="fs"&&effect!="ffi")throw Error("E_EFFECT","unsupported effect '"+effect+"'",fn.span);
      if(fn.effects.contains("ffi")&&fn.realm!="server")throw Error("E_REALM","ffi effect requires a server function",fn.span);
      if(fn.effects.contains("db")&&fn.realm!="server")throw Error("E_REALM","db effect requires a server function",fn.span);
      if(fn.effects.contains("fs")&&fn.realm!="server")throw Error("E_REALM","fs effect requires a server function",fn.span);
      if(fn.test && (!fn.params.empty()||fn.result!=Type::Unit||!fn.typeParameters.empty()))throw Error("E_TEST","test must take no generic/value parameters and return unit",fn.span);
    }
    for(size_t i=0;i<p.functions.size();++i)functionBody(p.functions[i]);
    std::set<std::string> publicSeen;
    std::function<void(const Type&,Span)> publicType=[&](const Type &t,Span span){
      if(t.element)publicType(*t.element,span);if(t.kind==Type::Function)for(const auto &argument:t.arguments)publicType(argument,span);
      if(t.kind==Type::Record){const auto &s=p.structure(t.name);if(!s.exported)throw Error("E_VISIBILITY","public API exposes private type '"+t.name+"'",span);if(publicSeen.insert(s.name).second){for(const auto &argument:s.typeArguments)publicType(argument,span);for(auto field:s.members())publicType(field->type,field->span);}}
    };
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
Program parse(std::string source,std::string path){
  try{nexrt::unicodeOffsets(source,false);}catch(const nexrt::DataError &err){
    Span span;span.begin=span.end=err.offset;span.file=path;
    for(size_t i=0;i<err.offset;++i){if(source[i]=='\n'){++span.line;span.column=1;}else ++span.column;}
    throw Error(err.code,err.what(),span);
  }
  return Parser(std::move(source),std::move(path)).run();
}
void check(Program &p){Checker(p).run();}
Type checkExpression(Program &p,const std::string &function,E expression,const std::map<std::string,Type> &locals){return Checker(p).watch(function,expression,locals);}
Type parseType(std::string source){return Parser(std::move(source),"<debug-type>").typeOnly();}
E parseExpression(std::string source,std::string path,unsigned maxTokens){
  try{nexrt::unicodeOffsets(source,false);}catch(const nexrt::DataError &err){throw Error(err.code,err.what(),Span{1,1,err.offset,err.offset,path});}
  return Parser(std::move(source),std::move(path),maxTokens).expressionOnly();
}
llvm::json::Value canonical(const Function &f) {
  llvm::json::Array params,effects;
  for(const auto &p:f.params)params.push_back(llvm::json::Object{{"name",p.name},{"type",typeName(p.type)}});
  for(const auto &e:f.effects)effects.push_back(e);
  llvm::json::Array generic,arguments;for(const auto &parameter:f.typeParameters)generic.push_back(parameter);for(const auto &argument:f.typeArguments)arguments.push_back(typeName(argument));
  llvm::json::Object result{{"format","nex.function/12"},{"name",f.name},{"owner",f.owner},{"public",f.exported},{"realm",f.realm},{"parameters",std::move(params)},{"result",typeName(f.result)},{"effects",std::move(effects)},{"test",f.test},{"type_parameters",std::move(generic)},{"type_bounds",canonicalBounds(f.typeParameters,f.typeBounds)},{"template",f.templateName},{"type_arguments",std::move(arguments)},{"body",blockJSON(f.body)}};
  if(f.foreign)result["foreign"]=llvm::json::Object{{"library",f.foreign->library},{"export",f.foreign->symbol},{"manifest_sha256",f.foreign->manifest}};
  if(f.closure){llvm::json::Array captures;for(const auto &capture:f.captures)captures.push_back(llvm::json::Object{{"name",capture.name},{"type",typeName(capture.type)}});result["closure_owner"]=f.closureOwner;result["captures"]=std::move(captures);}return result;
}
llvm::json::Value canonical(const Structure &s) {
  llvm::json::Array generic,arguments;for(const auto &parameter:s.typeParameters)generic.push_back(parameter);for(const auto &argument:s.typeArguments)arguments.push_back(typeName(argument));
  llvm::json::Object result{{"format",s.enumeration?"nex.enum/3":"nex.structure/4"},{"name",s.name},{"owner",s.owner},{"public",s.exported},{"type_parameters",std::move(generic)},{"type_bounds",canonicalBounds(s.typeParameters,s.typeBounds)},{"template",s.templateName},{"type_arguments",std::move(arguments)}};
  if(s.enumeration){llvm::json::Array variants;for(const auto &variant:s.variants){llvm::json::Array fields;for(const auto &field:variant.fields)fields.push_back(llvm::json::Object{{"name",field.name},{"type",typeName(field.type)}});variants.push_back(llvm::json::Object{{"name",variant.name},{"fields",std::move(fields)}});}result["variants"]=std::move(variants);}
  else{llvm::json::Array fields;for(const auto &f:s.fields)fields.push_back(llvm::json::Object{{"name",f.name},{"type",typeName(f.type)}});result["fields"]=std::move(fields);}return result;
}
llvm::json::Value canonical(const Endpoint &endpoint){
  return llvm::json::Object{{"format","nex.endpoint/1"},{"name",endpoint.name},{"method",endpoint.method},{"path",endpoint.path},{"success_status",endpoint.successStatus},{"handler",endpoint.target}};
}
std::string revision(const Program &p) {
  std::map<std::string,std::string> ordered;
  for(const auto &f:p.functions)if(f.templateName.empty()&&!f.closure)ordered[f.name]=json(canonical(f),false);
  llvm::json::Object functions;for(const auto &[name,text]:ordered)functions[name]=text;
  llvm::json::Object structures;for(const auto &s:p.structures)if(s.templateName.empty())structures[s.name]=canonical(s);
  llvm::json::Object modules;
  for(const auto &[key,unit]:p.units){std::set<std::string> targets;for(const auto &import:unit.imports)targets.insert(p.units.at(import.target).module);llvm::json::Array deps;for(const auto &target:targets)deps.push_back(target);modules[unit.module]=std::move(deps);}
  llvm::json::Object endpoints;for(const auto &endpoint:p.endpoints)endpoints[endpoint.name]=canonical(endpoint);
  return hash(json(llvm::json::Object{{"format","nex.program/13"},{"language",languageVersion},{"module",p.module},{"functions",std::move(functions)},{"structures",std::move(structures)},{"modules",std::move(modules)},{"endpoints",std::move(endpoints)}},false));
}
llvm::json::Value describe() {
  return llvm::json::Object{
    {"schema","nex.language/1"},{"version",languageVersion},
    {"types",llvm::json::Array{"i64","f64","bool","unit","str","bytes","file","list<T>","result<T>","nominal structures","nominal enums","user generic types","function values"}},
    {"effects",llvm::json::Array{"io","db","fs","ffi"}},
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
      {"invocation_context",llvm::json::Object{{"source_support",true},{"host_schema","nex.foreign-host/1"},{"binding_schema","nex.foreign-binding/1"},{"header","runtime/nex_foreign.h"},{"native_header","runtime/nex_foreign_abi.h"},{"features",llvm::json::Array{"explicit_regular_file_catalogue","relative_operator_paths","no_ambient_grants","lexical_thread_contexts","snapshotted_call_storage","bounded_binding_cache","request_rebinding","native_managed_value_bridge","sticky_native_source_traps","terminal_module_cleanup"}},{"limits",llvm::json::Object{{"configuration_bytes",1048576},{"binding_bytes",1048576},{"cached_bindings",4096},{"cached_binding_utf8_bytes",67108864},{"scope_depth",64},{"arguments",4096}}}}},
      {"module_loading",llvm::json::Object{{"source_support",true},{"schema","nex.foreign-bundle/1"},{"abi_version",1},{"header","runtime/nex_ffi_module.h"},{"host_header","runtime/nex_ffi_loader.h"},{"platforms",llvm::json::Array{"macos-arm64","macos-x86_64","linux-arm64","linux-x86_64"}},{"features",llvm::json::Array{"explicit_host_export_grants","manifest_and_signature_pins","preload_member_hashes","private_snapshot","typed_calls","resource_scope_revocation","physical_image_leases","cooperative_cancellation","content_addressed_image_cache"}},{"limits",llvm::json::Object{{"manifest_bytes",1048576},{"files",128},{"member_bytes",67108864},{"bundle_bytes",268435456},{"exports",1024},{"host_grants",128}}}}},
      {"features",llvm::json::Array{"source_external_declarations","server_ffi_effect","pinned_source_bindings","interpreter_native_calls","browser_server_exclusion","call_scoped_tokens","copied_utf8_and_bytes","immutable_aggregate_inspection","owned_value_forwarding","sticky_host_traps","cooperative_polling","thread_checked_contexts","typed_input_validation","typed_return_validation","nominal_builders","borrowed_callable_authority","unit_results","legacy_c_table_prefix"}},
      {"default_limits",llvm::json::Object{{"references",4096},{"copied_bytes",1048576},{"operations",65536}}},
      {"pending",llvm::json::Array{"source_validation","dependency_closure_packaging","callbacks_into_nex","stable_abi_validation"}}}},
    {"resource_features",llvm::json::Array{"server_file_type","identity_aliases","owned_aggregate_and_capture_values","explicit_close","scope_revocation","bounded_streaming_io","opaque_pure_debug_identity","no_wire_or_browser_authority"}},
    {"host_resource_runtime",llvm::json::Object{
      {"source_support",true},{"status","development_source_files"},{"design","docs/resources-design.md"},
      {"features",llvm::json::Array{"typed_alias_owners","physical_operation_leases","ancestor_revocation","physical_quotas","streaming_regular_files","managed_file_values","profiled_owned_payloads","nested_json_resource_rejection","native_streaming_boundary","joined_request_capabilities"}},
      {"limits",llvm::json::Object{{"default_domain_resources",64},{"maximum_domain_resources",4096},{"domain_depth",8},{"file_call_bytes",1048576}}},
      {"pending",llvm::json::Array{"general_resource_types","stable_ffi_abi","async_tasks","full_platform_sdk_validation"}}}},
    {"realms",llvm::json::Array{"shared","client","server"}},
    {"features",llvm::json::Array{"functions","recursion","let","var","assignment","if","while","short_circuit","checked_i64","tests","unicode_strings","immutable_lists","structures","algebraic_enums","exhaustive_match","automatic_reference_counting","modules","imports","public_exports","source_bundles","dependency_locks","typescript_backend","web_ui","web_state_update_view","web_request_commands","web_request_cancellation","client_reachability","recoverable_results","typed_json","native_libraries","request_scopes","sqlite_storage","native_http","native_https","principal_storage","cooperative_request_cancellation"}},
    {"builtins",llvm::json::Array{"as_f64(i64) -> f64","as_i64(f64) -> result<i64>","print(T) -> unit !{io}","assert(bool) -> unit","len(str|bytes|list<T>) -> i64","str(T) -> str","push(list<T>, T) -> list<T>","push(bytes, i64) -> bytes","set(list<T>, i64, T) -> list<T>","set(bytes, i64, i64) -> bytes","slice(str, i64, i64) -> str","slice(bytes, i64, i64) -> bytes","contains(str, str) -> bool","ok(T) -> result<T>","err<T>(str, str) -> result<T>","is_ok(result<T>) -> bool","unwrap(result<T>) -> T","error_code(result<T>) -> str","error_message(result<T>) -> str","encode_json(T) -> str","decode_json<T>(str) -> result<T>","read_env(str) -> result<str> !{io} [server]","store_get(str) -> result<str> !{db} [server]","store_put(str, str) -> result<bool> !{db} [server]","store_remove(str) -> result<bool> !{db} [server]","store_keys(str) -> result<list<str>> !{db} [server]","file_read_text(str) -> result<str> !{fs} [server]","file_write_text(str, str) -> result<bool> !{fs} [server]","bytes(list<i64>) -> result<bytes>","utf8_bytes(str) -> bytes","decode_utf8(bytes) -> result<str>","encode_base64(bytes) -> str","decode_base64(str) -> result<bytes>","file_read_bytes(str) -> result<bytes> !{fs} [server]","file_write_bytes(str, bytes) -> result<bool> !{fs} [server]","file_open_read(str) -> result<file> !{fs} [server]","file_open_write(str) -> result<file> !{fs} [server]","file_open_append(str) -> result<file> !{fs} [server]","file_read(file, i64) -> result<bytes> !{fs} [server]","file_write(file, bytes) -> result<i64> !{fs} [server]","file_seek(file, i64) -> result<i64> !{fs} [server]","file_size(file) -> result<i64> !{fs} [server]","file_flush(file) -> result<bool> !{fs} [server]","file_close(file) -> bool !{fs} [server]","file_is_open(file) -> bool !{fs} [server]"}},
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
    {"generic_features",llvm::json::Array{"parametric_body_checking","generic_functions","generic_structures","generic_enums","expected_type_inference","argument_type_inference","checked_monomorphization","derived_instance_context","source_template_patches","builtin_type_constraints","constraint_implication","constrained_numeric_literals"}},
    {"generic_constraints",llvm::json::Object{{"add",llvm::json::Array{"i64","f64","str","bytes","list<T>"}},{"ordered",llvm::json::Array{"i64","f64"}},{"integer",llvm::json::Array{"i64"}},{"number",llvm::json::Array{"i64","f64"}},{"wire","recursive scalar/list/result/nominal payloads without function values or file types, including phantom file arguments"},{"implications",llvm::json::Object{{"integer",llvm::json::Array{"number","add","ordered","wire"}},{"number",llvm::json::Array{"add","ordered","wire"}},{"ordered",llvm::json::Array{"wire"}}}}}},
    {"function_value_features",llvm::json::Array{"typed_named_references","generic_reference_inference","higher_order_calls","snapshot_closures","transitive_captures","identity_equality","native_indirect_calls","typescript_closures","owned_capture_cleanup","lazy_callable_watches"}},
    {"function_value_limits",llvm::json::Object{{"parameters",1024},{"captures",1024},{"closure_nesting",64},{"closure_instances",4096},{"signature_bytes",4096},{"target_name_bytes",4096}}},
    {"function_value_guide","docs/functions.md"},
    {"generic_limits",llvm::json::Object{{"parameters",64},{"instances_per_kind",4096},{"type_expansion_depth",64},{"source_type_depth",128},{"instance_name_bytes",4096}}},
    {"api_features",llvm::json::Array{"endpoint_declarations","api_generation","openapi_3_1","typed_request_validation","generated_client_helpers","generated_server_dispatch"}},
    {"debug_features",llvm::json::Array{"dwarf_parameters","dwarf_locals","lexical_scopes","bounded_value_previews","read_only_frame_json","lldb_dap_launch","checked_pure_expressions","exact_typed_frame_capture","isolated_expression_interpreter","nex_dap_watches","paged_computed_values","demand_driven_aggregate_reads"}},
    {"debug_guide","docs/debugging.md"},
    {"graph_features",llvm::json::Array{"persistent_operation_ids","typed_operation_tree","lexical_binding_edges","paged_operation_context","deterministic_operation_sites","history_preserving_operation_index"}},
    {"operation_guide","docs/operations.md"},{"operation_schema","llm/operations.schema.json"},{"operation_identity_policy","nex.operation-identity/1"},{"graph_database_schema",3},
    {"expression_guide","docs/expressions.md"},{"debug_frame_schema","llm/debug-frame.schema.json"},
    {"partial_debug_frame_schema","llm/debug-frame-v2.schema.json"},{"debug_frame_protocols",llvm::json::Array{"nex.debug-frame/1","nex.debug-frame/2"}},
    {"debug_wire_schema","llm/debug-wire.schema.json"},{"debug_value_protocol","nex.debug-wire/1"},{"debug_runtime_view","nex.runtime-view/3"},{"debug_expression_protocol","nex.debug-expression/3"},
    {"build_features",llvm::json::Array{"native_module_compilation","native_function_compilation","function_source_invalidation","frozen_debug_source_maps","interface_type_invalidation","verified_native_object_cache","compilation_dependency_index","explicit_native_toolchains","target_abi_probe","architecture_isolated_caches","macos_cross_compilation","linux_native","explicit_linker_selection","streamed_artifact_copy","relative_host_sdk","explicit_archive_debug_tools"}},
    {"host_sdk_schema","llm/sdk-host.schema.json"},{"sdk_bundle_tool","tools/sdk_bundle.py"},{"sdk_bundle_platforms",llvm::json::Array{"macos","linux"}},
    {"application_package_command","nex package [file] --directory NEW [--target server] [--notices FILE] [--dpkg-notices] --json"},
    {"application_package_platforms",llvm::json::Array{"macos","linux"}},
    {"application_package_schema","llm/application-package.schema.json"},
    {"application_package_guide","docs/packaging.md"},
    {"application_package_limits",llvm::json::Array{"host_platform_assembly","external_platform_runtime","execution_verified_separately","no_web_assets_or_runtime_secrets","no_gui_installer_or_notarization"}},
    {"native_toolchain_schema","llm/toolchain.schema.json"},{"native_target_policy","64-bit host ABI; macOS arm64/x86_64 cross-builds on macOS; run/test/debug/profile require host architecture; target libraries must be supplied for cross-storage/server builds"},
    {"build_guide","docs/incremental.md"},{"linux_guide","docs/linux.md"},{"toolchain_fingerprint","nex.toolchain-snapshot/2"},
    {"profile_features",llvm::json::Array{"native_function_instrumentation","graph_attributed_wall_time","bounded_trace_events","managed_shallow_allocations","tracy_cpu_zones","tracy_named_memory_pools"}},
    {"profile_guide","docs/profiling.md"},
    {"verification_features",llvm::json::Array{"snapshot_bound_contracts","z3_checked_scalar_proofs","inductive_while_invariants","loop_termination_rankings","inlined_pure_calls","counterexample_models","replayable_smt_queries","explicit_unproven_status"}},
    {"verification_guide","docs/verification.md"},
    {"task_features",llvm::json::Array{"task_contracts","pinned_acceptance_intent","requirement_graph_linkage","multi_program_snapshots","acceptance_checks","checkpointed_receipts","task_input_replay","process_group_cleanup","pinned_native_toolchains","foreign_build_acceptance","trusted_toolchain_replay","reviewed_foreign_catalogues","captured_foreign_inventory","trusted_foreign_replay","owned_foreign_temporary_files"}},
    {"task_guide","docs/tasks.md"},{"task_schema","llm/task.schema.json"},
    {"task_catalogue_command","nex foreign HOST.json --json"},{"task_foreign_field","foreign_hash"},
    {"not_yet_supported",llvm::json::Array{"custom_traits","higher_kinded_types","async","wasm","gpu","ffi_declarations","effect_handlers","mutable_collections","cyclic_module_imports","remote_package_registry"}},
    {"specification","docs/language.md"},{"grammar","docs/grammar.ebnf"},{"llm_prompt","llm/SYSTEM_PROMPT.md"},{"web_guide","docs/web.md"},{"server_guide","docs/server.md"},{"api_guide","docs/api.md"},
    {"discovery_commands",llvm::json::Array{"nex guide --kind prompt --json","nex guide --kind language --json","nex guide --kind grammar --json","nex guide --kind protocol --json","nex guide --kind web --json","nex guide --kind server --json","nex guide --kind api --json","nex api FILE --json"}}};
}
}
