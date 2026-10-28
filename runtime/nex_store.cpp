#include "nex_io.h"
#include <sqlite3.h>
#include <functional>

namespace nexrt {
namespace {
thread_local Database *currentDatabase=nullptr;
struct Connection {
  sqlite3 *db=nullptr;
  explicit Connection(const std::string &path){
    if(path.empty()||path==":memory:"||path.starts_with("file:")||path.find('\0')!=std::string::npos)throw DataError("VALIDATION","database capability requires a filesystem path");
    int rc=sqlite3_open_v2(path.c_str(),&db,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE|SQLITE_OPEN_NOMUTEX,nullptr);
    if(rc!=SQLITE_OK){if(db)sqlite3_close(db);db=nullptr;throw DataError("E_STORE","cannot open configured database");}
    sqlite3_busy_timeout(db,1000);sqlite3_extended_result_codes(db,1);
    if(sqlite3_exec(db,"PRAGMA synchronous=FULL",nullptr,nullptr,nullptr)!=SQLITE_OK){sqlite3_close(db);db=nullptr;throw DataError("E_STORE","cannot configure database durability");}
  }
  ~Connection(){if(db)sqlite3_close(db);}
};
void verify(sqlite3 *db,int status){
  if(status==SQLITE_OK||status==SQLITE_ROW||status==SQLITE_DONE)return;
  int code=sqlite3_extended_errcode(db)&0xff;throw DataError(code==SQLITE_BUSY||code==SQLITE_LOCKED?"STORE_BUSY":"E_STORE","database operation failed");
}
void execute(sqlite3 *db,const char *sql){verify(db,sqlite3_exec(db,sql,nullptr,nullptr,nullptr));}
struct Statement {
  sqlite3 *db;sqlite3_stmt *statement=nullptr;
  Statement(sqlite3 *db,const char *sql):db(db){int result=sqlite3_prepare_v2(db,sql,-1,&statement,nullptr);if(result!=SQLITE_OK){sqlite3_finalize(statement);statement=nullptr;verify(db,result);}}
  ~Statement(){sqlite3_finalize(statement);}
  void text(int at,const std::string &value){verify(db,sqlite3_bind_text(statement,at,value.data(),int(value.size()),SQLITE_TRANSIENT));}
  bool row(){int result=sqlite3_step(statement);verify(db,result);return result==SQLITE_ROW;}
  std::string value(int at){auto *data=sqlite3_column_blob(statement,at);return data?std::string(static_cast<const char*>(data),sqlite3_column_bytes(statement,at)):"";}
};
bool validKey(const std::string &key,bool prefix=false){return (prefix||!key.empty())&&key.size()<=1024&&key.find('\0')==std::string::npos;}
Value operation(const std::function<Value(Database&)> &call,bool writable){
  if(currentDatabase)return call(*currentDatabase);
  try{
    auto path=platform::environment("NEX_DATABASE"),owner=platform::environment("NEX_STORAGE_OWNER");
    if(!path||path->empty())return failure("CAPABILITY","database capability is not configured");
    Database::initialize(*path);Database database(*path,owner?*owner:"local",writable);auto result=call(database);
    if(!isSuccess(result)){database.rollback();return result;}
    auto committed=database.commit();return isSuccess(committed)?result:committed;
  }catch(const DataError &e){return failure(e.code,e.what());}
}
}
struct Database::Impl {
  Connection connection;std::string principal;bool writable,active=false,failed=false;
  Impl(const std::string &path,const std::string &principal,bool writable):connection(path),principal(principal),writable(writable){
    unicodeOffsets(principal,false);if(principal.empty()||principal.size()>256||principal.find('\0')!=std::string::npos)throw DataError("VALIDATION","invalid database principal");
    execute(connection.db,writable?"BEGIN IMMEDIATE":"BEGIN");active=true;
  }
};
void Database::initialize(const std::string &path){
  Connection connection(path);
  {Statement mode(connection.db,"PRAGMA journal_mode");if(!mode.row())throw DataError("E_STORE","cannot read database journal mode");auto current=mode.value(0);if(current!="wal"){sqlite3_finalize(mode.statement);mode.statement=nullptr;execute(connection.db,"PRAGMA journal_mode=WAL");}}
  execute(connection.db,"PRAGMA synchronous=FULL; CREATE TABLE IF NOT EXISTS nex_kv(owner TEXT NOT NULL,key TEXT NOT NULL,value BLOB NOT NULL,PRIMARY KEY(owner,key));");
  {
    Statement columns(connection.db,"PRAGMA table_info(nex_kv)");
    const std::vector<std::string> names={"owner","key","value"},types={"TEXT","TEXT","BLOB"};size_t count=0;
    while(columns.row()){
      if(count>=3||columns.value(1)!=names[count]||columns.value(2)!=types[count]||sqlite3_column_int(columns.statement,3)!=1||sqlite3_column_int(columns.statement,5)!=(count<2?int(count)+1:0))throw DataError("E_STORE_SCHEMA","incompatible storage table schema");++count;
    }
    if(count!=3)throw DataError("E_STORE_SCHEMA","incompatible storage table schema");
    Statement indices(connection.db,"SELECT name FROM pragma_index_list('nex_kv') WHERE origin='pk' AND \"unique\"=1 AND partial=0");
    if(!indices.row())throw DataError("E_STORE_SCHEMA","storage table requires a primary index");auto name=indices.value(0);
    Statement fields(connection.db,"SELECT name,coll FROM pragma_index_xinfo(?) WHERE key=1 ORDER BY seqno");fields.text(1,name);count=0;
    while(fields.row()){if(count>=2||fields.value(0)!=names[count]||fields.value(1)!="BINARY")throw DataError("E_STORE_SCHEMA","storage principal/key collation must be binary");++count;}
    if(count!=2)throw DataError("E_STORE_SCHEMA","incompatible storage primary index");
  }
}
Database::Database(const std::string &path,const std::string &principal,bool writable):impl(std::make_unique<Impl>(path,principal,writable)){}
Database::~Database(){rollback();}
void Database::rollback(){if(impl->active){sqlite3_exec(impl->connection.db,"ROLLBACK",nullptr,nullptr,nullptr);impl->active=false;}}
Value Database::commit(){
  if(!impl->active)return failure("E_STORE","transaction is no longer active");
  if(impl->failed){rollback();return failure("TRANSACTION_ABORTED","a storage operation failed; transaction rolled back");}
  try{execute(impl->connection.db,"COMMIT");impl->active=false;return success(Value(1,true));}
  catch(const DataError &e){rollback();return failure(e.code,e.what());}
}
Value Database::get(const std::string &key){
  if(!validKey(key))return failure("VALIDATION","invalid storage key");
  try{
    Statement q(impl->connection.db,"SELECT value FROM nex_kv WHERE owner=? AND key=?");q.text(1,impl->principal);q.text(2,key);
    if(!q.row())return failure("NOT_FOUND","storage key does not exist");return success(Value(string(q.value(0))));
  }catch(const DataError &e){impl->failed=true;return failure(e.code,e.what());}
}
Value Database::put(const std::string &key,const std::string &value){
  if(!impl->writable||!validKey(key)||value.size()>1024*1024){impl->failed=true;return failure("VALIDATION","write is not allowed or storage key/value exceeds limits");}
  try{
    Statement q(impl->connection.db,"INSERT INTO nex_kv(owner,key,value) VALUES(?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value");q.text(1,impl->principal);q.text(2,key);
    verify(impl->connection.db,sqlite3_bind_blob(q.statement,3,value.data(),int(value.size()),SQLITE_TRANSIENT));q.row();return success(Value(1,true));
  }catch(const DataError &e){impl->failed=true;return failure(e.code,e.what());}
}
Value Database::remove(const std::string &key){
  if(!impl->writable||!validKey(key)){impl->failed=true;return failure("VALIDATION","write is not allowed or storage key is invalid");}
  try{Statement q(impl->connection.db,"DELETE FROM nex_kv WHERE owner=? AND key=?");q.text(1,impl->principal);q.text(2,key);q.row();return success(Value(sqlite3_changes(impl->connection.db)!=0,true));}
  catch(const DataError &e){impl->failed=true;return failure(e.code,e.what());}
}
Value Database::keys(const std::string &prefix){
  if(!validKey(prefix,true))return failure("VALIDATION","invalid storage prefix");
  try{
    Statement q(impl->connection.db,"SELECT key FROM nex_kv WHERE owner=? AND substr(key,1,length(?))=? ORDER BY key COLLATE BINARY LIMIT 10001");q.text(1,impl->principal);q.text(2,prefix);q.text(3,prefix);
    auto data=std::make_shared<Data>(Data::List);while(q.row()){if(data->values.size()==10000)return failure("LIMIT","storage key result exceeds item limit");data->values.emplace_back(string(q.value(0)));}return success(Value(data));
  }catch(const DataError &e){impl->failed=true;return failure(e.code,e.what());}
}
StorageScope::StorageScope(Database &database):previous(currentDatabase){currentDatabase=&database;}
StorageScope::~StorageScope(){currentDatabase=previous;}
Value storageGet(const std::string &key){return operation([&](Database &db){return db.get(key);},false);}
Value storagePut(const std::string &key,const std::string &value){return operation([&](Database &db){return db.put(key,value);},true);}
Value storageRemove(const std::string &key){return operation([&](Database &db){return db.remove(key);},true);}
Value storageKeys(const std::string &prefix){return operation([&](Database &db){return db.keys(prefix);},false);}
}
