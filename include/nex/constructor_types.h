#pragma once
#include "nex/language.h"

namespace nex {
// Compile-time constructor terms. None of these are runtime values. Source
// binding supplies canonical nominal names and declared arities to this layer.
struct KindContext {
  std::map<std::string,unsigned> parameters;
  std::map<std::string,unsigned> constructors{{"list",1},{"result",1}};
  std::map<std::string,std::vector<unsigned>> constructorParameters;
};
using TypeSubstitution = std::map<std::string,Type>;

// A kind is the number of value-type arguments required to produce a value
// type. Constructor parameters are fully applied; no type lambdas are inferred.
unsigned typeKind(const Type &,const KindContext &,Span={});
Type applyTypeConstructor(const Type &,std::vector<Type>,const KindContext &,Span={});
Type substituteConstructorTypes(const Type &,const TypeSubstitution &,const KindContext &,Span={});

// The right side must be concrete. A failed structural match returns nullopt;
// malformed/kind-invalid terms and resource exhaustion remain diagnostics.
std::optional<TypeSubstitution> matchImplementationType(
  const Type &pattern,const Type &concrete,const KindContext &,Span={});
std::optional<TypeSubstitution> matchRigidImplementationType(
  const Type &pattern,const Type &actual,const KindContext &,
  const std::set<std::string> &variables,Span={});

// Both sides have independent binders. Bounds cannot make overlapping heads
// coherent, so this check operates only on kinds and head structure.
bool implementationTypesOverlap(const Type &,const KindContext &,
                                const Type &,const KindContext &,Span={});
}
