#pragma once
#ifdef _WIN32
#include "nex/task_process.h"
#include "nex_host_windows.h"
#include "llvm/Support/Program.h"
#include <atomic>
#include <chrono>
#include <fstream>
#include <cwchar>
#include <memory>
#include <thread>

namespace nex::windows_process {
inline std::atomic_flag active=ATOMIC_FLAG_INIT;
inline std::atomic<int> interrupted{0};
inline BOOL WINAPI interrupt(DWORD event){
  if(event==CTRL_C_EVENT||event==CTRL_BREAK_EVENT||event==CTRL_CLOSE_EVENT){interrupted.store(2);return TRUE;}return FALSE;
}
[[noreturn]] inline void fail(const std::string &operation){
  auto code=GetLastError();throw Error("E_TASK_PROCESS",operation+" failed (Windows error "+std::to_string(code)+")");
}
inline std::wstring quote(std::wstring_view value){
  std::wstring result=L"\"";size_t slashes=0;
  for(auto c:value){if(c==L'\\'){++slashes;continue;}
    result.append(c==L'"'?slashes*2+1:slashes,L'\\');slashes=0;result+=c;}
  result.append(slashes*2,L'\\');return result+L'"';
}
struct Less {bool operator()(const std::wstring &a,const std::wstring &b)const{return CompareStringOrdinal(a.data(),int(a.size()),b.data(),int(b.size()),TRUE)==CSTR_LESS_THAN;}};
struct Guard {
  nexrt::host_windows::Handle job,process,thread,completion,stopEvent;
  std::vector<std::unique_ptr<nexrt::host_windows::Handle>> members;
  uint64_t observedMembers=0;
  std::vector<unsigned char> attributeStorage;LPPROC_THREAD_ATTRIBUTE_LIST attributes=nullptr;
  bool handler=false,attributesReady=false;
  Guard(){if(active.test_and_set())throw Error("E_TASK_PROCESS","task process supervisor is already active");interrupted=0;}
  ~Guard(){
    if(job.value!=INVALID_HANDLE_VALUE&&job.value)TerminateJobObject(job.value,137);
    if(process.value!=INVALID_HANDLE_VALUE&&process.value)WaitForSingleObject(process.value,5000);
    if(handler)SetConsoleCtrlHandler(interrupt,FALSE);
    if(attributesReady)DeleteProcThreadAttributeList(attributes);active.clear();
  }
};
inline void observeMembers(Guard &guard){
  for(;;){
    DWORD message=0;ULONG_PTR key=0;LPOVERLAPPED payload=nullptr;
    if(!GetQueuedCompletionStatus(guard.completion.value,&message,&key,&payload,0)){
      if(GetLastError()==WAIT_TIMEOUT)return;fail("read task membership notifications");
    }
    if(message!=JOB_OBJECT_MSG_NEW_PROCESS)continue;
    ++guard.observedMembers;
    auto process=std::make_unique<nexrt::host_windows::Handle>(OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,DWORD(reinterpret_cast<ULONG_PTR>(payload))));
    if(!process->value){
      // A PID no longer present has already completed physical teardown.
      if(GetLastError()==ERROR_INVALID_PARAMETER)continue;fail("retain task member process");
    }
    BOOL belongs=FALSE;if(!IsProcessInJob(process->value,guard.job.value,&belongs))fail("check task member identity");
    // A reused PID outside this private job means the original member is gone.
    if(belongs)guard.members.push_back(std::move(process));
  }
}
inline uint64_t size(const std::filesystem::path &path){std::error_code error;auto result=std::filesystem::file_size(path,error);return error?0:result;}
inline std::string prefix(const std::filesystem::path &path){
  std::ifstream input(path,std::ios::binary);if(!input)throw Error("E_TASK_PROCESS","cannot read task process output");
  std::string result(std::min<uint64_t>(size(path),8*1024*1024),'\0');input.read(result.data(),result.size());result.resize(input.gcount());return result;
}
inline TaskProcessResult run(const std::vector<std::string> &arguments,const std::string &directory,
  const std::map<std::string,std::string> &overrides,unsigned seconds,const std::string &logs){
  using nexrt::platform::wide;using nexrt::host_windows::Handle;
  if(arguments.empty()||!seconds)throw Error("E_TASK_PROCESS","task command and positive timeout required");
  for(const auto &value:arguments)if(value.find('\0')!=std::string::npos)throw Error("E_TASK_PROCESS","NUL is not valid in task process arguments");
  auto executable=llvm::sys::findProgramByName(arguments[0]);if(!executable)throw Error("E_TOOL","cannot find task compiler executable: "+arguments[0]);
  std::wstring command;for(const auto &value:arguments){if(!command.empty())command+=L' ';command+=quote(wide(value));}
  if(command.size()>=32767)throw Error("E_TASK_PROCESS","Windows task command exceeds32766 UTF-16 units");
  Guard guard;
  nexrt::host_windows::PrivateSecurity controlSecurity(EVENT_MODIFY_STATE|SYNCHRONIZE);
  SECURITY_ATTRIBUTES controlAttributes{sizeof(controlAttributes),&controlSecurity.descriptor,FALSE};
  auto controlName=L"Local\\NEX.Task.Stop."+std::to_wstring(GetCurrentProcessId());
  guard.stopEvent.value=CreateEventW(&controlAttributes,TRUE,FALSE,controlName.c_str());
  if(!guard.stopEvent.value||GetLastError()==ERROR_ALREADY_EXISTS)fail("create private task control event");
  std::map<std::wstring,std::wstring,Less> environment;
  auto raw=GetEnvironmentStringsW();if(!raw)fail("read process environment");
  struct Environment {LPWCH value;~Environment(){FreeEnvironmentStringsW(value);}} release{raw};
  for(const wchar_t *row=raw;*row;row+=std::wcslen(row)+1){std::wstring value=row;auto split=value.find(L'=',value[0]==L'='?1:0);
    if(split!=std::wstring::npos)environment[value.substr(0,split)]=value.substr(split+1);}
  for(const auto &[name,value]:overrides){
    if(name.empty()||name.find_first_of(std::string("=\0",2))!=std::string::npos||value.find('\0')!=std::string::npos)throw Error("E_TASK_PROCESS","invalid Windows environment override");
    environment[wide(name)]=wide(value);
  }
  std::wstring block;for(const auto &[name,value]:environment){block+=name+L'='+value;block+=L'\0';}block+=L'\0';
  std::filesystem::create_directories(wide(logs));auto out=std::filesystem::path(wide(logs))/L"stdout",err=std::filesystem::path(wide(logs))/L"stderr";
  nexrt::host_windows::PrivateSecurity security;SECURITY_ATTRIBUTES inheritable{sizeof(inheritable),&security.descriptor,TRUE};
  Handle output(CreateFileW(out.c_str(),GENERIC_WRITE|FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,&inheritable,CREATE_ALWAYS,FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
  Handle errors(CreateFileW(err.c_str(),GENERIC_WRITE|FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,&inheritable,CREATE_ALWAYS,FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
  SECURITY_ATTRIBUTES nullAttributes{sizeof(nullAttributes),nullptr,TRUE};Handle input(CreateFileW(L"NUL",GENERIC_READ,7,&nullAttributes,OPEN_EXISTING,0,nullptr));
  if(output.value==INVALID_HANDLE_VALUE||errors.value==INVALID_HANDLE_VALUE||input.value==INVALID_HANDLE_VALUE)fail("open task standard handles");
  auto outIdentity=nexrt::host_windows::identity(output.value),errIdentity=nexrt::host_windows::identity(errors.value);
  if(!outIdentity||outIdentity->directory||!errIdentity||errIdentity->directory)throw Error("E_TASK_PROCESS","task output requires regular non-reparse files");
  guard.job.value=CreateJobObjectW(nullptr,nullptr);if(!guard.job.value)fail("create task job");
  JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
  if(!SetInformationJobObject(guard.job.value,JobObjectExtendedLimitInformation,&limits,sizeof(limits)))fail("configure task job");
  guard.completion.value=CreateIoCompletionPort(INVALID_HANDLE_VALUE,nullptr,0,1);
  if(!guard.completion.value)fail("create task completion port");
  JOBOBJECT_ASSOCIATE_COMPLETION_PORT association{&guard,guard.completion.value};
  if(!SetInformationJobObject(guard.job.value,JobObjectAssociateCompletionPortInformation,&association,sizeof(association)))fail("observe task process membership");
  SIZE_T bytes=0;InitializeProcThreadAttributeList(nullptr,1,0,&bytes);guard.attributeStorage.resize(bytes);
  guard.attributes=reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(guard.attributeStorage.data());
  if(!InitializeProcThreadAttributeList(guard.attributes,1,0,&bytes))fail("initialize task handle inheritance");
  guard.attributesReady=true;
  HANDLE handles[]={input.value,output.value,errors.value};
  if(!UpdateProcThreadAttribute(guard.attributes,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,handles,sizeof(handles),nullptr,nullptr))fail("restrict inherited task handles");
  STARTUPINFOEXW start{};start.StartupInfo.cb=sizeof(start);start.StartupInfo.dwFlags=STARTF_USESTDHANDLES;
  start.StartupInfo.hStdInput=input.value;start.StartupInfo.hStdOutput=output.value;start.StartupInfo.hStdError=errors.value;start.lpAttributeList=guard.attributes;
  PROCESS_INFORMATION process{};auto program=wide(*executable),cwd=wide(directory);
  if(!SetConsoleCtrlHandler(interrupt,TRUE))fail("install task interrupt handler");guard.handler=true;
  if(!CreateProcessW(program.c_str(),command.data(),nullptr,nullptr,TRUE,
      CREATE_SUSPENDED|CREATE_UNICODE_ENVIRONMENT|CREATE_NEW_PROCESS_GROUP|EXTENDED_STARTUPINFO_PRESENT,
      block.data(),cwd.c_str(),&start.StartupInfo,&process))fail("launch "+arguments[0]);
  guard.process.value=process.hProcess;guard.thread.value=process.hThread;
  if(!AssignProcessToJobObject(guard.job.value,guard.process.value)){TerminateProcess(guard.process.value,137);fail("assign task process to job");}
  if(ResumeThread(guard.thread.value)==DWORD(-1))fail("resume task process");
  auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(seconds);TaskProcessResult result{};DWORD exit=0;
  for(;;){
    observeMembers(guard);
    auto waited=WaitForSingleObject(guard.process.value,10);if(waited==WAIT_OBJECT_0)break;if(waited==WAIT_FAILED)fail("wait for task process");
    if(std::chrono::steady_clock::now()>=deadline){result.timedOut=true;break;}
    if(size(out)>8*1024*1024||size(err)>8*1024*1024){result.outputLimit=true;break;}
    auto control=WaitForSingleObject(guard.stopEvent.value,0);
    if(control==WAIT_OBJECT_0)interrupted=2;
    else if(control!=WAIT_TIMEOUT)fail("inspect task control event");
    if(interrupted.load())break;
  }
  if(!GetExitCodeProcess(guard.process.value,&exit))fail("read task exit status");
  if(!TerminateJobObject(guard.job.value,interrupted.load()?130:137))fail("stop task job");
  auto settlement=std::chrono::steady_clock::now()+std::chrono::seconds(10);
  for(;;){JOBOBJECT_BASIC_ACCOUNTING_INFORMATION info{};
    observeMembers(guard);
    if(!QueryInformationJobObject(guard.job.value,JobObjectBasicAccountingInformation,&info,sizeof(info),nullptr))fail("inspect task job settlement");
    if(!info.ActiveProcesses&&guard.observedMembers==info.TotalProcesses){
      bool complete=true;
      for(const auto &member:guard.members){auto waited=WaitForSingleObject(member->value,0);
        if(waited==WAIT_FAILED)fail("wait for task member teardown");complete&=waited==WAIT_OBJECT_0;}
      if(complete)break;
    }
    if(std::chrono::steady_clock::now()>=settlement)throw Error("E_TASK_PROCESS","task job did not physically settle within10 seconds");
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  if(exit==STILL_ACTIVE&&!GetExitCodeProcess(guard.process.value,&exit))fail("read settled task exit status");
  result.interrupted=interrupted.load();result.process={int(exit),prefix(out),prefix(err)};
  result.outputLimit=result.outputLimit||size(out)>8*1024*1024||size(err)>8*1024*1024;
  for(const auto &path:{out,err})if(size(path)>8*1024*1024)std::filesystem::resize_file(path,8*1024*1024);
  return result;
}
}
#endif
