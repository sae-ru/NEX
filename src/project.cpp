#include "nex/project.h"
#include "nex/operation_store.h"
#include "nex/graph_store.h"
#include <sqlite3.h>
#include <random>
#include <algorithm>
#include "llvm/Support/Error.h"

namespace nex {
namespace {
struct Statement {
  sqlite3 *db;sqlite3_stmt *stmt=nullptr;
  Statement(sqlite3 *db,const char *sql):db(db){if(sqlite3_prepare_v2(db,sql,-1,&stmt,nullptr)!=SQLITE_OK)throw Error("E_STORE",sqlite3_errmsg(db));}
  ~Statement(){sqlite3_finalize(stmt);}
  void bind(int index,const std::string &s){if(sqlite3_bind_text(stmt,index,s.data(),int(s.size()),SQLITE_TRANSIENT)!=SQLITE_OK)throw Error("E_STORE",sqlite3_errmsg(db));}
  bool row(){int rc=sqlite3_step(stmt);if(rc==SQLITE_ROW)return true;if(rc==SQLITE_DONE)return false;throw Error("E_STORE",sqlite3_errmsg(db));}
  std::string text(int column){auto p=sqlite3_column_text(stmt,column);return p?std::string(reinterpret_cast<const char*>(p),sqlite3_column_bytes(stmt,column)):"";}
};
void sql(sqlite3 *db,const char *text){char *message=nullptr;if(sqlite3_exec(db,text,nullptr,nullptr,&message)!=SQLITE_OK){std::string m=message?message:"database error";sqlite3_free(message);throw Error("E_STORE",m);}}
std::string head(sqlite3 *db){Statement q(db,"SELECT revision FROM head WHERE id=1");return q.row()?q.text(0):"";}
std::string nodeId(sqlite3 *db,const std::string &module,const std::string &name){Statement q(db,"SELECT id FROM node_ids WHERE module=? AND name=?");q.bind(1,module);q.bind(2,name);return q.row()?q.text(0):"";}
}
struct Store::Impl{sqlite3 *db=nullptr;bool legacyLanguage=false;~Impl(){if(db)sqlite3_close(db);}};
Store::Store(const std::filesystem::path &directory,StoreOpenMode mode):impl(std::make_unique<Impl>()) {
  if(mode==StoreOpenMode::ReadOnly){
    if(sqlite3_open_v2((directory/"graph.db").string().c_str(),&impl->db,SQLITE_OPEN_READONLY,nullptr)!=SQLITE_OK)
      throw Error("E_STORE","cannot open existing graph database read-only");
    sqlite3_busy_timeout(impl->db,5000);
    Statement q(impl->db,"SELECT value FROM metadata WHERE key='schema'");
    if(!q.row()||(q.text(0)!="1"&&q.text(0)!="2"&&q.text(0)!="3"&&q.text(0)!="4"))
      throw Error("E_SCHEMA","unsupported graph database schema");
    impl->legacyLanguage=q.text(0)=="1";
    return;
  }
  std::filesystem::create_directories(directory);
  if(sqlite3_open((directory/"graph.db").string().c_str(),&impl->db)!=SQLITE_OK)throw Error("E_STORE","cannot open graph database");
  sqlite3_busy_timeout(impl->db,5000);
  sql(impl->db,"PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL;"
    "CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);"
    "INSERT OR IGNORE INTO metadata VALUES('schema','1');"
    "CREATE TABLE IF NOT EXISTS revisions(hash TEXT PRIMARY KEY,module TEXT NOT NULL,source TEXT NOT NULL,path TEXT NOT NULL,created TEXT DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')));"
    "CREATE TABLE IF NOT EXISTS head(id INTEGER PRIMARY KEY CHECK(id=1),revision TEXT NOT NULL REFERENCES revisions(hash));"
    "CREATE TABLE IF NOT EXISTS node_ids(module TEXT NOT NULL,name TEXT NOT NULL,id TEXT NOT NULL UNIQUE,PRIMARY KEY(module,name));"
    "CREATE TABLE IF NOT EXISTS nodes(revision TEXT NOT NULL REFERENCES revisions(hash),id TEXT NOT NULL REFERENCES node_ids(id),hash TEXT NOT NULL,canonical TEXT NOT NULL,PRIMARY KEY(revision,id));"
    "CREATE TABLE IF NOT EXISTS edges(revision TEXT NOT NULL REFERENCES revisions(hash),caller TEXT NOT NULL REFERENCES node_ids(id),callee TEXT NOT NULL REFERENCES node_ids(id),PRIMARY KEY(revision,caller,callee));"
    "CREATE TABLE IF NOT EXISTS task_runs(id TEXT PRIMARY KEY,task TEXT NOT NULL,task_hash TEXT NOT NULL,status TEXT NOT NULL,report TEXT NOT NULL,report_hash TEXT NOT NULL,created TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')));");
  std::string version;{Statement q(impl->db,"SELECT value FROM metadata WHERE key='schema'");if(q.row())version=q.text(0);}
  if(version=="1"){
    sql(impl->db,"BEGIN IMMEDIATE");
    try{
      {Statement q(impl->db,"SELECT value FROM metadata WHERE key='schema'");q.row();version=q.text(0);}
      if(version=="1")sql(impl->db,"ALTER TABLE revisions ADD COLUMN language TEXT NOT NULL DEFAULT '0.1'; UPDATE metadata SET value='2' WHERE key='schema'");
      else if(version!="2"&&version!="3"&&version!="4")throw Error("E_SCHEMA","unsupported graph database schema");
      sql(impl->db,"COMMIT");
    }
    catch(...){sql(impl->db,"ROLLBACK");throw;}
  }else if(version!="2"&&version!="3"&&version!="4")throw Error("E_SCHEMA","unsupported graph database schema");
  sql(impl->db,"BEGIN IMMEDIATE");
  try{
    {Statement q(impl->db,"SELECT value FROM metadata WHERE key='schema'");q.row();version=q.text(0);}
    if(version=="2")sql(impl->db,
      "CREATE TABLE operation_ids(id TEXT PRIMARY KEY,function TEXT NOT NULL REFERENCES node_ids(id),kind TEXT NOT NULL);"
      "CREATE TABLE operation_versions(revision TEXT NOT NULL REFERENCES revisions(hash),function TEXT NOT NULL REFERENCES node_ids(id),path TEXT NOT NULL,parent TEXT NOT NULL,role TEXT NOT NULL,ordinal INTEGER NOT NULL,id TEXT NOT NULL REFERENCES operation_ids(id),kind TEXT NOT NULL,anchor TEXT NOT NULL,hash TEXT NOT NULL,site TEXT NOT NULL,PRIMARY KEY(revision,function,path),UNIQUE(revision,id),UNIQUE(revision,site));"
      "CREATE TABLE operation_functions(revision TEXT NOT NULL REFERENCES revisions(hash),function TEXT NOT NULL REFERENCES node_ids(id),content_hash TEXT NOT NULL,basis TEXT NOT NULL,PRIMARY KEY(revision,function));"
      "UPDATE metadata SET value='3' WHERE key='schema'");
    else if(version!="3"&&version!="4")throw Error("E_SCHEMA","unsupported graph database schema");
    initializeChanges(impl->db);
    sql(impl->db,"UPDATE metadata SET value='4' WHERE key='schema'");
    sql(impl->db,"COMMIT");
  }catch(...){sql(impl->db,"ROLLBACK");throw;}
  initializeGraphIdentities(impl->db);
}
Store::~Store()=default;
std::string Store::save(const Program &p,const std::string &expected,bool makeHead,const ChangeInfo &change,const std::string &expectedNamespace) {
  validateChangeInfo(change);
  if(p.units.empty())throw Error("E_STORE","cannot save a program without its source snapshot");
  auto db=impl->db;auto rev=revision(p);bool outer=sqlite3_get_autocommit(db)!=0;
  sql(db,outer?"BEGIN IMMEDIATE":"SAVEPOINT nex_save_program");
  try{
    auto previous=head(db);
    if(!expectedNamespace.empty()&&graphIdentityNamespace(db)!=expectedNamespace)throw Error("E_CONFLICT","graph identity namespace changed before save");
    if(!expected.empty()&&previous!=(expected=="EMPTY"?"":expected))throw Error("E_CONFLICT","graph HEAD changed; read context and retry");
    // Live synchronization is not a language migration. Repeat this check
    // inside the write transaction: an explicit migration can race parsing or
    // the coordinator's earlier readonly HEAD check.
    if(makeHead&&!previous.empty()){
      Statement current(db,"SELECT language FROM revisions WHERE hash=?");current.bind(1,previous);
      if(!current.row())throw Error("E_REVISION","graph HEAD revision is missing");
      if(current.text(0)!=programLanguage(p)&&(change.action=="synchronize"||((isTypedSourceErrorLanguage(p.sourceLanguage)||(current.text(0)=="0.27"||current.text(0)=="0.28"||current.text(0)=="0.29"))&&change.action!="migrate")))
        throw Error("E_LANGUAGE_VERSION","graph HEAD uses another language version; run nex migrate explicitly");
    }
    {Statement existing(db,"SELECT language FROM revisions WHERE hash=?");existing.bind(1,rev);
      if(existing.row()&&existing.text(0)!=programLanguage(p))throw Error("E_REVISION","stored revision language differs from its checked semantic identity");}
    {Statement q(db,"INSERT OR IGNORE INTO revisions(hash,module,source,path,language) VALUES(?,?,?,?,?)");q.bind(1,rev);q.bind(2,p.module);q.bind(3,json(sourceBundle(p),false));q.bind(4,p.path);q.bind(5,programLanguage(p));q.row();}
    for(const auto &f:p.functions){
      auto id=nodeId(db,f.owner,f.localName);
      if(id.empty()){
        std::random_device random;id=hash(p.module+f.name+std::to_string(random())+std::to_string(random())).substr(0,32);
        Statement q(db,"INSERT INTO node_ids(module,name,id) VALUES(?,?,?)");q.bind(1,f.owner);q.bind(2,f.localName);q.bind(3,id);q.row();
      }
      auto data=json(canonical(f),false);
      Statement q(db,"INSERT OR IGNORE INTO nodes(revision,id,hash,canonical) VALUES(?,?,?,?)");q.bind(1,rev);q.bind(2,id);q.bind(3,hash(data));q.bind(4,data);q.row();
    }
    for(const auto &f:p.functions)saveOperationGraph(db,p,f,nodeId(db,f.owner,f.localName),rev,head(db));
    for(const auto &f:p.functions)for(const auto &dependency:f.dependencies){
      const auto &callee=p.function(dependency);
      Statement q(db,"INSERT OR IGNORE INTO edges(revision,caller,callee) VALUES(?,?,?)");q.bind(1,rev);q.bind(2,nodeId(db,f.owner,f.localName));q.bind(3,nodeId(db,callee.owner,callee.localName));q.row();
    }
    for(const auto &endpoint:p.endpoints){
      auto local="@endpoint/"+endpoint.localName;auto id=nodeId(db,endpoint.owner,local);
      if(id.empty()){std::random_device random;id=hash(endpoint.name+std::to_string(random())+std::to_string(random())).substr(0,32);Statement q(db,"INSERT INTO node_ids(module,name,id) VALUES(?,?,?)");q.bind(1,endpoint.owner);q.bind(2,local);q.bind(3,id);q.row();}
      auto data=json(canonical(endpoint),false);Statement node(db,"INSERT OR IGNORE INTO nodes(revision,id,hash,canonical) VALUES(?,?,?,?)");node.bind(1,rev);node.bind(2,id);node.bind(3,hash(data));node.bind(4,data);node.row();
      const auto &handler=p.function(endpoint.target);Statement edge(db,"INSERT OR IGNORE INTO edges(revision,caller,callee) VALUES(?,?,?)");edge.bind(1,rev);edge.bind(2,id);edge.bind(3,nodeId(db,handler.owner,handler.localName));edge.row();
    }
    saveGraphDeclarations(db,p);
    if(makeHead)recordHeadChange(db,previous,rev,previous==rev?std::string{}:hash(json(bundle(rev),false)),change);
    if(makeHead){Statement q(db,"INSERT INTO head(id,revision) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision");q.bind(1,rev);q.row();}
    sql(db,outer?"COMMIT":"RELEASE nex_save_program");return rev;
  }catch(...){sql(db,outer?"ROLLBACK":"ROLLBACK TO nex_save_program; RELEASE nex_save_program");throw;}
}
llvm::json::Value Store::declarations(const Program &p,const std::string &kind,const std::string &symbol,unsigned offset,unsigned limit){
  if(!graphDeclarationsReady(impl->db,p))save(p,"",false);return graphDeclarations(impl->db,p,kind,symbol,offset,limit);
}
llvm::json::Value Store::search(const Program &p,const GraphQueryOptions &options){
  validateGraphQuery(options,false);if(!graphDeclarationsReady(impl->db,p))save(p,"",false);return searchGraph(impl->db,p,options);
}
llvm::json::Value Store::subgraph(const Program &p,const GraphQueryOptions &options){
  validateGraphQuery(options,true);if(!graphDeclarationsReady(impl->db,p))save(p,"",false);return subgraphGraph(impl->db,p,options);
}
llvm::json::Value Store::identities(const Program &p,const std::string &kind,const std::string &symbol,unsigned offset,unsigned limit){
  if(!graphDeclarationsReady(impl->db,p))save(p,"",false);return graphIdentities(impl->db,p,kind,symbol,offset,limit);
}
llvm::json::Value Store::renameIdentity(const Program &p,const std::string &from,const std::string &to,const std::string &expectedHead){
  if(expectedHead.empty())throw Error("E_OPTION","identity rename requires an expected graph HEAD");
  sql(impl->db,"BEGIN IMMEDIATE");
  try{
    if(head(impl->db)!=(expectedHead=="EMPTY"?"":expectedHead))throw Error("E_CONFLICT","graph HEAD changed; read context and retry");
    auto result=renameGraphIdentity(impl->db,p,from,to);sql(impl->db,"COMMIT");return result;
  }catch(...){sql(impl->db,"ROLLBACK");throw;}
}
llvm::json::Value Store::reconcileIdentities(const Program &p,const llvm::json::Value &manifest,const std::string &expectedHead){
  if(expectedHead.empty())throw Error("E_OPTION","identity reconciliation requires an expected graph HEAD");
  sql(impl->db,"BEGIN IMMEDIATE");
  try{
    if(head(impl->db)!=(expectedHead=="EMPTY"?"":expectedHead))throw Error("E_CONFLICT","graph HEAD changed; read context and retry");
    if(!graphDeclarationsReady(impl->db,p))save(p,"",false);
    auto result=reconcileGraphIdentities(impl->db,p,manifest);sql(impl->db,"COMMIT");return result;
  }catch(...){sql(impl->db,"ROLLBACK");throw;}
}
llvm::json::Value Store::resolveIdentity(const Program &p,const std::string &origin,const std::string &sourceRevision,const std::string &id){
  if(!graphDeclarationsReady(impl->db,p))save(p,"",false);return resolveGraphIdentity(impl->db,p,origin,sourceRevision,id);
}
llvm::json::Value Store::operations(const Program &p,const std::string &symbol,const std::string &selector,unsigned offset,unsigned limit,bool context){
  bool ready=false;{Statement q(impl->db,"SELECT count(*) FROM operation_functions WHERE revision=?");q.bind(1,revision(p));q.row();ready=q.text(0)==std::to_string(p.functions.size());}
  if(!ready)save(p,"",false);return storedOperations(impl->db,p,symbol,selector,offset,limit,context);
}
llvm::json::Value Store::graph(const Program &p) {
  auto operationGraph=operations(p,"","",0,0);
  auto declarations=this->declarations(p,"","",0,0);auto declarationNodes=declarations.getAsObject()->getArray("nodes");
  llvm::json::Array nodes;
  for(const auto &f:p.functions){
    llvm::json::Array deps;for(const auto &d:f.dependencies){const auto &callee=p.function(d);deps.push_back(llvm::json::Object{{"name",d},{"id",nodeId(impl->db,callee.owner,callee.localName)}});}
    auto data=canonical(f);
    nodes.push_back(llvm::json::Object{{"id",nodeId(impl->db,f.owner,f.localName)},{"name",f.name},{"local_name",f.localName},{"module",f.owner},{"file",f.unit},{"native_symbol",nativeSymbol(f.name)},{"hash",hash(json(data,false))},{"definition",std::move(data)},
      {"source",p.definition(f)},{"line",int64_t(f.span.line)},{"dependencies",std::move(deps)}});
  }
  llvm::json::Array structures;for(const auto &s:p.structures)structures.push_back(canonical(s));
  llvm::json::Array endpoints;for(const auto &endpoint:p.endpoints){auto data=canonical(endpoint);const auto &handler=p.function(endpoint.target);endpoints.push_back(llvm::json::Object{{"id",nodeId(impl->db,endpoint.owner,"@endpoint/"+endpoint.localName)},{"name",endpoint.name},{"file",endpoint.unit},{"module",endpoint.owner},{"line",int64_t(endpoint.span.line)},{"source",p.definition(endpoint)},{"definition",data},{"hash",hash(json(data,false))},{"handler_id",nodeId(impl->db,handler.owner,handler.localName)}});}
  llvm::json::Array modules;
  for(const auto &[key,unit]:p.units){llvm::json::Array imports;for(const auto &dep:unit.imports)imports.push_back(llvm::json::Object{{"alias",dep.alias},{"path",dep.path},{"target",dep.target},{"module",p.units.at(dep.target).module}});llvm::json::Object module{{"file",key},{"name",unit.module},{"imports",std::move(imports)}};
    for(const auto &node:*declarationNodes){auto value=node.getAsObject();if(value->getString("kind")=="module"&&value->getString("symbol")==unit.module){module["id"]=value->getString("id")->str();module["hash"]=value->getString("hash")->str();module["context_hash"]=value->getString("context_hash")->str();break;}}modules.push_back(std::move(module));}
  return llvm::json::Object{{"schema","nex.graph/2"},{"language",programLanguage(p)},{"module",p.module},{"revision",revision(p)},{"identity_namespace",graphIdentityNamespace(impl->db)},{"source",p.source},{"path",p.path},{"bundle",sourceBundle(p)},{"nodes",std::move(nodes)},{"operation_graph",std::move(operationGraph)},{"declaration_graph",std::move(declarations)},{"structures",std::move(structures)},{"modules",std::move(modules)},{"endpoints",std::move(endpoints)}};
}
llvm::json::Value Store::history() {
  llvm::json::Array rows;Statement q(impl->db,"SELECT hash,module,created,language FROM revisions ORDER BY created DESC,hash");
  while(q.row())rows.push_back(llvm::json::Object{{"revision",q.text(0)},{"module",q.text(1)},{"created",q.text(2)},{"language",q.text(3)}});
  return llvm::json::Object{{"schema","nex.history/1"},{"head",head(impl->db)},{"revisions",std::move(rows)}};
}
llvm::json::Value Store::changes(unsigned offset,unsigned limit){
  bool outer=sqlite3_get_autocommit(impl->db)!=0;if(outer)sql(impl->db,"BEGIN");
  try{auto result=graphChanges(impl->db,offset,limit);if(outer)sql(impl->db,"COMMIT");return result;}
  catch(...){if(outer)sql(impl->db,"ROLLBACK");throw;}
}
std::string Store::source(const std::string &rev) {
  auto value=bundle(rev);auto obj=value.getAsObject();auto entry=obj?obj->getString("entry"):std::nullopt;auto files=obj?obj->getObject("files"):nullptr;
  if(!entry||!files||!files->getString(*entry))throw Error("E_STORE","invalid stored source snapshot");return files->getString(*entry)->str();
}
llvm::json::Value Store::bundle(const std::string &rev){
  std::string text,language;
  {Statement q(impl->db,impl->legacyLanguage?"SELECT source FROM revisions WHERE hash=?":"SELECT source,language FROM revisions WHERE hash=?");q.bind(1,rev=="HEAD"?head(impl->db):rev);if(!q.row())throw Error("E_REVISION","revision not found; run nex check first");text=q.text(0);language=impl->legacyLanguage?"0.1":q.text(1);}
  if(language=="0.1"||language=="0.2"){
    auto structured=llvm::json::parse(text);
    if(structured){if(auto object=structured->getAsObject();object&&object->getString("schema")=="nex.sources/1")
      throw Error("E_REVISION","stored legacy language contradicts its structured source bundle");}
    else llvm::consumeError(structured.takeError());
    return llvm::json::Object{{"schema","nex.sources/1"},{"entry","main.nex"},{"files",llvm::json::Object{{"main.nex",text}}}};
  }
  auto parsed=llvm::json::parse(text);if(!parsed)throw Error("E_REVISION",llvm::toString(parsed.takeError()));return std::move(*parsed);
}
std::string Store::headRevision(){return head(impl->db);}
std::string Store::identityNamespace(){return graphIdentityNamespace(impl->db);}
void Store::recordTask(const std::string &id,const std::string &task,const std::string &taskHash,const std::string &status,const std::string &report,const std::string &reportHash){
  Statement q(impl->db,"INSERT INTO task_runs(id,task,task_hash,status,report,report_hash) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,report_hash=excluded.report_hash");
  q.bind(1,id);q.bind(2,task);q.bind(3,taskHash);q.bind(4,status);q.bind(5,report);q.bind(6,reportHash);q.row();
}
llvm::json::Value Store::taskHistory(const std::string &task,unsigned limit){
  Statement q(impl->db,"SELECT id,task_hash,status,report,report_hash,created FROM task_runs WHERE task=? ORDER BY created DESC,id DESC LIMIT ?");q.bind(1,task);q.bind(2,std::to_string(std::min(limit,50u)));llvm::json::Array rows;
  while(q.row())rows.push_back(llvm::json::Object{{"run_id",q.text(0)},{"task_hash",q.text(1)},{"status",q.text(2)},{"report",q.text(3)},{"report_hash",q.text(4)},{"created",q.text(5)}});
  return llvm::json::Object{{"schema","nex.task-history/1"},{"task",task},{"runs",std::move(rows)}};
}
std::string Store::revisionLanguage(const std::string &rev){
  if(impl->legacyLanguage){if(!containsRevision(rev))throw Error("E_REVISION","revision not found");return "0.1";}
  Statement q(impl->db,"SELECT language FROM revisions WHERE hash=?");q.bind(1,rev=="HEAD"?head(impl->db):rev);
  if(!q.row())throw Error("E_REVISION","revision not found");return q.text(0);
}
bool Store::containsRevision(const std::string &rev){
  Statement q(impl->db,"SELECT 1 FROM revisions WHERE hash=?");q.bind(1,rev=="HEAD"?head(impl->db):rev);return q.row();
}
std::filesystem::path projectRoot(std::filesystem::path start) {
  start=std::filesystem::absolute(start);
  auto original=start;
  while(!start.empty()){
    if(std::filesystem::exists(start/"nex.json"))return start;
    auto parent=start.parent_path();if(parent==start)break;start=parent;
  }
  return original;
}
}
