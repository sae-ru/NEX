// Controlled Windows test runner. Requires Windows 10 / Server 2016 or later.
// Ownership comes only from a fresh unnamed kernel job, never parent PIDs.
#define _WIN32_WINNT 0x0A00
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <sddl.h>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

struct Handle {
  HANDLE value = nullptr;
  Handle() = default;
  explicit Handle(HANDLE h) : value(h) {}
  Handle(const Handle &) = delete;
  Handle &operator=(const Handle &) = delete;
  Handle(Handle &&o) noexcept : value(o.value) { o.value = nullptr; }
  Handle &operator=(Handle &&o) noexcept {
    if (this != &o) { reset(); value = o.value; o.value = nullptr; }
    return *this;
  }
  ~Handle() { reset(); }
  bool valid() const { return value && value != INVALID_HANDLE_VALUE; }
  void reset(HANDLE h = nullptr) {
    if (valid()) CloseHandle(value);
    value = h;
  }
};
static void checked(BOOL ok, const char *where) {
  if (!ok) throw std::runtime_error(std::string(where) + ": Win32 " + std::to_string(GetLastError()));
}
static std::string utf8(const std::wstring &s) {
  if (s.empty()) return {};
  int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s.data(), int(s.size()), nullptr, 0, nullptr, nullptr);
  checked(n != 0, "UTF16 conversion");
  std::string r(n, '\0');
  checked(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s.data(), int(s.size()), r.data(), n, nullptr, nullptr) == n, "UTF16 conversion");
  return r;
}
static std::string json(const std::string &s) {
  const char *hex = "0123456789abcdef";
  std::string r = "\"";
  for (unsigned char c : s) {
    if (c == '"' || c == '\\') { r += '\\'; r += c; }
    else if (c < 32) { r += "\\u00"; r += hex[c >> 4]; r += hex[c & 15]; }
    else r += c;
  }
  return r + '"';
}
static std::wstring quote(const std::wstring &s) {
  std::wstring r = L"\""; size_t slashes = 0;
  for (wchar_t c : s) {
    if (c == L'\\') { ++slashes; continue; }
    r.append(c == L'"' ? slashes * 2 + 1 : slashes, L'\\'); r += c; slashes = 0;
  }
  r.append(slashes * 2, L'\\'); return r + L'"';
}
static uint64_t created(HANDLE h) {
  FILETIME c{}, e{}, k{}, u{}; checked(GetProcessTimes(h, &c, &e, &k, &u), "GetProcessTimes");
  return (uint64_t(c.dwHighDateTime) << 32) | c.dwLowDateTime;
}
struct Record {
  Handle process;
  DWORD pid = 0;
  uint64_t birth = 0;
  std::string image;
};
struct Attributes {
  std::vector<unsigned char> storage;
  LPPROC_THREAD_ATTRIBUTE_LIST value = nullptr;
  explicit Attributes(DWORD count) {
    SIZE_T size = 0; InitializeProcThreadAttributeList(nullptr, count, 0, &size);
    checked(size != 0, "attribute size"); storage.resize(size);
    value = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(storage.data());
    if (!InitializeProcThreadAttributeList(value, count, 0, &size)) { value = nullptr; checked(FALSE, "attribute init"); }
  }
  ~Attributes() { if (value) DeleteProcThreadAttributeList(value); }
};
struct Sid {
  PSID value = nullptr;
  explicit Sid(const std::wstring &text, DWORD kind) {
    checked(ConvertStringSidToSidW(text.c_str(), &value), "parse AppContainer SID");
    SID_IDENTIFIER_AUTHORITY authority = SECURITY_APP_PACKAGE_AUTHORITY;
    if (!IsValidSid(value) || *GetSidSubAuthorityCount(value) < 2 ||
        std::memcmp(GetSidIdentifierAuthority(value), &authority, sizeof(authority)) ||
        *GetSidSubAuthority(value, 0) != kind) {
      LocalFree(value); value = nullptr;
      throw std::runtime_error("expected package/capability SID from the AppPackage authority");
    }
  }
  Sid(const Sid &) = delete;
  Sid &operator=(const Sid &) = delete;
  Sid(Sid &&other) noexcept : value(other.value) { other.value = nullptr; }
  ~Sid() { if (value) LocalFree(value); }
  std::string text() const {
    LPWSTR name = nullptr; checked(ConvertSidToStringSidW(value, &name), "format AppContainer SID");
    auto result = utf8(name); LocalFree(name); return result;
  }
};
struct Launch {
  std::wstring directory, package;
  std::vector<std::wstring> capabilities;
};
struct Probe {
  Handle job, port, root, outside;
  std::map<std::pair<DWORD, uint64_t>, Record> records;
  std::vector<DWORD> notifications;
  std::vector<DWORD> inaccessible;
  DWORD root_pid = 0;
  bool created_root = false, member_verified = false, resumed = false;
  bool timed_out = false, job_terminated = false, complete = false;
  bool accounting_observed = false;
  bool outside_before = false, outside_after = false;
  DWORD outside_pid = 0;
  DWORD active = 0, total = 0, root_exit = STILL_ACTIVE;
  std::string error;
  bool app_requested = false, app_verified = false;
  std::string app_sid, directory;
  std::vector<std::string> app_capabilities;

