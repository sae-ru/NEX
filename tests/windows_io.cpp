#include "nex_files.h"
#include "nex_io.h"
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <aclapi.h>

namespace fs=std::filesystem;
using namespace nexrt;
namespace {
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
void ok(const Value &value){require(isSuccess(value),printable(value));}
void code(const Value &value,const std::string &name){require(!isSuccess(value)&&value.object->text==name,"expected "+name+", got "+printable(value));}
std::string text(const Value &value){ok(value);return unwrap(value).object->text;}
std::string path(const fs::path &value){return platform::utf8(value.wstring());}
ByteBuffer octets(std::string_view text){return ByteBuffer::copy({reinterpret_cast<const uint8_t*>(text.data()),text.size()});}
std::string stringBytes(const ByteBuffer &bytes){auto v=bytes.view();return v.empty()?std::string():std::string(reinterpret_cast<const char*>(v.data()),v.size());}
template<class F> void error(const std::string &expected,F call){try{call();}catch(const DataError &e){require(e.code==expected,"expected "+expected+", got "+e.code);return;}throw std::runtime_error("missing "+expected);}
void raw(const fs::path &p,const std::string &value){std::ofstream f(p,std::ios::binary);f.write(value.data(),value.size());require(bool(f),"fixture write failed");}
void noTemporary(const fs::path &root){for(const auto &p:fs::recursive_directory_iterator(root))require(!p.path().filename().wstring().starts_with(L".nex-write-"),"orphan temporary");}
DWORD handles(){DWORD count=0;require(GetProcessHandleCount(GetCurrentProcess(),&count),"handle count unavailable");return count;}
void link(const fs::path &target,const fs::path &name,bool directory){
 if(!CreateSymbolicLinkW(name.c_str(),target.c_str(),SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE|(directory?SYMBOLIC_LINK_FLAG_DIRECTORY:0)))
  throw std::runtime_error("cannot create test symbolic link: Win32 error "+std::to_string(GetLastError()));
 auto attributes=GetFileAttributesW(name.c_str());require(attributes!=INVALID_FILE_ATTRIBUTES&&(attributes&FILE_ATTRIBUTE_REPARSE_POINT),"fixture is not a real reparse point");
}
void privateAcl(const fs::path &path){
 HANDLE file=CreateFileW(path.c_str(),READ_CONTROL,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,0,nullptr);require(file!=INVALID_HANDLE_VALUE,"cannot inspect file ACL");
 PSECURITY_DESCRIPTOR descriptor=nullptr;PACL acl=nullptr;auto result=GetSecurityInfo(file,SE_FILE_OBJECT,DACL_SECURITY_INFORMATION,nullptr,nullptr,&acl,nullptr,&descriptor);CloseHandle(file);require(result==ERROR_SUCCESS&&descriptor&&acl,"file ACL unavailable");
 SECURITY_DESCRIPTOR_CONTROL control{};DWORD revision=0;require(GetSecurityDescriptorControl(descriptor,&control,&revision)&&(control&SE_DACL_PROTECTED),"file DACL not protected");require(acl->AceCount==1,"file grants unexpected principals");
 void *raw=nullptr;require(GetAce(acl,0,&raw),"file ACE unavailable");auto ace=static_cast<ACCESS_ALLOWED_ACE*>(raw);require(ace->Header.AceType==ACCESS_ALLOWED_ACE_TYPE&&!(ace->Header.AceFlags&INHERITED_ACE)&&ace->Mask==FILE_ALL_ACCESS,"file ACE differs");
 HANDLE token=nullptr;require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token),"process token unavailable");DWORD size=0;GetTokenInformation(token,TokenUser,nullptr,0,&size);std::vector<unsigned char> buffer(size);require(GetTokenInformation(token,TokenUser,buffer.data(),size,&size),"token user unavailable");CloseHandle(token);require(EqualSid(&ace->SidStart,reinterpret_cast<TOKEN_USER*>(buffer.data())->User.Sid),"file granted another user");LocalFree(descriptor);
}
}
int main(){
 try{
  auto base=fs::temp_directory_path()/(L"nex065-"+std::to_wstring(GetCurrentProcessId()));fs::create_directories(base);auto root=base/L"root Я🧠",outside=base/L"outside";fs::create_directories(root/L"nested");fs::create_directories(outside);unsigned count=0;
  unsigned failed=0;
  auto run=[&](const char *name,const auto &call){try{call();++count;std::cout<<"PASS "<<name<<std::endl;}catch(const DataError &e){++failed;std::cerr<<"FAIL "<<name<<": "<<e.code<<": "<<e.what()<<std::endl;}catch(const std::exception &e){++failed;std::cerr<<"FAIL "<<name<<": "<<e.what()<<std::endl;}};
  run("Unicode process environment, empty and missing",[&]{
   require(SetEnvironmentVariableW(L"NEX065_Я🧠",L"значение 🧠"),"set Unicode environment");require(text(readEnvironment("NEX065_Я🧠"))=="значение 🧠","Unicode environment differs");
   require(SetEnvironmentVariableW(L"NEX065_EMPTY",L""),"set empty environment");require(text(readEnvironment("NEX065_EMPTY")).empty(),"empty environment lost");SetEnvironmentVariableW(L"NEX065_MISSING",nullptr);code(readEnvironment("NEX065_MISSING"),"NOT_FOUND");code(readEnvironment("a=b"),"VALIDATION");code(readEnvironment(std::string("a\0b",3)),"VALIDATION");
  });
  run("strict UTF-16 environment values",[&]{wchar_t invalid[]={wchar_t(0xd800),0};require(SetEnvironmentVariableW(L"NEX065_BAD",invalid),"set raw UTF16");code(readEnvironment("NEX065_BAD"),"E_UTF8");SetEnvironmentVariableW(L"NEX065_BAD",nullptr);});
  {
  TextFiles files(path(root),true),readonly(path(root),false);
  run("whole text Unicode and NUL",[&]{auto value=std::string("a\0",2)+"Я🧠\n";ok(files.write("nested/Я🧠.txt",value));require(text(files.read("nested/Я🧠.txt"))==value,"whole text roundtrip");});
  run("whole arbitrary octets",[&]{auto value=std::string("\0\xff\xc0\x80",4);ok(files.writeBytes("binary",octets(value)));auto read=files.readBytes("binary");ok(read);require(stringBytes(byteBuffer(unwrap(read).object))==value,"binary roundtrip");code(files.read("binary"),"E_UTF8");});
  run("read only and missing paths",[&]{code(readonly.write("denied","x"),"CAPABILITY");require(!fs::exists(root/L"denied"),"read only side effect");code(files.read("absent"),"NOT_FOUND");code(files.write("absent/file","x"),"NOT_FOUND");});
  run("bounded relative Windows names",[&]{for(const auto &n:std::vector<std::string>{"","../outside","/absolute","C:/absolute","nested\\escape","nested//x","nested/./x","nested/../x","nested/","name:stream","name.","name ","NUL","CON.txt","COM1","LPT9","com¹.txt","LPT²","COM³",std::string("a\0b",3),std::string(4097,'a')}){code(files.read(n),"VALIDATION");code(files.write(n,"x"),"VALIDATION");}});
  run("strict text and byte bounds",[&]{code(files.write("invalid",std::string("\xc3\x28",2)),"E_UTF8");require(!fs::exists(root/L"invalid"),"bad text side effect");std::string value(TextFiles::byteLimit,'a');ok(files.write("maximum",value));require(text(files.read("maximum"))==value,"exact byte limit");value+='b';code(files.write("large",value),"LIMIT");raw(root/L"large",value);code(files.read("large"),"LIMIT");code(files.read("nested"),"VALIDATION");});
  run("atomic cancellation and temporary cleanup",[&]{ok(files.write("original","retained"));for(unsigned stop:{2,3,6}){unsigned polls=0;bool cancelled=false;try{files.write("original",std::string(150000,'b'),[&]{if(++polls==stop)throw std::runtime_error("cancel");});}catch(const std::runtime_error &e){require(std::string(e.what())=="cancel","wrong cancellation");cancelled=true;}require(cancelled&&text(files.read("original"))=="retained","cancelled publication");noTemporary(root);}});
  run("streaming owners, cursors and append",[&]{auto a=files.open("stream",FileMode::WriteTruncate),alias=a;require(a.identity()==alias.identity(),"identity alias");require(a.write(octets("abc"))==3&&a.size()==3,"stream write");a.flush();require(a.close()&&!alias.isOpen()&&!alias.close(),"shared close");error("E_RESOURCE_CLOSED",[&]{alias.size();});auto append=files.open("stream",FileMode::Append);append.seek(0);require(append.write(octets("d"))==1,"append write");append.close();auto read=files.open("stream",FileMode::Read);require(stringBytes(read.read(2))=="ab"&&read.seek(1)==1&&stringBytes(read.read(10))=="bcd","stream cursor");error("CAPABILITY",[&]{read.write(octets("x"));});error("E_RANGE",[&]{read.seek(-1);});error("LIMIT",[&]{read.read(TextFiles::byteLimit+1);});});
  run("scope revocation and quota",[&]{auto scope=files.resourceScope(1);auto a=files.openIn(scope,"stream",FileMode::Read);error("E_RESOURCE_LIMIT",[&]{files.openIn(scope,"original",FileMode::Read);});scope.revoke();require(!a.isOpen(),"scope escape");error("E_RESOURCE_SCOPE",[&]{a.size();});});
  run("quota checked before create and truncate",[&]{auto scope=files.resourceScope(1);auto held=files.openIn(scope,"stream",FileMode::Read);error("E_RESOURCE_LIMIT",[&]{files.openIn(scope,"quota-new",FileMode::WriteTruncate);});error("E_RESOURCE_LIMIT",[&]{files.openIn(scope,"original",FileMode::WriteTruncate);});require(!fs::exists(root/L"quota-new")&&text(files.read("original"))=="retained","quota failure mutated file");});
  run("cancelled open and reentrant close release handles",[&]{auto scope=files.resourceScope(1);auto baseline=handles();for(unsigned stop:{1,2,3}){unsigned polls=0;bool cancelled=false;try{files.openIn(scope,"original",FileMode::WriteTruncate,[&]{if(++polls==stop)throw std::runtime_error("cancel");});}catch(const std::runtime_error &e){require(std::string(e.what())=="cancel","wrong open cancellation");cancelled=true;}require(cancelled&&scope.used()==0&&handles()==baseline&&text(files.read("original"))=="retained","cancelled open leaked or truncated");}auto value=files.openIn(scope,"stream",FileMode::Read);error("E_RESOURCE_CLOSED",[&]{value.size([&]{value.close();});});require(!scope.used()&&handles()==baseline,"reentrant close leaked");});
  run("stream write cancellation exposes completed writes",[&]{auto output=files.open("stream-cancel",FileMode::WriteTruncate);try{output.write(octets("before"),[]{throw std::runtime_error("cancel");});}catch(const std::runtime_error &e){require(std::string(e.what())=="cancel","wrong cancellation");}require(!output.size(),"pre-write cancellation wrote");unsigned polls=0;try{output.write(octets("after"),[&]{if(++polls==2)throw std::runtime_error("cancel");});}catch(const std::runtime_error &e){require(std::string(e.what())=="cancel","wrong cancellation");}require(polls==2&&output.size()==5,"completed stream write incorrectly rolled back");});
  run("whole replacement preserves opened reader",[&]{ok(files.write("replace-open","old"));auto old=files.open("replace-open",FileMode::Read);ok(files.write("replace-open","new"));require(stringBytes(old.read(10))=="old"&&text(files.read("replace-open"))=="new","replacement retargeted reader");});
  run("new whole and streaming files have private protected ACL",[&]{ok(files.write("private-whole","private"));auto a=files.open("private-stream",FileMode::WriteTruncate);a.close();auto b=files.open("private-append",FileMode::Append);b.close();privateAcl(root/L"private-whole");privateAcl(root/L"private-stream");privateAcl(root/L"private-append");});
  run("leaf and directory reparse points are rejected",[&]{raw(outside/L"private","outside");link(outside/L"private",root/L"leaf-link",false);link(outside,root/L"dir-link",true);auto baseline=handles();for(auto name:{"leaf-link","dir-link/private"}){code(files.read(name),"VALIDATION");code(files.write(name,"escape"),"VALIDATION");for(auto mode:{FileMode::Read,FileMode::WriteTruncate,FileMode::Append})error("VALIDATION",[&]{files.open(name,mode);});}require(handles()==baseline,"reparse rejection leaked handles");std::ifstream check(outside/L"private",std::ios::binary);require(std::string(std::istreambuf_iterator<char>(check),{})=="outside","reparse traversal escaped");});
  run("parent handle remains pinned during replacement",[&]{fs::create_directory(root/L"race");ok(files.write("race/item","inside"));auto restore=[&]{if(fs::exists(root/L"race-moved")){RemoveDirectoryW((root/L"race").c_str());fs::rename(root/L"race-moved",root/L"race");}};try{unsigned polls=0;auto result=files.write("race/item","updated",[&]{if(++polls==3){fs::rename(root/L"race",root/L"race-moved");link(outside,root/L"race",true);}});ok(result);require(text(files.read("race-moved/item"))=="updated"&&!fs::exists(outside/L"item"),"parent race escaped");restore();}catch(...){restore();throw;}});
  run("root pinned across pathname replacement",[&]{auto moved=base/L"pinned";fs::rename(root,moved);fs::create_directories(root);raw(root/L"original","replacement");require(text(files.read("original"))=="retained","root retargeted");fs::remove_all(root);fs::rename(moved,root);});
  run("Unicode environment file capability and explicit scope denial",[&]{SetEnvironmentVariableW(L"NEX_FILES_ROOT",root.c_str());SetEnvironmentVariableW(L"NEX_FILES_WRITE",L"1");resetFileEnvironment();ok(fileWriteText("env.txt","environment"));require(text(fileReadText("env.txt"))=="environment","environment file capability");{FileScope deny(false);code(fileReadText("env.txt"),"CAPABILITY");code(fileWriteText("env.txt","escape"),"CAPABILITY");}require(text(fileReadText("env.txt"))=="environment","scope denial changed file");resetFileEnvironment();SetEnvironmentVariableW(L"NEX_FILES_ROOT",nullptr);SetEnvironmentVariableW(L"NEX_FILES_WRITE",nullptr);code(fileReadText("env.txt"),"CAPABILITY");resetFileEnvironment();});
  run("captured read grant crosses workers and retains revoked physical quota",[&]{
   auto resources=files.resourceScope(1);FileReadGrant grant;FileReadLease lease;
   {FileScope scope(files,resources);grant=captureFileReadGrant(false);lease=grant.lease("original");
    auto data=std::async(std::launch::async,[lease]{return lease.read();}).get();require(std::string(data.begin(),data.end())=="retained","captured worker read differs");require(resources.used()==1,"physical read quota missing");}
   error("E_RESOURCE_SCOPE",[&]{grant.check();});error("E_RESOURCE_SCOPE",[&]{lease.read();});
   require(resources.used()==1,"revocation released an outstanding physical lease");lease=FileReadLease{};require(resources.used()==0,"retired read lease leaked quota");
  });
  run("captured write and stream grants use coordinator authority on workers",[&]{
   FileScope scope(files);auto writes=captureFileWriteGrant(false);auto lease=writes.lease("captured-write");
   std::async(std::launch::async,[lease]{std::array<uint8_t,3> data{0,255,65};lease.write(data);}).get();
   auto opened=writes.openWrite("captured-stream");auto file=std::async(std::launch::async,[opened]{return opened.open();}).get();
   auto stream=file.lease();require(std::async(std::launch::async,[stream]{std::array<uint8_t,3> data{0,255,65};return stream.write(data);}).get()==3,"worker stream write differs");file.close();
   require(stringBytes(byteBuffer(unwrap(files.readBytes("captured-write")).object))==std::string("\0\xff" "A",3),"captured write differs");
   require(stringBytes(byteBuffer(unwrap(files.readBytes("captured-stream")).object))==std::string("\0\xff" "A",3),"captured stream differs");
  });
  run("captured read-only and absent grants fail before mutation",[&]{
   {FileScope scope(readonly);auto writes=captureFileWriteGrant(false);error("CAPABILITY",[&]{writes.openWrite("denied-capture");});}
   {FileScope scope(false);auto reads=captureFileReadGrant(false);auto writes=captureFileWriteGrant(false);error("CAPABILITY",[&]{reads.lease("original");});error("CAPABILITY",[&]{writes.lease("denied-capture");});}
   require(!fs::exists(root/L"denied-capture"),"denied captured grant mutated file");
  });
  run("Unicode SQLite path and principal isolation",[&]{auto database=base/L"данные 🧠.sqlite";SetEnvironmentVariableW(L"NEX_DATABASE",database.c_str());SetEnvironmentVariableW(L"NEX_STORAGE_OWNER",L"alice Я🧠");ok(storagePut("key","значение 🧠"));require(text(storageGet("key"))=="значение 🧠","SQLite roundtrip");SetEnvironmentVariableW(L"NEX_STORAGE_OWNER",L"bob");code(storageGet("key"),"NOT_FOUND");SetEnvironmentVariableW(L"NEX_STORAGE_OWNER",L"alice Я🧠");require(text(storageGet("key"))=="значение 🧠","SQLite persistence");ok(storageRemove("key"));SetEnvironmentVariableW(L"NEX_DATABASE",nullptr);SetEnvironmentVariableW(L"NEX_STORAGE_OWNER",nullptr);code(storageGet("key"),"CAPABILITY");});
  run("final temporary cleanup",[&]{noTemporary(root);});
  } // Release pinned roots before removing their containing directory on Windows.
  std::cout<<"RESULT passed="<<count<<" failed="<<failed<<std::endl;fs::remove_all(base);return failed?1:0;
 }catch(const DataError &e){std::cerr<<"FAIL "<<e.code<<": "<<e.what()<<std::endl;return 1;}catch(const std::exception &e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}
}
