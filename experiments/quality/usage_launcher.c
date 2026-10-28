#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

int main(int argc,char **argv) {
  if(argc<3)return 125;
  pid_t child=fork();
  if(child<0){perror("measurement fork");return 125;}
  if(child==0){execvp(argv[2],argv+2);perror("measurement exec");_exit(127);}
  int status;struct rusage usage;
  while(wait4(child,&status,0,&usage)<0){if(errno==EINTR)continue;perror("measurement wait4");return 125;}
  int code=WIFEXITED(status)?WEXITSTATUS(status):WIFSIGNALED(status)?128+WTERMSIG(status):125;
  FILE *output=fopen(argv[1],"wx");
  if(!output){perror("measurement output");return 125;}
  long long rss=(long long)usage.ru_maxrss;
#ifndef __APPLE__
  rss*=1024;
#endif
  int written=fprintf(output,"{\"exit_code\":%d,\"child_pid\":%ld,\"user_seconds\":%.9f,\"system_seconds\":%.9f,\"maximum_rss_bytes\":%lld}\n",code,(long)child,
    (double)usage.ru_utime.tv_sec+(double)usage.ru_utime.tv_usec/1000000.0,
    (double)usage.ru_stime.tv_sec+(double)usage.ru_stime.tv_usec/1000000.0,rss);
  int closed=fclose(output);
  if(written<0||closed!=0)return 125;
  return code;
}
