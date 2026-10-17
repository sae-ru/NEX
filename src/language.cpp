#include "nex/language.h"
#include "llvm/Support/BLAKE3.h"
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
std::string typeName(Type t) {
  switch (t.kind) { case Type::I64: return "i64"; case Type::Bool: return "bool";
    case Type::Unit: return "unit";case Type::Str:return "str";
    case Type::List:return "list<"+typeName(*t.element)+">";
    case Type::Result:return "result<"+typeName(*t.element)+">";
    case Type::Record:return t.name;default: return "unknown"; }
}
const std::set<std::string> &builtinNames(){
  static const std::set<std::string> names={"print","assert","len","str","push","set","slice","contains","ok","err","is_ok","unwrap","error_code","error_message","encode_json","decode_json","read_env","store_get","store_put","store_remove","store_keys"};
  return names;
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
const Function &Program::function(const std::string &name,Span span) const {
  for (const auto &f : functions) if (f.name == name || (name.find("::")==std::string::npos&&f.owner==module&&f.localName==name)) return f;
  throw Error("E_NAME", "unknown function '" + name + "'",span);
}
const Structure &Program::structure(const std::string &name) const {
  for(const auto &s:structures)if(s.name==name||(name.find("::")==std::string::npos&&s.owner==module&&s.localName==name))return s;
  throw Error("E_TYPE","unknown structure '"+name+"'");
}
bool Program::hasStructure(const std::string &name)const {
  return std::any_of(structures.begin(),structures.end(),[&](const auto &s){return s.name==name||(name.find("::")==std::string::npos&&s.owner==module&&s.localName==name);});
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
  if(name.find("::")==std::string::npos)return "nex_user_"+name;
  std::string result="nex";size_t begin=0;
  for(;;){auto end=name.find("::",begin);auto part=name.substr(begin,end==std::string::npos?end:end-begin);result+="_"+std::to_string(part.size())+"_"+part;if(end==std::string::npos)break;begin=end+2;}
  return result;
}
namespace {
struct Token { std::string text; Span span; enum Kind { Id, Num, Symbol, End, String } kind; };
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
    } else {
      std::string pair = source.substr(i, 2);
      if (pair == "->" || pair == "==" || pair == "!=" || pair == "<=" || pair == ">=" || pair == "&&" || pair == "||" || pair=="::") { advance(); advance(); }
      else if (std::string("(){}[]:;.,+-*/%<>=!").find(c) != std::string::npos) advance();
      else throw Error("E_LEX", "unexpected character", s);
    }
    s.end = i; return {source.substr(s.begin, i-s.begin), s, kind};
  }
};
class Parser {
  Program p; std::vector<Token> tokens; size_t i = 0;
  const Token &peek(size_t n=0) const { return tokens.at(std::min(i+n,tokens.size()-1)); }
  Token take() { return tokens.at(i++); }
  bool accept(const std::string &s) { if (peek().text == s) { take(); return true; } return false; }
  Token expect(const std::string &s) {
    if (peek().text != s) throw Error("E_PARSE", "expected '"+s+"', found '"+peek().text+"'", peek().span);
    return take();
  }
  Token name() {
    static const std::set<std::string> reserved = {"module","fn","test","let","var","return","if","else","while","true","false","client","server","shared","i64","bool","unit","str","list","struct","pub","import","as"};
    if (peek().kind != Token::Id || reserved.contains(peek().text))
      throw Error("E_PARSE", "expected identifier", peek().span);
    return take();
  }
  std::string qualified(){auto result=name().text;while(accept("::"))result+="::"+name().text;return result;}
  Type type() {
    auto t = take();
    if (t.text=="i64") return Type::I64; if (t.text=="bool") return Type::Bool; if(t.text=="unit")return Type::Unit;if(t.text=="str")return Type::Str;
    if(t.text=="list"||(t.text=="result"&&peek().text=="<")) {
      expect("<");auto item=type();
      if(peek().text==">="){tokens[i].text="=";++tokens[i].span.begin;++tokens[i].span.column;}else expect(">");
      return t.text=="list"?Type::list(std::move(item)):Type::result(std::move(item));
    }
    if(t.kind==Token::Id){auto text=t.text;while(accept("::"))text+="::"+name().text;return Type::record(text);}
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
      const auto &text=peek(n).text;if(text=="<")++depth;
      else if(text==">"){if(--depth==0)return peek(n+1).text=="(";}
      else if(text==";"||text=="{"||text=="}"||text=="=")break;
    }
    return false;
  }
  E expression(int minimum=1) {
    E e; auto token=take();
    if(token.kind==Token::String) {
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
    else if(token.kind==Token::Num) {
      e=std::make_shared<Expr>(); e->kind=Expr::Integer; e->span=token.span;
      auto result=std::from_chars(token.text.data(), token.text.data()+token.text.size(), e->number);
      if(result.ec!=std::errc())throw Error("E_RANGE","integer literal is outside i64",token.span);
    } else if(token.text=="true" || token.text=="false") {
      e=std::make_shared<Expr>(); e->kind=Expr::Boolean; e->span=token.span; e->number=token.text=="true";
    } else if(token.kind==Token::Id) {
      e=std::make_shared<Expr>(); e->kind=Expr::Name; e->span=token.span; e->text=token.text;
      while(accept("::"))e->text+="::"+name().text;
      if((e->text=="decode_json"||e->text=="err")&&genericAhead()){expect("<");e->annotation=type();expect(">");}
      if(accept("(")) {
        e->kind=Expr::Call;
        if(!accept(")")) { do {e->args.push_back(expression());}while(accept(",")); expect(")"); }
      }
    } else throw Error("E_PARSE","expected expression, found '"+token.text+"'",token.span);
    while(peek().text=="."||peek().text=="[") {
      auto op=take();auto b=std::make_shared<Expr>();b->span=op.span;b->args={e};
      if(op.text=="."){b->kind=Expr::Field;b->text=name().text;}
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
    } else {s->kind=Stmt::Expression;s->expr=expression();expect(";");}
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
      if(peek().text=="struct") {
        Structure s;take();s.span=start;s.exported=exported;s.name=name().text;expect("{");
        while(!accept("}")){auto field=name();expect(":");auto t=type();expect(";");s.fields.push_back({field.text,t,field.span});}
        s.span.end=tokens.at(i-1).span.end;p.structures.push_back(std::move(s));continue;
      }
      Function f; f.span=start;f.exported=exported;
      if(peek().text=="shared"||peek().text=="server"||peek().text=="client")f.realm=take().text;
      f.test=accept("test");expect("fn");f.name=name().text;expect("(");
      if(!accept(")")) {do {auto n=name();expect(":");f.params.push_back({n.text,type(),n.span});}while(accept(","));expect(")");}
      expect("->"); f.result=type();
      if(accept("!")) {expect("{");if(!accept("}")){do {auto n=name();if(!f.effects.insert(n.text).second)throw Error("E_EFFECT","duplicate effect",n.span);}while(accept(","));expect("}");}}
      f.body=block();f.span.end=tokens.at(i-1).span.end;p.functions.push_back(std::move(f));
    }
    return std::move(p);
  }
};
struct Binding {Type type;bool mutableValue;};
class Checker {
  Program &p; Function *f=nullptr; std::vector<std::map<std::string,Binding>> scopes;
  Binding lookup(const std::string &name,Span span) {
    for(auto it=scopes.rbegin();it!=scopes.rend();++it)if(it->contains(name))return it->at(name);
    throw Error("E_NAME","unknown local '"+name+"'",span);
  }
  void same(Type actual,Type expected,Span span) {
    if(actual!=expected)throw Error("E_TYPE","expected "+typeName(expected)+", found "+typeName(actual),span);
  }
  void define(const std::string &name,Binding b,Span span) {
    if(scopes.back().contains(name))throw Error("E_DUPLICATE","duplicate local '"+name+"'",span);
    scopes.back()[name]=b;
  }
  void validType(const Type &t,Span span,bool result=false) {
    if(t==Type::Unit&&!result)throw Error("E_TYPE","unit is only valid as a function result",span);
    if(t.kind==Type::Record&&!p.hasStructure(t.name))throw Error("E_TYPE","unknown type '"+t.name+"'",span);
    if(t.kind==Type::List||t.kind==Type::Result)validType(*t.element,span);
  }
  Type expr(E e,Type expected={}) {
    switch(e->kind) {
    case Expr::Integer:e->type=Type::I64;break;
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
      auto base=expr(e->args[0]);same(expr(e->args[1]),Type::I64,e->span);
      if(base.kind!=Type::List&&base!=Type::Str)throw Error("E_TYPE","indexing requires a list or string",e->span);
      e->type=base==Type::Str?Type(Type::Str):*base.element;break;
    }
    case Expr::Name:e->type=lookup(e->text,e->span).type;break;
    case Expr::Unary:
      same(expr(e->args[0]),e->text=="!"?Type::Bool:Type::I64,e->span);e->type=e->args[0]->type;break;
    case Expr::Binary: {
      Type a=expr(e->args[0],expected),b=expr(e->args[1],a);same(b,a,e->span);
      const auto &op=e->text;
      if(op=="&&"||op=="||"){same(a,Type::Bool,e->span);e->type=Type::Bool;}
      else if(op=="=="||op=="!="){if(a==Type::Unit)throw Error("E_TYPE","cannot compare unit",e->span);e->type=Type::Bool;}
      else if(op=="+"&&(a==Type::Str||a.kind==Type::List))e->type=a;
      else {same(a,Type::I64,e->span);e->type=(op=="<"||op=="<="||op==">"||op==">=")?Type::Bool:Type::I64;}
      break;
    }
    case Expr::Call: {
      auto arity=[&](size_t count){if(e->args.size()!=count)throw Error("E_ARITY",e->text+" expects "+std::to_string(count)+" arguments",e->span);};
      if(e->text=="read_env"||e->text=="store_get"||e->text=="store_put"||e->text=="store_remove"||e->text=="store_keys"){
        arity(e->text=="store_put"?2:1);for(auto a:e->args)same(expr(a),Type::Str,a->span);
        if(f->realm!="server")throw Error("E_REALM",e->text+" requires a server function",e->span);
        std::string effect=e->text=="read_env"?"io":"db";if(!f->effects.contains(effect))throw Error("E_EFFECT",e->text+" requires declared effect "+effect,e->span);
        e->type=Type::result(e->text=="store_keys"?Type::list(Type::Str):e->text=="store_put"||e->text=="store_remove"?Type(Type::Bool):Type(Type::Str));break;
      }
      if(e->text=="ok"){
        arity(1);auto item=expr(e->args[0],expected.kind==Type::Result?*expected.element:Type());validType(item,e->span);e->type=Type::result(item);break;
      }
      if(e->text=="err"){
        arity(2);for(auto a:e->args)same(expr(a),Type::Str,a->span);
        auto item=e->annotation!=Type::Unknown?e->annotation:expected.kind==Type::Result?*expected.element:Type();
        if(item==Type::Unknown)throw Error("E_INFER","err requires result<T> context or err<T>(code, message)",e->span);
        validType(item,e->span);e->type=Type::result(item);break;
      }
      if(e->text=="is_ok"||e->text=="unwrap"||e->text=="error_code"||e->text=="error_message"){
        arity(1);auto item=expr(e->args[0]);if(item.kind!=Type::Result)throw Error("E_TYPE",e->text+" requires result<T>",e->span);
        e->type=e->text=="is_ok"?Type(Type::Bool):e->text=="unwrap"?*item.element:Type(Type::Str);break;
      }
      if(e->text=="encode_json"){
        arity(1);validType(expr(e->args[0]),e->span);e->type=Type::Str;break;
      }
      if(e->text=="decode_json"){
        arity(1);same(expr(e->args[0]),Type::Str,e->span);
        if(e->annotation==Type::Unknown)throw Error("E_INFER","decode_json requires an explicit type: decode_json<T>(text)",e->span);
        validType(e->annotation,e->span);e->type=Type::result(e->annotation);break;
      }
      if(p.hasStructure(e->text)) {
        const auto &s=p.structure(e->text);arity(s.fields.size());
        for(size_t i=0;i<e->args.size();++i)same(expr(e->args[i],s.fields[i].type),s.fields[i].type,e->args[i]->span);
        e->type=Type::record(s.name);break;
      }
      if(e->text=="len"||e->text=="str") {
        arity(1);auto t=expr(e->args[0]);
        if(e->text=="len"&&t!=Type::Str&&t.kind!=Type::List)throw Error("E_TYPE","len requires str or list",e->span);
        if(t==Type::Unit)throw Error("E_TYPE","cannot format unit",e->span);
        e->type=e->text=="len"?Type::I64:Type::Str;break;
      }
      if(e->text=="push"||e->text=="set") {
        arity(e->text=="push"?2:3);auto item=e->args.back();
        Type itemType=expr(item,expected.kind==Type::List?*expected.element:Type());
        auto list=expr(e->args[0],Type::list(itemType));
        if(list.kind!=Type::List)throw Error("E_TYPE",e->text+" requires a list",e->span);
        same(itemType,*list.element,e->span);if(e->text=="set")same(expr(e->args[1]),Type::I64,e->span);e->type=list;break;
      }
      if(e->text=="slice"||e->text=="contains") {
        arity(e->text=="slice"?3:2);same(expr(e->args[0]),Type::Str,e->span);
        for(size_t i=1;i<e->args.size();++i)same(expr(e->args[i]),e->text=="slice"?Type::I64:Type::Str,e->span);
        e->type=e->text=="slice"?Type::Str:Type::Bool;break;
      }
      if(e->text=="print"||e->text=="assert") {
        if(e->args.size()!=1)throw Error("E_ARITY",e->text+" expects one argument",e->span);
        auto t=expr(e->args[0]);
        if(e->text=="assert")same(t,Type::Bool,e->span);
        else {if(t==Type::Unit)throw Error("E_TYPE","cannot print unit",e->span);
          if(!f->effects.contains("io"))throw Error("E_EFFECT","print requires declared effect io",e->span);}
        e->type=Type::Unit;break;
      }
      const auto &callee=p.function(e->text,e->span);
      if(callee.test)throw Error("E_TEST","test functions cannot be called",e->span);
      if(callee.params.size()!=e->args.size())throw Error("E_ARITY","incorrect number of arguments to '"+e->text+"'",e->span);
      for(size_t j=0;j<e->args.size();++j)same(expr(e->args[j],callee.params[j].type),callee.params[j].type,e->args[j]->span);
      for(const auto &effect:callee.effects)if(!f->effects.contains(effect))throw Error("E_EFFECT","call requires declared effect "+effect,e->span);
      if(callee.realm!="shared" && callee.realm!=f->realm)throw Error("E_REALM","direct call from "+f->realm+" to "+callee.realm+" is forbidden",e->span);
      f->dependencies.insert(callee.name);e->type=callee.result;break;
    }
    }
    return e->type;
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
        same(expr(s->expr),Type::Bool,s->span);bool a=block(s->body),b=block(s->alternative);returns=a&&b;break;
      }
      case Stmt::While:same(expr(s->expr),Type::Bool,s->span);block(s->body);break;
      }
    }
    if(newScope)scopes.pop_back();return returns;
  }
