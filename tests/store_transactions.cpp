#include "nex_io.h"
#include <sqlite3.h>
#include <chrono>
#include <filesystem>
#include <future>
#include <iostream>
#include <iomanip>
#include <random>
#include <stdexcept>
#include <string>
using namespace nexrt;
namespace {
unsigned checks=0;
void require(bool value,const char *message){++checks;if(!value)throw std::runtime_error(message);}
void ok(const Value &value,const char *message){require(isSuccess(value),message);}
void error(const Value &value,const char *code){require(!isSuccess(value)&&value.object->text==code,"unexpected storage error");}
std::string text(const Value &value){ok(value,"storage read failed");return value.object->values.at(0).object->text;}
struct Raw {
 sqlite3 *db=nullptr;
 explicit Raw(const std::string &path){require(sqlite3_open_v2(path.c_str(),&db,SQLITE_OPEN_READWRITE,nullptr)==SQLITE_OK,"open observer");sqlite3_busy_timeout(db,0);}
 ~Raw(){if(db)sqlite3_close(db);}
 int sql(const char *value){return sqlite3_exec(db,value,nullptr,nullptr,nullptr);}
 bool lease(){int result=sql("BEGIN IMMEDIATE");if(result==SQLITE_OK){require(sql("ROLLBACK")==SQLITE_OK,"release observer lease");return true;}require(result==SQLITE_BUSY||result==SQLITE_LOCKED,"unexpected writer admission error");return false;}
 std::string read(const char *key){sqlite3_stmt *q=nullptr;require(sqlite3_prepare_v2(db,"SELECT value FROM nex_kv WHERE owner='alice' AND key=?",-1,&q,nullptr)==SQLITE_OK,"prepare observer read");sqlite3_bind_text(q,1,key,-1,SQLITE_STATIC);int result=sqlite3_step(q);require(result==SQLITE_ROW||result==SQLITE_DONE,"observer read");std::string value=result==SQLITE_ROW?std::string(static_cast<const char*>(sqlite3_column_blob(q,0)),sqlite3_column_bytes(q,0)):"";sqlite3_finalize(q);return value;}
};
void tests(const std::string &path){
 using Start=Database::TransactionStart;
 Database::initialize(path);Raw observer(path);
 // The existing constructor retains its eager admission and C++ symbol.
 {Database eager(path,"alice",true);require(!observer.lease(),"legacy writer was no longer eager");ok(eager.put("seed","old"),"seed");ok(eager.commit(),"legacy commit");error(eager.commit(),"E_STORE");}require(observer.lease(),"legacy commit kept lease");
 // An unused HTTP scope must not make another real writer wait through the
 // unchanged1000ms busy timeout. This fails against the old eager HTTP policy.
 {Database held(path,"alice",true,Start::OnFirstOperation);require(observer.lease(),"unused HTTP scope acquired writer lease");
  auto writer=std::async(std::launch::async,[&]{try{Database other(path,"alice",true);return isSuccess(other.put("seed","new"))&&isSuccess(other.commit());}catch(const DataError &){return false;}});
  require(writer.wait_for(std::chrono::seconds(3))==std::future_status::ready,"unused HTTP scope blocked writer");require(writer.get(),"writer failed while no request DB operation ran");
  require(text(held.get("seed"))=="new","first read did not observe pre-operation commit");require(!observer.lease(),"first POST storage operation did not acquire real writer lease");
  ok(held.put("left","one"),"first pending write");ok(held.put("right","two"),"second pending write");require(observer.read("left").empty()&&observer.read("right").empty(),"partial writes escaped transaction");held.rollback();error(held.commit(),"E_STORE");}
 require(observer.read("left").empty()&&observer.read("right").empty()&&observer.lease(),"rollback did not release/remove partial writes");
 {Database scope(path,"alice",true,Start::OnFirstOperation);ok(scope.commit(),"empty commit");error(scope.commit(),"E_STORE");require(observer.lease(),"empty commit acquired lease");}
 {Database scope(path,"alice",true,Start::OnFirstOperation);scope.rollback();error(scope.commit(),"E_STORE");require(observer.lease(),"unused rollback acquired lease");}
 {Database scope(path,"alice",false,Start::OnFirstOperation);error(scope.put("left","denied"),"VALIDATION");require(observer.lease(),"rejected mutation acquired writer lease");error(scope.commit(),"TRANSACTION_ABORTED");}
 {Database scope(path,"alice",true,Start::OnFirstOperation);ok(scope.put("left","uncommitted"),"pending write before rejected mutation");error(scope.remove(""),"VALIDATION");error(scope.commit(),"TRANSACTION_ABORTED");require(observer.read("left").empty(),"ignored failed write committed earlier mutation");}
 // Read-only GET scopes take a stable snapshot from first storage access,
 // without preventing a WAL writer from committing its next value.
 {Database reader(path,"alice",false,Start::OnFirstOperation);require(text(reader.get("seed"))=="new","initial GET snapshot");
  {Database writer(path,"alice",true);ok(writer.put("seed","later"),"WAL writer");ok(writer.commit(),"WAL commit");}
  require(text(reader.get("seed"))=="new","GET lost its transaction snapshot");ok(reader.commit(),"GET commit");}
 {Database reader(path,"alice",false,Start::OnFirstOperation);require(text(reader.get("seed"))=="later","new GET did not see commit");ok(reader.commit(),"new GET commit");}
 {Database scope(path,"alice",true,Start::OnFirstOperation);ok(scope.put("unicode",std::string("Я\0🙂",7)),"Unicode/NUL write");ok(scope.put("other","atomic"),"second committed write");ok(scope.commit(),"multiwrite commit");}
 {Database reader(path,"alice",false,Start::OnFirstOperation);require(text(reader.get("unicode"))==std::string("Я\0🙂",7),"Unicode/NUL changed");ok(reader.keys("uni"),"lazy key listing");ok(reader.commit(),"keys commit");}
 {Database bob(path,"bob",false,Start::OnFirstOperation);error(bob.get("unicode"),"NOT_FOUND");ok(bob.commit(),"missing read poisoned transaction");}
 {Database scope(path,"alice",true,Start::OnFirstOperation);ok(scope.remove("other"),"lazy remove");ok(scope.commit(),"remove commit");require(observer.read("other").empty(),"remove not committed");}
 // A genuine writer conflict still returns STORE_BUSY and poisons its scope.
 require(observer.sql("BEGIN IMMEDIATE")==SQLITE_OK,"hold genuine writer");
 {Database conflict(path,"alice",true,Start::OnFirstOperation);error(conflict.get("seed"),"STORE_BUSY");error(conflict.commit(),"TRANSACTION_ABORTED");}
 require(observer.sql("ROLLBACK")==SQLITE_OK&&observer.lease(),"conflict rollback changed lock ownership");
 {Database scope(path,"alice",true,Start::OnFirstOperation);StorageScope injected(scope);ok(storagePut("injected","scope"),"injected lazy scope");require(text(storageGet("injected"))=="scope","injected read");scope.rollback();require(observer.read("injected").empty(),"injected rollback");}
}
}
int main(int argc,char **argv){try{if(argc>2)throw std::runtime_error("expected optional fresh database path");std::filesystem::path path;if(argc==2)path=argv[1];else{std::random_device random;for(unsigned i=0;i<32;++i){auto directory=std::filesystem::temp_directory_path()/("nex-store-transactions-"+std::to_string(random())+"-"+std::to_string(random()));if(std::filesystem::create_directory(directory)){path=directory/"database.sqlite";break;}}require(!path.empty(),"fresh test directory");}require(!std::filesystem::exists(path),"probe requires fresh database");tests(path.string());require(liveObjects==0,"storage Value leak");std::cout<<"{\"ok\":true,\"checks\":"<<checks<<",\"database\":"<<std::quoted(path.string())<<",\"deferred_HTTP_start\":true,\"legacy_eager_constructor\":true,\"busy_timeout_ms\":1000,\"real_write_conflict_retained\":true}\n";return 0;}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
