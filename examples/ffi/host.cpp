#include "nex_ffi_host.h"
#include "nex_json.h"
#include <fstream>
#include <iostream>
extern "C" nex_ffi_status nex_example_c_nominal(const nex_ffi_api_v1*,nex_ffi_call,
    const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);
int main(int argc,char **argv){try{
  if(argc!=2)throw std::runtime_error("usage: host signature.json");
  std::ifstream in(argv[1],std::ios::binary);if(!in)throw std::runtime_error("cannot open signature");
  std::string text;char chunk[65536];
  while(in){in.read(chunk,sizeof(chunk));auto count=size_t(in.gcount());
    if(count>1048576-text.size())throw std::runtime_error("signature exceeds byte limit");text.append(chunk,count);
  }
  if(!in.eof())throw std::runtime_error("cannot read signature");
  nexrt::ForeignSignature signature(text);std::vector<uint8_t> data{0,255,128,1};
  std::vector<nexrt::Value> args{nexrt::Value(nexrt::bytes(nexrt::ByteBuffer::copy(data)))};
  std::cout<<nexrt::encodeJSON(nexrt::invokeForeignTyped(nex_example_c_nominal,args,signature))<<'\n';return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
