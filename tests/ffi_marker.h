#pragma once
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
static void nex_test_marker(const char *variable,char event){
  wchar_t name[256],path[32768];
  if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,variable,-1,name,256))return;
  DWORD size=GetEnvironmentVariableW(name,path,32768);if(!size||size>=32768)return;
  HANDLE file=CreateFileW(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return;DWORD written=0;(void)WriteFile(file,&event,1,&written,NULL);CloseHandle(file);
}
#else
#include <fcntl.h>
#include <stdlib.h>
#include <unistd.h>
static void nex_test_marker(const char *variable,char event){
  const char *path=getenv(variable);if(!path)return;
  int fd=open(path,O_WRONLY|O_CREAT|O_APPEND,0600);if(fd<0)return;(void)write(fd,&event,1);close(fd);
}
#endif
