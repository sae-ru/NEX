#include "nex/profiling.h"
#include "nex/task_limits.h"
#include "nex/operations.h"
#include <filesystem>
#include <iostream>
#include <set>

// Private data-only entry to the actual production reader/validator. It never
// builds or runs a program and does not add a public report-reading CLI option.
int main(int argc,char **argv){
  using namespace nex;
  try{
    if(argc!=2||std::filesystem::file_size(argv[1])>128u*1024*1024)
      throw Error("E_PROFILE","expected one bounded request file");
    auto request=llvm::json::parse(readFile(argv[1]));
    auto object=request?request->getAsObject():nullptr;
    if(!object||(object->size()!=4&&object->size()!=5)||
       (object->size()==5&&!object->getObject("image_catalog"))||!object->get("raw")||!object->getObject("expected")||
       !object->get("catalog")||!object->get("effective"))
      throw Error("E_PROFILE","invalid private profile request shape");
    const auto &raw=*object->get("raw");
    auto text=raw.getAsString()?raw.getAsString()->str():json(raw,false);
    auto report=parseTaskProfileRuntimeReport(text);
    if(!report.getAsObject())throw Error("E_PROFILE","profile runtime report must be an object");
    auto catalog=parseNativeTaskProfileCatalog(*object->get("catalog"));
    auto effective=parseTaskLimitsJSON(*object->get("effective"),"E_PROFILE");
    validateTaskProfileRuntimeReport(*report.getAsObject(),*object->getObject("expected"),effective,&catalog);
    if(auto image=object->getObject("image_catalog")){
      auto definitions=image->getObject("definitions");
      if((image->size()!=3&&image->size()!=4)||(image->size()==4&&!image->getBoolean("rebind_profile"))||
         !image->get("provider")||!image->get("catalog")||!definitions||
         definitions->empty()||definitions->size()>128)
        throw Error("E_PROFILE","invalid private image catalog request");
      std::map<std::string,std::set<std::string>> expected;size_t total=0;
      for(const auto &[component,value]:*definitions){
        auto names=value.getAsArray();if(!names||names->empty()||names->size()>16384-total)
          throw Error("E_PROFILE","invalid private image definition limit");
        total+=names->size();auto &selected=expected[component.str()];
        for(const auto &name:*names){auto text=name.getAsString();
          if(!text||text->empty()||text->size()>4096||!selected.insert(text->str()).second)
            throw Error("E_PROFILE","invalid private image definition");
        }
      }
      auto provider=parseNativeTaskProvider(*image->get("provider"));
      auto local=parseNativeTaskProfileCatalog(*image->get("catalog"));
      // Construct internally consistent test-only metadata so a corrupted
      // owner/definition ledger cannot reject solely on the old hash check.
      if(image->getBoolean("rebind_profile").value_or(false))provider.profiling=nativeTaskProfileInfo(local);
      validateTaskProfileCatalogOwnership(provider,local,expected);
    }
    std::cout<<"{\"ok\":true}\n";return 0;
  }catch(const Error &error){
    std::cout<<json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",std::string(error.what())}})<<'\n';
    return 1;
  }catch(const std::exception &error){
    std::cout<<json(llvm::json::Object{{"ok",false},{"code","E_PROFILE"},{"message",std::string(error.what())}})<<'\n';
    return 1;
  }
}
