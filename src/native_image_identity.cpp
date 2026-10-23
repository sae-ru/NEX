#include "nex/native_images.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Object/BuildID.h"
#include "llvm/Object/MachO.h"
#include "llvm/Object/ObjectFile.h"
#include "llvm/Support/Error.h"

namespace nex {
std::string nativeImageUUID(const std::string &path){
  auto input=llvm::object::ObjectFile::createObjectFile(path);
  if(!input)throw Error("E_PROJECT_IMAGE","cannot inspect linked image: "+llvm::toString(input.takeError()));
  auto *object=input->getBinary();
  auto id=llvm::isa<llvm::object::MachOObjectFile>(object)?llvm::cast<llvm::object::MachOObjectFile>(object)->getUuid():llvm::object::getBuildID(object);
  if(id.empty())throw Error("E_PROJECT_IMAGE","linked image has no UUID/build ID: "+path);
  return llvm::toHex(id,true);
}
}
