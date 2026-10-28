#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <unistd.h>
#include <vector>
static void u32(uint32_t n){for(int i=0;i<4;++i)std::cout.put(char(uint8_t(n>>(8*i))));}
static uint32_t get(){uint8_t b[4];std::cin.read(reinterpret_cast<char*>(b),4);if(!std::cin)return 0xffffffff;return uint32_t(b[0])|(uint32_t(b[1])<<8)|(uint32_t(b[2])<<16)|(uint32_t(b[3])<<24);}
int main(){
 {std::ofstream f(std::getenv("NEX_TEST_PID"));f<<getpid();}
 std::string mode=std::getenv("NEX_TEST_MODE");if(get()!=1||get()!=0||get()!=1||get()!=24)return 7;char data[24];std::cin.read(data,24);if(!std::cin||std::cin.peek()!=std::char_traits<char>::eof())return 7;
 if(mode=="exit")return 7;if(mode=="killed"){raise(SIGKILL);return 7;}if(mode=="cancel"){for(;;)pause();}
 if(mode=="short"){u32(0);return 0;}
 if(mode=="large"){std::cout<<std::string(1048600,'x');return 0;}
 if(mode=="error"||mode=="malformed-error"||mode=="extra-error"||mode=="large-error"){
  std::string text=mode=="malformed-error"?"[broken":mode=="extra-error"?"{\"code\":\"E_TEST\",\"message\":\"controlled\",\"extra\":1}":mode=="large-error"?"{\"code\":\"E_TEST\",\"message\":\""+std::string(5000,'x')+"\"}":"{\"code\":\"E_TEST\",\"message\":\"controlled\"}";
  u32(1);u32(text.size());std::cout<<text;return 0;
 }
 uint32_t size=mode=="length"?25:24;u32(mode=="status"?2:0);u32(12+size+(mode=="trailing"?1:0));u32(mode=="version"?2:1);u32(mode=="count"?2:1);u32(size);
 std::vector<char> result(size);if(mode=="nonfinite"){result[2]=char(128);result[3]=char(127);}std::cout.write(result.data(),result.size());if(mode=="trailing")std::cout.put('x');return 0;
}
