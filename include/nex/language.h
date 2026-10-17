#pragma once
#include <cstdint>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include "llvm/Support/JSON.h"

namespace nex {
inline constexpr const char *languageVersion = "0.5";
struct Span { unsigned line = 1, column = 1; size_t begin = 0, end = 0; std::string file; };
struct Error : std::runtime_error {
  std::string code, output; Span span;
  Error(std::string code, std::string message, Span span = {})
      : std::runtime_error(std::move(message)), code(std::move(code)), span(span) {}
};
struct Type {
  enum Kind { I64, Bool, Unit, Unknown, Str, List, Record, Result } kind = Unknown;
  std::string name; std::shared_ptr<Type> element;
  Type() = default;
  Type(Kind kind) : kind(kind) {}
  static Type list(Type item) { Type t(List); t.element=std::make_shared<Type>(std::move(item)); return t; }
  static Type result(Type item) { Type t(Result); t.element=std::make_shared<Type>(std::move(item)); return t; }
  static Type record(std::string name) { Type t(Record); t.name=std::move(name); return t; }
  bool heap() const { return kind==Str||kind==List||kind==Record||kind==Result; }
  bool operator==(const Type &other) const {
    return kind==other.kind && name==other.name && ((!element&&!other.element) || (element&&other.element&&*element==*other.element));
  }
};
std::string typeName(Type type);
struct Expr {
  enum Kind { Integer, Boolean, Name, Unary, Binary, Call, String, List, Field, Index } kind;
  Span span; std::string text; int64_t number = 0; Type type = Type::Unknown, annotation = Type::Unknown;
  std::vector<std::shared_ptr<Expr>> args;
};
using E = std::shared_ptr<Expr>;
struct Stmt {
  enum Kind { Let, Var, Assign, Expression, Return, If, While } kind;
  Span span; std::string name; Type type = Type::Unknown; E expr;
  std::vector<std::shared_ptr<Stmt>> body, alternative;
};
using S = std::shared_ptr<Stmt>;
struct Param { std::string name; Type type; Span span; };
struct Structure { std::string name; std::vector<Param> fields; Span span; bool exported=false; std::string owner,localName,unit; };
struct Function {
  std::string name, realm = "shared"; std::vector<Param> params;
  Type result = Type::Unit; std::set<std::string> effects, dependencies;
  std::vector<S> body; Span span; bool test = false;
  bool exported=false; std::string owner,localName,unit;
};
struct Import { std::string path,alias,target; Span span; };
struct Endpoint {
  std::string name,localName,owner,unit,method,path,target;
  int64_t successStatus=200; Span span;
};
struct SourceUnit { std::string key,module,source,path; std::vector<Import> imports; };
struct Program {
  std::string module, source, path;
  std::vector<Function> functions;
  std::vector<Structure> structures;
  std::vector<Import> imports;
  std::vector<Endpoint> endpoints;
  std::string entryUnit;
  std::map<std::string,SourceUnit> units;
  const Function &function(const std::string &name,Span span={}) const;
  const Structure &structure(const std::string &name) const;
  bool hasStructure(const std::string &name) const;
  std::string definition(const Function &function) const;
  std::string definition(const Structure &structure) const;
  std::string definition(const Endpoint &endpoint) const;
  std::string location(const Span &span) const;
};
Program parse(std::string source, std::string path);
E parseExpression(std::string source,std::string path,unsigned maxTokens=0);
Type parseType(std::string source);
void bindExpression(const Program &program,const std::string &function,E expression);
Type checkExpression(Program &program,const std::string &function,E expression,const std::map<std::string,Type> &locals);
Program loadProgram(const std::string &entry,const std::string &root,bool enforceLock=true);
Program loadBundle(const llvm::json::Value &bundle,const std::string &root);
llvm::json::Value sourceBundle(const Program &program);
llvm::json::Value dependencyLock(const Program &program);
void exportProject(const llvm::json::Value &bundle,const std::string &directory,const std::string &language);
std::string nativeSymbol(const std::string &name);
void check(Program &program);
llvm::json::Value canonical(const Function &function);
llvm::json::Value canonical(const Structure &structure);
llvm::json::Value canonical(const Endpoint &endpoint);
std::string json(const llvm::json::Value &value, bool pretty = true);
std::string hash(const std::string &text);
std::string revision(const Program &program);
llvm::json::Value describe();
const std::set<std::string> &builtinNames();
llvm::json::Value wireSchema(const Program &program,const Type &type);
struct Evaluation { llvm::json::Value value = nullptr; std::string output; uint64_t steps = 0; };
Evaluation evaluate(const Program &program, const std::string &entry = "main",
                    uint64_t stepLimit = 1000000);
// Typed wire values are decoded lazily, preserving short-circuit behavior when
// a referenced stopped-frame value is unavailable. No target process is called.
llvm::json::Value evaluateExpression(const Program &program,E expression,const std::map<std::string,Type> &types,
  const llvm::json::Object &values,uint64_t stepLimit=100000,const llvm::json::Array *captures=nullptr,bool demand=false);
std::string readFile(const std::string &path);
void writeFile(const std::string &path, const std::string &text);
std::string resourceFile(const std::string &relative);
}
