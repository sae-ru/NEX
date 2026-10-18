#include "nex/operation_store.h"
#include <sqlite3.h>
#include <random>
#include "llvm/Support/Error.h"
namespace nex {
namespace {
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
struct Query {
  sqlite3 *db;sqlite3_stmt *stmt=nullptr;
  Query(sqlite3 *db,const char *sql):db(db){if(sqlite3_prepare_v2(db,sql,-1,&stmt,nullptr)!=SQLITE_OK)throw Error("E_STORE",sqlite3_errmsg(db));}
  ~Query(){sqlite3_finalize(stmt);}
  void bind(int index,const std::string &text){if(sqlite3_bind_text(stmt,index,text.data(),int(text.size()),SQLITE_TRANSIENT)!=SQLITE_OK)throw Error("E_STORE",sqlite3_errmsg(db));}
  bool row(){int code=sqlite3_step(stmt);if(code==SQLITE_ROW)return true;if(code==SQLITE_DONE)return false;throw Error("E_STORE",sqlite3_errmsg(db));}
  std::string text(int column){auto data=sqlite3_column_text(stmt,column);return data?std::string(reinterpret_cast<const char*>(data),sqlite3_column_bytes(stmt,column)):"";}
};
std::string functionId(sqlite3 *db,const Function &f){Query q(db,"SELECT id FROM node_ids WHERE module=? AND name=?");q.bind(1,f.owner);q.bind(2,f.localName);if(!q.row())throw Error("E_STORE","missing operation owner");return q.text(0);}
std::map<std::string,std::string> identities(sqlite3 *db,const std::string &revision,const std::string &function){Query q(db,"SELECT path,id FROM operation_versions WHERE revision=? AND function=?");q.bind(1,revision);q.bind(2,function);std::map<std::string,std::string> ids;while(q.row())ids[q.text(0)]=q.text(1);return ids;}
}
void saveOperationGraph(sqlite3 *db,const Program &p,const Function &f,const std::string &function,const std::string &rev,const std::string &basis){
  auto content=hash(json(canonical(f),false));
  {Query q(db,"SELECT 1 FROM operation_functions WHERE revision=? AND function=?");q.bind(1,rev);q.bind(2,function);if(q.row())return;}
  std::string previous;
  {Query q(db,"SELECT revision FROM operation_functions WHERE function=? AND content_hash=? ORDER BY rowid DESC LIMIT 1");q.bind(1,function);q.bind(2,content);if(q.row())previous=q.text(0);}
  if(previous.empty()){Query q(db,"SELECT revision FROM operation_functions WHERE function=? ORDER BY (revision=?) DESC,rowid DESC LIMIT 1");q.bind(1,function);q.bind(2,basis);if(q.row())previous=q.text(0);}
  std::vector<Operation> old;
  if(!previous.empty()){Query q(db,"SELECT path,parent,role,ordinal,kind,anchor,hash FROM operation_versions WHERE revision=? AND function=?");q.bind(1,previous);q.bind(2,function);while(q.row()){Operation o;o.path=q.text(0);o.parent=q.text(1);o.role=q.text(2);o.ordinal=unsigned(sqlite3_column_int64(q.stmt,3));o.kind=q.text(4);o.anchor=q.text(5);o.content=q.text(6);old.push_back(std::move(o));}}
  auto tree=operationTree(p,f);auto ids=matchOperations(tree,old,identities(db,previous,function));
  for(const auto &o:tree){
    auto id=ids[o.path];if(id.empty()){std::random_device random;id=hash(function+o.path+std::to_string(random())+std::to_string(random())).substr(0,32);
      Query q(db,"INSERT INTO operation_ids(id,function,kind) VALUES(?,?,?)");q.bind(1,id);q.bind(2,function);q.bind(3,o.kind);q.row();}
    Query q(db,"INSERT INTO operation_versions(revision,function,path,parent,role,ordinal,id,kind,anchor,hash,site) VALUES(?,?,?,?,?,?,?,?,?,?,?)");
    q.bind(1,rev);q.bind(2,function);q.bind(3,o.path);q.bind(4,o.parent);q.bind(5,o.role);q.bind(6,std::to_string(o.ordinal));q.bind(7,id);q.bind(8,o.kind);q.bind(9,o.anchor);q.bind(10,o.content);q.bind(11,o.site);q.row();
  }
  Query q(db,"INSERT INTO operation_functions(revision,function,content_hash,basis) VALUES(?,?,?,?)");q.bind(1,rev);q.bind(2,function);q.bind(3,content);q.bind(4,previous);q.row();
}
JSON storedOperations(sqlite3 *db,const Program &p,const std::string &symbol,const std::string &selector,unsigned offset,unsigned limit,bool context){
  Array result,ancestors;uint64_t total=0;bool selected=false;auto rev=revision(p);
  const Function *named=symbol.empty()?nullptr:&p.function(symbol);std::string ownerFilter;
  if(!selector.empty()){Query q(db,"SELECT function FROM operation_versions WHERE revision=? AND (id=? OR site=?)");q.bind(1,rev);q.bind(2,selector);q.bind(3,selector);if(!q.row())throw Error("E_OPERATION","operation ID/site is not in the selected revision");ownerFilter=q.text(0);}
  for(const auto &f:p.functions){
    if(named&&named!=&f)continue;auto owner=functionId(db,f);if(!ownerFilter.empty()&&owner!=ownerFilter)continue;
    auto ids=identities(db,rev,owner);auto tree=operationTree(p,f);
    if(ids.size()!=tree.size())throw Error("E_STORE","operation identities are missing; recheck the selected revision");
    {Query q(db,"SELECT path,hash,site FROM operation_versions WHERE revision=? AND function=?");q.bind(1,rev);q.bind(2,owner);std::map<std::string,std::pair<std::string,std::string>> stored;while(q.row())stored[q.text(0)]={q.text(1),q.text(2)};
      for(const auto &o:tree)if(!ids.contains(o.path)||stored[o.path]!=std::pair{o.content,o.site})throw Error("E_STORE","operation metadata differs from checked sources");}
    std::map<std::string,const Operation*> paths;std::map<std::string,std::vector<const Operation*>> children;
    for(const auto &o:tree){paths[o.path]=&o;children[o.parent].push_back(&o);}
    auto record=[&](const Operation &o){
      Array operands,references;for(auto child:children[o.path]){if(operands.size()==100)break;operands.push_back(Object{{"id",ids.at(child->path)},{"site",child->site},{"role",child->role},{"ordinal",int64_t(child->ordinal)}});}
      if(!o.binding.empty())references.push_back(Object{{"role","binding"},{"id",ids.at(o.binding)}});
      if(!o.callee.empty())references.push_back(Object{{"role","callee"},{"id",functionId(db,p.function(o.callee))},{"symbol",o.callee}});
      auto definition=o.definition;auto bytes=json(definition,false).size();bool omitted=limit&&bytes>8192;if(omitted)definition=nullptr;
      const auto &source=p.units.contains(f.unit)?p.units.at(f.unit).source:p.source;
      bool ranged=o.sourceRange.valid&&!o.fragment.empty()&&o.sourceRange.begin<o.sourceRange.end&&o.sourceRange.end<=source.size()&&o.sourceRange.begin>=f.span.begin&&o.sourceRange.end<=f.span.end;
      JSON range=nullptr;if(ranged)range=Object{{"kind",o.fragment},{"byte_begin",int64_t(o.sourceRange.begin)},{"byte_end",int64_t(o.sourceRange.end)},{"editable",f.templateName.empty()&&!f.closure}};
      Object value{{"id",ids.at(o.path)},{"site",o.site},{"function",f.name},{"function_id",owner},{"path",o.path},{"parent",o.parent.empty()?owner:ids.at(o.parent)},{"role",o.role},{"ordinal",int64_t(o.ordinal)},{"kind",o.kind},{"hash",o.content},{"definition",std::move(definition)},{"definition_bytes",int64_t(bytes)},{"definition_omitted",omitted},
        {"location",Object{{"file",f.unit},{"line",int64_t(o.span.line)},{"column",int64_t(o.span.column)},{"byte_begin",int64_t(o.span.begin)},{"byte_end",int64_t(o.span.end)}}},
        {"children",std::move(operands)},{"child_count",int64_t(children[o.path].size())},{"children_truncated",children[o.path].size()>100},{"references",std::move(references)},{"source_range",std::move(range)}};
      if(context&&ranged){
        auto end=std::min(o.sourceRange.end,o.sourceRange.begin+size_t(4096));
        while(end>o.sourceRange.begin&&end<source.size()&&(static_cast<unsigned char>(source[end])&0xc0)==0x80)--end;
        value["source_preview"]=source.substr(o.sourceRange.begin,end-o.sourceRange.begin);
        value["source_bytes"]=int64_t(o.sourceRange.end-o.sourceRange.begin);value["source_truncated"]=end<o.sourceRange.end;
      }
      return value;
    };
    for(const auto &o:tree){
      if(!selector.empty()&&selector!=ids.at(o.path)&&selector!=o.site)continue;
      selected=true;if(total++<offset||(limit&&result.size()>=limit))continue;result.push_back(record(o));
      if(context){auto parent=o.parent;while(!parent.empty()){auto node=paths.at(parent);ancestors.push_back(Object{{"id",ids.at(parent)},{"site",node->site},{"path",parent},{"kind",node->kind}});parent=node->parent;}}
    }
  }
  if(!selector.empty()&&!selected)throw Error("E_OPERATION","operation ID/site is not in the selected revision");
  Object output{{"schema",context?"nex.operation-context/1":"nex.operations/1"},{"language",languageVersion},{"revision",rev},{"source_hash",hash(json(sourceBundle(p),false))},{"identity_scope","local_store"},{"identity_policy","nex.operation-identity/1"},{"total",int64_t(total)},{"offset",int64_t(offset)},{"truncated",uint64_t(offset)+result.size()<total},{"nodes",std::move(result)}};
  if(context)output["ancestors"]=std::move(ancestors);return output;
}
}
