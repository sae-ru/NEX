#define _WIN32_WINNT 0x0A00
#include <windows.h>
#include <cstdio>
#include <string>
#include <vector>
int wmain(int argc,wchar_t **argv){
 std::vector<wchar_t> module(32768),result(32768);
 DWORD n=GetModuleFileNameW(nullptr,module.data(),DWORD(module.size()));
 std::printf("MODULE_LENGTH %lu ERROR %lu\n",n,GetLastError());
 SetLastError(0);n=GetLongPathNameW(module.data(),result.data(),DWORD(result.size()));
 std::printf("OWN_LONG_PATH_LENGTH %lu ERROR %lu\n",n,GetLastError());
 if(argc==2){SetLastError(0);n=GetLongPathNameW(argv[1],result.data(),DWORD(result.size()));std::printf("TARGET_LONG_PATH_LENGTH %lu ERROR %lu\n",n,GetLastError());}
 return 0;
}
