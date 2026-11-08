#include "nex_host_windows.h"
#include <iostream>
int wmain(int argc,wchar_t **argv){
 if(argc!=2)return 2;std::cout.setf(std::ios::unitbuf);namespace fs=std::filesystem;fs::path root(argv[1]);
 if(!nexrt::host_windows::createPrivateDirectory(root))return 3;
 fs::create_directory(root/L"nested");nexrt::host_windows::writePrivateFile(root/L"nested/data","42");
 nexrt::host_windows::DirectoryPermissions outer(root),inner(root/L"nested");
 nexrt::host_windows::privateAccess(root/L"nested/data",FILE_GENERIC_READ);
 inner.seal(FILE_GENERIC_READ|FILE_GENERIC_EXECUTE);outer.seal(FILE_GENERIC_READ|FILE_GENERIC_EXECUTE);
 std::cout<<"sealed_snapshot_ready=1\n";
 TerminateProcess(GetCurrentProcess(),93);return 94;
}
