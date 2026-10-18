#include "nex_bytes.h"
#include <functional>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>

using nexrt::ByteBuffer;
void require(bool condition){if(!condition)throw std::runtime_error("byte runtime assertion failed");}
void error(const std::string &code,const std::function<void()> &action){
  try{action();}catch(const nexrt::DataError &e){require(e.code==code);return;}
  throw std::runtime_error("expected byte error "+code);
}
std::string hex(const ByteBuffer &bytes){
  static constexpr char digits[]="0123456789abcdef";std::string result;
  for(auto byte:bytes.view()){result+=digits[byte>>4];result+=digits[byte&15];}return result;
}
ByteBuffer unhex(const std::string &text){
  require(text.size()%2==0);std::vector<uint8_t> bytes;
  auto nibble=[](char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;};
  for(size_t i=0;i<text.size();i+=2){auto a=nibble(text[i]),b=nibble(text[i+1]);require(a>=0&&b>=0);bytes.push_back(uint8_t(a*16+b));}
  return ByteBuffer::copy(bytes);
}
void selfTest(){
  unsigned cases=0;
  {
    ByteBuffer empty;require(empty.length()==0&&empty.toVector().empty()&&empty.base64().empty());
    error("E_BOUNDS",[&]{empty.at(0);});error("E_BOUNDS",[&]{empty.set(0,1);});
    require(empty.slice(0,0)==empty);++cases;
  }
  {
    std::vector<uint8_t> raw{0,255,128,65};auto a=ByteBuffer::copy(raw);raw[0]=7;
    auto exported=a.toVector();exported[1]=1;require(hex(a)=="00ff8041");++cases;
  }
  {
    auto source=unhex("00010203");auto alias=source;auto changed=source.set(1,255);
    require(hex(source)=="00010203"&&alias==source&&hex(changed)=="00ff0203");
    require(hex(source.append(128))=="0001020380"&&source.length()==4);++cases;
  }
  {
    ByteBuffer slice;
    {auto original=unhex("0001020304");slice=original.slice(1,4).slice(1,2);}
    require(hex(slice)=="0203"&&slice.at(0)==2&&slice.at(1)==3);
    require(hex(slice.concat(slice))=="02030203"&&ByteBuffer().concat(slice)==slice);++cases;
  }
  {
    auto value=unhex("00ff");auto moved=std::move(value);require(value.length()==0&&value.toVector().empty()&&value.base64().empty());
    error("E_BOUNDS",[&]{value.at(0);});require(hex(moved)=="00ff");
    value=std::move(moved);require(moved.length()==0&&value.length()==2);++cases;
  }
  {
    const std::vector<int64_t> input{0,127,128,255};require(hex(ByteBuffer::fromIntegers(input))=="007f80ff");
    error("E_RANGE",[]{const std::vector<int64_t> v{-1};ByteBuffer::fromIntegers(v);});
    error("E_RANGE",[]{const std::vector<int64_t> v{256};ByteBuffer::fromIntegers(v);});
    auto value=unhex("01");error("E_RANGE",[&]{value.append(-1);});error("E_RANGE",[&]{value.set(0,256);});++cases;
  }
  {
    auto value=unhex("00ff");auto max=std::numeric_limits<int64_t>::max();
    for(auto index:{int64_t(-1),int64_t(2),max})error("E_BOUNDS",[&]{value.at(index);});
    for(auto pair:std::vector<std::pair<int64_t,int64_t>>{{-1,0},{0,-1},{3,0},{1,2},{max,1},{1,max}})
      error("E_BOUNDS",[&]{value.slice(pair.first,pair.second);});
    require(value.slice(2,0).length()==0&&hex(value)=="00ff");++cases;
  }
  {
    for(auto text:{"Zg","Zg=","Zg===","====","A===","Zm=8","Zg==\n","Zg== ","AA-_","Zh==","Zm9=","Zg==AAAA"})
      error("E_BASE64",[&]{ByteBuffer::fromBase64(text);});
    require(hex(ByteBuffer::fromBase64("Zg=="))=="66"&&hex(ByteBuffer::fromBase64("Zm8="))=="666f");++cases;
  }
  std::cout<<cases<<" immutable byte runtime cases passed\n";
}
int main(int argc,char **argv){
  try{
    if(argc==1){selfTest();return 0;}
    require(argc==2&&std::string(argv[1])=="--stream");
    for(std::string line;std::getline(std::cin,line);){
      require(line.size()>=2&&line[1]==' ');
      try{
        if(line[0]=='E')std::cout<<unhex(line.substr(2)).base64()<<'\n';
        else if(line[0]=='D')std::cout<<hex(ByteBuffer::fromBase64(line.substr(2)))<<'\n';
        else throw std::runtime_error("unknown byte request");
      }catch(const nexrt::DataError &e){std::cout<<"ERR:"<<e.code<<'\n';}
    }
    return 0;
  }catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
