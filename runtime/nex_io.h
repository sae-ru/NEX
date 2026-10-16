#pragma once
#include "nex_value.h"
#include <cstdlib>

namespace nexrt {
inline Value readEnvironment(const std::string &name){
  if(name.empty()||name.size()>256||name.find_first_of("=\0",0,2)!=std::string::npos)return failure("VALIDATION","invalid environment variable name");
  const char *text=std::getenv(name.c_str());if(!text)return failure("NOT_FOUND","environment variable is not defined");
  try{return success(Value(string(text)));}catch(const DataError &){return failure("E_UTF8","environment value is not valid UTF-8");}
}
class Database {
  struct Impl;std::unique_ptr<Impl> impl;
public:
  static void initialize(const std::string &path);
  Database(const std::string &path,const std::string &principal,bool writable);
  ~Database();
  Database(const Database&)=delete;
  Database &operator=(const Database&)=delete;
  Value get(const std::string &key);
  Value put(const std::string &key,const std::string &value);
  Value remove(const std::string &key);
  Value keys(const std::string &prefix);
  Value commit();
  void rollback();
};
class StorageScope {
  Database *previous;
public:
  explicit StorageScope(Database &database);
  ~StorageScope();
  StorageScope(const StorageScope&)=delete;
  StorageScope &operator=(const StorageScope&)=delete;
};
Value storageGet(const std::string &key);
Value storagePut(const std::string &key,const std::string &value);
Value storageRemove(const std::string &key);
Value storageKeys(const std::string &prefix);
}
