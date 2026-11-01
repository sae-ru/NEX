#include "nex/graph_snapshot.h"
#include "nex/language.h"
#include "nex_value.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/SHA256.h"
#include <sqlite3.h>
#include <array>
#include <chrono>
#include <cerrno>
#include <ctime>
#include <filesystem>
#include <fcntl.h>
#include <map>
#include <limits>
#include <set>
#include <sys/stat.h>
#include <unistd.h>
#ifdef _WIN32
#include "nex_host_windows.h"
#endif

namespace nex {
namespace {
namespace fs=std::filesystem;
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
struct Deadline {
  std::chrono::steady_clock::time_point end;
  explicit Deadline(unsigned seconds){if(!seconds||seconds>3600)throw Error("E_OPTION","snapshot timeout must be 1..3600 seconds");end=std::chrono::steady_clock::now()+std::chrono::seconds(seconds);}
  bool expired()const{return std::chrono::steady_clock::now()>=end;}
  void check()const{if(expired())throw Error("E_SNAPSHOT_TIMEOUT","graph snapshot operation exceeded its deadline");}
};
struct File {
  int fd=-1;
  File(const fs::path &path,int flags)
#ifdef _WIN32
    :fd(nexrt::host_windows::openRegularDescriptor(path,flags)){
#else
    :fd(::open(path.c_str(),flags|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK,0600)){
#endif
    struct stat info{};if(fd<0||::fstat(fd,&info)||!S_ISREG(info.st_mode)){if(fd>=0)::close(fd);fd=-1;throw Error("E_SNAPSHOT_FILE","snapshot member requires a regular non-symlink file");}
  }
  ~File(){if(fd>=0)::close(fd);}
  File(const File&)=delete;File&operator=(const File&)=delete;
};
struct Output {
  fs::path path;bool retained=false;
#ifdef _WIN32
  std::optional<nexrt::host_windows::Identity> identity;
#else
  dev_t device;ino_t inode;
#endif
  explicit Output(const std::string &directory){
    path=fs::absolute(directory).lexically_normal();fs::create_directories(path.parent_path());
#ifdef _WIN32
    if(!nexrt::host_windows::createPrivateDirectory(path))throw Error(errno==EEXIST?"E_EXISTS":"E_SNAPSHOT_FILE","snapshot/recovery requires a new output directory");
    identity=nexrt::host_windows::identity(path);if(!identity||!identity->directory)throw Error("E_SNAPSHOT_FILE","cannot identify snapshot output directory");
#else
    if(::mkdir(path.c_str(),0700))throw Error(errno==EEXIST?"E_EXISTS":"E_SNAPSHOT_FILE","snapshot/recovery requires a new output directory");
    struct stat info{};if(::lstat(path.c_str(),&info)){::rmdir(path.c_str());throw Error("E_SNAPSHOT_FILE","cannot identify output directory");}device=info.st_dev;inode=info.st_ino;
#endif
  }
#ifdef _WIN32
  ~Output(){if(!retained&&nexrt::host_windows::identity(path)==identity){std::error_code error;fs::remove_all(path,error);}}
#else
  ~Output(){if(retained)return;struct stat info{};if(!::lstat(path.c_str(),&info)&&S_ISDIR(info.st_mode)&&info.st_dev==device&&info.st_ino==inode){std::error_code error;fs::remove_all(path,error);}}
#endif
};
void failure(int code,const std::string &operation,Deadline &deadline,std::string detail={}){deadline.check();if(detail.size()>1024)detail.resize(1024);throw Error("E_SNAPSHOT",operation+" failed (SQLite "+std::to_string(code)+": "+sqlite3_errstr(code)+(detail.empty()?"":"; "+detail)+")");}
struct Database {
  sqlite3 *db=nullptr;Deadline &deadline;
  Database(const fs::path &path,bool writable,Deadline &deadline):deadline(deadline){
    File regular(path,O_RDONLY);
    int flags=(writable?SQLITE_OPEN_READWRITE:SQLITE_OPEN_READONLY)|SQLITE_OPEN_FULLMUTEX|SQLITE_OPEN_NOFOLLOW;
    auto filename=fs::canonical(path.parent_path())/path.filename();
    auto rc=sqlite3_open_v2(filename.string().c_str(),&db,flags,nullptr);if(rc!=SQLITE_OK){if(db)sqlite3_close(db);db=nullptr;failure(rc,"open graph database",deadline);}
    sqlite3_busy_timeout(db,25);sqlite3_enable_load_extension(db,0);
    sqlite3_db_config(db,SQLITE_DBCONFIG_DEFENSIVE,1,nullptr);sqlite3_db_config(db,SQLITE_DBCONFIG_TRUSTED_SCHEMA,0,nullptr);
    sqlite3_limit(db,SQLITE_LIMIT_SQL_LENGTH,1048576);sqlite3_limit(db,SQLITE_LIMIT_EXPR_DEPTH,128);sqlite3_limit(db,SQLITE_LIMIT_ATTACHED,0);
    sqlite3_progress_handler(db,1000,[](void *p){return static_cast<Deadline*>(p)->expired()?1:0;},&deadline);
    sqlite3_set_authorizer(db,[](void*,int action,const char *first,const char *second,const char*,const char*){
      if(action==SQLITE_ATTACH||action==SQLITE_DETACH||action==SQLITE_CREATE_VTABLE||action==SQLITE_DROP_VTABLE)return SQLITE_DENY;
      // SQLite3.54 authorizes timestamp defaults during quick_check. The
      // graph's own created defaults use this read-only builtin.
      if(action==SQLITE_FUNCTION){std::string name=second?second:first?first:"";if(name!="count"&&name!="length"&&name!="typeof"&&name!="strftime")return SQLITE_DENY;}
      return SQLITE_OK;
    },nullptr);
  }
  ~Database(){if(db)sqlite3_close(db);}
  Database(const Database&)=delete;Database&operator=(const Database&)=delete;
  void close(){if(!db)return;auto rc=sqlite3_close(db);if(rc!=SQLITE_OK)failure(rc,"close graph database",deadline);db=nullptr;}
};
struct Query {
  Database &connection;sqlite3_stmt *statement=nullptr;
  Query(Database &db,const std::string &sql):connection(db){for(;;){db.deadline.check();auto rc=sqlite3_prepare_v2(db.db,sql.c_str(),-1,&statement,nullptr);if(rc==SQLITE_OK)break;std::string detail=sqlite3_errmsg(db.db);if(statement){sqlite3_finalize(statement);statement=nullptr;}if(rc==SQLITE_BUSY||rc==SQLITE_LOCKED){sqlite3_sleep(10);continue;}failure(rc,"prepare graph snapshot query",db.deadline,detail);}}
  ~Query(){sqlite3_finalize(statement);}
  void bind(int index,const std::string &text){auto rc=sqlite3_bind_text(statement,index,text.data(),int(text.size()),SQLITE_TRANSIENT);if(rc!=SQLITE_OK)failure(rc,"bind snapshot metadata",connection.deadline);}
  bool row(){for(;;){connection.deadline.check();auto rc=sqlite3_step(statement);if(rc==SQLITE_ROW)return true;if(rc==SQLITE_DONE)return false;if(rc==SQLITE_BUSY||rc==SQLITE_LOCKED){sqlite3_sleep(10);continue;}failure(rc,"read graph snapshot",connection.deadline);}}
  std::string text(int column){auto p=sqlite3_column_text(statement,column);return p?std::string(reinterpret_cast<const char*>(p),sqlite3_column_bytes(statement,column)):"";}
  int64_t integer(int column){return sqlite3_column_int64(statement,column);}
};
void sql(Database &db,const std::string &text){Query query(db,text);while(query.row()){};}
std::string identifier(const std::string &name){std::string result="\"";for(char c:name){if(c=='"')result+='"';result+=c;}return result+'"';}
bool digest(const std::string &text,size_t length=64,bool empty=false){return (empty&&text.empty())||(text.size()==length&&text.find_first_not_of("0123456789abcdef")==std::string::npos);}
std::string metadata(Database &db,const std::string &key){Query query(db,"SELECT value FROM metadata WHERE key=?");query.bind(1,key);if(!query.row())return {};auto text=query.text(0);if(text.size()>128)throw Error("E_SNAPSHOT_FORMAT","oversized graph metadata");return text;}
Object summary(Database &db){
  std::set<std::string> tables;
  {Query objects(db,"SELECT type FROM sqlite_schema WHERE type IN ('view','trigger')");if(objects.row())throw Error("E_SNAPSHOT_FORMAT","graph snapshots do not accept views or triggers");}
  {Query list(db,"PRAGMA table_list");while(list.row()){
    if(list.text(0)!="main"||list.text(1)=="sqlite_schema")continue;
    auto name=list.text(1),kind=list.text(2);if(kind!="table"||name.size()>128||name.find('\0')!=std::string::npos||tables.size()>=64)throw Error("E_SNAPSHOT_FORMAT","unsupported graph table kind/name/count");
    try{nexrt::unicodeOffsets(name,false);}catch(const nexrt::DataError&){throw Error("E_SNAPSHOT_FORMAT","graph table names must be UTF-8");}tables.insert(name);
  }}
  std::map<std::string,std::set<std::string>> columns;
  for(const auto &table:tables){Query info(db,"PRAGMA table_xinfo("+identifier(table)+")");while(info.row()){if(info.integer(6))throw Error("E_SNAPSHOT_FORMAT","graph snapshots do not accept generated or hidden columns");columns[table].insert(info.text(1));}}
  for(const auto &table:{"metadata","revisions","head","node_ids","nodes","edges"})if(!tables.contains(table))throw Error("E_SNAPSHOT_FORMAT","graph database lacks a required table");
  for(const auto &[table,column]:std::vector<std::pair<std::string,std::string>>{{"metadata","key"},{"metadata","value"},{"revisions","hash"},{"head","id"},{"head","revision"}})if(!columns[table].contains(column))throw Error("E_SNAPSHOT_FORMAT","graph database lacks a required column");
  auto version=metadata(db,"schema");if(version!="1"&&version!="2"&&version!="3"&&version!="4")throw Error("E_SCHEMA","snapshot requires graph schema 1..4");
  Object counts;for(const auto &table:tables){Query count(db,"SELECT count(*) FROM "+identifier(table));count.row();counts[table]=count.integer(0);}
  std::string head,language;
  {Query query(db,"SELECT revision FROM head WHERE id=1");if(query.row())head=query.text(0);}
  if(!digest(head,64,true)||*counts.getInteger("head")>(head.empty()?0:1))throw Error("E_SNAPSHOT_FORMAT","invalid graph HEAD");
  if(!head.empty()){
    if(version!="1"&&!columns["revisions"].contains("language"))throw Error("E_SNAPSHOT_FORMAT","graph revisions lack language metadata");
    Query query(db,version=="1"?"SELECT '0.1' FROM revisions WHERE hash=?":"SELECT language FROM revisions WHERE hash=?");query.bind(1,head);if(!query.row())throw Error("E_SNAPSHOT_FORMAT","graph HEAD revision is missing");language=query.text(0);
    if(language.empty()||language.size()>32||language.find('\0')!=std::string::npos)throw Error("E_SNAPSHOT_FORMAT","invalid graph HEAD language");
    try{nexrt::unicodeOffsets(language,false);}catch(const nexrt::DataError&){throw Error("E_SNAPSHOT_FORMAT","invalid graph language UTF-8");}
  }
  auto nameSpace=metadata(db,"identity_namespace");if(!digest(nameSpace,32,true))throw Error("E_SNAPSHOT_FORMAT","invalid graph identity namespace");
  {Query check(db,"PRAGMA quick_check");if(!check.row()||check.text(0)!="ok"||check.row())throw Error("E_SNAPSHOT_FORMAT","graph database integrity check failed");}
  {Query check(db,"PRAGMA foreign_key_check");if(check.row())throw Error("E_SNAPSHOT_FORMAT","graph database foreign key check failed");}
  return Object{{"graph_schema",int64_t(version[0]-'0')},{"head",head},{"head_language",language},{"namespace",nameSpace},{"table_counts",std::move(counts)}};
}
void syncDirectory(const fs::path &path){
#ifdef _WIN32
  nexrt::host_windows::Handle directory(CreateFileW(path.c_str(),GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
    nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_BACKUP_SEMANTICS,nullptr));
  auto id=nexrt::host_windows::identity(directory.value);
  if(!id||!id->directory||!FlushFileBuffers(directory.value))throw Error("E_SNAPSHOT_FILE","cannot synchronize Windows snapshot directory");
#else
  int fd=::open(path.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
  if(fd<0)throw Error("E_SNAPSHOT_FILE","cannot open snapshot directory for synchronization");
  auto result=::fsync(fd);::close(fd);if(result)throw Error("E_SNAPSHOT_FILE","cannot synchronize snapshot directory");
#endif
}
void syncFile(File &file){
#ifdef _WIN32
  if(nexrt::host_windows::synchronize(file.fd))
#else
  if(::fsync(file.fd))
#endif
    throw Error("E_SNAPSHOT_FILE","cannot synchronize snapshot file");
}
void write(const fs::path &path,const std::string &text){File file(path,O_WRONLY|O_CREAT|O_EXCL);size_t offset=0;while(offset<text.size()){auto count=::write(file.fd,text.data()+offset,text.size()-offset);if(count<0){if(errno==EINTR)continue;throw Error("E_SNAPSHOT_FILE","cannot write snapshot metadata");}if(!count)throw Error("E_SNAPSHOT_FILE","short snapshot write");offset+=size_t(count);}syncFile(file);}
struct Digest {std::string sha;int64_t bytes;};
Digest copyHash(const fs::path &source,const fs::path *destination,Deadline &deadline){
  File input(source,O_RDONLY);std::unique_ptr<File> output;if(destination)output=std::make_unique<File>(*destination,O_WRONLY|O_CREAT|O_EXCL);
  llvm::SHA256 hash;std::array<uint8_t,65536> buffer{};int64_t bytes=0;
  for(;;){deadline.check();auto count=::read(input.fd,buffer.data(),buffer.size());if(count<0){if(errno==EINTR)continue;throw Error("E_SNAPSHOT_FILE","cannot read snapshot database");}if(!count)break;
    if(bytes>std::numeric_limits<int64_t>::max()-count)throw Error("E_SNAPSHOT_FILE","snapshot database size exceeds supported range");bytes+=count;hash.update(llvm::ArrayRef<uint8_t>(buffer.data(),size_t(count)));
    if(output){size_t offset=0;while(offset<size_t(count)){deadline.check();auto n=::write(output->fd,buffer.data()+offset,size_t(count)-offset);if(n<0){if(errno==EINTR)continue;throw Error("E_SNAPSHOT_FILE","cannot copy snapshot database");}if(!n)throw Error("E_SNAPSHOT_FILE","short database copy");offset+=size_t(n);}}
  }
  if(output)syncFile(*output);auto raw=hash.final();std::string result;const char *hex="0123456789abcdef";for(auto byte:raw){result+=hex[byte>>4];result+=hex[byte&15];}return {result,bytes};
}
std::string readManifest(const fs::path &path){
  File file(path,O_RDONLY);std::string result;std::array<char,8192> buffer{};
  for(;;){auto count=::read(file.fd,buffer.data(),buffer.size());if(count<0){if(errno==EINTR)continue;throw Error("E_SNAPSHOT_FILE","cannot read snapshot manifest");}if(!count)break;if(result.size()+size_t(count)>65536)throw Error("E_SNAPSHOT_FORMAT","snapshot manifest exceeds 65536 bytes");result.append(buffer.data(),size_t(count));}
  try{nexrt::unicodeOffsets(result,false);}catch(const nexrt::DataError&){throw Error("E_SNAPSHOT_FORMAT","snapshot manifest must be UTF-8");}
  unsigned depth=0;bool quoted=false,escape=false;for(char c:result){if(quoted){if(escape)escape=false;else if(c=='\\')escape=true;else if(c=='"')quoted=false;continue;}if(c=='"')quoted=true;else if(c=='{'||c=='['){if(++depth>16)throw Error("E_SNAPSHOT_FORMAT","snapshot manifest exceeds depth 16");}else if((c=='}'||c==']')&&depth)--depth;}
  return result;
}
std::string created(){auto value=std::time(nullptr);std::tm utc{};
#ifdef _WIN32
  if(gmtime_s(&utc,&value))
#else
  if(!gmtime_r(&value,&utc))
#endif
    throw Error("E_SNAPSHOT","cannot read UTC time");char text[32];std::strftime(text,sizeof(text),"%Y-%m-%dT%H:%M:%SZ",&utc);return text;}
}
JSON createGraphSnapshot(const std::string &root,const std::string &directory,unsigned timeoutSeconds){
  Deadline deadline(timeoutSeconds);Database source(fs::path(root)/".nex/graph.db",false,deadline);
  sql(source,"BEGIN");{Query pin(source,"SELECT name FROM sqlite_schema LIMIT 1");(void)pin.row();}
  Output output(directory);auto path=output.path/"graph.db";write(path,"");Object state;
  {
    Database destination(path,true,deadline);auto backup=sqlite3_backup_init(destination.db,"main",source.db,"main");if(!backup)failure(sqlite3_errcode(destination.db),"initialize graph backup",deadline);
    struct Backup {sqlite3_backup *handle;~Backup(){if(handle)sqlite3_backup_finish(handle);}} guard{backup};
    for(;;){deadline.check();auto code=sqlite3_backup_step(backup,256);if(code==SQLITE_DONE)break;if(code==SQLITE_BUSY||code==SQLITE_LOCKED){sqlite3_sleep(10);continue;}if(code!=SQLITE_OK)failure(code,"copy graph backup",deadline);}
    auto code=sqlite3_backup_finish(backup);guard.handle=nullptr;if(code!=SQLITE_OK)failure(code,"finish graph backup",deadline);
    sql(destination,"PRAGMA journal_mode=DELETE");state=summary(destination);destination.close();
  }
  sql(source,"ROLLBACK");source.close();{
#ifdef _WIN32
    // FlushFileBuffers requires write access to the newly created backup.
    File file(path,O_RDWR);
#else
    File file(path,O_RDONLY);
#endif
    syncFile(file);
  }auto data=copyHash(path,nullptr,deadline);
  auto selectedHead=state.getString("head")->str(),selectedNamespace=state.getString("namespace")->str();auto selectedSchema=*state.getInteger("graph_schema");
  Object manifest{{"schema","nex.graph-snapshot/1"},{"created",created()},{"toolchain",NEX_VERSION},{"compiler_build",NEX_BUILD_ID},
    {"database",Object{{"file","graph.db"},{"sha256",data.sha},{"bytes",data.bytes}}},{"state",std::move(state)},
    {"contents",Array{"graph_database","archived_sources","local_identities","identity_aliases","change_journal","task_run_index"}},{"external_artifacts_included",false}};
  write(output.path/"snapshot.json",json(std::move(manifest))+"\n");syncDirectory(output.path);syncDirectory(fs::canonical(output.path.parent_path()));deadline.check();output.retained=true;
  return Object{{"schema","nex.snapshot-result/1"},{"ok",true},{"directory",output.path.string()},{"manifest",(output.path/"snapshot.json").string()},{"database_sha256",data.sha},{"bytes",data.bytes},{"source_unchanged",true},{"head",selectedHead},{"namespace",selectedNamespace},{"graph_schema",selectedSchema}};
}
JSON recoverGraphSnapshot(const std::string &snapshot,const std::string &directory,unsigned timeoutSeconds){
  Deadline deadline(timeoutSeconds);auto input=fs::absolute(snapshot).lexically_normal();auto text=readManifest(input/"snapshot.json");
  auto value=llvm::json::parse(text);if(!value){llvm::consumeError(value.takeError());throw Error("E_SNAPSHOT_FORMAT","invalid snapshot JSON");}auto manifest=value->getAsObject();
  const std::set<std::string> fields={"schema","created","toolchain","compiler_build","database","state","contents","external_artifacts_included"};
  if(!manifest||manifest->size()!=fields.size())throw Error("E_SNAPSHOT_FORMAT","invalid snapshot manifest fields");for(const auto &[key,v]:*manifest){(void)v;if(!fields.contains(key.str()))throw Error("E_SNAPSHOT_FORMAT","unknown snapshot manifest field");}
  auto database=manifest->getObject("database"),state=manifest->getObject("state");auto contents=manifest->getArray("contents");
  if(manifest->getString("schema")!="nex.graph-snapshot/1"||manifest->getBoolean("external_artifacts_included")!=false||!database||database->size()!=3||database->getString("file")!="graph.db"||!database->getString("sha256")||!digest(database->getString("sha256")->str())||!database->getInteger("bytes")||*database->getInteger("bytes")<512||!state||!contents||contents->size()!=6||!manifest->getString("created")||!manifest->getString("toolchain")||!manifest->getString("compiler_build")||!digest(manifest->getString("compiler_build")->str()))throw Error("E_SNAPSHOT_FORMAT","invalid snapshot manifest values");
  auto creator=manifest->getString("toolchain")->str(),timestamp=manifest->getString("created")->str();
  if(creator.empty()||creator.size()>64||creator.find('\0')!=std::string::npos||timestamp.size()!=20)throw Error("E_SNAPSHOT_FORMAT","invalid snapshot creator/time metadata");
  for(size_t n=0;n<timestamp.size();++n){char fixed=n==4||n==7?'-':n==10?'T':n==13||n==16?':':n==19?'Z':0;if(fixed?timestamp[n]!=fixed:timestamp[n]<'0'||timestamp[n]>'9')throw Error("E_SNAPSHOT_FORMAT","invalid snapshot timestamp");}
  Array expectedContents{"graph_database","archived_sources","local_identities","identity_aliases","change_journal","task_run_index"};if(*contents!=expectedContents)throw Error("E_SNAPSHOT_FORMAT","unsupported snapshot contents");
  Output output(directory);auto dataDirectory=output.path/".nex";
#ifdef _WIN32
  if(!nexrt::host_windows::createPrivateDirectory(dataDirectory))
#else
  if(::mkdir(dataDirectory.c_str(),0700))
#endif
    throw Error("E_SNAPSHOT_FILE","cannot create recovered graph directory");auto target=dataDirectory/"graph.db";
  auto data=copyHash(input/"graph.db",&target,deadline);if(data.sha!=database->getString("sha256")->str()||data.bytes!=*database->getInteger("bytes"))throw Error("E_SNAPSHOT_INTEGRITY","snapshot database does not match its manifest digest/size");
  Object recovered;
  {Database db(target,false,deadline);recovered=summary(db);db.close();}
  if(recovered!=*state)throw Error("E_SNAPSHOT_INTEGRITY","snapshot database metadata does not match its manifest");
  auto language=recovered.getString("head_language")->str();write(output.path/"nex.json",json(Object{{"schema","nex.project/1"},{"language",language.empty()?languageVersion:language},{"entry","main.nex"}})+"\n");
  write(output.path/"RECOVERY.md","# Recovered NEX graph\n\nArchived sources and local identities are in `.nex/graph.db`.\nUse `nex history`, then commands with `--revision HEAD`; export to a new\ndirectory to materialize source. Older languages need their matching SDK\nor explicit migration. External receipt/artifact files, application data and\ncompiler/SDK dependencies are separate from this graph snapshot.\n");
  syncDirectory(dataDirectory);syncDirectory(output.path);syncDirectory(fs::canonical(output.path.parent_path()));deadline.check();output.retained=true;
  return Object{{"schema","nex.recovery-result/1"},{"ok",true},{"directory",output.path.string()},{"database_sha256",data.sha},{"head",recovered.getString("head")->str()},{"namespace",recovered.getString("namespace")->str()},{"graph_schema",*recovered.getInteger("graph_schema")},{"materialized",false},{"existing_project_unchanged",true}};
}
}
