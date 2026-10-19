#include "nex/graph_store.h"
#include "nex/operations.h"
#include <sqlite3.h>
#include <algorithm>
#include <functional>
#include <random>
#include <tuple>

namespace nex {
namespace {
using Value=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
constexpr size_t maximumNodes=100000,maximumEdges=2000000,maximumPage=1000;
struct Query {
  sqlite3 *db;sqlite3_stmt *statement=nullptr;
  Query(sqlite3 *db,const char *sql):db(db){if(sqlite3_prepare_v2(db,sql,-1,&statement,nullptr)!=SQLITE_OK)throw Error("E_STORE",sqlite3_errmsg(db));}
  ~Query(){sqlite3_finalize(statement);}
  void bind(int index,const std::string &value){if(sqlite3_bind_text(statement,index,value.data(),int(value.size()),SQLITE_TRANSIENT)!=SQLITE_OK)throw Error("E_STORE",sqlite3_errmsg(db));}
  bool row(){int code=sqlite3_step(statement);if(code==SQLITE_ROW)return true;if(code==SQLITE_DONE)return false;throw Error("E_STORE",sqlite3_errmsg(db));}
  std::string text(int column){auto data=sqlite3_column_text(statement,column);return data?std::string(reinterpret_cast<const char*>(data),sqlite3_column_bytes(statement,column)):"";}
};
void sql(sqlite3 *db,const char *text){char *message=nullptr;if(sqlite3_exec(db,text,nullptr,nullptr,&message)!=SQLITE_OK){std::string detail=message?message:"database error";sqlite3_free(message);throw Error("E_STORE",detail);}}
std::string fresh(){std::random_device random;std::string entropy;for(unsigned i=0;i<8;++i)entropy+=std::to_string(random())+"/";return hash(entropy).substr(0,32);}
using Key=std::pair<std::string,std::string>;
struct Entity {
  std::string kind,symbol,module,file,source,id,content,context;
  Value definition=nullptr;bool derived=false;std::set<Key> dependencies;
};
using Entities=std::map<Key,Entity>;
bool digest(const std::string &value){return value.size()==64&&value.find_first_not_of("0123456789abcdef")==std::string::npos;}
std::string token(const Object &object,const std::string &key,size_t maximum=8192){auto text=object.getString(key);if(!text||text->empty()||text->size()>maximum||text->contains('\0'))throw Error("E_IDENTITY_SCHEMA","invalid identity field: "+key);return text->str();}
void keys(const Object &object,const std::set<std::string> &allowed){for(const auto &[key,value]:object){(void)value;if(!allowed.contains(key.str()))throw Error("E_IDENTITY_SCHEMA","unknown identity field: "+key.str());}}
std::string clipped(const std::string &text,size_t limit){if(text.size()<=limit)return text;while(limit&&(static_cast<unsigned char>(text[limit])&0xc0)==0x80)--limit;return text.substr(0,limit);}
Key add(Entities &entities,std::string kind,std::string symbol,std::string module,std::string file,Value definition,std::string source={},bool derived=false){
  Key key{kind,symbol};Entity value;value.kind=std::move(kind);value.symbol=std::move(symbol);value.module=std::move(module);value.file=std::move(file);value.source=std::move(source);value.content=hash(json(definition,false));value.definition=std::move(definition);value.derived=derived;
  if(entities.size()>=maximumNodes)throw Error("E_IDENTITY_LIMIT","declaration graph exceeds 100000 nodes");
  if(!entities.emplace(key,std::move(value)).second)throw Error("E_STORE","duplicate checked graph entity");return key;
}
Entities describeEntities(const Program &p){
  Entities result;
  for(const auto &f:p.functions)add(result,"function",f.name,f.owner,f.unit,canonical(f),p.definition(f),!f.templateName.empty()||f.closure);
  for(const auto &s:p.structures)add(result,"type",s.name,s.owner,s.unit,canonical(s),p.definition(s),!s.templateName.empty());
  for(const auto &e:p.endpoints)add(result,"endpoint",e.name,e.owner,e.unit,canonical(e),p.definition(e));
  for(const auto &[file,unit]:p.units){
    std::set<std::string> imported;for(const auto &dependency:unit.imports)imported.insert(p.units.at(dependency.target).module);
    Array imports,members;for(const auto &name:imported)imports.push_back(name);
    for(const auto &[key,entity]:result)if(entity.module==unit.module&&!entity.derived)members.push_back(Object{{"kind",key.first},{"symbol",key.second},{"hash",entity.content}});
    add(result,"module",unit.module,unit.module,file,Object{{"format","nex.module/1"},{"name",unit.module},{"imports",std::move(imports)},{"members",std::move(members)}});
  }
  auto types=[&](Entity &entity,const Type &type,auto &&self)->void{
    if(type.kind==Type::Record){Key key{"type",type.name};if(result.contains(key))entity.dependencies.insert(key);}
    if(type.element)self(entity,*type.element,self);for(const auto &argument:type.arguments)self(entity,argument,self);
  };
  for(const auto &s:p.structures){auto &entity=result.at({"type",s.name});for(auto field:s.members())types(entity,field->type,types);for(const auto &argument:s.typeArguments)types(entity,argument,types);if(!s.templateName.empty())entity.dependencies.insert({"type",s.templateName});}
  for(const auto &f:p.functions){
    auto &entity=result.at({"function",f.name});for(const auto &name:f.dependencies)entity.dependencies.insert({"function",p.function(name).name});
    if(!f.templateName.empty())entity.dependencies.insert({"function",f.templateName});
    types(entity,f.result,types);for(const auto &parameter:f.params)types(entity,parameter.type,types);for(const auto &capture:f.captures)types(entity,capture.type,types);for(const auto &argument:f.typeArguments)types(entity,argument,types);
    std::function<void(E)> expression;std::function<void(const std::vector<S>&)> block;
    // Match arm bodies belong to the expression and are visited there.
    // childBlocks would visit them a second time, doubling each nesting level.
    block=[&](const auto &body){for(const auto &statement:body){types(entity,statement->type,types);expression(statement->expr);block(statement->body);block(statement->alternative);}};
    expression=[&](E value){if(!value)return;types(entity,value->type,types);types(entity,value->annotation,types);for(const auto &argument:value->typeArguments)types(entity,argument,types);for(auto argument:value->args)expression(argument);
      if(value->lambda){types(entity,value->lambda->result,types);for(const auto &parameter:value->lambda->params)types(entity,parameter.type,types);block(value->lambda->body);}
      for(auto arm:value->arms){for(const auto &binding:arm->bindings)types(entity,binding.type,types);block(arm->body);}
    };block(f.body);
  }
  for(const auto &endpoint:p.endpoints)result.at({"endpoint",endpoint.name}).dependencies.insert({"function",p.function(endpoint.target).name});
  for(const auto &[file,unit]:p.units){(void)file;auto &entity=result.at({"module",unit.module});
    for(const auto &dependency:unit.imports)entity.dependencies.insert({"module",p.units.at(dependency.target).module});
    for(const auto &[key,member]:result)if(member.kind!="module"&&member.module==unit.module&&!member.derived)entity.dependencies.insert(key);
  }
  size_t edges=0;for(const auto &[key,entity]:result){(void)key;if(entity.dependencies.size()>maximumEdges-edges)throw Error("E_IDENTITY_LIMIT","declaration graph exceeds 2000000 edges");edges+=entity.dependencies.size();}
  return result;
}
void identify(sqlite3 *db,Entities &entities){
  for(auto &[key,entity]:entities){
    if(entity.kind=="module"||entity.kind=="type"){
      Query q(db,"SELECT id FROM declaration_ids WHERE kind=? AND symbol=?");q.bind(1,key.first);q.bind(2,key.second);if(q.row())entity.id=q.text(0);
    }else{
      auto local=entity.kind=="endpoint"?"@endpoint/"+entity.symbol.substr(entity.symbol.rfind("::")+2):entity.symbol.substr(entity.module.size()+2);
      Query q(db,"SELECT id FROM node_ids WHERE module=? AND name=?");q.bind(1,entity.module);q.bind(2,local);if(q.row())entity.id=q.text(0);
    }
    if(entity.id.empty())throw Error("E_STORE","missing persistent graph identity: "+entity.symbol);
  }
}
// Iterative SCC construction avoids recursive hashing and stack depth limits.
// Incoming callers are deliberately excluded from a node's context fingerprint.
void contexts(Entities &entities){
  std::vector<Entity*> nodes;std::map<Key,size_t> indices;for(auto &[key,value]:entities){indices[key]=nodes.size();nodes.push_back(&value);}
  std::vector<std::vector<size_t>> edges(nodes.size()),reverse(nodes.size());size_t count=0;
  for(size_t i=0;i<nodes.size();++i)for(const auto &key:nodes[i]->dependencies){auto found=indices.find(key);if(found==indices.end())throw Error("E_STORE","missing checked graph dependency: "+key.second);if(++count>maximumEdges)throw Error("E_IDENTITY_LIMIT","declaration graph exceeds 2000000 edges");edges[i].push_back(found->second);reverse[found->second].push_back(i);}
  std::vector<bool> seen(nodes.size());std::vector<size_t> order;
  for(size_t i=0;i<nodes.size();++i)if(!seen[i]){
    std::vector<std::pair<size_t,size_t>> stack{{i,0}};seen[i]=true;
    while(!stack.empty()){auto &[node,next]=stack.back();if(next<edges[node].size()){auto child=edges[node][next++];if(!seen[child]){seen[child]=true;stack.emplace_back(child,0);}}else{order.push_back(node);stack.pop_back();}}
  }
  std::vector<size_t> component(nodes.size(),nodes.size());std::vector<std::vector<size_t>> groups;
  for(auto iterator=order.rbegin();iterator!=order.rend();++iterator)if(component[*iterator]==nodes.size()){
    auto id=groups.size();groups.emplace_back();std::vector<size_t> stack{*iterator};component[*iterator]=id;
    while(!stack.empty()){auto node=stack.back();stack.pop_back();groups[id].push_back(node);for(auto child:reverse[node])if(component[child]==nodes.size()){component[child]=id;stack.push_back(child);}}
    std::sort(groups[id].begin(),groups[id].end());
  }
  std::vector<std::string> hashes(groups.size());
  for(size_t id=groups.size();id-->0;){Array members,dependencies;std::set<std::string> unique;
    for(auto node:groups[id]){members.push_back(Object{{"kind",nodes[node]->kind},{"symbol",nodes[node]->symbol},{"hash",nodes[node]->content}});for(auto child:edges[node])if(component[child]!=id){if(hashes[component[child]].empty())throw Error("E_STORE","invalid graph component ordering");unique.insert(hashes[component[child]]);}}
    for(const auto &dependency:unique)dependencies.push_back(dependency);
    hashes[id]=hash(json(Object{{"format","nex.graph-component/1"},{"members",std::move(members)},{"dependencies",std::move(dependencies)}},false));
    for(auto node:groups[id])nodes[node]->context=hash(json(Object{{"format","nex.graph-context/1"},{"kind",nodes[node]->kind},{"symbol",nodes[node]->symbol},{"component",hashes[id]}},false));
  }
}
Entities checkedEntities(sqlite3 *db,const Program &p){
  auto entities=describeEntities(p);identify(db,entities);auto rev=revision(p);
  std::map<Key,std::tuple<std::string,std::string,std::string>> stored;
  {Query q(db,"SELECT kind,symbol,id,hash,canonical FROM declaration_versions WHERE revision=?");q.bind(1,rev);while(q.row())stored[{q.text(0),q.text(1)}]={q.text(2),q.text(3),q.text(4)};}
  size_t declarations=0;std::set<std::string> ids;std::set<std::tuple<std::string,std::string,std::string,std::string>> expectedEdges;
  for(const auto &[key,entity]:entities){
    if(!ids.insert(entity.id).second)throw Error("E_STORE","duplicate persistent graph identity");
    auto expected=std::tuple{entity.id,entity.content,json(entity.definition,false)};
    if(key.first=="module"||key.first=="type"){
      ++declarations;auto found=stored.find(key);if(found==stored.end()||found->second!=expected)throw Error("E_STORE","declaration metadata differs from checked source: "+key.second);
    }else{
      Query q(db,"SELECT hash,canonical FROM nodes WHERE revision=? AND id=?");q.bind(1,rev);q.bind(2,entity.id);
      if(!q.row()||q.text(0)!=entity.content||q.text(1)!=std::get<2>(expected))throw Error("E_STORE","node metadata differs from checked source: "+key.second);
    }
    for(const auto &dependency:entity.dependencies){auto found=entities.find(dependency);if(found==entities.end())throw Error("E_STORE","missing checked graph dependency: "+dependency.second);expectedEdges.emplace(key.first,entity.id,dependency.first,found->second.id);}
  }
  if(declarations!=stored.size())throw Error("E_STORE","unexpected stored declarations");
  {Query q(db,"SELECT source_kind,source,target_kind,target FROM graph_edges WHERE revision=?");q.bind(1,rev);while(q.row())if(!expectedEdges.erase({q.text(0),q.text(1),q.text(2),q.text(3)}))throw Error("E_STORE","unexpected stored graph edge");}
  if(!expectedEdges.empty())throw Error("E_STORE","missing stored graph edges");
  contexts(entities);return entities;
}
Object reference(const Entity &entity,const std::string &path="",const std::string &id="",const std::string &content="",const std::string &context=""){
  return Object{{"kind",path.empty()?entity.kind:"operation"},{"symbol",entity.symbol},{"path",path},{"id",id.empty()?entity.id:id},
    {"hash",content.empty()?entity.content:content},{"context_hash",context.empty()?entity.context:context}};
}
std::string operationContext(const Entity &owner,const Operation &operation){return hash(json(Object{{"format","nex.graph-operation-context/1"},{"function",owner.context},{"path",operation.path},{"kind",operation.kind},{"hash",operation.content}},false));}
std::string selectedSymbol(const Program &p,const Entities &entities,const std::string &kind,const std::string &symbol){
  if(symbol.empty())return {};auto name=symbol.find("::")==std::string::npos?p.module+"::"+symbol:symbol;
  if(kind=="module"){if(entities.contains({"module",symbol}))return symbol;throw Error("E_IDENTITY_SYMBOL","module is not in the selected graph");}
  if(kind=="all")for(const auto &candidate:{"function","type","endpoint"})if(entities.contains({candidate,name}))return name;
  if(kind=="all"&&entities.contains({"module",symbol}))return symbol;
  if(kind=="operation"){if(entities.contains({"function",name}))return name;}
  else if(entities.contains({kind,name}))return name;
  throw Error("E_IDENTITY_SYMBOL","symbol is not in the selected graph");
}
struct Selection {std::string kind,symbol;bool module=false;};
Selection select(const Program &p,const Entities &entities,const std::string &kind,const std::string &symbol){
  if(!std::set<std::string>{"all","module","type","function","endpoint","operation"}.contains(kind))throw Error("E_OPTION","entity must be all, module, type, function, endpoint or operation");
  auto name=selectedSymbol(p,entities,kind,symbol);return {kind,name,!name.empty()&&(kind=="module"||(kind=="all"&&entities.contains({"module",name})))};
}
bool includes(const Selection &selection,const Entity &entity,bool operation=false){
  if(selection.module)return entity.module==selection.symbol&&!entity.derived;
  if(!selection.symbol.empty()&&entity.symbol!=selection.symbol)return false;
  if(operation)return selection.kind=="all"||selection.kind=="operation";
  return selection.kind=="all"||selection.kind==entity.kind;
}
// A reconciliation page can contain many operations from one function. Build
// and verify that function's tree once, then resolve individual paths in O(log N).
struct OperationLookup {
  struct Records {std::vector<Object> ordered;std::map<std::string,size_t> paths;};
  sqlite3 *db;const Program &program;std::set<std::string> declarationIds;std::map<std::string,Records> cache;
  OperationLookup(sqlite3 *db,const Program &program,const Entities &entities):db(db),program(program){for(const auto &[key,entity]:entities){(void)key;declarationIds.insert(entity.id);}}
  const Records &all(const Entity &owner){
    auto found=cache.find(owner.symbol);if(found!=cache.end())return found->second;
    auto rev=revision(program);auto operations=operationTree(program,program.function(owner.symbol));
    {Query q(db,"SELECT content_hash FROM operation_functions WHERE revision=? AND function=?");q.bind(1,rev);q.bind(2,owner.id);if(!q.row()||q.text(0)!=owner.content)throw Error("E_STORE","operation owner differs from checked source");}
    std::map<std::string,std::vector<std::string>> stored;
    {Query q(db,"SELECT v.path,v.id,v.kind,v.hash,v.site,v.parent,v.role,v.ordinal,v.anchor,i.function,i.kind FROM operation_versions v LEFT JOIN operation_ids i ON i.id=v.id WHERE v.revision=? AND v.function=?");q.bind(1,rev);q.bind(2,owner.id);while(q.row()){auto &row=stored[q.text(0)];for(int i=1;i<=10;++i)row.push_back(q.text(i));}}
    if(stored.size()!=operations.size())throw Error("E_STORE","operation identities are missing");
    Records result;
    for(const auto &operation:operations){
      auto item=stored.find(operation.path);if(item==stored.end())throw Error("E_STORE","missing operation path");const auto &row=item->second;
      if(row[0].empty()||declarationIds.contains(row[0])||row[1]!=operation.kind||row[2]!=operation.content||row[3]!=operation.site||row[4]!=operation.parent||row[5]!=operation.role||row[6]!=std::to_string(operation.ordinal)||row[7]!=operation.anchor||row[8]!=owner.id||row[9]!=operation.kind)throw Error("E_STORE","operation metadata differs from checked source");
      result.paths[operation.path]=result.ordered.size();result.ordered.push_back(reference(owner,operation.path,row[0],operation.content,operationContext(owner,operation)));
    }
    return cache.emplace(owner.symbol,std::move(result)).first->second;
  }
  Object at(const Entity &owner,const std::string &path){const auto &records=all(owner);auto found=records.paths.find(path);if(found==records.paths.end())throw Error("E_IDENTITY_CONTENT","operation path is absent from the checked target graph");return records.ordered[found->second];}
};
Value localRecord(OperationLookup &operations,const Entities &entities,const std::string &kind,const std::string &symbol,const std::string &path){
  auto key=Key{kind=="operation"?"function":kind,symbol};auto found=entities.find(key);
  if(found==entities.end())throw Error("E_IDENTITY_CONTENT","identity symbol is absent from the checked target graph: "+symbol);
  if(kind=="operation")return operations.at(found->second,path);
  return reference(found->second);
}
constexpr size_t queryPreviewBytes=2048,queryCollectionBytes=65536,queryResponseBytes=262144;
void queryText(const std::string &value,size_t maximum,bool empty,const char *field){
  if((!empty&&value.empty())||value.size()>maximum||value.find('\0')!=std::string::npos||!llvm::json::isUTF8(value))
    throw Error("E_QUERY_OPTION",std::string("invalid graph query ")+field);
}
void queryLabel(const std::string &value,size_t maximum){
  if(value.size()>maximum||value.find('\0')!=std::string::npos||!llvm::json::isUTF8(value))
    throw Error("E_QUERY_LIMIT","graph query result contains an oversized or invalid reference label");
}
Object queryReference(const Entity &entity){
  queryLabel(entity.symbol,8192);queryLabel(entity.module,8192);queryLabel(entity.file,8192);queryLabel(entity.id,128);
  return reference(entity);
}
Object queryNode(const Entity &entity,bool includeSource,size_t focus=0,size_t matchBytes=0){
  auto row=queryReference(entity);row["module"]=entity.module;row["file"]=entity.file;row["derived"]=entity.derived;
  row["editable"]=entity.kind!="module"&&!entity.derived;row["preview"]=nullptr;
  if(includeSource&&!entity.source.empty()){
    const auto &source=entity.source;size_t begin=focus>512?focus-512:0,end=std::min(source.size(),begin+queryPreviewBytes);
    while(begin<end&&(static_cast<unsigned char>(source[begin])&0xc0)==0x80)++begin;
    while(end<source.size()&&end>begin&&(static_cast<unsigned char>(source[end])&0xc0)==0x80)--end;
    Value match=nullptr;if(matchBytes)match=Object{{"byte_begin",int64_t(focus)},{"byte_end",int64_t(focus+matchBytes)}};
    row["preview"]=Object{{"relative_to","declaration_source"},{"source_hash",hash(source)},{"source_bytes",int64_t(source.size())},
      {"byte_begin",int64_t(begin)},{"byte_end",int64_t(end)},{"text",source.substr(begin,end-begin)},
      {"truncated_before",begin!=0},{"truncated_after",end!=source.size()},{"match",std::move(match)}};
  }
  return row;
}
bool queryAppend(Array &rows,Object row,size_t &used){
  Value value=std::move(row);auto encoded=json(value);auto cost=encoded.size()+8*(std::count(encoded.begin(),encoded.end(),'\n')+1)+16;
  if(cost>queryCollectionBytes)throw Error("E_QUERY_LIMIT","a graph query row exceeds its output budget");
  if(cost>queryCollectionBytes-used)return false;used+=cost;rows.push_back(std::move(value));return true;
}
Object queryPage(unsigned offset,unsigned limit,size_t total,size_t count,bool byteLimited){
  auto next=size_t(offset)+count;Value cursor=nullptr;if(next<total)cursor=int64_t(next);
  return Object{{"offset",int64_t(offset)},{"limit",int64_t(limit)},{"total",int64_t(total)},{"returned",int64_t(count)},
    {"next_offset",std::move(cursor)},{"truncated",next<total},{"byte_limited",byteLimited}};
}
Object queryEnvelope(sqlite3 *db,const Program &p,const char *schema,Object selection){
  Object result{{"schema",schema},{"query_policy","nex.graph-query/1"},{"language",languageVersion},
    {"namespace",graphIdentityNamespace(db)},{"revision",revision(p)},{"source_hash",hash(json(sourceBundle(p),false))},{"selection",std::move(selection)}};
  // Selection identity excludes page ranges; exact archived input and namespace
  // participate, so clients can pin a revision and reject mixed query pages.
  result["query_hash"]=hash(json(Value(Object(result)),false));return result;
}
Value finishQuery(Object result){Value value=std::move(result);if(json(value).size()+1>queryResponseBytes)throw Error("E_QUERY_LIMIT","graph query response exceeds 256 KiB");return value;}

}

void initializeGraphIdentities(sqlite3 *db){
  sql(db,"BEGIN IMMEDIATE");
  try{
    sql(db,"CREATE TABLE IF NOT EXISTS declaration_ids(kind TEXT NOT NULL,symbol TEXT NOT NULL,id TEXT NOT NULL UNIQUE,PRIMARY KEY(kind,symbol));"
      "CREATE TABLE IF NOT EXISTS declaration_versions(revision TEXT NOT NULL REFERENCES revisions(hash),kind TEXT NOT NULL,symbol TEXT NOT NULL,id TEXT NOT NULL REFERENCES declaration_ids(id),hash TEXT NOT NULL,canonical TEXT NOT NULL,PRIMARY KEY(revision,kind,symbol));"
      "CREATE TABLE IF NOT EXISTS graph_edges(revision TEXT NOT NULL REFERENCES revisions(hash),source_kind TEXT NOT NULL,source TEXT NOT NULL,target_kind TEXT NOT NULL,target TEXT NOT NULL,PRIMARY KEY(revision,source_kind,source,target_kind,target));"
      "CREATE TABLE IF NOT EXISTS identity_revisions(revision TEXT PRIMARY KEY REFERENCES revisions(hash),policy TEXT NOT NULL);"
      "CREATE TABLE IF NOT EXISTS identity_links(origin TEXT NOT NULL,remote_id TEXT NOT NULL,source_revision TEXT NOT NULL,target_revision TEXT NOT NULL REFERENCES revisions(hash),local_id TEXT NOT NULL,kind TEXT NOT NULL,symbol TEXT NOT NULL,path TEXT NOT NULL,hash TEXT NOT NULL,context_hash TEXT NOT NULL,manifest_hash TEXT NOT NULL,PRIMARY KEY(origin,remote_id,source_revision,target_revision),UNIQUE(origin,source_revision,target_revision,kind,symbol,path));"
      "INSERT OR IGNORE INTO metadata VALUES('identity_schema','1');");
    {Query q(db,"SELECT value FROM metadata WHERE key='identity_schema'");if(!q.row()||q.text(0)!="1")throw Error("E_SCHEMA","unsupported graph identity extension");}
    {Query q(db,"SELECT value FROM metadata WHERE key='identity_namespace'");if(!q.row()){Query insert(db,"INSERT INTO metadata VALUES('identity_namespace',?)");insert.bind(1,fresh());insert.row();}}
    (void)graphIdentityNamespace(db);sql(db,"COMMIT");
  }catch(...){sql(db,"ROLLBACK");throw;}
}
std::string graphIdentityNamespace(sqlite3 *db){Query q(db,"SELECT value FROM metadata WHERE key='identity_namespace'");if(!q.row())throw Error("E_STORE","missing graph identity namespace");auto value=q.text(0);if(value.size()!=32||value.find_first_not_of("0123456789abcdef")!=std::string::npos)throw Error("E_STORE","invalid graph identity namespace");return value;}
bool graphDeclarationsReady(sqlite3 *db,const Program &p){Query q(db,"SELECT policy FROM identity_revisions WHERE revision=?");q.bind(1,revision(p));if(!q.row())return false;if(q.text(0)!="nex.graph-identity/1")throw Error("E_SCHEMA","unsupported stored graph identity policy");return true;}
void saveGraphDeclarations(sqlite3 *db,const Program &p){
  (void)graphDeclarationsReady(db,p);
  auto entities=describeEntities(p);auto rev=revision(p);
  for(auto &[key,entity]:entities)if(key.first=="module"||key.first=="type"){
    std::string id;{Query q(db,"SELECT id FROM declaration_ids WHERE kind=? AND symbol=?");q.bind(1,key.first);q.bind(2,key.second);if(q.row())id=q.text(0);}
    if(id.empty()){id=fresh();Query q(db,"INSERT INTO declaration_ids(kind,symbol,id) VALUES(?,?,?)");q.bind(1,key.first);q.bind(2,key.second);q.bind(3,id);q.row();}
    auto canonical=json(entity.definition,false);
    {Query q(db,"SELECT id,hash,canonical FROM declaration_versions WHERE revision=? AND kind=? AND symbol=?");q.bind(1,rev);q.bind(2,key.first);q.bind(3,key.second);if(q.row()&&(q.text(0)!=id||q.text(1)!=entity.content||q.text(2)!=canonical))throw Error("E_STORE","stored declaration differs from checked source: "+key.second);}
    Query q(db,"INSERT OR IGNORE INTO declaration_versions(revision,kind,symbol,id,hash,canonical) VALUES(?,?,?,?,?,?)");q.bind(1,rev);q.bind(2,key.first);q.bind(3,key.second);q.bind(4,id);q.bind(5,entity.content);q.bind(6,canonical);q.row();
  }
  identify(db,entities);
  for(const auto &[key,entity]:entities)for(const auto &dependency:entity.dependencies){
    auto found=entities.find(dependency);if(found==entities.end())throw Error("E_STORE","missing checked graph dependency: "+dependency.second);
    Query q(db,"INSERT OR IGNORE INTO graph_edges(revision,source_kind,source,target_kind,target) VALUES(?,?,?,?,?)");q.bind(1,rev);q.bind(2,key.first);q.bind(3,entity.id);q.bind(4,dependency.first);q.bind(5,found->second.id);q.row();
  }
  Query q(db,"INSERT OR REPLACE INTO identity_revisions(revision,policy) VALUES(?,?)");q.bind(1,rev);q.bind(2,"nex.graph-identity/1");q.row();
}
Value graphDeclarations(sqlite3 *db,const Program &p,const std::string &kind,const std::string &symbol,unsigned offset,unsigned limit){
  if(limit>maximumPage)throw Error("E_IDENTITY_LIMIT","declaration page exceeds 1000 nodes");
  auto entities=checkedEntities(db,p);auto selection=select(p,entities,kind.empty()?"all":kind,symbol);Array rows;uint64_t total=0;
  for(const auto &[key,entity]:entities){if((key.first!="module"&&key.first!="type")||(!kind.empty()&&key.first!=kind)||(!selection.symbol.empty()&&key.second!=selection.symbol))continue;
    if(total++<offset||(limit&&rows.size()>=limit))continue;
    Array dependencies;for(const auto &dependency:entity.dependencies){if(limit&&dependencies.size()>=100)break;const auto &node=entities.at(dependency);dependencies.push_back(reference(node));}
    auto definition=entity.definition;auto definitionBytes=json(definition,false).size();bool omitted=limit&&definitionBytes>8192;if(omitted)definition=nullptr;
    auto source=limit?clipped(entity.source,4096):entity.source;
    auto value=reference(entity);value["module"]=entity.module;value["file"]=entity.file;value["source"]=std::move(source);value["source_bytes"]=int64_t(entity.source.size());value["source_truncated"]=limit&&entity.source.size()>4096;
    value["definition"]=std::move(definition);value["definition_bytes"]=int64_t(definitionBytes);value["definition_omitted"]=omitted;value["editable"]=entity.kind=="type"&&!entity.derived;value["derived"]=entity.derived;
    value["references"]=std::move(dependencies);value["reference_count"]=int64_t(entity.dependencies.size());value["references_truncated"]=limit&&entity.dependencies.size()>100;rows.push_back(std::move(value));
  }
  return Object{{"schema","nex.declarations/1"},{"language",languageVersion},{"revision",revision(p)},{"namespace",graphIdentityNamespace(db)},
    {"identity_policy","nex.graph-identity/1"},{"total",int64_t(total)},{"offset",int64_t(offset)},{"truncated",offset+rows.size()<total},{"nodes",std::move(rows)}};
}
Value graphIdentities(sqlite3 *db,const Program &p,const std::string &kind,const std::string &symbol,unsigned offset,unsigned limit){
  if(!limit||limit>maximumPage)throw Error("E_IDENTITY_LIMIT","identity page must contain 1..1000 nodes");
  auto entities=checkedEntities(db,p);auto selection=select(p,entities,kind,symbol);Array rows;uint64_t total=0;
  auto append=[&](Object row){if(total++>=offset&&rows.size()<limit)rows.push_back(std::move(row));};
  for(const auto &[key,entity]:entities){(void)key;if(includes(selection,entity))append(reference(entity));}
  OperationLookup operations{db,p,entities};
  for(const auto &[key,entity]:entities){if(key.first!="function"||!includes(selection,entity,true))continue;
    for(const auto &operation:operations.all(entity).ordered)append(operation);
  }
  return Object{{"schema","nex.identities/1"},{"language",languageVersion},{"identity_policy","nex.graph-identity/1"},{"namespace",graphIdentityNamespace(db)},
    {"revision",revision(p)},{"source_hash",hash(json(sourceBundle(p),false))},{"selection",Object{{"entity",kind},{"symbol",selection.symbol}}},
    {"offset",int64_t(offset)},{"total",int64_t(total)},{"truncated",offset+rows.size()<total},{"nodes",std::move(rows)}};
}
void validateGraphQuery(const GraphQueryOptions &o,bool subgraph){
  const std::set<std::string> kinds={"module","type","function","endpoint"};
  if((!subgraph&&o.entity!="all"&&!kinds.contains(o.entity))||(subgraph&&!kinds.contains(o.entity)))throw Error("E_QUERY_OPTION","graph query entity must be module, type, function or endpoint; search also accepts all");
  if(o.offset>10000000||!o.limit||o.limit>1000||o.edgeOffset>10000000||!o.edgeLimit||o.edgeLimit>1000||o.depth>8)throw Error("E_QUERY_OPTION","graph query page/depth limit exceeded");
  if(subgraph){queryText(o.symbol,8192,false,"symbol");if(!std::set<std::string>{"dependencies","dependents","both"}.contains(o.direction))throw Error("E_QUERY_OPTION","subgraph direction must be dependencies, dependents or both");}
  else{queryText(o.query,1024,false,"text");if(!std::set<std::string>{"symbol","source","any"}.contains(o.field))throw Error("E_QUERY_OPTION","search field must be symbol, source or any");}
}
Value searchGraph(sqlite3 *db,const Program &p,const GraphQueryOptions &o){
  validateGraphQuery(o,false);auto entities=checkedEntities(db,p);Array rows;size_t total=0,used=0;bool byteLimited=false;
  for(const auto &[key,entity]:entities){
    if(o.entity!="all"&&key.first!=o.entity)continue;Array fields;size_t sourceMatch=std::string::npos;
    if(o.field!="source"&&entity.symbol.find(o.query)!=std::string::npos)fields.push_back("symbol");
    if(o.field=="any"){
      if(entity.module.find(o.query)!=std::string::npos)fields.push_back("module");
      if(entity.file.find(o.query)!=std::string::npos)fields.push_back("file");
    }
    if(o.field!="symbol"){sourceMatch=entity.source.find(o.query);if(sourceMatch!=std::string::npos)fields.push_back("source");}
    if(fields.empty())continue;auto index=total++;
    if(index<o.offset||rows.size()>=o.limit||byteLimited)continue;
    auto row=queryNode(entity,sourceMatch!=std::string::npos,sourceMatch,sourceMatch==std::string::npos?0:o.query.size());row["matched_fields"]=std::move(fields);
    if(!queryAppend(rows,std::move(row),used))byteLimited=true;
  }
  auto result=queryEnvelope(db,p,"nex.graph-search/1",Object{{"query",o.query},{"entity",o.entity},{"field",o.field}});
  result["page"]=queryPage(o.offset,o.limit,total,rows.size(),byteLimited);result["nodes"]=std::move(rows);return finishQuery(std::move(result));
}
Value subgraphGraph(sqlite3 *db,const Program &p,const GraphQueryOptions &o){
  validateGraphQuery(o,true);auto entities=checkedEntities(db,p);Key root{o.entity,o.symbol};
  if(!entities.contains(root)&&o.entity!="module")root.second=p.module+"::"+o.symbol;
  if(!entities.contains(root))throw Error("E_QUERY_SYMBOL","subgraph root is absent from the selected checked graph");
  std::map<Key,std::set<Key>> adjacency;
  for(const auto &[key,entity]:entities)for(const auto &target:entity.dependencies){
    if(o.direction!="dependents")adjacency[key].insert(target);
    if(o.direction!="dependencies")adjacency[target].insert(key);
  }
  std::map<Key,unsigned> distances{{root,0}};std::vector<Key> queue{root};
  for(size_t next=0;next<queue.size();++next){auto node=queue[next];auto distance=distances.at(node);if(distance==o.depth)continue;
    for(const auto &target:adjacency[node])if(distances.emplace(target,distance+1).second)queue.push_back(target);
  }
  size_t boundary=0;for(const auto &[node,distance]:distances){(void)distance;for(const auto &target:adjacency[node])if(!distances.contains(target))++boundary;}
  std::sort(queue.begin(),queue.end(),[&](const Key &a,const Key &b){return std::tuple{distances.at(a),a}<std::tuple{distances.at(b),b};});
  Array nodes,edges;size_t nodeBytes=0,edgeBytes=0,totalEdges=0;bool nodeLimited=false,edgeLimited=false;
  for(size_t i=o.offset;i<queue.size()&&nodes.size()<o.limit;++i){auto row=queryNode(entities.at(queue[i]),true);row["distance"]=int64_t(distances.at(queue[i]));if(!queryAppend(nodes,std::move(row),nodeBytes)){nodeLimited=true;break;}}
  for(const auto &[key,entity]:entities)if(distances.contains(key))for(const auto &target:entity.dependencies)if(distances.contains(target)){
    auto index=totalEdges++;if(index<o.edgeOffset||edges.size()>=o.edgeLimit||edgeLimited)continue;
    Object row{{"source",queryReference(entity)},{"target",queryReference(entities.at(target))}};
    if(!queryAppend(edges,std::move(row),edgeBytes))edgeLimited=true;
  }
  auto result=queryEnvelope(db,p,"nex.subgraph/1",Object{{"entity",o.entity},{"symbol",root.second},{"direction",o.direction},{"depth",int64_t(o.depth)}});
  result["root"]=queryReference(entities.at(root));result["depth_limited"]=boundary!=0;result["boundary_references"]=int64_t(boundary);
  result["node_page"]=queryPage(o.offset,o.limit,queue.size(),nodes.size(),nodeLimited);result["edge_page"]=queryPage(o.edgeOffset,o.edgeLimit,totalEdges,edges.size(),edgeLimited);
  result["nodes"]=std::move(nodes);result["edges"]=std::move(edges);return finishQuery(std::move(result));
}

Value reconcileGraphIdentities(sqlite3 *db,const Program &p,const Value &manifest){
  auto object=manifest.getAsObject();if(!object)throw Error("E_IDENTITY_SCHEMA","identity manifest must be an object");
  keys(*object,{"schema","language","identity_policy","namespace","revision","source_hash","selection","offset","total","truncated","nodes"});
  if(token(*object,"schema")!="nex.identities/1"||token(*object,"identity_policy")!="nex.graph-identity/1")throw Error("E_IDENTITY_SCHEMA","unsupported graph identity protocol");
  if(token(*object,"language")!=languageVersion)throw Error("E_LANGUAGE_VERSION","identity manifest uses another language version");
  auto origin=token(*object,"namespace",32),sourceRevision=token(*object,"revision",64),sourceHash=token(*object,"source_hash",64),current=revision(p),localNamespace=graphIdentityNamespace(db);
  if(origin.size()!=32||origin.find_first_not_of("0123456789abcdef")!=std::string::npos||!digest(sourceRevision)||!digest(sourceHash))throw Error("E_IDENTITY_SCHEMA","invalid namespace or source digest");
  auto nodes=object->getArray("nodes");if(!nodes||nodes->empty()||nodes->size()>maximumPage)throw Error("E_IDENTITY_LIMIT","reconciliation requires 1..1000 identity records");
  auto offset=object->getInteger("offset"),total=object->getInteger("total");auto truncated=object->getBoolean("truncated");auto scope=object->getObject("selection");
  if(!offset||!total||!truncated||!scope||*offset<0||*offset>10000000||*total<*offset||uint64_t(*total-*offset)<nodes->size()||*truncated!=(uint64_t(*total-*offset)>nodes->size()))throw Error("E_IDENTITY_SCHEMA","invalid identity page metadata");
  keys(*scope,{"entity","symbol"});auto scopeKind=token(*scope,"entity",16);auto scopeSymbol=scope->getString("symbol");if(!scopeSymbol||scopeSymbol->size()>8192||scopeSymbol->contains('\0'))throw Error("E_IDENTITY_SCHEMA","invalid identity selection");
  auto entities=checkedEntities(db,p);auto selection=select(p,entities,scopeKind,scopeSymbol->str());
  if(selection.symbol!=scopeSymbol->str())throw Error("E_IDENTITY_SCHEMA","identity selection requires a fully qualified symbol");
  OperationLookup operations{db,p,entities};Array mappings;std::set<std::string> remoteIds;std::set<std::tuple<std::string,std::string,std::string>> selected;auto manifestHash=hash(json(manifest,false));
  struct Link{std::string remote,local,kind,symbol,path,content,context;};std::vector<Link> links;
  for(const auto &value:*nodes){auto node=value.getAsObject();if(!node)throw Error("E_IDENTITY_SCHEMA","identity record must be an object");keys(*node,{"kind","symbol","path","id","hash","context_hash"});
    auto kind=token(*node,"kind",16),symbol=token(*node,"symbol"),remote=token(*node,"id",128),content=token(*node,"hash",64),context=token(*node,"context_hash",64);auto path=node->getString("path");
    if(!path||path->size()>8192||path->contains('\0')||!std::set<std::string>{"module","type","function","endpoint","operation"}.contains(kind)||((kind=="operation")!=!path->empty())||!digest(content)||!digest(context))throw Error("E_IDENTITY_SCHEMA","invalid checked identity record");
    if(!remoteIds.insert(remote).second||!selected.emplace(kind,symbol,path->str()).second)throw Error("E_IDENTITY_SCHEMA","duplicate identity record or remote ID");
    auto local=localRecord(operations,entities,kind,symbol,path->str());auto target=local.getAsObject();
    if(!includes(selection,entities.at({kind=="operation"?"function":kind,symbol}),kind=="operation"))throw Error("E_IDENTITY_SCHEMA","identity record is outside its selection");
    if(target->getString("hash")!=content||target->getString("context_hash")!=context)throw Error("E_IDENTITY_CONTENT","definition or dependency context differs: "+symbol+(path->empty()?"":" at "+path->str()));
    auto id=target->getString("id")->str();if(origin==localNamespace&&remote!=id)throw Error("E_IDENTITY_CONFLICT","manifest would rename an identity in this store's own namespace");
    {Query q(db,"SELECT local_id,kind,symbol,path,hash,context_hash FROM identity_links WHERE origin=? AND remote_id=? AND source_revision=? AND target_revision=?");q.bind(1,origin);q.bind(2,remote);q.bind(3,sourceRevision);q.bind(4,current);
      if(q.row()&&(q.text(0)!=id||q.text(1)!=kind||q.text(2)!=symbol||q.text(3)!=path->str()||q.text(4)!=content||q.text(5)!=context))throw Error("E_IDENTITY_CONFLICT","remote identity already has another checked mapping");}
    {Query q(db,"SELECT remote_id FROM identity_links WHERE origin=? AND source_revision=? AND target_revision=? AND kind=? AND symbol=? AND path=?");q.bind(1,origin);q.bind(2,sourceRevision);q.bind(3,current);q.bind(4,kind);q.bind(5,symbol);q.bind(6,path->str());if(q.row()&&q.text(0)!=remote)throw Error("E_IDENTITY_CONFLICT","source snapshot assigns another ID to the same node");}
    mappings.push_back(Object{{"source",Object{{"namespace",origin},{"revision",sourceRevision},{"id",remote}}},{"target",Object{{"namespace",localNamespace},{"revision",current},{"id",id}}},{"kind",kind},{"symbol",symbol},{"path",path->str()},{"hash",content},{"context_hash",context}});
    links.push_back({remote,id,kind,symbol,path->str(),content,context});
  }
  for(const auto &link:links){Query q(db,"INSERT OR IGNORE INTO identity_links(origin,remote_id,source_revision,target_revision,local_id,kind,symbol,path,hash,context_hash,manifest_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)");q.bind(1,origin);q.bind(2,link.remote);q.bind(3,sourceRevision);q.bind(4,current);q.bind(5,link.local);q.bind(6,link.kind);q.bind(7,link.symbol);q.bind(8,link.path);q.bind(9,link.content);q.bind(10,link.context);q.bind(11,manifestHash);q.row();}
  return Object{{"schema","nex.identity-reconciliation/1"},{"ok",true},{"language",languageVersion},{"revision",current},{"namespace",localNamespace},{"source_namespace",origin},{"source_revision",sourceRevision},{"manifest_hash",manifestHash},{"mappings",std::move(mappings)},{"source_unchanged",true},{"head_unchanged",true}};
}
Value resolveGraphIdentity(sqlite3 *db,const Program &p,const std::string &origin,const std::string &sourceRevision,const std::string &id){
  if(origin.size()!=32||origin.find_first_not_of("0123456789abcdef")!=std::string::npos||!digest(sourceRevision)||id.empty()||id.size()>128||id.find('\0')!=std::string::npos)throw Error("E_IDENTITY_SCHEMA","invalid snapshot identity reference");
  auto entities=checkedEntities(db,p);OperationLookup operations{db,p,entities};auto targetRevision=revision(p);Value result=nullptr;std::string manifestHash;
  Query q(db,"SELECT local_id,kind,symbol,path,hash,context_hash,manifest_hash FROM identity_links WHERE origin=? AND remote_id=? AND source_revision=? AND target_revision=?");q.bind(1,origin);q.bind(2,id);q.bind(3,sourceRevision);q.bind(4,targetRevision);
  if(q.row()){result=localRecord(operations,entities,q.text(1),q.text(2),q.text(3));auto record=result.getAsObject();if(record->getString("id")!=q.text(0)||record->getString("hash")!=q.text(4)||record->getString("context_hash")!=q.text(5))throw Error("E_IDENTITY_CONFLICT","stored mapping differs from the selected checked graph");manifestHash=q.text(6);}
  else if(origin==graphIdentityNamespace(db)&&sourceRevision==targetRevision){
    for(const auto &[key,entity]:entities){(void)key;if(entity.id==id){result=reference(entity);break;}}
    if(result.getAsNull())for(const auto &f:p.functions){const auto &owner=entities.at({"function",f.name});for(const auto &node:operations.all(owner).ordered)if(node.getString("id")==id){result=Object(node);break;}if(!result.getAsNull())break;}
  }
  if(result.getAsNull())throw Error("E_IDENTITY_REF","identity reference has no mapping in the selected revision");
  return Object{{"schema","nex.identity-resolution/1"},{"language",languageVersion},{"source",Object{{"namespace",origin},{"revision",sourceRevision},{"id",id}}},
    {"target",Object{{"namespace",graphIdentityNamespace(db)},{"revision",targetRevision},{"node",std::move(result)}}},{"manifest_hash",manifestHash}};
}
}