public:
  explicit Checker(Program &p):p(p){}
  Type watch(const std::string &function,E expression,const std::map<std::string,Type> &locals){
    auto context=p.function(function);context.effects.clear();context.dependencies.clear();f=&context;scopes.emplace_back();
    for(const auto &[name,type]:locals){validType(type,expression->span);define(name,{type,false},expression->span);}
    return expr(expression);
  }
  void run() {
    std::set<std::string> names;
    const auto &builtins=builtinNames();
    for(const auto &s:p.structures){
      if(builtins.contains(s.localName.empty()?s.name:s.localName)||!names.insert(s.name).second)throw Error("E_DUPLICATE","duplicate or reserved structure '"+s.name+"'",s.span);
      std::set<std::string> fields;for(const auto &field:s.fields){if(!fields.insert(field.name).second)throw Error("E_DUPLICATE","duplicate field '"+field.name+"'",field.span);validType(field.type,field.span);}
    }
    for(const auto &fn:p.functions) {
      if(builtins.contains(fn.localName.empty()?fn.name:fn.localName)||!names.insert(fn.name).second)throw Error("E_DUPLICATE","duplicate or reserved function '"+fn.name+"'",fn.span);
      validType(fn.result,fn.span,true);
      for(const auto &effect:fn.effects)if(effect!="io"&&effect!="db")throw Error("E_EFFECT","unsupported effect '"+effect+"'",fn.span);
      if(fn.effects.contains("db")&&fn.realm!="server")throw Error("E_REALM","db effect requires a server function",fn.span);
      if(fn.test && (!fn.params.empty()||fn.result!=Type::Unit))throw Error("E_TEST","test must take no parameters and return unit",fn.span);
    }
    for(auto &fn:p.functions) {
      f=&fn;f->dependencies.clear();scopes.clear();scopes.emplace_back();
      for(const auto &param:fn.params){validType(param.type,param.span);define(param.name,{param.type,false},param.span);}
      if(!block(fn.body,false) && fn.result!=Type::Unit)throw Error("E_RETURN","not all paths return a value in '"+fn.name+"'",fn.span);
    }
    std::function<void(const Type&,Span)> publicType=[&](const Type &t,Span span){
      if(t.kind==Type::List||t.kind==Type::Result)publicType(*t.element,span);
      if(t.kind==Type::Record&&!p.structure(t.name).exported)throw Error("E_VISIBILITY","public API exposes private type '"+t.name+"'",span);
    };
    for(const auto &s:p.structures)if(s.exported)for(const auto &field:s.fields)publicType(field.type,field.span);
    for(const auto &fn:p.functions)if(fn.exported){publicType(fn.result,fn.span);for(const auto &param:fn.params)publicType(param.type,param.span);}
    std::set<std::string> operations,routes;
    auto apiWire=[&](const Type &type,Span span){
      auto schema=wireSchema(p,type);auto object=schema.getAsObject();auto records=object->getObject("records");size_t nodes=0;
      if(json(schema,false).size()>262144||records->size()>1024)throw Error("E_API_LIMIT","endpoint wire schema exceeds size/record limits",span);
      std::function<void(const llvm::json::Value&,unsigned)> descriptor=[&](const auto &value,unsigned depth){if(++nodes>10000||depth>64)throw Error("E_API_LIMIT","endpoint wire schema exceeds descriptor limits",span);if(auto object=value.getAsObject()){if(auto item=object->get("list"))descriptor(*item,depth+1);if(auto item=object->get("result"))descriptor(*item,depth+1);}};
      for(const auto &[name,fields]:*records){auto array=fields.getAsArray();if(array->size()>1024)throw Error("E_API_LIMIT","endpoint record exceeds field limit",span);for(const auto &field:*array)descriptor(*field.getAsObject()->get("type"),0);}
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
      if(handler.realm!="server"||handler.test||handler.params.empty()||handler.params.size()>2||handler.params[0].type!=Type::record("std::api::Context")||handler.result.kind!=Type::Result)throw Error("E_API_SIGNATURE","endpoint handler must be server fn(Context[, Input]) -> result<Output>",endpoint.span);
      if(endpoint.method=="GET"&&handler.params.size()!=1)throw Error("E_API_SIGNATURE","GET endpoints have context only; query/body input is not implicit",endpoint.span);
      const auto &context=p.structure("std::api::Context");
      if(context.fields.size()!=2||context.fields[0].name!="user"||context.fields[0].type!=Type::Str||context.fields[1].name!="request_id"||context.fields[1].type!=Type::Str)throw Error("E_API_SIGNATURE","incompatible std::api::Context",endpoint.span);
      publicType(handler.result,endpoint.span);
      if(handler.params.size()==2){publicType(handler.params[1].type,endpoint.span);apiWire(handler.params[1].type,endpoint.span);}
      apiWire(handler.result,endpoint.span);
    }
  }
};
llvm::json::Value exprJSON(E e) {
  if(!e)return nullptr;
  llvm::json::Array args;for(auto a:e->args)args.push_back(exprJSON(a));
  return llvm::json::Object{{"kind",int64_t(e->kind)},{"operator",e->text},{"value",e->number},{"type",typeName(e->type)},{"args",std::move(args)}};
}
llvm::json::Array blockJSON(const std::vector<S> &body) {
  llvm::json::Array out;
  for(auto s:body)out.push_back(llvm::json::Object{{"kind",int64_t(s->kind)},{"name",s->name},{"type",typeName(s->type)},{"expression",exprJSON(s->expr)},{"body",blockJSON(s->body)},{"else",blockJSON(s->alternative)}});
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
  return llvm::json::Object{{"format","nex.function/3"},{"name",f.name},{"owner",f.owner},{"public",f.exported},{"realm",f.realm},{"parameters",std::move(params)},{"result",typeName(f.result)},{"effects",std::move(effects)},{"test",f.test},{"body",blockJSON(f.body)}};
}
llvm::json::Value canonical(const Structure &s) {
  llvm::json::Array fields;for(const auto &f:s.fields)fields.push_back(llvm::json::Object{{"name",f.name},{"type",typeName(f.type)}});
  return llvm::json::Object{{"format","nex.structure/2"},{"name",s.name},{"owner",s.owner},{"public",s.exported},{"fields",std::move(fields)}};
}
llvm::json::Value canonical(const Endpoint &endpoint){
  return llvm::json::Object{{"format","nex.endpoint/1"},{"name",endpoint.name},{"method",endpoint.method},{"path",endpoint.path},{"success_status",endpoint.successStatus},{"handler",endpoint.target}};
}
std::string revision(const Program &p) {
  std::map<std::string,std::string> ordered;
  for(const auto &f:p.functions)ordered[f.name]=json(canonical(f),false);
  llvm::json::Object functions;for(const auto &[name,text]:ordered)functions[name]=text;
  llvm::json::Object structures;for(const auto &s:p.structures)structures[s.name]=canonical(s);
  llvm::json::Object modules;
  for(const auto &[key,unit]:p.units){std::set<std::string> targets;for(const auto &import:unit.imports)targets.insert(p.units.at(import.target).module);llvm::json::Array deps;for(const auto &target:targets)deps.push_back(target);modules[unit.module]=std::move(deps);}
  llvm::json::Object endpoints;for(const auto &endpoint:p.endpoints)endpoints[endpoint.name]=canonical(endpoint);
  return hash(json(llvm::json::Object{{"format","nex.program/4"},{"language",languageVersion},{"module",p.module},{"functions",std::move(functions)},{"structures",std::move(structures)},{"modules",std::move(modules)},{"endpoints",std::move(endpoints)}},false));
}
llvm::json::Value describe() {
  return llvm::json::Object{
    {"schema","nex.language/1"},{"version",languageVersion},
    {"types",llvm::json::Array{"i64","bool","unit","str","list<T>","result<T>","nominal structures"}},
    {"effects",llvm::json::Array{"io","db"}},
    {"realms",llvm::json::Array{"shared","client","server"}},
    {"features",llvm::json::Array{"functions","recursion","let","var","assignment","if","while","short_circuit","checked_i64","tests","unicode_strings","immutable_lists","structures","automatic_reference_counting","modules","imports","public_exports","source_bundles","dependency_locks","typescript_backend","web_ui","web_state_update_view","web_request_commands","web_request_cancellation","client_reachability","recoverable_results","typed_json","native_libraries","request_scopes","sqlite_storage","native_http","native_https","principal_storage","cooperative_request_cancellation"}},
    {"builtins",llvm::json::Array{"print(T) -> unit !{io}","assert(bool) -> unit","len(str|list<T>) -> i64","str(T) -> str","push(list<T>, T) -> list<T>","set(list<T>, i64, T) -> list<T>","slice(str, i64, i64) -> str","contains(str, str) -> bool","ok(T) -> result<T>","err<T>(str, str) -> result<T>","is_ok(result<T>) -> bool","unwrap(result<T>) -> T","error_code(result<T>) -> str","error_message(result<T>) -> str","encode_json(T) -> str","decode_json<T>(str) -> result<T>","read_env(str) -> result<str> !{io} [server]","store_get(str) -> result<str> !{db} [server]","store_put(str, str) -> result<bool> !{db} [server]","store_remove(str) -> result<bool> !{db} [server]","store_keys(str) -> result<list<str>> !{db} [server]"}},
    {"api_features",llvm::json::Array{"endpoint_declarations","api_generation","openapi_3_1","typed_request_validation","generated_client_helpers","generated_server_dispatch"}},
    {"debug_features",llvm::json::Array{"dwarf_parameters","dwarf_locals","lexical_scopes","bounded_value_previews","read_only_frame_json","lldb_dap_launch","checked_pure_expressions","exact_typed_frame_capture","isolated_expression_interpreter","nex_dap_watches","paged_computed_values","demand_driven_aggregate_reads"}},
    {"debug_guide","docs/debugging.md"},
    {"graph_features",llvm::json::Array{"persistent_operation_ids","typed_operation_tree","lexical_binding_edges","paged_operation_context","deterministic_operation_sites","history_preserving_operation_index"}},
    {"operation_guide","docs/operations.md"},{"operation_schema","llm/operations.schema.json"},{"operation_identity_policy","nex.operation-identity/1"},{"graph_database_schema",3},
    {"expression_guide","docs/expressions.md"},{"debug_frame_schema","llm/debug-frame.schema.json"},
    {"partial_debug_frame_schema","llm/debug-frame-v2.schema.json"},{"debug_frame_protocols",llvm::json::Array{"nex.debug-frame/1","nex.debug-frame/2"}},
    {"build_features",llvm::json::Array{"native_module_compilation","interface_type_invalidation","verified_native_object_cache","compilation_dependency_index"}},
    {"build_guide","docs/incremental.md"},
    {"profile_features",llvm::json::Array{"native_function_instrumentation","graph_attributed_wall_time","bounded_trace_events","managed_shallow_allocations","tracy_cpu_zones","tracy_named_memory_pools"}},
    {"profile_guide","docs/profiling.md"},
    {"verification_features",llvm::json::Array{"snapshot_bound_contracts","z3_checked_scalar_proofs","inductive_while_invariants","loop_termination_rankings","inlined_pure_calls","counterexample_models","replayable_smt_queries","explicit_unproven_status"}},
    {"verification_guide","docs/verification.md"},
    {"task_features",llvm::json::Array{"task_contracts","pinned_acceptance_intent","requirement_graph_linkage","multi_program_snapshots","acceptance_checks","checkpointed_receipts","task_input_replay","process_group_cleanup"}},
    {"task_guide","docs/tasks.md"},{"task_schema","llm/task.schema.json"},
    {"not_yet_supported",llvm::json::Array{"async","wasm","gpu","ffi_declarations","effect_handlers","mutable_collections","cyclic_module_imports","remote_package_registry"}},
    {"specification","docs/language.md"},{"grammar","docs/grammar.ebnf"},{"llm_prompt","llm/SYSTEM_PROMPT.md"},{"web_guide","docs/web.md"},{"server_guide","docs/server.md"},{"api_guide","docs/api.md"},
    {"discovery_commands",llvm::json::Array{"nex guide --kind prompt --json","nex guide --kind language --json","nex guide --kind grammar --json","nex guide --kind protocol --json","nex guide --kind web --json","nex guide --kind server --json","nex guide --kind api --json","nex api FILE --json"}}};
}
}
