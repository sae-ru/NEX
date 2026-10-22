#pragma once
#include "nex_value.h"
namespace nex {struct TaskReferenceAccess;}
namespace nexrt {
// The private constructor and immutable owner family prevent base slicing and
// native/reference reinterpretation. A snapshot never keeps a scheduler alive.
struct ReferenceTaskData final:Data {
private:
  friend struct nex::TaskReferenceAccess;
  const std::weak_ptr<const void> owner;
  const size_t scope,index;
  ReferenceTaskData(Kind kind,const std::shared_ptr<const void> &owner,size_t scope,size_t index)
    :Data(kind,sizeof(ReferenceTaskData),TaskOwnerFamily::Reference),owner(owner),scope(scope),index(index){}
};
}
