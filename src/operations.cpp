#include "nex/operations.h"
#include <functional>
#include <algorithm>

namespace nex {
namespace {
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
const char *exprKinds[]={"integer","boolean","name","unary","binary","call","string","list","field","index","match"};
const char *stmtKinds[]={"let","var","assign","expression","return","if","while","match"};
class Tree {
  const Program &p;const Function &f;std::vector<Operation> nodes;
  std::vector<std::map<std::string,std::string>> scopes;
  size_t add(std::string path,std::string parent,std::string role,unsigned ordinal,std::string kind,std::string anchor,Span span,JSON definition,const void *ast=nullptr){
    if(nodes.size()>=100000||std::count(path.begin(),path.end(),'/')>512)throw Error("E_GRAPH_LIMIT","function operation graph exceeds its node/depth budget",span);
    Operation op;op.path=std::move(path);op.parent=std::move(parent);op.role=std::move(role);op.ordinal=ordinal;op.kind=std::move(kind);op.anchor=std::move(anchor);op.span=std::move(span);op.definition=std::move(definition);op.ast=ast;nodes.push_back(std::move(op));return nodes.size()-1;
  }
  std::string binding(const std::string &name){for(auto i=scopes.rbegin();i!=scopes.rend();++i)if(i->contains(name))return i->at(name);throw Error("E_INTERNAL","checked operation binding is missing: "+name);}
  void arms(E e,const std::string &key){
    for(size_t i=0;i<e->arms.size();++i){auto arm=e->arms[i];bool legacy=arm->pattern->kind==Pattern::Constructor&&arm->pattern->type.kind==Type::Record&&p.structure(arm->pattern->type.name).enumeration&&!arm->guard&&std::all_of(arm->pattern->args.begin(),arm->pattern->args.end(),[](P p){return p->kind==Pattern::Binding||p->kind==Pattern::Wildcard;})&&std::count_if(e->arms.begin(),e->arms.end(),[&](auto other){return other->variant==arm->variant;})==1;
      auto parent=key+"/case/"+(legacy?arm->variant:"arm-"+std::to_string(i));
      add(parent,key,"case",legacy?arm->ordinal:i,"pattern.case",arm->variant,arm->span,legacy?JSON(Object{{"kind","pattern.case"},{"variant",arm->variant},{"number",std::to_string(arm->ordinal)}}):JSON(Object{{"kind","pattern.case"},{"pattern",canonicalPattern(arm->pattern)}}),arm.get());
      scopes.emplace_back();
      auto binding=[&](P pattern,const std::string &path,const std::string &owner,unsigned ordinal){const auto &b=arm->bindings.at(pattern->binding);auto kind=b.name=="_"?"pattern.discard":"pattern.binding";add(path,owner,"parameter",ordinal,kind,b.name,b.span,Object{{"kind",kind},{"name",b.name},{"type",typeName(b.type)}},&b);if(b.name!="_")scopes.back()[b.name]=path;};
      if(legacy){for(unsigned j=0;j<arm->pattern->args.size();++j)binding(arm->pattern->args[j],parent+"/parameter/"+std::to_string(j),parent,j);}
      else {std::function<void(P,const std::string&,unsigned)> visit=[&](P pattern,const std::string &owner,unsigned ordinal){auto path=owner+"/pattern/"+std::to_string(ordinal);if(pattern->kind==Pattern::Binding||pattern->kind==Pattern::Wildcard)binding(pattern,path,owner,ordinal);else{add(path,owner,"pattern",ordinal,"pattern.test",pattern->text,pattern->span,canonicalPattern(pattern),pattern.get());for(unsigned j=0;j<pattern->args.size();++j)visit(pattern->args[j],path,j);}};visit(arm->pattern,parent,0);}
      if(arm->guard)expression(e->args[arm->guard],parent,"guard",0);
      if(e->statementMatch)block(arm->body,parent,"body",arm->span,false);else expression(e->args[arm->value],parent,"value",0);
      scopes.pop_back();
    }
  }
  void expression(E e,const std::string &parent,const std::string &role,unsigned ordinal){
    if(!e)return;auto path=parent+"/"+role+"/"+std::to_string(ordinal),kind=std::string("expression.")+exprKinds[e->kind];
    Object definition{{"kind",kind},{"type",typeName(e->type)},{"text",e->text},{"number",std::to_string(e->number)}};
    auto index=add(path,parent,role,ordinal,kind,kind,e->span,std::move(definition),e.get());
    if(e->kind==Expr::Name)nodes[index].binding=binding(e->text);
    if(e->kind==Expr::Call&&!builtinNames().contains(e->text)&&!p.hasStructure(e->text)&&!p.variant(e->text))nodes[index].callee=p.function(e->text).name;
    if(e->kind==Expr::Match){expression(e->args[0],path,"argument",0);arms(e,path);}
    else for(unsigned i=0;i<e->args.size();++i)expression(e->args[i],path,"argument",i);
  }
  void block(const std::vector<S> &body,const std::string &parent,const std::string &role,Span span,bool scoped){
    auto path=parent.empty()?role:parent+"/"+role;
    add(path,parent,role,0,"block","block",span,Object{{"kind","block"}});
    if(scoped)scopes.emplace_back();
    for(unsigned i=0;i<body.size();++i){
      auto s=body[i];auto key=path+"/statement/"+std::to_string(i),kind=std::string("statement.")+stmtKinds[s->kind];
      auto anchor=kind+":"+s->name;if(s->kind==Stmt::Expression&&s->expr&&s->expr->kind==Expr::Call)anchor+=":"+s->expr->text;
      auto index=add(key,path,"statement",i,kind,anchor,s->span,Object{{"kind",kind},{"name",s->name},{"type",typeName(s->type)}},s.get());
      if(s->kind==Stmt::Assign)nodes[index].binding=binding(s->name);
      expression(s->kind==Stmt::Match?s->expr->args[0]:s->expr,key,"expression",0);
      if(s->kind==Stmt::Let||s->kind==Stmt::Var)scopes.back()[s->name]=key;
      if(s->kind==Stmt::Match)arms(s->expr,key);
      if(s->kind==Stmt::If||s->kind==Stmt::While)block(s->body,key,"body",s->span,true);
      if(s->kind==Stmt::If)block(s->alternative,key,"else",s->span,true);
    }
    if(scoped)scopes.pop_back();
  }
public:
  Tree(const Program &p,const Function &f):p(p),f(f){}
  std::vector<Operation> run(){
    scopes.emplace_back();
    for(unsigned i=0;i<f.params.size();++i){const auto &param=f.params[i];auto path="parameter/"+std::to_string(i);add(path,"","parameter",i,"parameter",param.name,param.span,Object{{"kind","parameter"},{"name",param.name},{"type",typeName(param.type)}});scopes.back()[param.name]=path;}
    block(f.body,"","body",f.span,false);
    std::map<std::string,Array> children;auto functionHash=hash(json(canonical(f),false));
    for(auto i=nodes.rbegin();i!=nodes.rend();++i){std::reverse(children[i->path].begin(),children[i->path].end());i->content=hash(json(Object{{"format","nex.operation-content/1"},{"definition",i->definition},{"children",std::move(children[i->path])}},false));i->site=hash("nex.operation-site/1\n"+functionHash+"\n"+i->path);
      children[i->parent].push_back(Object{{"role",i->role},{"ordinal",int64_t(i->ordinal)},{"hash",i->content}});
    }
    return std::move(nodes);
  }
};
}
std::vector<Operation> operationTree(const Program &p,const Function &f){return Tree(p,f).run();}
Array operationSites(const Program &p,const Function &f){
  Array a;for(const auto &o:operationTree(p,f))a.push_back(Object{{"site",o.site},{"path",o.path},{"parent",o.parent},{"kind",o.kind},{"file",f.unit},{"line",int64_t(o.span.line)},{"column",int64_t(o.span.column)}});
  return a;
}
std::map<std::string,std::string> matchOperations(const std::vector<Operation> &current,const std::vector<Operation> &previous,const std::map<std::string,std::string> &ids){
  std::map<std::string,std::vector<const Operation*>> a,b;for(const auto &o:current)a[o.parent].push_back(&o);for(const auto &o:previous)b[o.parent].push_back(&o);
  std::map<std::string,std::string> result;
  std::function<void(const std::string&,const std::string&,bool)> match=[&](const auto &parent,const auto &oldParent,bool identical){
    std::map<const Operation*,const Operation*> pairs;std::set<const Operation*> used;
    auto pair=[&](const Operation *x,const Operation *y){if(x->kind==y->kind&&!pairs.contains(x)&&used.insert(y).second)pairs[x]=y;};
    std::map<std::pair<std::string,unsigned>,const Operation*> positions;for(auto y:b[oldParent])positions[{y->role,y->ordinal}]=y;
    for(auto x:a[parent])if(x->role!="parameter"&&x->role!="case"&&(x->role!="statement"||identical)){auto y=positions.find({x->role,x->ordinal});if(y!=positions.end())pair(x,y->second);}
    auto unique=[&](const std::string &role,bool content){
      std::map<std::string,std::vector<const Operation*>> left,right;
      for(auto x:a[parent])if(x->role==role&&!pairs.contains(x))left[x->kind+":"+(content?x->content:x->anchor)].push_back(x);
      for(auto y:b[oldParent])if(y->role==role&&!used.contains(y))right[y->kind+":"+(content?y->content:y->anchor)].push_back(y);
      for(const auto &[key,group]:left)if(group.size()==1&&right[key].size()==1)pair(group[0],right[key][0]);
    };
    unique("parameter",false);unique("case",false);
    if(!identical){unique("statement",true);unique("statement",false);}
    for(const auto &[x,y]:pairs){auto id=ids.find(y->path);if(id==ids.end())continue;result[x->path]=id->second;match(x->path,y->path,x->content==y->content);}
  };
  match("","",false);return result;
}
}
