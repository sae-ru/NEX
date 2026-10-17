#include "nex/language.h"
#include <algorithm>
#include <optional>

namespace nex {
void checkPattern(Program &program,P pattern,Type type,std::vector<Param> &bindings){
  pattern->type=type;std::vector<Type> children;
  auto fail=[&](const std::string &message){throw Error("E_MATCH_TYPE",message,pattern->span);};
  switch(pattern->kind){
  case Pattern::Binding:case Pattern::Wildcard:
    pattern->binding=bindings.size();bindings.push_back({pattern->kind==Pattern::Wildcard?"_":pattern->text,type,pattern->span});return;
  case Pattern::Integer:if(type!=Type::I64&&!satisfiesConstraint(program,type,"integer"))fail("integer pattern requires i64 or an integer-constrained parameter");return;
  case Pattern::Boolean:if(type!=Type::Bool)fail("boolean pattern requires bool");return;
  case Pattern::String:if(type!=Type::Str)fail("string pattern requires str");return;
  case Pattern::List:
    if(type.kind!=Type::List)fail("list pattern requires list<T>");children.assign(pattern->args.size(),*type.element);break;
  case Pattern::Constructor:
    if(type.kind==Type::Result){
      if(pattern->text=="ok"){pattern->ordinal=1;children={*type.element};}
      else if(pattern->text=="err"){pattern->ordinal=0;children={Type::Str,Type::Str};}
      else throw Error("E_MATCH_VARIANT","result patterns use ok(value) or err(code,message)",pattern->span);
    }else if(type.kind==Type::Record){
      const auto &expected=program.structure(type.name);
      if(expected.enumeration){
        const Structure *owner=nullptr;auto variant=program.variant(pattern->text,&owner);
        if(variant&&owner->name!=expected.name&&owner->name==expected.templateName){pattern->text=expected.name+"::"+variant->name;variant=program.variant(pattern->text,&owner);}
        if(!variant||owner->name!=expected.name)throw Error("E_MATCH_VARIANT","pattern is not a variant of "+type.name,pattern->span);
        pattern->ordinal=variant->ordinal;for(const auto &field:variant->fields)children.push_back(field.type);
      }else{
        if(pattern->text!=expected.name&&pattern->text!=expected.templateName)throw Error("E_MATCH_VARIANT","pattern is not the constructor of "+type.name,pattern->span);
        pattern->text=expected.name;for(const auto &field:expected.fields)children.push_back(field.type);
      }
    }else fail("constructor pattern requires its nominal type or result<T>");
    break;
  }
  if(children.size()!=pattern->args.size())throw Error("E_ARITY","pattern argument count differs from constructor payload",pattern->span);
  for(size_t i=0;i<children.size();++i)checkPattern(program,pattern->args[i],children[i],bindings);
}

namespace {
using Row=std::vector<P>;using Matrix=std::vector<Row>;
bool wildcard(P p){return p->kind==Pattern::Binding||p->kind==Pattern::Wildcard;}
P any(Type type){auto p=std::make_shared<Pattern>();p->type=type;return p;}
std::string key(P p){return std::to_string(p->kind)+":"+p->text+":"+std::to_string(p->kind==Pattern::List?int64_t(p->args.size()):p->number);}
std::optional<Row> constructors(const Program &program,Type type){
  Row values;auto add=[&](Pattern::Kind kind,std::string text,int64_t number,std::vector<Type> children){auto p=std::make_shared<Pattern>();p->kind=kind;p->text=std::move(text);p->number=number;p->type=type;for(auto child:children)p->args.push_back(any(child));values.push_back(std::move(p));};
  if(type==Type::Bool){add(Pattern::Boolean,"",0,{});add(Pattern::Boolean,"",1,{});}
  else if(type.kind==Type::Result){add(Pattern::Constructor,"ok",0,{*type.element});add(Pattern::Constructor,"err",0,{Type::Str,Type::Str});}
  else if(type.kind==Type::Record){const auto &record=program.structure(type.name);if(record.enumeration){for(const auto &variant:record.variants){std::vector<Type> fields;for(const auto &field:variant.fields)fields.push_back(field.type);add(Pattern::Constructor,record.name+"::"+variant.name,0,std::move(fields));}}else{std::vector<Type> fields;for(const auto &field:record.fields)fields.push_back(field.type);add(Pattern::Constructor,record.name,0,std::move(fields));}}
  else return std::nullopt;return values;
}
Matrix specialize(const Matrix &matrix,P constructor){
  Matrix result;for(const auto &row:matrix){Row next;
    if(wildcard(row[0])){for(auto child:constructor->args)next.push_back(any(child->type));}
    else if(key(row[0])==key(constructor))next=row[0]->args;
    else continue;
    next.insert(next.end(),row.begin()+1,row.end());result.push_back(std::move(next));}return result;
}
Matrix defaults(const Matrix &matrix){Matrix result;for(const auto &row:matrix)if(wildcard(row[0]))result.emplace_back(row.begin()+1,row.end());return result;}
// Constructor specialization plus default rows. Infinite scalar/list domains
// always have a value outside a finite set of literal/length constructors.
bool useful(const Program &program,Matrix matrix,Row query,std::vector<Type> types,uint64_t &budget,unsigned depth,Span span){
  if(!budget--||depth>128)throw Error("E_MATCH_LIMIT","pattern coverage exceeds its state/depth budget",span);
  while(!query.empty()&&!matrix.empty()&&wildcard(query[0])&&std::all_of(matrix.begin(),matrix.end(),[](const auto &row){return wildcard(row[0]);})){
    matrix=defaults(matrix);query.erase(query.begin());types.erase(types.begin());if(!budget--)throw Error("E_MATCH_LIMIT","pattern coverage exceeds its state budget",span);
  }
  if(matrix.empty())return true;if(query.empty())return false;
  if(!wildcard(query[0])){
    Row next=query[0]->args;next.insert(next.end(),query.begin()+1,query.end());std::vector<Type> remaining;for(auto child:query[0]->args)remaining.push_back(child->type);remaining.insert(remaining.end(),types.begin()+1,types.end());
    return useful(program,specialize(matrix,query[0]),std::move(next),std::move(remaining),budget,depth+1,span);
  }
  if(auto finite=constructors(program,types[0])){
    for(auto constructor:*finite){Row next;std::vector<Type> remaining;for(auto child:constructor->args){next.push_back(any(child->type));remaining.push_back(child->type);}next.insert(next.end(),query.begin()+1,query.end());remaining.insert(remaining.end(),types.begin()+1,types.end());
      if(useful(program,specialize(matrix,constructor),std::move(next),std::move(remaining),budget,depth+1,span))return true;}return false;
  }
  return useful(program,defaults(matrix),Row(query.begin()+1,query.end()),std::vector<Type>(types.begin()+1,types.end()),budget,depth+1,span);
}
}
void checkMatchCoverage(const Program &program,E expression){
  Matrix covered;uint64_t budget=100000;auto type=expression->args[0]->type;
  for(auto arm:expression->arms){if(!useful(program,covered,{arm->pattern},{type},budget,0,arm->span))throw Error("E_MATCH_DUPLICATE","pattern is unreachable after earlier unguarded arms",arm->span);if(!arm->guard)covered.push_back({arm->pattern});}
  if(useful(program,covered,{any(type)},{type},budget,0,expression->span))throw Error("E_MATCH_EXHAUSTIVE","match is not exhaustive; guards do not establish coverage",expression->span);
}
llvm::json::Value canonicalPattern(P p){
  llvm::json::Array children;for(auto child:p->args)children.push_back(canonicalPattern(child));
  return llvm::json::Object{{"kind",int64_t(p->kind)},{"text",p->text},{"number",p->number},{"ordinal",p->ordinal},{"type",typeName(p->type)},{"arguments",std::move(children)}};
}
}