  ~Probe() {
    // Only the handle returned by our CreateProcess can reach this fallback.
    if (root.valid() && !member_verified && WaitForSingleObject(root.value, 0) == WAIT_TIMEOUT) {
      TerminateProcess(root.value, 125); WaitForSingleObject(root.value, 5000);
    }
    // KILL_ON_JOB_CLOSE affects only members of this fresh, private job.
    job.reset();
  }
  void accounting() {
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION info{};
    checked(QueryInformationJobObject(job.value, JobObjectBasicAccountingInformation, &info, sizeof(info), nullptr), "job accounting");
    active = info.ActiveProcesses; total = info.TotalProcesses;
    accounting_observed = true;
  }
  void capture(DWORD pid) {
    Handle h(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, pid));
    if (!h.valid()) { inaccessible.push_back(pid); return; }
    BOOL member = FALSE;
    // A notification's PID can already be stale. It grants no authority.
    if (!IsProcessInJob(h.value, job.value, &member) || !member) return;
    uint64_t birth = created(h.value);
    auto key = std::make_pair(pid, birth);
    if (records.count(key)) return;
    wchar_t image[32768]; DWORD length = 32768;
    checked(QueryFullProcessImageNameW(h.value, 0, image, &length), "owned image path");
    records.emplace(key, Record{std::move(h), pid, birth, utf8(std::wstring(image, length))});
  }
  void sample() {
    std::vector<ULONG_PTR> buffer(256);
    for (;;) {
      auto *ids = reinterpret_cast<JOBOBJECT_BASIC_PROCESS_ID_LIST *>(buffer.data());
      if (QueryInformationJobObject(job.value, JobObjectBasicProcessIdList, ids, DWORD(buffer.size() * sizeof(ULONG_PTR)), nullptr)) {
        for (DWORD i = 0; i < ids->NumberOfProcessIdsInList; ++i) capture(DWORD(ids->ProcessIdList[i]));
        return;
      }
      checked(GetLastError() == ERROR_MORE_DATA && buffer.size() < 1024 * 1024, "job process IDs");
      buffer.resize(buffer.size() * 2);
    }
  }
  void check_outside(bool &result) {
    if (!outside.valid()) return;
    BOOL member = TRUE;
    checked(IsProcessInJob(outside.value, job.value, &member), "outside canary membership");
    checked(!member, "outside canary unexpectedly belongs to job");
    result = WaitForSingleObject(outside.value, 0) == WAIT_TIMEOUT;
  }
  void retire_on_error() noexcept {
    if (job.valid() && created_root && member_verified) {
      if (TerminateJobObject(job.value, 125)) job_terminated = true;
      for (int i = 0; i < 500; ++i) {
        JOBOBJECT_BASIC_ACCOUNTING_INFORMATION info{};
        if (!QueryInformationJobObject(job.value, JobObjectBasicAccountingInformation, &info, sizeof(info), nullptr)) break;
        active = info.ActiveProcesses; total = info.TotalProcesses;
        if (!active) break;
        Sleep(10);
      }
    } else if (root.valid() && !member_verified) {
      TerminateProcess(root.value, 125); WaitForSingleObject(root.value, 5000);
    }
    if (root.valid()) GetExitCodeProcess(root.value, &root_exit);
    if (job.valid()) {
      JOBOBJECT_BASIC_ACCOUNTING_INFORMATION info{};
      if (QueryInformationJobObject(job.value, JobObjectBasicAccountingInformation, &info, sizeof(info), nullptr)) {
        active = info.ActiveProcesses; total = info.TotalProcesses; accounting_observed = true;
      }
      try { check_outside(outside_after); } catch (...) {}
    }
  }
  void run(const std::wstring &prefix, uint64_t timeout, DWORD canary, bool reject, const Launch &launch, int argc, wchar_t **argv, int first) {
    app_requested = !launch.package.empty(); directory = utf8(launch.directory);
    std::vector<Sid> sids;
    std::vector<SID_AND_ATTRIBUTES> capabilities;
    if (app_requested) {
      sids.emplace_back(launch.package, SECURITY_APP_PACKAGE_BASE_RID);
      app_sid = sids.front().text();
      sids.reserve(1 + launch.capabilities.size());
      for (const auto &text : launch.capabilities) {
        sids.emplace_back(text, SECURITY_CAPABILITY_BASE_RID);
        auto canonical = sids.back().text();
        checked(std::find(app_capabilities.begin(), app_capabilities.end(), canonical) == app_capabilities.end(), "duplicate capability");
        app_capabilities.push_back(canonical);
      }
      for (size_t i = 1; i < sids.size(); ++i) capabilities.push_back({sids[i].value, SE_GROUP_ENABLED});
    }
    job.reset(CreateJobObjectW(nullptr, nullptr)); checked(job.valid(), "create private job");
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    checked(SetInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits)), "kill-on-close");
    port.reset(CreateIoCompletionPort(INVALID_HANDLE_VALUE, nullptr, 0, 1)); checked(port.valid(), "completion port");
    JOBOBJECT_ASSOCIATE_COMPLETION_PORT association{this, port.value};
    checked(SetInformationJobObject(job.value, JobObjectAssociateCompletionPortInformation, &association, sizeof(association)), "associate completion port");
    outside_pid = canary;
    if (canary) { outside.reset(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, canary)); checked(outside.valid(), "open own outside canary"); check_outside(outside_before); checked(outside_before, "outside canary not alive"); }
    SECURITY_ATTRIBUTES sa{sizeof(sa), nullptr, TRUE};
    Handle output(CreateFileW((prefix + L".stdout").c_str(), GENERIC_WRITE, FILE_SHARE_READ, &sa, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr));
    Handle diagnostics(CreateFileW((prefix + L".stderr").c_str(), GENERIC_WRITE, FILE_SHARE_READ, &sa, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr));
    Handle input(CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    checked(output.valid() && diagnostics.valid() && input.valid(), "capture streams");
    HANDLE inherited[] = {input.value, output.value, diagnostics.value};
    HANDLE jobs[] = {reject ? INVALID_HANDLE_VALUE : job.value};
    Attributes attributes(app_requested ? 3 : 2);
    checked(UpdateProcThreadAttribute(attributes.value, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherited, sizeof(inherited), nullptr, nullptr), "stdio handle list");
    checked(UpdateProcThreadAttribute(attributes.value, 0, PROC_THREAD_ATTRIBUTE_JOB_LIST, jobs, sizeof(jobs), nullptr, nullptr), "job attribute");
    SECURITY_CAPABILITIES security{};
    if (app_requested) {
      security.AppContainerSid = sids.front().value;
      security.Capabilities = capabilities.empty() ? nullptr : capabilities.data();
      security.CapabilityCount = DWORD(capabilities.size());
      checked(UpdateProcThreadAttribute(attributes.value, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
          &security, sizeof(security), nullptr, nullptr), "AppContainer attribute");
    }
    STARTUPINFOEXW startup{}; startup.StartupInfo.cb = sizeof(startup); startup.lpAttributeList = attributes.value;
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput = input.value; startup.StartupInfo.hStdOutput = output.value; startup.StartupInfo.hStdError = diagnostics.value;
    std::wstring command;
    checked(std::filesystem::path(argv[first]).is_absolute(), "absolute program path required");
    for (int i = first; i < argc; ++i) { if (i != first) command += L' '; command += quote(argv[i]); }
    PROCESS_INFORMATION pi{};
    checked(CreateProcessW(argv[first], command.data(), nullptr, nullptr, TRUE,
        EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | CREATE_NO_WINDOW,
        nullptr, launch.directory.empty() ? nullptr : launch.directory.c_str(), &startup.StartupInfo, &pi), "CreateProcess with job assignment");
    root.reset(pi.hProcess); Handle thread(pi.hThread); root_pid = pi.dwProcessId; created_root = true;
    BOOL member = FALSE; checked(IsProcessInJob(root.value, job.value, &member), "new root job membership");
    checked(member, "new root not assigned"); member_verified = true; capture(root_pid);
    if (app_requested) {
      Handle token; checked(OpenProcessToken(root.value, TOKEN_QUERY, &token.value), "AppContainer root token");
      DWORD is_app = 0, bytes = 0;
      checked(GetTokenInformation(token.value, TokenIsAppContainer, &is_app, sizeof(is_app), &bytes), "AppContainer root flag");
      checked(is_app == 1, "root lacks AppContainer token");
      GetTokenInformation(token.value, TokenAppContainerSid, nullptr, 0, &bytes);
      checked(bytes >= sizeof(TOKEN_APPCONTAINER_INFORMATION), "AppContainer root SID size");
      std::vector<unsigned char> info(bytes);
      checked(GetTokenInformation(token.value, TokenAppContainerSid, info.data(), bytes, &bytes), "AppContainer root SID");
      checked(EqualSid(reinterpret_cast<TOKEN_APPCONTAINER_INFORMATION *>(info.data())->TokenAppContainer, sids.front().value), "AppContainer root SID mismatch");
      GetTokenInformation(token.value, TokenCapabilities, nullptr, 0, &bytes);
      checked(bytes >= sizeof(DWORD), "AppContainer capability size"); info.resize(bytes);
      checked(GetTokenInformation(token.value, TokenCapabilities, info.data(), bytes, &bytes), "AppContainer root capabilities");
      auto *groups = reinterpret_cast<TOKEN_GROUPS *>(info.data());
      checked(groups->GroupCount == capabilities.size(), "AppContainer capability count mismatch");
      for (const auto &capability : capabilities) {
        bool found = false;
        for (DWORD i = 0; i < groups->GroupCount; ++i)
          if (EqualSid(capability.Sid, groups->Groups[i].Sid) && (groups->Groups[i].Attributes & SE_GROUP_ENABLED)) found = true;
        checked(found, "AppContainer root capability mismatch");
      }
      app_verified = true;
    }
    checked(ResumeThread(thread.value) != DWORD(-1), "resume assigned root"); resumed = true;
    uint64_t started = GetTickCount64(), retirement = 0;
    for (;;) {
      sample(); accounting();
      if (!active) break;
      if (!timed_out && GetTickCount64() - started >= timeout) {
        timed_out = true; checked(TerminateJobObject(job.value, 238), "terminate own timed-out job");
        job_terminated = true; retirement = GetTickCount64();
      }
      checked(!timed_out || GetTickCount64() - retirement < 5000, "timed-out job did not retire");
      DWORD message = 0; ULONG_PTR key = 0; LPOVERLAPPED payload = nullptr;
      BOOL received = GetQueuedCompletionStatus(port.value, &message, &key, &payload, 10);
      if (received) {
        checked(key == reinterpret_cast<ULONG_PTR>(this), "foreign completion key");
        notifications.push_back(message);
        if (message == JOB_OBJECT_MSG_NEW_PROCESS) capture(DWORD(reinterpret_cast<ULONG_PTR>(payload)));
      } else checked(GetLastError() == WAIT_TIMEOUT, "completion wait");
    }
    checked(WaitForSingleObject(root.value, 5000) == WAIT_OBJECT_0, "root not retired");
    uint64_t final_wait = GetTickCount64();
    for (auto &[key, record] : records) {
      uint64_t elapsed = GetTickCount64() - final_wait;
      checked(WaitForSingleObject(record.process.value, DWORD(elapsed < 5000 ? 5000 - elapsed : 0)) == WAIT_OBJECT_0,
              "captured job member not retired");
    }
    checked(GetExitCodeProcess(root.value, &root_exit), "root exit code");
    check_outside(outside_after); complete = true;
  }
  void write(const std::wstring &prefix) {
    std::ofstream out(std::filesystem::path(prefix + L".json"), std::ios::binary);
    if (!out) throw std::runtime_error("cannot write observation report");
    out << "{\n\"schema\":\"nex.windows-job-observation/1\",\"probe_completed\":" << (complete ? "true" : "false")
        << ",\"error\":" << json(error) << ",\"created_root\":" << (created_root ? "true" : "false")
        << ",\"root_pid\":" << root_pid << ",\"root_exit_code\":";
    if (created_root) out << root_exit; else out << "null";
    out << ",\"root_job_verified_before_resume\":" << (member_verified ? "true" : "false")
        << ",\"root_resumed\":" << (resumed ? "true" : "false")
        << ",\"assignment_at_creation\":true,\"stdio_handles_only\":true,\"parent_PID_ownership_used\":false"
        << ",\"appcontainer_requested\":" << (app_requested ? "true" : "false")
        << ",\"appcontainer_verified_before_resume\":" << (app_verified ? "true" : "false")
        << ",\"appcontainer_sid\":" << json(app_sid) << ",\"working_directory\":" << json(directory)
        << ",\"appcontainer_capabilities\":[";
    for (size_t i = 0; i < app_capabilities.size(); ++i) { if (i) out << ','; out << json(app_capabilities[i]); }
    out << ']'
        << ",\"timed_out\":" << (timed_out ? "true" : "false")
        << ",\"private_job_termination_requested\":" << (job_terminated ? "true" : "false")
        << ",\"active_job_processes\":" << active << ",\"total_job_processes\":" << total
        << ",\"final_job_accounting_observed\":" << (accounting_observed ? "true" : "false")
        << ",\"outside_canary_pid\":" << outside_pid << ",\"outside_canary_alive_before\":" << (outside_before ? "true" : "false")
        << ",\"outside_canary_alive_after\":" << (outside_after ? "true" : "false")
        << ",\"processes\":[";
    bool separator = false;
    for (auto &[key, r] : records) {
      DWORD code = STILL_ACTIVE; BOOL got = GetExitCodeProcess(r.process.value, &code);
      if (separator) out << ','; separator = true;
      out << "{\"pid\":" << r.pid << ",\"created_100ns\":" << r.birth << ",\"image\":" << json(r.image)
          << ",\"kernel_membership_verified\":true,\"exited\":" << (WaitForSingleObject(r.process.value, 0) == WAIT_OBJECT_0 ? "true" : "false")
          << ",\"exit_code\":"; if (got) out << code; else out << "null"; out << '}';
    }
    out << "],\"capture_inaccessible_notifications\":" << inaccessible.size()
        << ",\"completion_notifications\":" << notifications.size()
        << ",\"all_child_exit_codes_claimed\":false}\n";
    out.flush(); if (!out) throw std::runtime_error("observation report write failed");
  }
};
int wmain(int argc, wchar_t **argv) {
  if (argc == 2 && std::wstring(argv[1]) == L"--describe") {
    std::cout << "{\"schema\":\"nex.windows-job-observer-capabilities/1\","
                 "\"kernel_job_assignment_at_creation\":true,\"appcontainer_at_creation\":true,"
                 "\"root_token_verified_before_resume\":true,\"explicit_working_directory\":true}\n";
    return 0;
  }
  if (argc < 6) return 126;
  std::wstring prefix = argv[1];
  wchar_t *end = nullptr; uint64_t timeout = wcstoull(argv[2], &end, 10);
  if (!end || *end || timeout < 1 || timeout > 3600000) return 126;
  DWORD canary = wcstoul(argv[3], &end, 10); if (!end || *end) return 126;
  int first = 4; bool reject = false; Launch launch;
  while (first < argc && std::wstring(argv[first]) != L"--") {
    std::wstring flag = argv[first++];
    if (flag == L"--reject-assignment" && !reject) { reject = true; continue; }
    if (first >= argc) return 126;
    if (std::wstring(argv[first]).empty()) return 126;
    if (flag == L"--directory" && launch.directory.empty()) launch.directory = argv[first++];
    else if (flag == L"--appcontainer-sid" && launch.package.empty()) launch.package = argv[first++];
    else if (flag == L"--capability" && launch.capabilities.size() < 64) launch.capabilities.emplace_back(argv[first++]);
    else return 126;
  }
  if ((!launch.directory.empty() && !std::filesystem::path(launch.directory).is_absolute()) ||
      (launch.package.empty() && !launch.capabilities.empty())) return 126;
  if (first >= argc || std::wstring(argv[first++]) != L"--" || first >= argc) return 126;
  Probe probe;
  try { probe.run(prefix, timeout, canary, reject, launch, argc, argv, first); }
  catch (const std::exception &e) { probe.error = e.what(); probe.retire_on_error(); }
  try { probe.write(prefix); }
  catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 125; }
  if (!probe.complete || !probe.error.empty()) return 125;
  return probe.timed_out ? 124 : int(probe.root_exit);
}
