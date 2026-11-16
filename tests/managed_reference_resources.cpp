#include "nex/managed_references.h"
#include "managed_reference_resource_host.h"
#include <filesystem>
using namespace nex;

int runManagedReferenceResourceImage(void *entry,bool request,const char *root,const char *catalogue,const char *report){
  return runManagedReferenceResources(entry,request,root,catalogue,report);
}
bool managedReferenceResourceCommand(int argc,char **argv,int &status){
  const auto mode=argc>1?std::string(argv[1]):std::string{};
  if(mode!="resources-reference"&&mode!="resources-signatures")return false;
  if((mode=="resources-reference"&&argc!=5)||(mode=="resources-signatures"&&argc!=3))
    throw std::runtime_error("expected resources-reference input root catalogue, or resources-signatures input");
  auto path=std::filesystem::absolute(argv[2]);auto p=parseManagedReferencesPrototype(readFile(path.string()),path.string());check(p);
  if(mode=="resources-signatures"){
    llvm::json::Object signatures;for(const auto &f:p.functions)if(f.foreign)signatures[f.name]=foreignSignature(p,f);
    std::cout<<json(std::move(signatures))<<'\n';status=0;return true;
  }
  const auto baseline=nexrt::liveObjects.load();const auto descriptors=managedResourceFiles();llvm::json::Object record;
  uint64_t remaining=0;
  {
    nexrt::TextFiles files(argv[3],true);nexrt::FileScope fileScope(files);
    auto libraries=std::string(argv[4])=="-"?nullptr:nexrt::loadForeignLibraries(argv[4]);
    std::unique_ptr<nexrt::ForeignScope> foreign;if(libraries)foreign=std::make_unique<nexrt::ForeignScope>(libraries);
    try{
      auto result=evaluateManagedReferencesPrototype(p);
      record=llvm::json::Object{{"kind","return"},{"value",std::move(result.evaluation.value)},{"output",result.evaluation.output},
        {"remaining_cells",int64_t(result.afterCollection.cells)},{"remaining_nodes",int64_t(result.afterCollection.nodes)}};
    }catch(const Error &error){record=llvm::json::Object{{"kind","trap"},{"code",error.code},{"message",error.message},{"output",error.output},{"line",int64_t(error.span.line)}};}
    if(libraries)remaining=libraries->resourceBytesUsed();
  }
  if(remaining||nexrt::liveObjects.load()!=baseline||managedResourceFiles()!=descriptors)
    throw std::runtime_error("reference cell/resource execution did not retire its values, files or external capacity");
  record["live_delta"]=0;record["file_delta"]=0;record["external_bytes"]=0;
  std::cout<<json(std::move(record))<<'\n';status=0;return true;
}
