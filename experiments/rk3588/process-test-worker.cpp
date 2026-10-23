// Controlled fake child. This does not emulate a hardware provider.
#include <unistd.h>
#include <signal.h>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <fstream>
static void put32(uint32_t n){uint8_t b[4];for(int i=0;i<4;++i)b[i]=uint8_t(n>>(8*i));write(1,b,4);}
int main(){
 std::string mode=std::getenv("NEX_TEST_MODE");
 if(auto path=std::getenv("NEX_TEST_PID")){std::ofstream o(path);o<<getpid();}
 if(mode=="cancel"){sleep(60);return 3;}
 if(mode=="killed"){kill(getpid(),SIGKILL);return 3;}
 if(mode=="exit")return 3;
 if(mode=="short"){write(1,"oops",4);return 0;}
 if(mode=="large"){std::string v(65545,'x');write(1,v.data(),v.size());return 0;}
 if(mode=="error"){std::string v="{\"code\":\"E_TEST\",\"message\":\"explicit\"}";put32(1);put32(v.size());write(1,v.data(),v.size());return 0;}
 if(mode=="length"){put32(0);put32(3);write(1,"abc",3);return 0;}
 put32(mode=="status"?2:0);put32(mode=="truncated"?100:4);uint8_t v[4]={1,2,3,4};write(1,v,4);
}
