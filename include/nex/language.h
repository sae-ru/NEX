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

namespace nexrt { struct TaskExecutionLimits;struct SourceErrorPayload;struct Value; }

namespace nex {
inline constexpr const char *languageVersion = "0.28";
inline constexpr const char *taskCandidateLanguageVersion = "0.28";
inline constexpr const char *developmentLanguageVersion = "0.29";
// Append semantic versions: retained ordinal values and archived interpretation
// must never change when the public compiler default advances.
enum class SourceLanguage { Language018, Tasks019, TaskFiles020, OwnedResources021, TaskForeign022, TaskWrites023, TaskStreams024, SourceExceptions025Prototype, SourceExceptions025, ExceptionHandlers026, TypedErrors027, Contracts028, Contracts029 };
inline constexpr SourceLanguage currentSourceLanguage=SourceLanguage::Contracts028;
inline bool isContractsLanguage(SourceLanguage language){
  return language==SourceLanguage::Contracts028||language==SourceLanguage::Contracts029;
}
inline bool isTypedSourceErrorLanguage(SourceLanguage language){
  return language==SourceLanguage::TypedErrors027||isContractsLanguage(language);
}
// A shared typed packet ABI still retains the exact source version in records.
inline bool isTypedSourceErrorVersion(llvm::StringRef language){
  return language=="0.27"||language=="0.28"||language=="0.29";
}
inline bool isPublicSourceExceptionLanguage(SourceLanguage language){
  return language==SourceLanguage::SourceExceptions025||language==SourceLanguage::ExceptionHandlers026||isTypedSourceErrorLanguage(language);
}
using TypeBounds = std::vector<std::set<std::string>>;
struct Span { unsigned line = 1, column = 1; size_t begin = 0, end = 0; std::string file; };
// Exact lexical interval, separate from the diagnostic token in Span.
// Generated semantic nodes leave valid=false; ranges never affect identities.
struct SourceRange {size_t begin=0,end=0;bool valid=false;};
struct SourceToken {std::string text;Span span;bool identifier=false;};
struct Fix {
  size_t begin=0,end=0;std::string replacement,safety;
};
struct Error : std::runtime_error {
  std::string code, message, output, operationSite, operationId, operationRevision, operationSource; Span span;std::vector<Fix> fixes;
  llvm::json::Value frontend=nullptr;
  Error(std::string code, std::string message, Span span = {})
      : std::runtime_error(""), code(std::move(code)), message(std::move(message)), span(span) {}
  const char *what()const noexcept override{return message.c_str();}
};
// Explicitly raised source errors are separate from checked traps and request
// control. Private025 handlers must never catch Error, DataError or cancellation.
struct SourceException : std::exception {
  std::string code,message,output;Span span;
  std::shared_ptr<const nexrt::SourceErrorPayload> payload;
  SourceException(std::string code,std::string message,Span span,
      std::shared_ptr<const nexrt::SourceErrorPayload> payload={})
      :code(std::move(code)),message(std::move(message)),span(std::move(span)),payload(std::move(payload)){}
  const char *what()const noexcept override{return message.c_str();}
};
struct Type {
  enum Kind { I64, Bool, Unit, Unknown, Str, List, Record, Result, Parameter, Function, F64, Bytes, File, Constructor, Projection, Task, Channel, TaskScope } kind = Unknown;
  std::string name; std::shared_ptr<Type> element; std::vector<Type> arguments;
  unsigned constructorArity=0;
  std::string realm="shared";std::set<std::string> effects;
  Type() = default;
  Type(Kind kind) : kind(kind) {}
  static Type list(Type item) { Type t(List); t.element=std::make_shared<Type>(std::move(item)); return t; }
  static Type result(Type item) { Type t(Result); t.element=std::make_shared<Type>(std::move(item)); return t; }
  static Type task(Type item) { Type t(Task); t.element=std::make_shared<Type>(std::move(item)); return t; }
  static Type channel(Type item) { Type t(Channel); t.element=std::make_shared<Type>(std::move(item)); return t; }
  static Type record(std::string name) { Type t(Record); t.name=std::move(name); return t; }
  static Type constructor(std::string name,unsigned arity) { Type t(Constructor);t.name=std::move(name);t.constructorArity=arity;return t; }
  static Type function(std::vector<Type> parameters,Type result,std::string realm="shared",std::set<std::string> effects={}) {
    Type t(Function);t.arguments=std::move(parameters);t.element=std::make_shared<Type>(std::move(result));t.realm=std::move(realm);t.effects=std::move(effects);return t;
  }
  bool heap() const { return kind==Str||kind==List||kind==Record||kind==Result||kind==Function||kind==Bytes||kind==File||kind==Task||kind==Channel||kind==TaskScope; }
  bool operator==(const Type &other) const {
    return kind==other.kind && name==other.name && constructorArity==other.constructorArity && arguments==other.arguments && realm==other.realm && effects==other.effects && ((!element&&!other.element) || (element&&other.element&&*element==*other.element));
  }
};
std::string typeName(Type type);
// Only the current function body: nested lambdas have separate return boundaries.
struct Function;
bool propagatesResult(const Function &function);
bool usesParallelMap(const Function &function);
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
  enum Kind { Integer, Boolean, Name, Unary, Binary, Call, String, List, Field, Index, Match, Invoke, FunctionRef, Lambda, Floating, Propagate } kind;
  Span span;SourceRange sourceRange;unsigned syntaxHeight=1; std::string text; int64_t number = 0; Type type = Type::Unknown, annotation = Type::Unknown;
  std::string localName;std::shared_ptr<Function> lambda;
  std::vector<std::shared_ptr<Expr>> args;
  std::vector<Type> typeArguments;std::set<std::string> effectArguments;
  std::vector<Type> methodArguments;
  std::vector<Type> traitArguments;
  std::string traitContract,implementation;
  std::vector<std::shared_ptr<MatchArm>> arms;bool statementMatch=false;
  // Checked028 loop observations have their own pure, non-returning boundary.
  // Execution uses the ordinary expression; the marker participates in identity.
  bool contractPure=false;
};
using E = std::shared_ptr<Expr>;
// Independent syntax copy before module binding or generic specialization.
E cloneSourceExpression(E);
struct Stmt {
  enum Kind { Let, Var, Assign, Expression, Return, If, While, Match, Try, Throw, Finally, TypedThrow, TypedTry, CatchClause } kind;
  Span span;SourceRange sourceRange; std::string name; Type type = Type::Unknown; E expr;
  std::vector<std::shared_ptr<Stmt>> body, alternative;
  std::vector<std::shared_ptr<MatchArm>> arms;
  // Only Try uses this second immutable string binding. Empty on retained ASTs.
  std::string catchMessage;
  // Concrete checked027 payload identity; absent from all retained026 forms.
  std::string errorTypeKey;
};
using S = std::shared_ptr<Stmt>;
// A filtered handler may let the original source error escape. Literal true is
// total; every other predicate keeps an explicit outward throw effect.
inline bool totalSourceHandler(const S &statement){
  return !statement->expr||(statement->expr->kind==Expr::Boolean&&statement->expr->number!=0);
}
struct Param { std::string name; Type type; Span span; };
struct MatchArm { std::string variant; std::vector<Param> bindings; std::vector<S> body; Span span; int64_t ordinal=0;
  P pattern;unsigned guard=0,value=0;
};
template<class F> void childBlocks(const S &statement,F visit){visit(statement->body);visit(statement->alternative);for(const auto &arm:statement->arms)visit(arm->body);}
struct Variant { std::string name; std::vector<Param> fields; Span span; int64_t ordinal=0; };
struct Structure {
  std::string name; std::vector<Param> fields; Span span; bool exported=false; std::string owner,localName,unit;
  bool enumeration=false; std::vector<Variant> variants;
  bool opaqueResource=false;
  std::vector<std::string> typeParameters; std::vector<Type> typeArguments; std::string templateName;
  TypeBounds typeBounds;
  std::vector<unsigned> typeArities;
  std::vector<unsigned> typeParameterCodes;
  std::vector<std::vector<unsigned>> typeParameterSlots;
  std::vector<Type> typeDefaults;
  // Non-semantic physical name origin. In particular, the contextual word in
  // `server resource resource;` is not the declaration's identifier token.
  std::optional<Span> nameOrigin;
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
  // Original spelling, including aliases/parentheses. Derived source metadata;
  // it never participates in semantic identities or archived canonical ASTs.
  SourceRange resultTypeSource;
  // Physical clause interval, retained only for source projections.
  SourceRange sourceContractClauses;
  std::vector<S> body; Span span; bool test = false;
  bool exported=false; std::string owner,localName,unit;
  std::vector<std::string> typeParameters; std::vector<Type> typeArguments; std::string templateName; bool checked=false;
  TypeBounds typeBounds;
  std::vector<unsigned> typeArities;
  std::vector<unsigned> typeParameterCodes;
  std::vector<std::vector<unsigned>> typeParameterSlots;
  std::vector<Type> typeDefaults;
  std::string traitOwner;
  bool traitSignature=false;
  bool closure=false;std::string closureOwner;std::vector<Param> captures;
  // Set only by compiler-owned list/text-constructor lowering, never from source.
  bool compilerListBuilder=false;
  bool compilerTextBuilder=false;
  bool compilerBytesBuilder=false;
  std::optional<ForeignBinding> foreign;
  // Generated contract helpers have no editable physical declaration.
  std::string sourceContractOrigin;
  unsigned sourceRequires=0,sourceEnsures=0;
};
struct Import { std::string path,alias,target; Span span; };
struct Endpoint {
  std::string name,localName,owner,unit,method,path,target;
  int64_t successStatus=200; Span span;
};
struct SourceUnit { std::string key,module,source,path; std::vector<Import> imports; bool taskPrototype=false; SourceLanguage sourceLanguage=SourceLanguage::Language018; };
struct Trait {
  std::string name,localName,owner,unit;Span span;bool exported=false;
  unsigned selfArity=0;unsigned selfCode=0;
  std::vector<unsigned> selfSlots;
  std::map<std::string,std::set<std::string>> associated;
  std::vector<Function> methods;
};
struct ImplementationMethod {std::string target;std::vector<Type> typeArguments;Span span;};
struct Implementation {
  std::string name,localName,owner,unit,trait;Span span;bool exported=false;
  Type self;
  std::vector<std::string> typeParameters;TypeBounds typeBounds;std::vector<unsigned> typeArities;
  std::vector<unsigned> typeParameterCodes;std::vector<std::vector<unsigned>> typeParameterSlots;
  std::map<std::string,Type> associated;
  std::map<std::string,ImplementationMethod> methods;
};
// Opt-in editor projection of actual parsed names. Never serialized in semantic
// identities or included in Type equality. Targets are bound by the module loader.
struct EditorName {
  std::string kind,name,target;Span span;std::optional<Span> localTarget;
};
struct Program {
  std::string module, source, path;
  std::vector<Function> functions;
  std::vector<Structure> structures;
  std::vector<Import> imports;
  std::vector<Endpoint> endpoints;
  std::vector<Trait> traits;
  std::vector<Implementation> implementations;
  std::vector<EditorName> editorNames;
  bool traitsPrepared=false;
  // Task syntax/continuations are shared by public019/020 and guarded raw018
  // development frontend. sourceLanguage distinguishes their semantic identity.
  bool taskPrototype=false;
  SourceLanguage sourceLanguage=SourceLanguage::Language018;
  std::string entryUnit;
  std::map<std::string,SourceUnit> units;
  std::map<std::string,Function> functionTemplates;
  std::map<std::string,Structure> structureTemplates;
  std::map<std::string,std::set<std::string>> parameterBounds;
  std::map<std::string,unsigned> parameterKinds;
  std::map<std::string,unsigned> parameterCodes;
  std::map<std::string,std::vector<unsigned>> parameterSlotCodes;
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
// The checked program's semantic version, separate from the installed public
// compiler default. Historical programs retain their explicit identity.
const char *programLanguage(SourceLanguage language);
// Internal typed-error identity; requires a checked concrete type. No source
// syntax or language-version promotion is implied by this helper.
std::string sourceErrorTypeKey(const Program &,const Type &);
// Owned, key- and kind-checked binding shared by the source execution engines.
nexrt::Value checkedSourceErrorValue(const Program &,const SourceException &,const Type &,const std::string &,Span);
bool supportsSourceExceptions(const Program &);
const char *programLanguage(const Program &program);
Program parse(std::string source, std::string path,bool editorNames=false,bool editorDetails=false);
// Compiler-private frontend/reference experiment. Normal source/project parsing
// remains024; this identity cannot be loaded from a public project manifest.
Program parseSourceExceptionsPrototype(std::string source,std::string path);
// Separate compiler-private cooperative task/exception experiment.
Program parseSourceExceptionTasksPrototype(std::string source,std::string path);
// Select syntax and semantic identity before checking, never by retagging a
// program already checked under the public default.
Program parseVersioned(std::string source,std::string path,SourceLanguage language,
    bool editorNames=false,bool editorDetails=false);
Program parseLegacy018(std::string source,std::string path,
    bool editorNames=false,bool editorDetails=false);
E parseExpression(std::string source,std::string path,unsigned maxTokens=0);
E parseSourceExceptionWatchPrototype(std::string source,std::string path,unsigned maxTokens=0);
S parseStatement(std::string source,std::string path,unsigned maxTokens=0);
P parsePattern(std::string source,std::string path,unsigned maxTokens=0);
Type parseType(std::string source);
void bindExpression(const Program &program,const std::string &function,E expression);
Type checkExpression(Program &program,const std::string &function,E expression,const std::map<std::string,Type> &locals);
llvm::json::Value evaluateSourceExceptionWatchPrototype(const Program &,E,const std::map<std::string,Type> &,
    const llvm::json::Object &,uint64_t,const llvm::json::Array *captures=nullptr,bool demand=false,
    const std::set<std::string> *compiledCallables=nullptr);
// Check explicit physical-project version/format without opening its graph store.
SourceLanguage projectSourceLanguage(const std::string &root);
void validateProjectMetadata(const std::string &root,SourceLanguage language=currentSourceLanguage);
Program loadProgram(const std::string &entry,const std::string &root,bool enforceLock=true,
    const std::map<std::string,std::string> &overlays={},bool editorNames=false,bool editorDetails=false);
// Explicit compiler-owned source selection; never inferred from nex.json.
// Rechecks physical sources and matching locks without opening a graph Store.
Program loadVersionedProgram(const std::string &entry,const std::string &root,SourceLanguage language,
    bool enforceLock=true,const std::map<std::string,std::string> &overlays={},bool editorNames=false,bool editorDetails=false);
// Same lexer as the parser, for checked editor projections; no source identities.
std::vector<SourceToken> sourceTokens(const std::string &source,const std::string &file);
Program loadBundle(const llvm::json::Value &bundle,const std::string &root);
// Explicit versioned recheck; no physical manifest relabel or auto-detection.
//018 uses the retained legacy parser;019/020 keep their own semantic checks.
Program loadVersionedBundle(const llvm::json::Value &bundle,const std::string &root,
    const std::string &language);
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
Function &instantiateFunction(Program &program,const Function &source,const std::vector<Type> &arguments,Span span,const std::map<std::string,std::set<std::string>> &effectArguments={});
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
const std::set<std::string> &builtinNames(bool tasks=true,bool resources=false);
const std::set<std::string> &externalResourceBuiltins();
bool supportsExternalResources(const Program &program);
bool isExternalResource(const Program &program,const Type &type);
bool containsExternalResource(const Program &program,const Type &type);
bool containsNonTaskResource(const Program &program,const Type &type);
std::pair<std::string,std::string> sourceResourceClass(const Program &program,const Structure &declaration);
const std::set<std::string> &streamFileBuiltins();
bool containsFile(const Program &program,const Type &type);
llvm::json::Value wireSchema(const Program &program,const Type &type);
llvm::json::Value foreignSignature(const Program &program,const Function &function);
llvm::json::Value foreignBinding(const Program &program,const Function &function);
struct Evaluation { llvm::json::Value value = nullptr; std::string output; uint64_t steps = 0; };
Evaluation evaluate(const Program &program, const std::string &entry = "main",
                    uint64_t stepLimit = 1000000,
                    const nexrt::TaskExecutionLimits *taskLimits = nullptr);
// Typed wire values are decoded lazily, preserving short-circuit behavior when
// a referenced stopped-frame value is unavailable. No target process is called.
llvm::json::Value evaluateExpression(const Program &program,E expression,const std::map<std::string,Type> &types,
  const llvm::json::Object &values,uint64_t stepLimit=100000,const llvm::json::Array *captures=nullptr,bool demand=false,const std::set<std::string> *compiledCallables=nullptr);
std::string readFile(const std::string &path);
void writeFile(const std::string &path, const std::string &text);
void copyFile(const std::string &source, const std::string &destination, bool overwrite = false);
std::string resourceFile(const std::string &relative);
}
