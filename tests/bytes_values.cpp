#include "nex_host.h"
#include "nex_files.h"
#include "nex_json.h"
#include "third_party/json.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <functional>
#include <optional>
#include <tuple>
#include <type_traits>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

using nexrt::Value;
using nexrt::ByteBuffer;
using nexrt::Handle;
using JSON=nlohmann::ordered_json;
namespace fs=std::filesystem;
namespace {
std::mutex allocationsMutex;
std::map<const void*,std::pair<size_t,int>> allocations;
bool profileError=false;
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
void error(const std::string &code,const std::function<void()> &action){
  try{action();}catch(const nexrt::DataError &e){require(e.code==code,"wrong error: "+e.code);return;}
  throw std::runtime_error("expected "+code);
}
void code(const Value &value,const std::string &expected){require(!nexrt::isSuccess(value)&&value.object->text==expected,"expected "+expected+", got "+nexrt::printable(value));}
ByteBuffer buffer(const Value &value){return nexrt::byteBuffer(nexrt::unwrap(value).object);}
ByteBuffer unhex(const std::string &text){
  require(text.size()%2==0,"bad hex length");std::vector<uint8_t> result;
  auto digit=[](char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;};
  for(size_t i=0;i<text.size();i+=2){auto a=digit(text[i]),b=digit(text[i+1]);require(a>=0&&b>=0,"bad hex digit");result.push_back(uint8_t(a*16+b));}
  return ByteBuffer::copy(result);
}
std::string hex(const ByteBuffer &value){
  constexpr char digits[]="0123456789abcdef";std::string result;
  for(auto byte:value.view()){result+=digits[byte>>4];result+=digits[byte&15];}return result;
}
const std::string schema=R"({"schema":"nex.wire/2","root":"bytes","records":{},"enums":{}})";
Value list(const std::vector<int64_t> &values){auto d=std::make_shared<nexrt::Data>(nexrt::Data::List);for(auto v:values)d->values.emplace_back(v);return Value(d);}
struct Fixture {
  fs::path path;
  Fixture(){auto pattern=(fs::temp_directory_path()/"nex-binary-XXXXXX").string();auto p=::mkdtemp(pattern.data());require(p,"cannot create fixture");path=fs::canonical(p);}
  ~Fixture(){std::error_code ec;fs::remove_all(path,ec);}
};
struct Environment {
  std::string name;std::optional<std::string> original;
  Environment(std::string name,const std::string &value):name(name){if(auto p=std::getenv(name.c_str()))original=p;::setenv(name.c_str(),value.c_str(),1);}
  ~Environment(){if(original)::setenv(name.c_str(),original->c_str(),1);else ::unsetenv(name.c_str());nexrt::resetFileEnvironment();}
};
void noTemporary(const fs::path &root){for(const auto &entry:fs::recursive_directory_iterator(root))require(!entry.path().filename().string().starts_with(".nex-write-"),"temporary file leaked");}
int descriptors(){int result=0;for(int fd=0;fd<512;++fd)if(::fcntl(fd,F_GETFD)>=0)++result;return result;}
}
extern "C" {
void nex_profile_enter(const char*,const char*,int64_t,const char*){}
void nex_profile_leave(){}
void nex_profile_unwind(){}
void nex_profile_allocation(const void *p,size_t size,int pool){std::lock_guard lock(allocationsMutex);if(!allocations.emplace(p,std::pair{size,pool}).second)profileError=true;}
void nex_profile_free(const void *p){std::lock_guard lock(allocationsMutex);if(allocations.erase(p)!=1)profileError=true;}
Handle *nex_retain(Handle*);
Handle *nex_bytes_from_integers(Handle*,int64_t);
Handle *nex_utf8_bytes(Handle*,int64_t);
Handle *nex_decode_utf8(Handle*,int64_t);
Handle *nex_encode_base64(Handle*,int64_t);
Handle *nex_decode_base64(Handle*,int64_t);
Handle *nex_list_update_i64(Handle*,int64_t,int64_t,int64_t,int64_t,int64_t);
Handle *nex_heap_concat(Handle*,Handle*,int64_t);
Handle *nex_string_slice(Handle*,int64_t,int64_t,int64_t);
int64_t nex_collection_get_i64(Handle*,int64_t,int64_t);
int64_t nex_length(Handle*);
Handle *nex_file_read_bytes(Handle*,int64_t);
Handle *nex_file_write_bytes(Handle*,Handle*,int64_t);
}
void selfTest(){
  unsigned cases=0;auto run=[&](const char *name,const auto &call){call();++cases;require(nexrt::liveObjects==0,"managed values leaked after "+std::string(name));require(!profileError&&allocations.empty(),"profile ownership differs after "+std::string(name));std::cout<<"PASS "<<name<<'\n';};
  run("owned binary subtype and shallow allocation accounting",[]{
    auto value=nexrt::bytes(unhex("00ff8041"));require(value->kind==nexrt::Data::Bytes,"wrong byte kind");
    require(allocations.at(value.get())==std::pair{sizeof(nexrt::ByteData),1},"binary allocation size differs");
    auto text=nexrt::string("x");require(allocations.at(text.get())==std::pair{sizeof(nexrt::Data),1},"ordinary value size changed");
    static_assert(nexrt::Data::String==0&&nexrt::Data::Closure==6&&nexrt::Data::Bytes==7);
    static_assert(!std::is_polymorphic_v<nexrt::Data>);
    error("E_RUNTIME",[&]{(void)std::make_shared<nexrt::Data>(*value);});
    error("E_RUNTIME",[]{(void)std::make_shared<nexrt::Data>(nexrt::Data::Bytes);});
  });
  run("empty byte value and copied host boundaries",[]{
    auto empty=nexrt::bytes({});require(nexrt::length(empty)==0&&nexrt::representation(Value(empty))=="\"\"","empty value differs");
    error("E_BOUNDS",[&]{nexrt::get(empty,0);});require(nexrt::length(nexrt::slice(empty,0,0))==0,"empty slice differs");
    std::vector<uint8_t> raw{0,255,128};auto value=nexrt::bytes(ByteBuffer::copy(raw));raw[0]=9;
    auto exported=nexrt::byteBuffer(value).toVector();exported[1]=0;require(hex(nexrt::byteBuffer(value))=="00ff80","mutable alias escaped");
  });
  run("construction and recoverable range errors",[]{
    require(hex(buffer(nexrt::bytesFromIntegers(list({0,127,128,255}))))=="007f80ff","construction differs");
    code(nexrt::bytesFromIntegers(list({-1})),"E_RANGE");code(nexrt::bytesFromIntegers(list({256})),"E_RANGE");
    error("E_RUNTIME",[]{nexrt::bytesFromIntegers(Value(1));});
  });
  run("retained slices and structural aggregate equality",[]{
    Value sliced;{auto owner=nexrt::bytes(unhex("00010203ff"));sliced=Value(nexrt::slice(owner,1,3));}
    auto same=Value(nexrt::bytes(unhex("010203")));require(nexrt::equal(sliced,same),"binary equality differs");
    require(!nexrt::equal(same,Value(nexrt::bytes(unhex("010204")))),"unequal bytes compared equal");
    auto a=std::make_shared<nexrt::Data>(nexrt::Data::List),b=std::make_shared<nexrt::Data>(nexrt::Data::List);
    a->values={sliced,nexrt::success(sliced)};b->values={same,nexrt::success(same)};require(nexrt::equal(Value(a),Value(b)),"nested binary equality differs");
    require(nexrt::get(sliced.object,2).scalar==3&&!nexrt::equal(same,Value(nexrt::string("AQID"))),"byte and string domains overlap");
  });
  run("strict UTF-8 without BOM or NUL loss",[]{
    for(const auto &text:std::vector<std::string>{"",std::string("A\0B",3),"Я🧠","\xef\xbb\xbftext","e\xcc\x81"}){
      auto encoded=nexrt::utf8Bytes(text);auto decoded=nexrt::decodeUTF8(nexrt::byteBuffer(encoded));
      require(nexrt::unwrap(decoded).object->text==text,"UTF-8 roundtrip differs");
    }
    for(auto bad:{"80","c080","c328","eda080","f4908080","f09f92","ff"})code(nexrt::decodeUTF8(unhex(bad)),"E_UTF8");
    error("E_UTF8",[]{nexrt::utf8Bytes(std::string("\xff",1));});
  });
  run("base64 results and display",[]{
    require(hex(buffer(nexrt::decodeBase64("AP+AQQ==")))=="00ff8041","base64 decode differs");
    for(auto bad:{"Zh==","AA-_","AA==\n","A==="})code(nexrt::decodeBase64(bad),"E_BASE64");
    auto value=Value(nexrt::bytes(unhex("00ff8041")));require(nexrt::printable(value)=="\"AP+AQQ==\"","binary display differs");
  });
  run("typed JSON bytes and historical nominal names",[]{
    auto value=Value(nexrt::bytes(unhex("00ff8041")));auto wire=nexrt::encodeJSON(value);
    require(wire=="\"AP+AQQ==\""&&nexrt::equal(value,nexrt::unwrap(nexrt::decodeJSON(wire,schema))),"wire roundtrip differs");
    for(auto bad:{"\"Zh==\"","\"AA== \"","[]","1","null","\"AA-_\""})code(nexrt::decodeJSON(bad,schema),"E_JSON");
    for(auto version:{"nex.wire/1","nex.wire/2"}){
      JSON old={{"schema",version},{"root",{{"record","bytes"}}},{"records",{{"bytes",JSON::array({{{"name","value"},{"type","i64"}}})}}},{"enums",JSON::object()}};
      auto nominal=nexrt::unwrap(nexrt::decodeJSON("{\"value\":\"7\"}",old.dump()));require(nominal.object->kind==nexrt::Data::Record&&nominal.object->values[0].scalar==7,"historical nominal bytes changed meaning");
    }
  });
  run("wire size is encoded size including padding",[]{
    std::vector<uint8_t> maximum(786429,255);auto value=Value(nexrt::bytes(ByteBuffer::copy(maximum)));
    auto wire=nexrt::encodeJSON(value);require(wire.size()==1048574&&buffer(nexrt::decodeJSON(wire,schema)).length()==786429,"exact wire limit differs");
    maximum.push_back(255);error("E_JSON",[&]{nexrt::encodeJSON(Value(nexrt::bytes(ByteBuffer::copy(maximum))));});
  });
  run("native handles immutable updates and retained ownership",[]{
    nexrt::RequestScope scope;auto input=nexrt::makeHandle(list({0,255,128}));auto result=nex_bytes_from_integers(input,11);
    auto original=nexrt::makeHandle(nexrt::unwrap(nexrt::readHandle(result)));auto alias=nex_retain(original);nex_release(result);nex_release(input);nex_release(original);
    auto changed=nex_list_update_i64(alias,1,3,0,1,13),appended=nex_list_update_i64(alias,0,7,0,0,14);
    require(hex(nexrt::byteBuffer(nexrt::readHandle(alias).object))=="00ff80","native alias mutated");
    require(nex_collection_get_i64(changed,1,15)==3&&nex_length(appended)==4,"native update differs");
    auto joined=nex_heap_concat(alias,changed,16),sliced=nex_string_slice(joined,2,2,17);
    nex_release(alias);nex_release(changed);nex_release(appended);nex_release(joined);
    require(hex(nexrt::byteBuffer(nexrt::readHandle(sliced).object))=="8000","native slice owner lost");
    auto encoded=nex_encode_base64(sliced,18),decoded=nex_decode_base64(encoded,19);
    require(hex(buffer(nexrt::readHandle(decoded)))=="8000","native codec differs");
    // Leave handles live: RequestScope must reclaim them on normal host exit.
  });
  run("native byte errors carry source lines and unwind owners",[]{
    for(auto [index,value,expected]:std::vector<std::tuple<int64_t,int64_t,std::string>>{{-1,256,"E_BOUNDS"},{1,256,"E_BOUNDS"},{0,256,"E_RANGE"}}){
      bool trapped=false;
      try{nexrt::RequestScope scope;auto h=nexrt::makeHandle(Value(nexrt::bytes(unhex("00"))));nex_list_update_i64(h,index,value,0,1,37);}
      catch(const nexrt::Trap &trap){trapped=trap.code==expected&&trap.line==37;}
      require(trapped&&nexrt::liveObjects==0,"byte trap or cleanup differs");
    }
  });
  run("native UTF-8 recoverable results",[]{
    nexrt::RequestScope scope;auto h=nexrt::makeHandle(Value(nexrt::string(std::string("Я\0🧠",7))));
    auto encoded=nex_utf8_bytes(h,41),decoded=nex_decode_utf8(encoded,42);
    require(nexrt::unwrap(nexrt::readHandle(decoded)).object->text==nexrt::readHandle(h).object->text,"native UTF-8 roundtrip differs");
    auto bad=nexrt::makeHandle(Value(nexrt::bytes(unhex("ff"))));code(nexrt::readHandle(nex_decode_utf8(bad,43)),"E_UTF8");
  });
  run("binary file exact octets and sliced payload",[]{
    Fixture f;nexrt::TextFiles files(f.path.string(),true);std::vector<uint8_t> all;for(unsigned i=0;i<256;++i)all.push_back(uint8_t(i));
    auto input=ByteBuffer::copy(all);require(nexrt::isSuccess(files.writeBytes("octets",input)),"binary write failed");
    require(buffer(files.readBytes("octets"))==input,"file octets differ");code(files.read("octets"),"E_UTF8");
    auto sliced=input.slice(127,3);require(nexrt::isSuccess(files.writeBytes("slice",sliced)),"slice write failed");require(hex(buffer(files.readBytes("slice")))=="7f8081","slice file differs");
    require(nexrt::isSuccess(files.writeBytes("empty",{}))&&buffer(files.readBytes("empty")).length()==0,"empty binary file differs");
  });
  run("binary file limits and text interoperability",[]{
    Fixture f;nexrt::TextFiles files(f.path.string(),true);
    std::vector<uint8_t> raw(nexrt::TextFiles::byteLimit,255);auto maximum=ByteBuffer::copy(raw);
    require(nexrt::isSuccess(files.writeBytes("maximum",maximum))&&buffer(files.readBytes("maximum"))==maximum,"binary file limit differs");
    raw.push_back(255);code(files.writeBytes("maximum",ByteBuffer::copy(raw)),"LIMIT");require(buffer(files.readBytes("maximum"))==maximum,"oversized write replaced file");
    {std::ofstream out(f.path/"oversized",std::ios::binary);out.write(reinterpret_cast<const char*>(raw.data()),raw.size());}code(files.readBytes("oversized"),"LIMIT");
    auto text=std::string("\xef\xbb\xbf" "A\0Я🧠",11);require(nexrt::isSuccess(files.write("text",text)),"text fixture failed");
    auto bytes=buffer(files.readBytes("text"));require(nexrt::unwrap(nexrt::decodeUTF8(bytes)).object->text==text,"BOM/NUL changed through file");
    noTemporary(f.path);
  });
  run("binary file capability path and nonregular denial",[]{
    Fixture f;fs::create_directory(f.path/"nested");nexrt::TextFiles files(f.path.string(),true),readonly(f.path.string(),false);
    auto input=unhex("ff00");code(readonly.writeBytes("denied",input),"CAPABILITY");
    for(auto path:{"../escape","/absolute","nested//file","nested/../file","nested/"}){code(files.readBytes(path),"VALIDATION");code(files.writeBytes(path,input),"VALIDATION");}
    fs::create_symlink(f.path/"target",f.path/"link");code(files.readBytes("link"),"VALIDATION");code(files.writeBytes("link",input),"VALIDATION");
    fs::create_directory_symlink(f.path/"nested",f.path/"linked");code(files.readBytes("linked/file"),"VALIDATION");code(files.writeBytes("linked/file",input),"VALIDATION");
    require(::mkfifo((f.path/"fifo").c_str(),0600)==0,"FIFO fixture failed");code(files.readBytes("fifo"),"VALIDATION");code(files.writeBytes("fifo",input),"VALIDATION");code(files.readBytes("nested"),"VALIDATION");
    require(!fs::exists(f.path/"target")&&!fs::exists(f.path/"denied"),"denied write changed filesystem");noTemporary(f.path);
  });
  run("binary cancellation cleans descriptors and temporary files",[]{
    Fixture f;nexrt::TextFiles files(f.path.string(),true);auto original=unhex("ff00"),large=ByteBuffer::copy(std::vector<uint8_t>(150000,128));
    require(nexrt::isSuccess(files.writeBytes("original",original)),"initial write failed");auto baseline=descriptors();
    for(unsigned stop:{1,2,3,4,5,6}){
      unsigned polls=0;bool cancelled=false;
      try{files.writeBytes("original",large,[&]{if(++polls==stop)throw nexrt::Trap("E_CANCELLED","cancelled",51);});}catch(const nexrt::Trap &trap){cancelled=trap.code=="E_CANCELLED";}
      require(cancelled&&buffer(files.readBytes("original"))==original,"cancelled binary write changed destination");require(descriptors()==baseline,"cancelled binary write leaked descriptor");noTemporary(f.path);
    }
  });
  run("HTTP scopes deny environment and accept explicit binary capability",[]{
    Fixture f;Environment root("NEX_FILES_ROOT",f.path.string()),write("NEX_FILES_WRITE","1");nexrt::TextFiles files(f.path.string(),true);
    {
      nexrt::RequestScope request;auto path=nexrt::makeHandle(Value(nexrt::string("data"))),value=nexrt::makeHandle(Value(nexrt::bytes(unhex("00ff"))));
      code(nexrt::readHandle(nex_file_write_bytes(path,value,61)),"CAPABILITY");code(nexrt::readHandle(nex_file_read_bytes(path,62)),"CAPABILITY");require(!fs::exists(f.path/"data"),"request inherited file environment");
      {nexrt::FileScope explicitGrant(files);require(nexrt::isSuccess(nexrt::readHandle(nex_file_write_bytes(path,value,63))),"explicit binary grant denied");require(hex(buffer(nexrt::readHandle(nex_file_read_bytes(path,64))))=="00ff","explicit binary read differs");}
      code(nexrt::readHandle(nex_file_read_bytes(path,65)),"CAPABILITY");
    }
    {nexrt::FileScope denied(false);code(nexrt::fileReadBytes("data"),"CAPABILITY");}
    require(hex(buffer(nexrt::fileReadBytes("data")))=="00ff","CLI environment read denied");
  });
  run("native binary file cancellation unwinds all handles",[]{
    Fixture f;nexrt::TextFiles files(f.path.string(),true);auto original=unhex("aabb");require(nexrt::isSuccess(files.writeBytes("data",original)),"initial write failed");
    bool cancelled=false;unsigned polls=0;
    try{
      nexrt::RequestScope request;nexrt::FileScope grant(files);request.setCancellation([&]{return ++polls==6;});
      auto path=nexrt::makeHandle(Value(nexrt::string("data"))),value=nexrt::makeHandle(Value(nexrt::bytes(ByteBuffer::copy(std::vector<uint8_t>(150000,255)))));
      nex_file_write_bytes(path,value,71);
    }catch(const nexrt::Trap &trap){cancelled=trap.code=="E_CANCELLED"&&trap.line==71;}
    require(cancelled&&buffer(files.readBytes("data"))==original,"native cancelled binary write was published");noTemporary(f.path);
  });
  run("ordinary native finish releases binary environment handles",[]{
    Fixture f;Environment root("NEX_FILES_ROOT",f.path.string()),write("NEX_FILES_WRITE","1");
    auto path=nexrt::makeHandle(Value(nexrt::string("data"))),value=nexrt::makeHandle(Value(nexrt::bytes(unhex("00ff80"))));
    auto written=nex_file_write_bytes(path,value,81);require(nexrt::isSuccess(nexrt::readHandle(written)),"CLI binary write failed");nex_release(written);
    auto read=nex_file_read_bytes(path,82);require(hex(buffer(nexrt::readHandle(read)))=="00ff80","CLI binary read differs");nex_release(read);nex_release(path);nex_release(value);
    nex_runtime_finish();
  });
  std::cout<<cases<<" managed binary value cases passed\n";
}
JSON observed(const ByteBuffer &buffer){
  auto value=Value(nexrt::bytes(buffer));auto wire=nexrt::encodeJSON(value);auto decoded=nexrt::decodeJSON(wire,schema);require(nexrt::isSuccess(decoded),"wire roundtrip failed");
  auto utf8=nexrt::decodeUTF8(buffer);
  return JSON{{"ok",true},{"hex",hex(buffer)},{"length",std::to_string(nexrt::length(value.object))},{"display",nexrt::representation(value)},
    {"wire",wire},{"wire_hex",hex(::buffer(decoded))},{"utf8_ok",nexrt::isSuccess(utf8)},{"utf8",nexrt::isSuccess(utf8)?nexrt::unwrap(utf8).object->text:utf8.object->text}};
}
JSON command(const JSON &request){
  try{
    auto op=request.at(0).get<std::string>();
    if(op=="decode"){auto value=nexrt::decodeJSON(request.at(1).get<std::string>(),schema);if(!nexrt::isSuccess(value))return JSON{{"ok",false},{"code",value.object->text}};return observed(buffer(value));}
    if(op=="construct"){std::vector<int64_t> values;for(const auto &v:request.at(1))values.push_back(std::stoll(v.get<std::string>()));auto result=nexrt::bytesFromIntegers(list(values));if(!nexrt::isSuccess(result))return JSON{{"ok",false},{"code",result.object->text}};return observed(buffer(result));}
    auto value=unhex(request.at(1).get<std::string>());
    if(op=="set")return observed(value.set(std::stoll(request.at(2).get<std::string>()),std::stoll(request.at(3).get<std::string>())));
    if(op=="push")return observed(value.append(std::stoll(request.at(2).get<std::string>())));
    if(op=="slice")return observed(value.slice(std::stoll(request.at(2).get<std::string>()),std::stoll(request.at(3).get<std::string>())));
    if(op=="concat")return observed(value.concat(unhex(request.at(2).get<std::string>())));
    if(op=="at")return JSON{{"ok",true},{"integer",std::to_string(nexrt::get(nexrt::bytes(value),std::stoll(request.at(2).get<std::string>())).scalar)}};
    return observed(value);
  }catch(const nexrt::DataError &error){return JSON{{"ok",false},{"code",error.code}};}
}
int main(int argc,char **argv){
  try{
    if(argc==1)selfTest();
    else{require(argc==2&&std::string(argv[1])=="--stream","bad probe arguments");for(std::string line;std::getline(std::cin,line);)if(!line.empty())std::cout<<command(JSON::parse(line)).dump()<<'\n';}
    nex_runtime_finish();require(!profileError&&allocations.empty(),"unbalanced final profile");return 0;
  }catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
}
