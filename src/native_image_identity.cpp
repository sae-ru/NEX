#include "nex/native_images.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Object/BuildID.h"
#include "llvm/Object/COFF.h"
#include "llvm/Object/CVDebugRecord.h"
#include "llvm/Object/MachO.h"
#include "llvm/Object/ObjectFile.h"
#include "llvm/Support/Error.h"
#include <algorithm>
#include <array>

namespace nex {
std::string nativeImageUUID(const std::string &path){
  auto input=llvm::object::ObjectFile::createObjectFile(path);
  if(!input)throw Error("E_PROJECT_IMAGE","cannot inspect linked image: "+llvm::toString(input.takeError()));
  auto *object=input->getBinary();
  if(auto *coff=llvm::dyn_cast<llvm::object::COFFObjectFile>(object)){
    const llvm::codeview::DebugInfo *info=nullptr;llvm::StringRef pdb;
    if(auto error=coff->getDebugPDBInfo(info,pdb))
      throw Error("E_PROJECT_IMAGE","cannot inspect PE CodeView identity: "+llvm::toString(std::move(error)));
    if(!info||info->Signature.CVSignature!=llvm::OMF::Signature::PDB70)
      throw Error("E_PROJECT_IMAGE","linked PE image has no CodeView GUID: "+path);
    auto id=llvm::ArrayRef<uint8_t>(info->PDB70.Signature);
    if(std::all_of(id.begin(),id.end(),[](auto byte){return byte==0;}))throw Error("E_PROJECT_IMAGE","linked PE image has an empty CodeView GUID: "+path);
    // LLDB's PE UUID is the canonical GUID fields followed by the PDB age.
    // The first three GUID fields and Age are little-endian in CodeView.
    std::array<uint8_t,20> identity{};
    constexpr std::array<unsigned,16> order{3,2,1,0,5,4,7,6,8,9,10,11,12,13,14,15};
    for(size_t i=0;i<order.size();++i)identity[i]=id[order[i]];
    const auto age=uint32_t(info->PDB70.Age);
    for(unsigned i=0;i<4;++i)identity[16+i]=uint8_t(age>>(24-8*i));
    return llvm::toHex(identity,true);
  }
  auto id=llvm::isa<llvm::object::MachOObjectFile>(object)?llvm::cast<llvm::object::MachOObjectFile>(object)->getUuid():llvm::object::getBuildID(object);
  if(id.empty())throw Error("E_PROJECT_IMAGE","linked image has no UUID/build ID: "+path);
  return llvm::toHex(id,true);
}
}
