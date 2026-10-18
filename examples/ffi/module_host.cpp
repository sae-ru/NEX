#include "nex_ffi_loader.h"
#include "nex_json.h"
#include <fstream>
#include <iostream>
int main(int argc,char **argv){try{
  if(argc!=4)throw std::runtime_error("usage: module_host BUNDLE MANIFEST_SHA256 SIGNATURE.json");
  std::ifstream in(argv[3],std::ios::binary);if(!in)throw std::runtime_error("cannot open signature");
  std::string text;char chunk[65536];while(in){in.read(chunk,sizeof(chunk));auto n=size_t(in.gcount());if(n>1048576-text.size())throw std::runtime_error("signature exceeds limit");text.append(chunk,n);}if(!in.eof())throw std::runtime_error("cannot read signature");
  nexrt::ForeignSignature signature(text);
  nexrt::ForeignLibraries libraries({{"example",{argv[1],argv[2],{"contract"}}}});
  auto function=libraries.bind("example","contract",signature,argv[2]);std::vector<uint8_t> data{0,255,128,1};
  std::vector<nexrt::Value> args{nexrt::Value(nexrt::bytes(nexrt::ByteBuffer::copy(data)))};
  std::cout<<nexrt::encodeJSON(function.invoke(args))<<'\n';return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
