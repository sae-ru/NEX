#pragma once
#include <cstdint>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include "llvm/Support/JSON.h"

namespace nex {
inline constexpr const char *languageVersion = "0.16";
using TypeBounds = std::vector<std::set<std::string>>;
struct Span { unsigned line = 1, column = 1; size_t begin = 0, end = 0; std::string file; };
// Exact lexical interval, separate from the diagnostic token in Span.
// Generated semantic nodes leave valid=false; ranges never affect identities.
struct SourceRange {size_t begin=0,end=0;bool valid=false;};
struct SourceToken {std::string text;Span span;bool identifier=false;};
struct Error : std::runtime_error {
  std::string code, output, operationSite, operationId, operationRevision, operationSource; Span span;
  llvm::json::Value frontend=nullptr;
  Error(std::string code, std::string message, Span span = {})
      : std::runtime_error(std::move(message)), code(std::move(code)), span(span) {}
};
struct Type {
  enum Kind { I64, Bool, Unit, Unknown, Str, List, Record, Result, Parameter, Function, F64, Bytes, File, Constructor, Projection } kind = Unknown;
  std::string name; std::shared_ptr<Type> element; std::vector<Type> arguments;
  unsigned constructorArity=0;
  std::string realm="shared";std::set<std::string> effects;
  Type() = default;
  Type(Kind kind) : kind(kind) {}
  static Type list(Type item) { Type t(List); t.element=std::make_shared<Type>(std::move(item)); return t; }
  static Type result(Type item) { Type t(Result); t.element=std::make_shared<Type>(std::move(item)); return t; }
  static Type record(std::string name) { Type t(Record); t.name=std::move(name); return t; }
  static Type constructor(std::string name,unsigned arity) { Type t(Constructor);t.name=std::move(name);t.constructorArity=arity;return t; }
  static Type function(std::vector<Type> parameters,Type result,std::string realm="shared",std::set<std::string> effects={}) {
    Type t(Function);t.arguments=std::move(parameters);t.element=std::make_shared<Type>(std::move(result));t.realm=std::move(realm);t.effects=std::move(effects);return t;
  }
  bool heap() const { return kind==Str||kind==List||kind==Record||kind==Result||kind==Function||kind==Bytes||kind==File; }
  bool operator==(const Type &other) const {
    return kind==other.kind && name==other.name && constructorArity==other.constructorArity && arguments==other.arguments && realm==other.realm && effects==other.effects && ((!element&&!other.element) || (element&&other.element&&*element==*other.element));
  }
};
std::string typeName(Type type);
std::string floatLiteral(int64_t bits);
struct Pattern;
using P = std::shared_ptr<Pattern>;
struct Pattern {
  enum Kind { Binding, Wildcard, Constructor, Integer, Boolean, String, List } kind=Wildcard;
  Span span;SourceRange sourceRange;std::string text;int64_t number=0,ordinal=0;Type type;
  size_t binding=0;std::vector<P> args;
};
template<class F> void visitPattern(P pattern,F visit){visit(pattern);for(auto child:pattern->args)visitPattern(child,visit);}
struct MatchArm;
struct Function;
struct Expr {
  enum Kind { Integer, Boolean, Name, Unary, Binary, Call, String, List, Field, Index, Match, Invoke, FunctionRef, Lambda, Floating } kind;
  Span span;SourceRange sourceRange;unsigned syntaxHeight=1; std::string text; int64_t number = 0; Type type = Type::Unknown, annotation = Type::Unknown;
  std::string localName;std::shared_ptr<Function> lambda;
  std::vector<std::shared_ptr<Expr>> args;
  std::vector<Type> typeArguments;
  std::vector<Type> methodArguments;
  std::vector<Type> traitArguments;
  std::string traitContract,implementation;
  std::vector<std::shared_ptr<MatchArm>> arms;bool statementMatch=false;
};
using E = std::shared_ptr<Expr>;
struct Stmt {
  enum Kind { Let, Var, Assign, Expression, Return, If, While, Match } kind;
  Span span;SourceRange sourceRange; std::string name; Type type = Type::Unknown; E expr;
  std::vector<std::shared_ptr<Stmt>> body, alternative;
  std::vector<std::shared_ptr<MatchArm>> arms;
};
using S = std::shared_ptr<Stmt>;
struct Param { std::string name; Type type; Span span; };
struct MatchArm { std::string variant; std::vector<Param> bindings; std::vector<S> body; Span span; int64_t ordinal=0;
  P pattern;unsigned guard=0,value=0;
};
template<class F> void childBlocks(const S &statement,F visit){visit(statement->body);visit(statement->alternative);for(const auto &arm:statement->arms)visit(arm->body);}
struct Variant { std::string name; std::vector<Param> fields; Span span; int64_t ordinal=0; };
struct Structure {
  std::string name; std::vector<Param> fields; Span span; bool exported=false; std::string owner,localName,unit;
  bool enumeration=false; std::vector<Variant> variants;
  std::vector<std::string> typeParameters; std::vector<Type> typeArguments; std::string templateName;
  TypeBounds typeBounds;
  std::vector<unsigned> typeArities;
  std::vector<Param*> members(){std::vector<Param*> result;for(auto &f:fields)result.push_back(&f);for(auto &v:variants)for(auto &f:v.fields)result.push_back(&f);return result;}
  std::vector<const Param*> members()const{std::vector<const Param*> result;for(const auto &f:fields)result.push_back(&f);for(const auto &v:variants)for(const auto &f:v.fields)result.push_back(&f);return result;}
};
struct ForeignBinding {
  std::string library,symbol,manifest;
  // Non-semantic token location for checked packaging projections. The pin
  // remains part of canonical identity; this span is not serialized there.
  Span manifestSpan;
};
struct Function {
  std::string name, realm = "shared"; std::vector<Param> params;
  Type result = Type::Unit; std::set<std::string> effects, dependencies;
  std::vector<S> body; Span span; bool test = false;
  bool exported=false; std::string owner,localName,unit;
  std::vector<std::string> typeParameters; std::vector<Type> typeArguments; std::string templateName; bool checked=false;
  TypeBounds typeBounds;
  std::vector<unsigned> typeArities;
  std::string traitOwner;
  bool traitSignature=false;
  bool closure=false;std::string closureOwner;std::vector<Param> captures;
  std::optional<ForeignBinding> foreign;
};
struct Import { std::string path,alias,target; Span span; };
struct Endpoint {
  std::string name,localName,owner,unit,method,path,target;
  int64_t successStatus=200; Span span;
};
struct SourceUnit { std::string key,module,source,path; std::vector<Import> imports; };
struct Trait {
  std::string name,localName,owner,unit;Span span;bool exported=false;
  unsigned selfArity=0;
  std::map<std::string,std::set<std::string>> associated;
  std::vector<Function> methods;
};
struct ImplementationMethod {std::string target;std::vector<Type> typeArguments;Span span;};
struct Implementation {
  std::string name,localName,owner,unit,trait;Span span;bool exported=false;
  Type self;
  std::vector<std::string> typeParameters;TypeBounds typeBounds;std::vector<unsigned> typeArities;
  std::map<std::string,Type> associated;
  std::map<std::string,ImplementationMethod> methods;
};
struct Program {
  std::string module, source, path;
  std::vector<Function> functions;
  std::vector<Structure> structures;
  std::vector<Import> imports;
  std::vector<Endpoint> endpoints;
  std::vector<Trait> traits;
  std::vector<Implementation> implementations;
  bool traitsPrepared=false;
  std::string entryUnit;
  std::map<std::string,SourceUnit> units;
  std::map<std::string,Function> functionTemplates;
  std::map<std::string,Structure> structureTemplates;
  std::map<std::string,std::set<std::string>> parameterBounds;
  std::map<std::string,unsigned> parameterKinds;
  const Function &function(const std::string &name,Span span={}) const;
  const Structure &structure(const std::string &name) const;
  bool hasStructure(const std::string &name) const;
  const Variant *variant(const std::string &name,const Structure **owner=nullptr) const;
  std::string definition(const Function &function) const;
  std::string definition(const Structure &structure) const;
  std::string definition(const Endpoint &endpoint) const;
  std::string definition(const Trait &trait) const;
  std::string definition(const Implementation &implementation) const;
  std::string location(const Span &span) const;
};
Program parse(std::string source, std::string path);
E parseExpression(std::string source,std::string path,unsigned maxTokens=0);
S parseStatement(std::string source,std::string path,unsigned maxTokens=0);
P parsePattern(std::string source,std::string path,unsigned maxTokens=0);
Type parseType(std::string source);
void bindExpression(const Program &program,const std::string &function,E expression);
Type checkExpression(Program &program,const std::string &function,E expression,const std::map<std::string,Type> &locals);
// Check explicit physical-project version/format without opening its graph store.
void validateProjectMetadata(const std::string &root);
Program loadProgram(const std::string &entry,const std::string &root,bool enforceLock=true,
    const std::map<std::string,std::string> &overlays={});
// Same lexer as the parser, for checked editor projections; no source identities.
std::vector<SourceToken> sourceTokens(const std::string &source,const std::string &file);
Program loadBundle(const llvm::json::Value &bundle,const std::string &root);
// Binding-only source syntax for reference projection. Never pass it to a
// backend: separately check both the original and projected source bundles.
Program bindBundle(const llvm::json::Value &bundle,const std::string &root);
llvm::json::Value sourceBundle(const Program &program);
llvm::json::Value dependencyLock(const Program &program);
void exportProject(const llvm::json::Value &bundle,const std::string &directory,const std::string &language);
std::string nativeSymbol(const std::string &name);
void prepareGenerics(Program &program);
bool satisfiesConstraint(const Program &program,const Type &type,const std::string &constraint);
void checkPattern(Program &program,P pattern,Type type,std::vector<Param> &bindings);
void checkMatchCoverage(const Program &program,E expression);
llvm::json::Value canonicalPattern(P pattern);
llvm::json::Value canonicalBounds(const std::vector<std::string> &parameters,const TypeBounds &bounds);
Type substituteType(Type type,const std::map<std::string,Type> &arguments);
Type resolveType(Program &program,Type type,Span span={},unsigned depth=0);
Function &instantiateFunction(Program &program,const Function &source,const std::vector<Type> &arguments,Span span);
std::string genericName(const std::string &name,const std::vector<Type> &arguments);
bool containsParameter(const Type &type);
void check(Program &program);
llvm::json::Value canonical(const Function &function);
llvm::json::Value canonical(const Structure &structure);
llvm::json::Value canonical(const Endpoint &endpoint);
llvm::json::Value canonical(const Trait &trait);
llvm::json::Value canonical(const Implementation &implementation);
std::string json(const llvm::json::Value &value, bool pretty = true);
std::string hash(const std::string &text);
std::string revision(const Program &program);
llvm::json::Value describe();
const std::set<std::string> &builtinNames();
const std::set<std::string> &streamFileBuiltins();
bool containsFile(const Program &program,const Type &type);
llvm::json::Value wireSchema(const Program &program,const Type &type);
llvm::json::Value foreignSignature(const Program &program,const Function &function);
llvm::json::Value foreignBinding(const Program &program,const Function &function);
struct Evaluation { llvm::json::Value value = nullptr; std::string output; uint64_t steps = 0; };
Evaluation evaluate(const Program &program, const std::string &entry = "main",
                    uint64_t stepLimit = 1000000);
// Typed wire values are decoded lazily, preserving short-circuit behavior when
// a referenced stopped-frame value is unavailable. No target process is called.
llvm::json::Value evaluateExpression(const Program &program,E expression,const std::map<std::string,Type> &types,
  const llvm::json::Object &values,uint64_t stepLimit=100000,const llvm::json::Array *captures=nullptr,bool demand=false,const std::set<std::string> *compiledCallables=nullptr);
std::string readFile(const std::string &path);
void writeFile(const std::string &path, const std::string &text);
void copyFile(const std::string &source, const std::string &destination, bool overwrite = false);
std::string resourceFile(const std::string &relative);
}
