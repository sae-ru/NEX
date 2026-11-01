// Native Windows equivalent of the executable Python forwarding fixture.
// It records response-file paths, then runs the real selected Clang unchanged.
#include "host_test.h"
#include "third_party/json.hpp"
#include <filesystem>
#include <fstream>
int wmain(int argc,wchar_t **argv){
  const auto log=::_wgetenv(L"NEX_TEST_FORWARDER_LOG"),target=::_wgetenv(L"NEX_TEST_FORWARDER_TARGET");
  if(!log||!target)return 125;
  nlohmann::json paths=nlohmann::json::array();
  std::vector<std::string> arguments;
  for(int i=1;i<argc;++i){arguments.push_back(nexrt::platform::utf8(argv[i]));if(argv[i][0]==L'@')paths.push_back(nexrt::platform::utf8(argv[i]+1));}
  {std::ofstream file(std::filesystem::path(log),std::ios::binary);file<<paths.dump();if(!file)return 126;}
  return int(nex_test::run(std::filesystem::path(target),arguments,true));
}
