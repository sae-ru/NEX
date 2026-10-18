#include "nex_foreign.h"
#include "nex_foreign_abi.h"
#include "nex_host.h"
#include "nex_json.h"
#include <fstream>
#include <iostream>
int main(int argc,char **argv){try{
  if(argc!=3)throw std::runtime_error("usage: scoped_host HOST.json BINDING.json");
  std::ifstream in(argv[2],std::ios::binary);if(!in)throw std::runtime_error("cannot open binding");
  std::string text;char chunk[65536];while(in){in.read(chunk,sizeof(chunk));auto n=size_t(in.gcount());if(n>1048576-text.size())throw std::runtime_error("binding exceeds limit");text.append(chunk,n);}if(!in.eof())throw std::runtime_error("cannot read binding");
  nexrt::ForeignScope foreign(nexrt::loadForeignLibraries(argv[1]));
  nexrt::RequestScope request;
  auto arguments=std::make_shared<nexrt::Data>(nexrt::Data::List);std::vector<uint8_t> bytes{0,255,128,1};
  arguments->values.emplace_back(nexrt::bytes(nexrt::ByteBuffer::copy(bytes)));
  auto input=nexrt::makeHandle(nexrt::Value(arguments));
  auto output=nex_foreign_invoke(text.data(),int64_t(text.size()),input,42);
  std::cout<<nexrt::encodeJSON(nexrt::readHandle(output).object->values.at(0))<<'\n';
  nex_release(output);nex_release(input);return 0;
}catch(const nexrt::Trap &e){std::cerr<<e.code<<": "<<e.what()<<" at source line "<<e.line<<'\n';return 1;}
catch(const nexrt::DataError &e){std::cerr<<e.code<<": "<<e.what()<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
