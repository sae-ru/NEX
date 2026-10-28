// Controlled protocol peer, never an accelerator substitute.
#include <unistd.h>
#include <signal.h>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <fstream>
#include <iostream>
static uint32_t get32(){uint8_t b[4];std::cin.read(reinterpret_cast<char*>(b),4);if(!std::cin)return 0;return uint32_t(b[0])|(uint32_t(b[1])<<8)|(uint32_t(b[2])<<16)|(uint32_t(b[3])<<24);}
static void put32(uint32_t n){uint8_t b[4];for(int i=0;i<4;++i)b[i]=uint8_t(n>>(8*i));write(1,b,4);}
int main(){
 if(get32()!=1||get32()!=4||get32()!=255)return 5;
 uint8_t data[8];std::cin.read(reinterpret_cast<char*>(data),8);if(!std::cin||std::cin.peek()!=std::char_traits<char>::eof())return 5;
 for(int i=0;i<8;++i)if(data[i]!=i+1)return 5;
 if(auto path=std::getenv("NEX_TEST_PID")){std::ofstream o(path);o<<getpid();}
 std::string mode=std::getenv("NEX_TEST_MODE");
 if(mode=="cancel"){sleep(60);return 3;}if(mode=="killed"){kill(getpid(),SIGKILL);return 3;}if(mode=="exit")return 3;
 if(mode=="short"){write(1,"oops",4);return 0;}
 if(mode=="large"){std::string value(262153,'x');write(1,value.data(),value.size());return 0;}
 if(mode=="error"){std::string value="{\"code\":\"E_TEST\",\"message\":\"explicit\"}";put32(1);put32(value.size());write(1,value.data(),value.size());return 0;}
 if(mode=="length"){put32(0);put32(3);write(1,"abc",3);return 0;}
 put32(mode=="status"?2:0);put32(mode=="truncated"?100:4);uint8_t result[4]={1,2,3,4};write(1,result,4);
}
