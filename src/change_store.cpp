#include "nex/change_store.h"
#include "nex/language.h"
#include "nex/graph_store.h"
#include "nex_value.h"
#include "llvm/Support/Error.h"
#include <sqlite3.h>
#include <limits>
#include <set>

namespace nex {
namespace {
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
struct Query {
  sqlite3 *db;sqlite3_stmt *stmt=nullptr;
  Query(sqlite3 *db,const char *sql):db(db){if(sqlite3_prepare_v2(db,sql,-1,&stmt,nullptr)!=SQLITE_OK)throw Error("E_STORE",sqlite3_errmsg(db));}
  ~Query(){sqlite3_finalize(stmt);}
  void bind(int index,const std::string &value){if(sqlite3_bind_text(stmt,index,value.data(),int(value.size()),SQLITE_TRANSIENT)!=SQLITE_OK)throw Error("E_STORE",sqlite3_errmsg(db));}
  bool row(){auto code=sqlite3_step(stmt);if(code==SQLITE_ROW)return true;if(code==SQLITE_DONE)return false;throw Error("E_STORE",sqlite3_errmsg(db));}
  std::string text(int column){auto p=sqlite3_column_text(stmt,column);return p?std::string(reinterpret_cast<const char*>(p),sqlite3_column_bytes(stmt,column)):"";}
};
void sql(sqlite3 *db,const char *text){char *message=nullptr;if(sqlite3_exec(db,text,nullptr,nullptr,&message)!=SQLITE_OK){std::string error=message?message:"change journal database error";sqlite3_free(message);throw Error("E_STORE",error);}}
bool digest(const std::string &value,size_t length=64,bool empty=false){return (empty&&value.empty())||(value.size()==length&&value.find_first_not_of("0123456789abcdef")==std::string::npos);}
const std::set<std::string> actions={"save","synchronize","apply","import","migrate","restore"};
std::string metadata(sqlite3 *db,const char *key){Query q(db,"SELECT value FROM metadata WHERE key=?");q.bind(1,key);if(!q.row())throw Error("E_CHANGE_INTEGRITY","missing change journal metadata");return q.text(0);}
std::string head(sqlite3 *db){Query q(db,"SELECT revision FROM head WHERE id=1");return q.row()?q.text(0):"";}
[[noreturn]] void invalid(){throw Error("E_CHANGE_INTEGRITY","stored change record or adjacent journal link is invalid");}
std::string string(const Object &object,const char *key){auto value=object.getString(key);if(!value)invalid();return value->str();}
Object checkedRecord(sqlite3 *db,Query &q){
  auto sequence=sqlite3_column_int64(q.stmt,0);auto revision=q.text(1),storedHash=q.text(2),text=q.text(3);
  if(sequence<1||text.size()>16384||!digest(revision)||!digest(storedHash)||hash(text)!=storedHash)invalid();
  unsigned depth=0;bool quoted=false,escaped=false;
  for(char c:text){if(quoted){if(escaped)escaped=false;else if(c=='\\')escaped=true;else if(c=='"')quoted=false;continue;}if(c=='"')quoted=true;else if(c=='['||c=='{'){if(++depth>16)invalid();}else if((c==']'||c=='}')&&depth)--depth;}
  auto value=llvm::json::parse(text);if(!value){llvm::consumeError(value.takeError());invalid();}auto object=value->getAsObject();if(!object)invalid();
  const std::set<std::string> fields={"schema","namespace","sequence","previous_change","previous_revision","revision","source_hash","language","action","command","actor","note","request_hash","toolchain","compiler_build","created"};
  if(object->size()!=fields.size())invalid();for(const auto &[key,value]:*object){(void)value;if(!fields.contains(key.str()))invalid();}
  if(object->getString("schema")!="nex.change/1"||object->getInteger("sequence")!=sequence||string(*object,"revision")!=revision||
     string(*object,"namespace")!=graphIdentityNamespace(db)||!digest(string(*object,"source_hash"))||
     !digest(string(*object,"previous_change"),64,true)||!digest(string(*object,"previous_revision"),64,true)||
     !digest(string(*object,"compiler_build"))||!digest(string(*object,"request_hash"),64,true))invalid();
  ChangeInfo info{string(*object,"action"),string(*object,"command"),string(*object,"actor"),string(*object,"note"),string(*object,"request_hash")};
  try{validateChangeInfo(info);}catch(const Error&){invalid();}
  if(string(*object,"language").empty()||string(*object,"language").size()>32||string(*object,"toolchain").empty()||string(*object,"toolchain").size()>64||string(*object,"created").size()!=24)invalid();
  auto result=std::move(*object);result["hash"]=storedHash;return result;
}
void checkLink(sqlite3 *db,const Object &record){
  auto sequence=*record.getInteger("sequence");Query previous(db,"SELECT sequence,revision,hash FROM change_journal WHERE sequence=?");previous.bind(1,std::to_string(sequence-1));
  if(sequence==1){if(string(record,"previous_change")!=""||string(record,"previous_revision")!=metadata(db,"change_base_revision"))invalid();}
  else{if(!previous.row()||string(record,"previous_change")!=previous.text(2)||string(record,"previous_revision")!=previous.text(1))invalid();}
}
Object latest(sqlite3 *db,const std::string &expected){
  Query q(db,"SELECT sequence,revision,hash,data FROM change_journal ORDER BY sequence DESC LIMIT 1");
  if(!q.row()){if(metadata(db,"change_base_revision")!=expected)invalid();return {};}
  auto record=checkedRecord(db,q);checkLink(db,record);if(string(record,"revision")!=expected)invalid();return record;
}
}
void validateChangeInfo(const ChangeInfo &info){
  if(!actions.contains(info.action)||info.command.size()>64||info.actor.size()>128||info.note.size()>1024||!digest(info.requestHash,64,true))throw Error("E_CHANGE","change provenance exceeds its field limits or has an invalid action/hash");
  for(const auto *value:{&info.command,&info.actor,&info.note}){
    if(value->find('\0')!=std::string::npos)throw Error("E_CHANGE","change provenance cannot contain NUL");
    try{nexrt::unicodeOffsets(*value,false);}catch(const nexrt::DataError&){throw Error("E_CHANGE","change provenance must be valid UTF-8");}
  }
}
void initializeChanges(sqlite3 *db){
  sql(db,"CREATE TABLE IF NOT EXISTS change_journal(sequence INTEGER PRIMARY KEY,revision TEXT NOT NULL REFERENCES revisions(hash),hash TEXT NOT NULL UNIQUE,data TEXT NOT NULL)");
  Query q(db,"INSERT OR IGNORE INTO metadata(key,value) VALUES('change_base_revision',?)");q.bind(1,head(db));q.row();
}
void recordHeadChange(sqlite3 *db,const std::string &before,const std::string &after,const std::string &sourceHash,const ChangeInfo &info){
  auto previous=latest(db,before);if(before==after)return;
  auto sequence=previous.empty()?int64_t(1):*previous.getInteger("sequence");if(!previous.empty()){if(sequence==std::numeric_limits<int64_t>::max())throw Error("E_CHANGE","change sequence exhausted");++sequence;}
  Query clock(db,"SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')");if(!clock.row())throw Error("E_STORE","cannot read change timestamp");
  Query language(db,"SELECT language FROM revisions WHERE hash=?");language.bind(1,after);
  if(!language.row())throw Error("E_REVISION","change target revision is missing");
  Object record{{"schema","nex.change/1"},{"namespace",graphIdentityNamespace(db)},{"sequence",sequence},
    {"previous_change",previous.empty()?"":string(previous,"hash")},{"previous_revision",before},{"revision",after},{"source_hash",sourceHash},
    {"language",language.text(0)},{"action",info.action},{"command",info.command},{"actor",info.actor},{"note",info.note},{"request_hash",info.requestHash},
    {"toolchain",NEX_VERSION},{"compiler_build",NEX_BUILD_ID},{"created",clock.text(0)}};
  auto data=json(std::move(record),false);if(data.size()>16384)throw Error("E_CHANGE","change record exceeds 16384 bytes");
  Query insert(db,"INSERT INTO change_journal(sequence,revision,hash,data) VALUES(?,?,?,?)");insert.bind(1,std::to_string(sequence));insert.bind(2,after);insert.bind(3,hash(data));insert.bind(4,data);insert.row();
}
JSON graphChanges(sqlite3 *db,unsigned offset,unsigned limit){
  if(!limit||limit>1000||offset>10000000)throw Error("E_OPTION","change history page limit is 1..1000 and offset is 0..10000000");
  auto current=head(db);latest(db,current);Query count(db,"SELECT count(*) FROM change_journal");count.row();auto total=sqlite3_column_int64(count.stmt,0);
  Query query(db,"SELECT sequence,revision,hash,data FROM change_journal ORDER BY sequence DESC LIMIT ? OFFSET ?");query.bind(1,std::to_string(limit));query.bind(2,std::to_string(offset));Array records;
  while(query.row()){auto record=checkedRecord(db,query);checkLink(db,record);records.push_back(std::move(record));}
  return Object{{"schema","nex.changes/1"},{"namespace",graphIdentityNamespace(db)},{"head",current},{"base_revision",metadata(db,"change_base_revision")},
    {"total",total},{"offset",int64_t(offset)},{"limit",int64_t(limit)},{"truncated",uint64_t(offset)+records.size()<uint64_t(total)},
    {"integrity_scope","selected_records_and_adjacent_links"},{"author_trust","declared"},{"changes",std::move(records)}};
}
}
